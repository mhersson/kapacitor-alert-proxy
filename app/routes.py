#!/usr/bin/env python
# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: routes.py

Created: 23.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''
import time
import calendar
import operator
from datetime import timedelta
from flask import Response, request, render_template, redirect, jsonify
from app import app, LOGGER, TZNAME
from app.forms.maintenance import ActivateForm, DeactivateForm, DeleteSchedule
from app.forms.maintenance import QuickActivate
from app.alertcontroller import AlertController
from app.dbcontroller import DBController


alertcontroller = AlertController()
db = DBController()


@app.route("/kap/alert", methods=['post'])
def alert():
    LOGGER.info("Received new data")
    al = alertcontroller.create_alert(request.json)
    if al is not None:
        al = db.get_tickets_and_keys(al)
        if not al.grafana_url:
            al.grafana_url = alertcontroller.add_grafana_url(al)
        LOGGER.info("Alert info:\n%s\n%s -> %s, Duration: %d\n"
                    "State duration: %s, Sent: %s\nJIRA: %s, PD: %s",
                    al.id, al.previouslevel, al.level, al.duration,
                    al.state_duration, al.sent,
                    al.jira_issue, al.pd_incident_key)
        if al.sent:
            if al.level != al.previouslevel:
                LOGGER.info("State has changed, notify targets")
                alertcontroller.dispatch_and_update_status(al)
            else:
                LOGGER.info("No change, updating existing alert")
                alertcontroller.dispatch_and_update_status(al, dispatch=False)
            return Response(response={'Success': True},
                            status=200, mimetype='application/json')
        else:
            if app.config['FLAPPING_DETECTION_ENABLED'] and db.is_flapping(al):
                LOGGER.info("Alert is flapping")
                al.message = "Flapping! " + al.message
                alertcontroller.dispatch_and_update_status(al, dispatch=False)
                return Response(response={'Success': True},
                                status=200, mimetype='application/json')
            if al.state_duration:
                LOGGER.info("Alert delayed by state duration, no dispatch")
                alertcontroller.dispatch_and_update_status(al, dispatch=False)
            elif al.duration < app.config['ALERTING_DELAY']:
                LOGGER.info("Alert delayed, no dispatch")
                alertcontroller.dispatch_and_update_status(al, dispatch=False)
            elif al.level == 'OK':
                LOGGER.info("Alert OK without being sent, no dispatch")
                alertcontroller.dispatch_and_update_status(al, dispatch=False)
            else:
                LOGGER.info("New alert, notify targets")
                alertcontroller.dispatch_and_update_status(al)
    return Response(response={'Success': True},
                    status=200, mimetype='application/json')


@app.route("/kap/maintenance", methods=['GET', 'POST'])
def maintenance():
    af = ActivateForm()
    df = DeactivateForm()
    dsf = DeleteSchedule()
    if af.validate_on_submit():
        if af.days.data and af.starttime.data != "":
            db.add_maintenance_schedule(
                af.starttime.data, af.duration.data, af.key.data, af.val.data,
                af.comment.data, bool(af.repeat.data), af.days.data)
        else:
            db.activate_maintenance(af.key.data, af.val.data,
                                    af.duration.data, af.comment.data)
        return redirect('/kap/maintenance')
    if df.validate_on_submit():
        db.deactive_maintenance(df.start.data, df.stop.data,
                                df.key.data, df.value.data)
        return redirect('/kap/maintenance')
    if dsf.validate_on_submit():
        db.delete_maintenance_schedule(int(dsf.schedule_id.data))
        return redirect('/kap/maintenance')
    mrules = db.get_active_maintenance_rules()
    schedule = db.get_maintenance_schedule()
    return render_template('maintenance.html', title="Maintenance",
                           mrules=mrules, schedule=schedule,
                           af=af, df=df, dsf=dsf, tzname=TZNAME)


@app.route("/kap/status", methods=['GET', 'POST'])
def status():
    quickmaintenance = QuickActivate()
    if quickmaintenance.validate_on_submit():
        db.activate_maintenance("id", quickmaintenance.alert_id.data,
                                "8h", "Muted from status page")
        return redirect('/kap/status')
    mrules = db.get_active_maintenance_rules()
    aim = []
    active_alerts = db.get_active_alerts()
    for a in active_alerts:
        if alertcontroller.affected_by_mrules(mrules=mrules, al=a):
            aim.append(a)
    return render_template('status.html', title="Active alerts",
                           alerts=active_alerts, maintenance=aim,
                           tzname=TZNAME, qm=quickmaintenance)


@app.route("/kap/statistics", methods=['GET'])
def statistics():
    stats = db.get_statistics(24)
    stats.sort(key=operator.itemgetter(1, 2, 4))
    return render_template('statistics.html', title="Last 24 hours",
                           stats=stats)


@app.route("/kap/log", methods=['GET'])
def log():
    records = db.get_log_records(12)
    return render_template('log.html', title="Last 12 hours",
                           records=records, tzname=TZNAME)


@app.route("/kap/ticks", methods=['GET'])
def ticks():
    defined_ticks = alertcontroller.get_defined_tick_scripts()
    return render_template('ticks.html', title="Defined tick scripts",
                           ticks=defined_ticks)


@app.route("/kap/tick-content", methods=['GET'])
def tick_content():
    tick = request.args.get('tick')
    content = alertcontroller.get_tick_script_content(tick)
    if not content:
        content = "Failed to read tick script"
    return jsonify(data=content)


@app.template_filter('ctime')
def timectime(s, use_tz=False):
    if use_tz:
        tzdiff = calendar.timegm(
            time.localtime()) - calendar.timegm(time.gmtime())
        return time.ctime(s + tzdiff)
    return time.ctime(s)


@app.template_filter('timedelta')
def format_secs(s):
    return str(timedelta(seconds=s)).split(".")[0]


@app.template_filter('truncate')
def truncate_string(s):
    if len(s) > 200:
        return s[:197] + "..."
    return s


@app.template_filter('fontawesome')
def fontawesome(level, text_and_icon=False):
    fa_html = '<span class="fas {icon}"></span>'
    if level == 'CRITICAL':
        fa_icon = "fa-skull-crossbones"
    elif level == "WARNING":
        fa_icon = "fa-exclamation-triangle"
    elif level == "INFO":
        fa_icon = "fa-info"
    else:
        fa_icon = "fa-check-circle"
    if text_and_icon:
        return level.title().ljust(
            len(level)+2, '\xa0') + fa_html.format(icon=fa_icon)
    return fa_html.format(icon=fa_icon)
