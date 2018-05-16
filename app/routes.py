#!/usr/bin/env python
# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: routes.py

Created: 23.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''
import os
import re
import json
import time
import hashlib
from datetime import datetime, timedelta
from flask import Response, request, render_template, redirect

from app import app, LOGGER, INSTALLDIR
from app.alert import Alert
from app.targets.slack import Slack
from app.targets.pagerduty import Pagerduty
from app.targets.jira import Incident
from app.forms.maintenance import ActivateForm, DeactivateForm

STARTUP_TIME = time.time()

ACTIVE_ALERTS = {}
STATISTICS = {}

slack = Slack(
    url=app.config['SLACK_URL'],
    channel=app.config['SLACK_CHANNEL'],
    username=app.config['SLACK_USERNAME'],
    state_change_only=app.config['SLACK_STATE_CHANGE_ONLY'])

pagerduty = Pagerduty(
    url=app.config['PAGERDUTY_URL'],
    service_key=app.config['PAGERDUTY_SERVICE_KEY'],
    state_change_only=app.config['PAGERDUTY_STATE_CHANGE_ONLY'])

jira = Incident(
    server=app.config['JIRA_SERVER'],
    username=app.config['JIRA_USERNAME'],
    password=app.config['JIRA_PASSWORD'],
    project_key=app.config['JIRA_PROJECT_KEY'],
    assignee=app.config['JIRA_ASSIGNEE'])


@app.route("/kap/alert", methods=['post'])
def alert():
    LOGGER.debug("Received new data")
    al = create_alert(request.json)
    al.pd_incident_key = get_pagerduty_incident_key(al)
    al.jira_issue = get_jira_issue(al)
    mrules = load_mrules()
    if app.config['SLACK_ENABLED'] and (
            not affected_by_mrules(mrules, al) or
            app.config['SLACK_IGNORE_MAINTENANCE']):
        slack.post(al)
    if app.config['PAGERDUTY_ENABLED'] and (
            not affected_by_mrules(mrules, al) or
            app.config['PAGERDUTY_IGNORE_MAINTENANCE']):
        al.pd_incident_key = pagerduty.post(al)
        LOGGER.debug("Pagerduty incident key: %s", al.pd_incident_key)
    if app.config['JIRA_ENABLED'] and not affected_by_mrules(mrules, al):
        al.jira_issue = jira.post(al)
        LOGGER.debug("JIRA issue: %s", al.jira_issue)
    modify_active(al)
    return Response(response={'Success': True},
                    status=200, mimetype='application/json')


@app.route("/kap/maintenance", methods=['GET', 'POST'])
def maintenance():
    af = ActivateForm()
    df = DeactivateForm()
    if af.validate_on_submit():
        activate_maintenance(af.key.data, af.val.data, af.duration.data)
        return redirect('/kap/maintenance')
    if df.validate_on_submit():
        deactive_maintenance(df.start.data, df.stop.data)
        return redirect('/kap/maintenance')
    mrules = load_mrules()
    return render_template('maintenance.html', title="Maintenance",
                           mrules=mrules, af=af, df=df)


@app.route("/kap/status", methods=['GET'])
def status():
    mrules = load_mrules()
    aim = []
    for a in ACTIVE_ALERTS:
        if affected_by_mrules(mrules=mrules, al=ACTIVE_ALERTS[a]):
            aim.append(ACTIVE_ALERTS[a])
    return render_template('status.html', title="Active alerts",
                           group_tag=app.config['MAIN_GROUP_TAG'],
                           alerts=ACTIVE_ALERTS, maintenance=aim)


@app.route("/kap/statistics", methods=['GET'])
def statistics():
    return render_template('statistics.html', title="Statistics",
                           stats=STATISTICS, startup_time=STARTUP_TIME)


@app.template_filter('ctime')
def timectime(s):
    return time.ctime(s)


@app.template_filter('timedelta')
def format_secs(s):
    return timedelta(seconds=s)


def create_alert(content):
    LOGGER.debug("Creating alert")
    tags = []
    for s in content['data']['series']:
        tags.extend([{'key': k, 'value': v} for k, v in s['tags'].items()])

    al = Alert(
        alertid=content['id'],
        duration=content['duration'] // (10 ** 9),
        message=content['message'],
        level=content['level'],
        previouslevel=content['previousLevel'],
        alerttime=datestr_to_datetime(datestr=content['time']),
        tags=tags)
    LOGGER.debug(al)
    return al


def datestr_to_datetime(datestr):
    m = re.match(
        "20[0-9]{2}-[0-2][0-9]-[0-3][0-9]T[0-2][0-9](:[0-5][0-9]){2}", datestr)
    if m:
        return datetime.strptime(m.group(0), '%Y-%m-%dT%H:%M:%S')
    return None


def get_hash(al):
    alhash = hashlib.sha256(al.id.encode() + str(al.tags).encode()).hexdigest()
    LOGGER.debug('Alert hash: %s', alhash)
    return alhash


def modify_active(al):
    alhash = get_hash(al)
    if al.level != 'OK' and alhash in ACTIVE_ALERTS:
        LOGGER.debug("Updating active alert")
        ACTIVE_ALERTS[alhash] = al
    elif al.level != 'OK' and alhash not in ACTIVE_ALERTS:
        LOGGER.debug("Setting new active alert")
        ACTIVE_ALERTS[alhash] = al
    elif al.level == 'OK' and alhash in ACTIVE_ALERTS:
        del ACTIVE_ALERTS[alhash]
        add_statistics(alhash, al)


def add_statistics(alhash, al):
    if alhash in STATISTICS:
        stats = STATISTICS[alhash]
        stats["count"] += 1
        stats["duration"] = stats["duration"] + ((
            al.duration - stats["duration"]) / stats["count"])
        STATISTICS[alhash] = stats
    else:
        STATISTICS[alhash] = {"id": al.id, "count": 1, "duration": al.duration}


def get_pagerduty_incident_key(al):
    alhash = get_hash(al)
    if alhash in ACTIVE_ALERTS:
        existing = ACTIVE_ALERTS[alhash]
        if existing.pd_incident_key:
            LOGGER.info("Found existing incident key")
            return existing.pd_incident_key
    return None


def get_jira_issue(al):
    alhash = get_hash(al)
    if alhash in ACTIVE_ALERTS:
        existing = ACTIVE_ALERTS[alhash]
        if existing.jira_issue:
            LOGGER.info("Found existing jira issue")
            return existing.jira_issue
    return None


def activate_maintenance(key, val, duration):
    LOGGER.debug('Setting maintenance')
    duration_secs = {'m': 60, 'h': 3600, 'd': 86400}
    start = int(time.time())
    stop = int(start + (int(duration[:-1]) * duration_secs[duration[-1]]))
    rule = {"key": key, "value": val, "start": start, "stop": stop}
    filename = "maintenance_{}-{}.json".format(start, stop)
    try:
        with open(os.path.join(INSTALLDIR, "maintenance", filename), 'w') as f:
            f.write(json.dumps(rule))
    except OSError:
        LOGGER.error("Failed to activate maintenance")


def deactive_maintenance(start, stop):
    LOGGER.debug("Deactive maintenance")
    filename = "maintenance_{}-{}.json".format(start, stop)
    try:
        os.remove(os.path.join(INSTALLDIR, "maintenance", filename))
    except OSError:
        LOGGER.error("Failed to deactivate maintenance")


def load_mrules():
    LOGGER.debug("Loading maintenance")
    mrules = []
    mdir = os.path.join(INSTALLDIR, "maintenance")
    mfiles = os.listdir(mdir)
    for mf in mfiles:
        m = re.match("maintenance_([0-9]{10})-([0-9]{10}).json", mf)
        if m:
            if int(m.group(1)) <= int(time.time()) <= int(m.group(2)):
                with open(os.path.join(mdir, mf), 'r') as f:
                    mrules.append(json.loads(f.read()))
            else:
                LOGGER.info("Deleting expired rule")
                os.remove(os.path.join(mdir, mf))
    return mrules


def affected_by_mrules(mrules, al):
    LOGGER.debug("Checking maintenance")
    for mrule in mrules:
        mrv = mrule['value']
        v = [tag['value'] for tag in al.tags if tag['key'] == mrule['key']]
        if mrv in v:
            LOGGER.info("In maintenance")
            return True
        elif mrv[0] == '*' and v[0].endswith(mrv[1:]):
            LOGGER.info("In maintenance")
            LOGGER.debug("Affected by rule wildcard *endswith")
            return True
        elif mrv[-1] == '*' and v[0].startswith(mrv[:-1]):
            LOGGER.info("In maintenance")
            LOGGER.debug("Affected by rule wildcard startswith*")
            return True
        if mrule['key'] == 'id':
            if al.id.endswith(mrule['value']):
                return True
    return False
