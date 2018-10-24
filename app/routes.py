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
import boto3
import hashlib
import requests
import calendar
import subprocess
from datetime import datetime, timedelta
from flask import Response, request, render_template, redirect
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError
from botocore.exceptions import NoCredentialsError, ProfileNotFound
from botocore.exceptions import NoRegionError, ClientError

from app import app, LOGGER, INSTALLDIR, TZNAME
from app.alert import Alert
from app.targets.slack import Slack
from app.targets.pagerduty import Pagerduty
from app.targets.jira import Incident
from app.forms.maintenance import ActivateForm, DeactivateForm, DeleteSchedule

STARTUP_TIME = time.time()

ACTIVE_ALERTS = {}
STATISTICS = {}
INSTANCES = {}

db = InfluxDBClient(host=app.config['INFLUXDB_HOST'],
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


def getActiveAlerts():
    return ACTIVE_ALERTS.values()

@app.route("/kap/alert", methods=['post'])
def alert():
    LOGGER.debug("Received new data")
    al = create_alert(request.json)
    if al is not None:
        alhash = get_hash(al)
        al.pd_incident_key = get_pagerduty_incident_key(alhash)
        al.jira_issue = get_jira_issue(alhash)
        al.grafana_url = add_grafana_url(al)
        mrules = load_mrules()
        in_maintenance = affected_by_mrules(mrules, al)
        run_slack(in_maintenance, al)
        al.pd_incident_key = run_pagerduty(in_maintenance, al)
        al.jira_issue = run_jira(in_maintenance, al)
        update_active_alerts(al, alhash)
        update_influxdb(al, alhash)
    return Response(response={'Success': True},
                    status=200, mimetype='application/json')


@app.route("/kap/maintenance", methods=['GET', 'POST'])
def maintenance():
    af = ActivateForm()
    df = DeactivateForm()
    dsf = DeleteSchedule()
    if af.validate_on_submit():
        if af.days.data and af.starttime.data != "":
            schedule_maintenance(af.key.data, af.val.data, af.duration.data,
                                 af.days.data, af.starttime.data,
                                 af.repeat.data)
        else:
            activate_maintenance(af.key.data, af.val.data, af.duration.data)
        return redirect('/kap/maintenance')
    if df.validate_on_submit():
        deactive_maintenance(df.key.data, df.value.data,
                             df.start.data, df.stop.data)
        return redirect('/kap/maintenance')
    if dsf.validate_on_submit():
        delete_schedule(dsf.filename.data)
        return redirect('/kap/maintenance')
    mrules = load_mrules()
    schedule = load_schedule()
    return render_template('maintenance.html', title="Maintenance",
                           mrules=mrules, schedule=schedule,
                           af=af, df=df, dsf=dsf, tzname=TZNAME)


@app.route("/kap/status", methods=['GET'])
def status():
    mrules = load_mrules()
    aim = []
    for a in ACTIVE_ALERTS:
        if affected_by_mrules(mrules=mrules, al=ACTIVE_ALERTS[a]):
            aim.append(ACTIVE_ALERTS[a])
    return render_template('status.html', title="Active alerts",
                           group_tag=app.config['MAIN_GROUP_TAG'],
                           alerts=ACTIVE_ALERTS, maintenance=aim,
                           tzname=TZNAME)


@app.route("/kap/statistics", methods=['GET'])
def statistics():
    return render_template('statistics.html', title="Statistics",
                           stats=STATISTICS, startup_time=STARTUP_TIME)


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
    LOGGER.debug(al)

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
        if not x:
            # Telegraf input plugin ping uses tag url
            # and net_response uses server and not host
            # so try and use that if host does not exist
            # but check that aint a proper web url
            x = [tag['value'] for tag in instance_tags
                 if tag['key'] in ['url', 'server']]
            if not x or x[0].startswith("http"):
                raise KeyError
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


def run_slack(in_maintenance, al):
    if app.config['SLACK_ENABLED'] and (
            not in_maintenance or
            app.config['SLACK_IGNORE_MAINTENANCE']):
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


def update_active_alerts(al, alhash):
    if al.level != 'OK' and alhash in ACTIVE_ALERTS:
        LOGGER.debug("Updating active alert")
        ACTIVE_ALERTS[alhash] = al
    elif al.level != 'OK' and alhash not in ACTIVE_ALERTS:
        LOGGER.debug("Setting new active alert")
        ACTIVE_ALERTS[alhash] = al
    elif al.level == 'OK' and alhash in ACTIVE_ALERTS:
        del ACTIVE_ALERTS[alhash]
    if al.level != al.previouslevel:
        update_statistics(alhash, al)


def update_influxdb(al, alhash):
    if app.config['INFLUXDB_ENABLED'] is True:
        if al.level != al.previouslevel:
            LOGGER.debug("Updating InfluxDB")
            update_db(influxify(al, alhash, "logs"))
            if al.level == 'OK':
                delete_active(al)
            else:
                update_db(influxify(al, alhash, "active", True))
        else:
            update_db(influxify(al, alhash, "active", True))


def update_db(data):
    LOGGER.debug("Running insert or update")
    try:
        db.write_points([data])
    except InfluxDBClientError as err:
        LOGGER.error("Error(%s) - %s", err.code, err.content)
    except requests.ConnectionError as err:
        LOGGER.error(err)


def delete_active(al):
    LOGGER.debug("Running delete series")
    try:
        db.delete_series(measurement="active", tags={"hash": get_hash(al)})
    except InfluxDBClientError as err:
        LOGGER.error("Error(%s) - %s", err.code, err.content)


def remove_stale_alerts(aws_instances):
    LOGGER.debug("Checking for stale alerts from terminated instances")
    # Remove old stale alerts from terminated instances
    for alhash, al in ACTIVE_ALERTS.items():
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
                del ACTIVE_ALERTS[alhash]
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
        json_body = {
            "measurement": measurement,
            "tags": {
                "hash": alhash},
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


def update_statistics(alhash, al):
    LOGGER.debug("Updating statistics")
    if alhash in STATISTICS:
        now = int(time.time())
        stats = STATISTICS[alhash]
        plevel = stats[al.previouslevel]
        plevel["count"] += 1
        plevel["duration"] = plevel["duration"] + ((
            (now - stats['timestamp']) - plevel["duration"]) / plevel["count"])
        stats[al.previouslevel] = plevel
        stats['timestamp'] = now
        STATISTICS[alhash] = stats
    else:
        if al.level != 'OK':
            STATISTICS[alhash] = initialize_stats_counters(al)


def initialize_stats_counters(al):
    stats = {'id': al.id, 'timestamp': int(time.time()),
             'OK': {'count': 0, 'duration': 0},
             'INFO': {'count': 0, 'duration': 0},
             'WARNING': {'count': 0, 'duration': 0},
             'CRITICAL': {'count': 0, 'duration': 0}}
    return stats


def get_pagerduty_incident_key(alhash):
    if alhash in ACTIVE_ALERTS:
        existing = ACTIVE_ALERTS[alhash]
        if existing.pd_incident_key:
            LOGGER.info("Found existing incident key")
            return existing.pd_incident_key
    return None


def get_jira_issue(alhash):
    if alhash in ACTIVE_ALERTS:
        existing = ACTIVE_ALERTS[alhash]
        if existing.jira_issue:
            LOGGER.info("Found existing jira issue")
            return existing.jira_issue
    return None


def activate_maintenance(key, val, duration):
    LOGGER.debug('Setting maintenance')
    duration_secs = {'m': 60, 'h': 3600, 'd': 86400, 'w': 604800}
    start = int(time.time())
    stop = int(start + (int(duration[:-1]) * duration_secs[duration[-1]]))
    rule = {"key": key, "value": val, "start": start, "stop": stop}
    filename = "maintenance_{}-{}.json".format(start, stop)
    path = os.path.join(INSTALLDIR, "maintenance", filename)
    rules = []
    # If multiple schedules start and stop at the exact same time
    # they will try to write to the same file, so reload file
    # into a list of rules and append the the latest rule
    if os.path.exists(path):
        rules = load_json(path)
    rules.append(rule)
    write_json(path, rules)


def deactive_maintenance(key, value, start, stop):
    LOGGER.debug("Deactive maintenance")
    rule = {"key": key, "value": value, "start": int(start), "stop": int(stop)}
    filename = "maintenance_{}-{}.json".format(start, stop)
    path = os.path.join(INSTALLDIR, "maintenance", filename)
    rules = load_json(path)
    if len(rules) == 1:
        os.remove(path)
    else:
        LOGGER.debug("Found multiple rules in maintenance file")
        for index, r in enumerate(rules):
            if r == rule:
                LOGGER.debug("Deleting rule %s", str(r))
                del rules[index]
                break
        write_json(path, rules)


def schedule_maintenance(key, val, duration, days, starttime, repeat):
    r = True if repeat else False
    filename = "schedule_{}.json".format(int(time.time()))
    counter = {day: 0 for day in days}
    schedule = {"key": key, "value": val, "duration": duration, "days": days,
                "starttime": starttime, "repeat": r,
                "runcounter": counter, "filename": filename}
    write_json(os.path.join(
        INSTALLDIR, "maintenance/schedule", filename), schedule)


def load_schedule():
    LOGGER.debug("Loading schedule")
    schedule = []
    msdir = os.path.join(INSTALLDIR, "maintenance/schedule")
    msfiles = os.listdir(msdir)
    for msf in msfiles:
        m = re.match("schedule_([0-9]{10}).json", msf)
        if m:
            schedule.append(load_json(os.path.join(msdir, msf)))
    return schedule


def delete_schedule(filename):
    LOGGER.debug("Delete schedule")
    try:
        os.remove(os.path.join(INSTALLDIR, "maintenance/schedule", filename))
    except OSError:
        LOGGER.error("Failed to delete schedule")


def load_mrules():
    LOGGER.debug("Loading maintenance")
    mrules = []
    mdir = os.path.join(INSTALLDIR, "maintenance")
    mfiles = os.listdir(mdir)
    for mf in mfiles:
        m = re.match("maintenance_([0-9]{10})-([0-9]{10}).json", mf)
        if m:
            if int(m.group(1)) <= int(time.time()) <= int(m.group(2)):
                mrules.extend(load_json(os.path.join(mdir, mf)))
            else:
                LOGGER.info("Deleting expired rule")
                os.remove(os.path.join(mdir, mf))
    return mrules


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


def get_hash(al):
    alhash = hashlib.sha256(al.id.encode()).hexdigest()
    LOGGER.debug('Alert hash: %s', alhash)
    return alhash


def write_json(path, content):
    try:
        with open(path, 'w') as f:
            f.write(json.dumps(content) + "\n")
    except OSError:
        LOGGER.error("Failed writing %s", path)


def load_json(path):
    try:
        with open(path, 'r') as f:
            return json.loads(f.read())
    except OSError:
        LOGGER.error("Failed reading %s", path)
