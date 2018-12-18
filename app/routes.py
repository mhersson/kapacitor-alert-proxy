#!/usr/bin/env python
# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: routes.py

Created: 23.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''
import re
import time
import boto3
import requests
import calendar
import operator
import subprocess
from datetime import datetime, timedelta
from flask import Response, request, render_template, redirect
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError
from botocore.exceptions import NoCredentialsError, ProfileNotFound
from botocore.exceptions import NoRegionError, ClientError

from app import app, LOGGER, TZNAME
from app.alert import Alert
from app.targets.slack import Slack
from app.targets.pagerduty import Pagerduty
from app.targets.jira import Incident
from app.forms.maintenance import ActivateForm, DeactivateForm, DeleteSchedule
from app.dbcontroller import DBController

STARTUP_TIME = time.time()

INSTANCES = {}

db = DBController()
influxdb = InfluxDBClient(host=app.config['INFLUXDB_HOST'],
                          port=app.config['INFLUXDB_PORT'],
                          database='kap')

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
    if al is not None:
        al = db.get_tickets_and_keys(al)
        LOGGER.debug(al)
        if db.is_flapping(al):
            LOGGER.debug("Alert is flapping")
            al.message = "FLAPPING DETECTED! " + al.message
            dispatch_and_update_status(al, dispatch=False)
            return Response(response={'Success': True},
                            status=200, mimetype='application/json')
        if al.state_duration or al.duration < app.config['ALERTING_DELAY']:
            LOGGER.debug("Alert delayed, no dispatch")
            dispatch_and_update_status(al, dispatch=False)
        else:
            if db.is_active(al):
                # Check state duration of active alert (previous)
                sd = db.state_duration(al)
                if ((sd or al.duration < app.config['ALERTING_DELAY'])
                        and al.level == 'OK'):
                    LOGGER.debug("Alert delayed, status OK, no dispatch")
                    dispatch_and_update_status(al, dispatch=False)
                elif ((sd or al.duration > app.config['ALERTING_DELAY'])
                      and al.level != 'OK'):
                    LOGGER.debug("Alert delayed, status NOT OK, full dispatch")
                    al.previouslevel = "OK"  # Override to trigger state change
                    dispatch_and_update_status(al)
                else:
                    dispatch_and_update_status(al)
            else:
                dispatch_and_update_status(al)
    return Response(response={'Success': True},
                    status=200, mimetype='application/json')


@app.route("/kap/maintenance", methods=['GET', 'POST'])
def maintenance():
    af = ActivateForm()
    df = DeactivateForm()
    dsf = DeleteSchedule()
    if af.validate_on_submit():
        if af.days.data and af.starttime.data != "":
            db.add_maintenance_schedule(af.starttime.data, af.duration.data,
                                        af.key.data, af.val.data,
                                        bool(af.repeat.data), af.days.data)
        else:
            db.activate_maintenance(af.key.data, af.val.data, af.duration.data)
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


@app.route("/kap/status", methods=['GET'])
def status():
    mrules = db.get_active_maintenance_rules()
    aim = []
    active_alerts = db.get_active_alerts()
    if active_alerts:
        for a in active_alerts:
            if affected_by_mrules(mrules=mrules, al=a):
                aim.append(a)
    return render_template('status.html', title="Active alerts",
                           alerts=active_alerts, maintenance=aim,
                           tzname=TZNAME)


@app.route("/kap/statistics", methods=['GET'])
def statistics():
    stats = db.get_24hours_stats()
    stats.sort(key=operator.itemgetter(1, 2, 4))
    return render_template('statistics.html', title="Statistics",
                           stats=stats, startup_time=STARTUP_TIME)


@app.route("/kap/ticks", methods=['GET'])
def ticks():
    defined_ticks = get_defined_tick_scripts()
    return render_template('ticks.html', title="Defined tick scripts",
                           ticks=defined_ticks)


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


def create_alert(content):
    LOGGER.debug("Creating alert")
    tags = []
    for s in content['data']['series']:
        try:
            tags.extend([{'key': k, 'value': v} for k, v in s['tags'].items()])
        except KeyError:
            continue

    al = Alert(alertid=content['id'],
               duration=content['duration'] // (10 ** 9),
               message=content['message'], level=content['level'],
               previouslevel=content['previousLevel'],
               alerttime=datestr_to_timestamp(datestr=content['time']),
               tags=tags)

    if app.config['AWS_API_ENABLED']:
        suppress, modified_tags = check_instance_tags(tags)
        if suppress:
            return None
        if modified_tags:
            al.tags = modified_tags
    return al


def check_instance_tags(instance_tags):
    # Try to find out if alert is from a normal ec2 instance or autoscaling
    # instance, and then suppress alerts from terminated autoscaling instances
    # If instance is valid and running, check that the Environment tag exists,
    # if not try to add it from aws info (this would be the case for e.g ping
    # test ran outside of the instance environment)
    instance_info = update_aws_instance_info()
    try:
        LOGGER.debug("Checking incoming host tag")
        x = [tag['value'] for tag in instance_tags if tag['key'] == 'host']
        url = False  # Needed if host/url not in instance_info (f.ex ELB)
        if not x:
            # Telegraf input plugin ping uses tag url
            # and net_response uses server and not host
            # so try and use that if host does not exist
            x = [tag['value'] for tag in instance_tags
                 if tag['key'] in ['url', 'server']]
            if not x:
                raise KeyError
            # if the url or server is in fact url
            if x[0].startswith("http"):
                url = True  # Mark as url to raise KeyError if not found
                # First remove http or https prefix, then split on : or /
                # to get the hostname
                x[0] = re.split(":|/", re.sub(r"http[s]?://", "", x[0]))[0]
            LOGGER.debug("Using url as host tag")
            instance_tags.append({'key': 'host', 'value': x[0]})
        LOGGER.debug("Host tag, %s", x[0])
        if instance_info:
            if (x[0] in instance_info and
                    instance_info[x[0]]['state'] in [16, 64, 80]):
                LOGGER.debug("Instance Name exists and status code is "
                             "valid, %s - %d", x[0],
                             instance_info[x[0]]['state'])
                env = [tag['value'] for tag in instance_tags
                       if tag['key'] == 'Environment']
                if not env or env == ['']:
                    # Remove the old Environment tag if env == ['']
                    tags = [tag for tag in instance_tags
                            if tag['key'] != 'Environment']
                    LOGGER.debug("Adding missing Environment tag")
                    tags.append({'key': 'Environment',
                                 'value': instance_info[x[0]]['env']})
                    return False, tags
            elif x[0] not in instance_info and url:
                raise KeyError
            elif x[0] not in instance_info:
                LOGGER.error("Instance host tag not in instance list, "
                             "suppressing alert")
                return True, None
            else:
                LOGGER.debug("Instance status looks like autoscaling"
                             " instance, supressing alert")
                return True, None
    except KeyError:
        LOGGER.debug("Alert is not instance specific or host tag is missing")
    finally:
        # To limit the number of API queries, chech for stale alerts here
        remove_stale_alerts(instance_info)
    return False, None


def dispatch_and_update_status(al, dispatch=True):
    if dispatch:
        if not al.sent and al.level == 'OK':
            LOGGER.debug("Alert message not sent, suppressing OK")
        elif not al.sent or (al.sent and al.level == 'OK'):
            LOGGER.debug("Dispatch to all targets")
            al.sent = True
            mrules = db.get_active_maintenance_rules()
            in_maintenance = affected_by_mrules(mrules, al)
            run_slack(in_maintenance, al)
            al.pd_incident_key = run_pagerduty(in_maintenance, al)
            al.jira_issue = run_jira(in_maintenance, al)
    update_active_alerts(al)
    update_influxdb(al)


def run_slack(in_maintenance, al):
    if app.config['SLACK_ENABLED'] and (
            not in_maintenance or
            app.config['SLACK_IGNORE_MAINTENANCE']):
        if not contains_excluded_tags(
                app.config['SLACK_EXCLUDED_TAGS'], al.tags):
            slack.post(al)


def run_pagerduty(in_maintenance, al):
    if app.config['PAGERDUTY_ENABLED'] and (
            not in_maintenance or
            app.config['PAGERDUTY_IGNORE_MAINTENANCE']):
        if contains_excluded_tags(
                app.config['PAGERDUTY_EXCLUDED_TAGS'], al.tags):
            return al.pd_incident_key
        if excluded_tick(al, app.config['PAGERDUTY_EXCLUDED_TICKS']):
            return al.pd_incident_key
        al.pd_incident_key = pagerduty.post(al)
        LOGGER.debug("Pagerduty incident key: %s", al.pd_incident_key)
    return al.pd_incident_key


def run_jira(in_maintenance, al):
    if app.config['JIRA_ENABLED'] and not in_maintenance:
        if contains_excluded_tags(app.config['JIRA_EXCLUDED_TAGS'], al.tags):
            return al.jira_issue
        al.jira_issue = jira.post(al)
        LOGGER.debug("JIRA issue: %s", al.jira_issue)
    return al.jira_issue


def add_grafana_url(al):
    if app.config['GRAFANA_ENABLED']:
        LOGGER.debug("Adding Grafana url")
        # Show from 12 hours before alert until 12 hours after
        # Do 12 hours to compensate for time zone differences
        # Does not matter what time zone one is in, the time of
        # the event should be visible
        if al.duration > 86400:
            starttime = int(time.time() - al.duration - 43200) * 1000
            stoptime = int(time.time() - al.duration + 43200) * 1000
        else:
            starttime = int(time.time() - 86400) * 1000
            stoptime = int(time.time()) * 1000
        urlvars = []
        for var in app.config['GRAFANA_URL_VARS']:
            urlvars.extend(
                [tag['value'] for tag in al.tags if tag['key'] == var])
        if len(urlvars) != len(app.config['GRAFANA_URL_VARS']):
            LOGGER.error("Failed setting Grafana url, missing variables")
            return None
        url = app.config['GRAFANA_URL'].format(*urlvars, starttime, stoptime)
        return url
    return None


def state_duration(al):
    for key in app.config['STATE_DURATION']:
        if al.id.find(key) != -1:
            if al.duration < app.config['STATE_DURATION'][key]:
                return True
    return False


def update_active_alerts(al):
    alert_is_active = db.is_active(al)
    if al.level != 'OK' and alert_is_active:
        LOGGER.debug("Updating active alert")
        db.activate_alert(al)
    elif al.level != 'OK' and not alert_is_active:
        LOGGER.debug("Setting new active alert")
        db.activate_alert(al)
    elif al.level == 'OK' and alert_is_active:
        db.deactivate_alert(al)
        db.log_alert(al)


def update_influxdb(al):
    if app.config['INFLUXDB_ENABLED'] is True:
        if al.level != al.previouslevel:
            LOGGER.debug("Updating InfluxDB")
            update_db(influxify(al, al.alhash, "logs"))
            if al.level == 'OK':
                delete_active(al)
            else:
                update_db(influxify(al, al.alhash, "active", True))
        else:
            update_db(influxify(al, al.alhash, "active", True))


def update_db(data):
    LOGGER.debug("Running insert or update")
    try:
        influxdb.write_points([data])
    except InfluxDBClientError as err:
        LOGGER.error("Error(%s) - %s", err.code, err.content)
    except requests.ConnectionError as err:
        LOGGER.error(err)


def delete_active(al):
    LOGGER.debug("Running delete series")
    try:
        influxdb.delete_series(measurement="active", tags={"hash": al.alhash})
    except InfluxDBClientError as err:
        LOGGER.error("Error(%s) - %s", err.code, err.content)


def remove_stale_alerts(aws_instances):
    LOGGER.debug("Checking for stale alerts from terminated instances")
    # Remove old stale alerts from terminated instances
    for al in db.get_active_alerts():
        x = [tag['value'] for tag in al.tags if tag['key'] == 'host']
        if not x:
            # Alert does not have host tag set, nothing to do
            continue
        else:
            if not (x[0] in aws_instances and
                    aws_instances[x[0]]['state'] in [16, 64, 80]):
                LOGGER.debug(
                    "Stale alert found, host not in aws instance list")
                LOGGER.debug("Removing stale alert")
                db.deactivate_alert(al)
                if app.config['INFLUXDB_ENABLED'] is True:
                    delete_active(al=al)
                LOGGER.debug("Cleaning up existing Pagerduty or JIRA tickets")
                al.level = "OK"
                if al.pd_incident_key:
                    pagerduty.post(alert=al)
                if al.jira_issue:
                    jira.post(alert=al)


def influxify(al, alhash, measurement, zero_time=False):
    LOGGER.debug("Creating InfluxDB json data")
    # Used to count currently active alerts
    if zero_time:
        LOGGER.debug("Creating zero time data")
        try:
            env = [tag['value'] for tag in al.tags
                   if tag['key'] == 'Environment'][0]
        except KeyError:
            env = None
        if env == ['']:
            env = None
        json_body = {
            "measurement": measurement,
            "tags": {
                "hash": alhash,
                "Environment": env},
            "fields": {
                "level": al.level,
                "id": al.id},
            "time": 0
        }
    else:
        json_body = {
            "measurement": measurement,
            "tags": {
                "id": al.id,
                "level": al.level,
                "previousLevel": al.previouslevel},
            "fields": {
                "id": al.id,
                "duration": al.duration,
                "message": al.message}
        }
        tags = json_body['tags']
        for t in al.tags:
            tags[t['key']] = t['value']
        json_body['tags'] = tags

    return json_body


def affected_by_mrules(mrules, al):
    # LOGGER.debug("Checking maintenance")
    # If this is an alert OK with an existing ticket, override maintenace
    if ((al.previouslevel != 'OK' and al.level == 'OK') and
            (al.jira_issue is not None or al.pd_incident_key is not None)):
        LOGGER.info("Running maintenance override to clear existing ticket")
    else:
        for mrule in mrules:
            mrv = mrule['value']
            v = [tag['value'] for tag in al.tags if tag['key'] == mrule['key']]
            if mrv in v:
                return True
            if mrv[0] == '*' and v[0].endswith(mrv[1:]):
                return True
            if mrv[-1] == '*' and v[0].startswith(mrv[:-1]):
                return True
            if mrule['key'] == 'id':
                if al.id.endswith(mrule['value']):
                    return True
    return False


def contains_excluded_tags(excluded, tags):
    x = [t for t in tags if t in excluded]
    if x:
        LOGGER.debug("One or more tags in exclude list: %s", str(x))
        return True
    # MonGroup is a special tag we use
    # that can have mulitple pipe separated values
    x = [t['value'] for t in excluded if t['key'] == 'MonGroup']
    if x:
        # There is a MonGroup in the exclude list, so get MonGroup from tags
        y = [t['value'] for t in tags if t['key'] == 'MonGroup']
        if y:
            # y should always have length 1 here if exists
            # Split the value and
            # create a new list to compare with the exclude list
            if not set(x).isdisjoint(y[0].split("|")):
                LOGGER.debug("Excluded MonGroup: %s", y[0])
                return True
    return False


def excluded_tick(al, excluded_ticks):
    # This only works if {{ .TaskName }} is the last element of the al.id
    LOGGER.debug("Check for excluded tick script")
    tn = al.id.split()[-1]
    if tn in excluded_ticks:
        LOGGER.debug("Tick %s is excluded", tn)
        return True
    return False


def get_defined_tick_scripts():
    defined_ticks = []
    try:
        byte_ticks = subprocess.check_output(['kapacitor', 'list', 'tasks'])
        for t in byte_ticks.decode().split('\n')[1:-1]:
            defined_ticks.append(t.split())
    except subprocess.CalledProcessError:
        LOGGER.error("Failed to list defined tick scripts")
    except FileNotFoundError:
        LOGGER.error("Kapacitor is not installed")
    return defined_ticks


def get_aws_instances():
    LOGGER.debug("Collecting instance info from AWS API")
    try:
        session = boto3.Session(region_name=app.config['AWS_REGION'])
        client = session.client('ec2')
        response = client.describe_instances()
        instances = []
        for reserv in response['Reservations']:
            instances.extend(reserv['Instances'])
        return instances
    except (NoRegionError, NoCredentialsError,
            ProfileNotFound, ClientError) as e:
        LOGGER.error(e)
    except KeyError:
        LOGGER.error("Failed to collect instance info")


def update_aws_instance_info():
    instances = get_aws_instances()
    if not instances:
        LOGGER.error("Got empty instance list from AWS")
        return None
    instance_status = {}
    LOGGER.debug("Updating instances and status codes")
    for i in instances:
        try:
            x = [tag['Value'] for tag in i.get('Tags') if tag['Key'] == 'Name']
        except TypeError:
            # Skip instance if no tags are set
            continue
        if x:
            env = [tag['Value'] for tag in i.get('Tags')
                   if tag['Key'] == 'Environment']
            if env:
                s = {'env': env[0], 'state': i.get('State')['Code']}
            else:
                s = {'state': i.get('State')['Code']}
            instance_status[x[0]] = s
    return instance_status


def datestr_to_timestamp(datestr):
    m = re.match(
        "20[0-9]{2}-[0-2][0-9]-[0-3][0-9]T[0-2][0-9](:[0-5][0-9]){2}", datestr)
    if m:
        return datetime.timestamp(
            datetime.strptime(m.group(0), '%Y-%m-%dT%H:%M:%S'))
    return None
