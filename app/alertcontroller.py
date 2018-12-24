#!/usr/bin/env python
# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: alertcontroller.py

Created: 27.Dec.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''
import re
import time
import boto3
import subprocess
from datetime import datetime
from botocore.exceptions import NoCredentialsError, ProfileNotFound
from botocore.exceptions import NoRegionError, ClientError

from app import app, LOGGER
from app.alert import Alert
from app.targets.slack import Slack
from app.targets.jira import Incident
from app.targets.pagerduty import Pagerduty
from app.dbcontroller import DBController
from app.influxdbcontroller import InfluxDBController


class AlertController():
    """Main controller class for all incoming alerts """

    def __init__(self):
        self._db = DBController()
        self._influx = InfluxDBController()
        self.slack = Slack(url=app.config['SLACK_URL'],
                           channel=app.config['SLACK_CHANNEL'],
                           username=app.config['SLACK_USERNAME'])
        self.pagerduty = Pagerduty(
            url=app.config['PAGERDUTY_URL'],
            service_key=app.config['PAGERDUTY_SERVICE_KEY'])
        self.jira = Incident(server=app.config['JIRA_SERVER'],
                             username=app.config['JIRA_USERNAME'],
                             password=app.config['JIRA_PASSWORD'],
                             project_key=app.config['JIRA_PROJECT_KEY'],
                             assignee=app.config['JIRA_ASSIGNEE'])

    def create_alert(self, content):
        LOGGER.info("Creating alert")
        tags = []
        for s in content['data']['series']:
            try:
                tags.extend([{'key': k, 'value': v}
                             for k, v in s['tags'].items()])
            except KeyError:
                continue

        al = Alert(alertid=content['id'],
                   duration=content['duration'] // (10 ** 9),
                   message=content['message'], level=content['level'],
                   previouslevel=content['previousLevel'],
                   alerttime=self.datestr_to_timestamp(
                       datestr=content['time']),
                   tags=tags)

        for key in app.config['STATE_DURATION']:
            if al.id.find(key) != -1:
                if al.duration < app.config['STATE_DURATION'][key]:
                    al.state_duration = True

        if app.config['AWS_API_ENABLED']:
            suppress, modified_tags = self.check_instance_tags(tags)
            if suppress:
                return None
            if modified_tags:
                al.tags = modified_tags
        return al

    def check_instance_tags(self, instance_tags):
        # Try to find out if alert is from a normal ec2 instance or autoscaling
        # instance, and then suppress alerts from terminated autoscaling
        # instances. If instance is valid and running, check that the
        # Environment tag exists, if not try to add it from aws info
        # (this would be the case for e.g ping tests running outside
        # of the instance environment)
        instance_info = self.update_aws_instance_info()
        try:
            LOGGER.info("Checking incoming host tag")
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
                LOGGER.info("Using url as host tag")
                instance_tags.append({'key': 'host', 'value': x[0]})
            LOGGER.info("Host tag, %s", x[0])
            if instance_info:
                if (x[0] in instance_info and
                        instance_info[x[0]]['state'] in [16, 64, 80]):
                    LOGGER.info("Instance Name exists and status code is "
                                "valid, %s - %d", x[0],
                                instance_info[x[0]]['state'])
                    env = [tag['value'] for tag in instance_tags
                           if tag['key'] == 'Environment']
                    if not env or env == ['']:
                        # Remove the old Environment tag if env == ['']
                        tags = [tag for tag in instance_tags
                                if tag['key'] != 'Environment']
                        LOGGER.info("Adding missing Environment tag")
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
                    LOGGER.info("Instance status looks like autoscaling"
                                " instance, supressing alert")
                    return True, None
        except KeyError:
            LOGGER.info(
                "Alert is not instance specific or host tag is missing")
        finally:
            if not url:
                self.remove_stale_alerts(instance_info)
        return False, None

    def dispatch_and_update_status(self, al, dispatch=True):
        if dispatch:
            LOGGER.info("Dispatch to all targets")
            al.sent = True
            mrules = self._db.get_active_maintenance_rules()
            in_maintenance = self.affected_by_mrules(mrules, al)
            self.run_slack(in_maintenance, al)
            al.pd_incident_key = self.run_pagerduty(in_maintenance, al)
            al.jira_issue = self.run_jira(in_maintenance, al)
        self.update_active_alerts(al)
        self._influx.update(al)

    def update_active_alerts(self, al):
        alert_is_active = self._db.is_active(al)
        if al.level != 'OK' and alert_is_active:
            self._db.update_alert(al)
        elif al.level != 'OK' and not alert_is_active:
            self._db.activate_alert(al)
        elif al.level == 'OK' and alert_is_active:
            self._db.deactivate_alert(al)
        if al.level != al.previouslevel:
            self._db.log_alert(al)

    def run_slack(self, in_maintenance, al):
        if app.config['SLACK_ENABLED'] and (
                not in_maintenance or
                app.config['SLACK_IGNORE_MAINTENANCE']):
            if not self.contains_excluded_tags(
                    app.config['SLACK_EXCLUDED_TAGS'], al.tags):
                self.slack.post(al)

    def run_pagerduty(self, in_maintenance, al):
        if app.config['PAGERDUTY_ENABLED'] and (
                not in_maintenance or
                app.config['PAGERDUTY_IGNORE_MAINTENANCE']):
            if self.contains_excluded_tags(
                    app.config['PAGERDUTY_EXCLUDED_TAGS'], al.tags):
                return al.pd_incident_key
            if self.excluded_tick(al, app.config['PAGERDUTY_EXCLUDED_TICKS']):
                return al.pd_incident_key
            al.pd_incident_key = self.pagerduty.post(al)
            LOGGER.info("Pagerduty incident key: %s", al.pd_incident_key)
        return al.pd_incident_key

    def run_jira(self, in_maintenance, al):
        if app.config['JIRA_ENABLED'] and not in_maintenance:
            if self.contains_excluded_tags(
                    app.config['JIRA_EXCLUDED_TAGS'], al.tags):
                return al.jira_issue
            al.jira_issue = self.jira.post(al)
            LOGGER.info("JIRA issue: %s", al.jira_issue)
        return al.jira_issue

    @staticmethod
    def add_grafana_url(al):
        if app.config['GRAFANA_ENABLED']:
            LOGGER.info("Adding Grafana url")
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
            url = app.config['GRAFANA_URL'].format(
                *urlvars, starttime, stoptime)
            return url
        return None

    def remove_stale_alerts(self, aws_instances):
        LOGGER.info("Checking for stale alerts from terminated instances")
        # Remove old stale alerts from terminated instances
        for al in self._db.get_active_alerts():
            x = [tag['value'] for tag in al.tags if tag['key'] == 'host']
            if not x:
                # Alert does not have host tag set, nothing to do
                continue
            else:
                if not (x[0] in aws_instances and
                        aws_instances[x[0]]['state'] in [16, 64, 80]):
                    LOGGER.info(
                        "Stale alert found, host not in aws instance list")
                    LOGGER.info("Removing stale alert")
                    self._db.deactivate_alert(al)
                    self._db.log_alert(al)
                    self._influx.delete_active(al)
                    LOGGER.info(
                        "Cleaning up existing Pagerduty or JIRA tickets")
                    al.level = "OK"
                    if al.pd_incident_key:
                        self.pagerduty.post(alert=al)
                    if al.jira_issue:
                        self.jira.post(alert=al)

    @staticmethod
    def affected_by_mrules(mrules, al):
        # LOGGER.info("Checking maintenance")
        # If this is an alert OK with an existing ticket, override maintenace
        if ((al.previouslevel != 'OK' and al.level == 'OK') and
                (al.jira_issue is not None or al.pd_incident_key is not None)):
            LOGGER.info(
                "Running maintenance override to clear existing ticket")
        else:
            for mrule in mrules:
                mrv = mrule['value']
                v = [tag['value']
                     for tag in al.tags if tag['key'] == mrule['key']]
                if mrv in v:
                    return True
                if mrv[0] == '*' and v[0].endswith(mrv[1:]):
                    return True
                if mrv[-1] == '*' and v[0].startswith(mrv[:-1]):
                    return True
                if mrule['key'] == 'id':
                    if mrule['value'] in al.id:
                        return True
        return False

    @staticmethod
    def contains_excluded_tags(excluded, tags):
        x = [t for t in tags if t in excluded]
        if x:
            LOGGER.info("One or more tags in exclude list: %s", str(x))
            return True
        # MonGroup is a special tag we use
        # that can have mulitple pipe separated values
        x = [t['value'] for t in excluded if t['key'] == 'MonGroup']
        if x:
            # There is a MonGroup in the exclude list, so get tag MonGroup
            y = [t['value'] for t in tags if t['key'] == 'MonGroup']
            if y:
                # y should always have length 1 here if exists
                # Split the value and
                # create a new list to compare with the exclude list
                if not set(x).isdisjoint(y[0].split("|")):
                    LOGGER.info("Excluded MonGroup: %s", y[0])
                    return True
        return False

    @staticmethod
    def excluded_tick(al, excluded_ticks):
        # This only works if {{ .TaskName }} is the last element of the al.id
        LOGGER.info("Check for excluded tick script")
        tn = al.id.split()[-1]
        if tn in excluded_ticks:
            LOGGER.info("Tick %s is excluded", tn)
            return True
        return False

    @staticmethod
    def get_defined_tick_scripts():
        defined_ticks = []
        try:
            byte_ticks = subprocess.check_output(
                ['kapacitor', 'list', 'tasks'])
            for t in byte_ticks.decode().split('\n')[1:-1]:
                defined_ticks.append(t.split())
        except subprocess.CalledProcessError:
            LOGGER.error("Failed to list defined tick scripts")
        except FileNotFoundError:
            LOGGER.error("Kapacitor is not installed")
        return defined_ticks

    @staticmethod
    def get_aws_instances():
        LOGGER.info("Collecting instance info from AWS API")
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

    def update_aws_instance_info(self):
        instances = self.get_aws_instances()
        if not instances:
            LOGGER.error("Got empty instance list from AWS")
            return None
        instance_status = {}
        LOGGER.info("Updating instances and status codes")
        for i in instances:
            try:
                x = [tag['Value']
                     for tag in i.get('Tags') if tag['Key'] == 'Name']
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

    @staticmethod
    def datestr_to_timestamp(datestr):
        m = re.match(
            "20[0-9]{2}-[0-2][0-9]-[0-3][0-9]T[0-2][0-9](:[0-5][0-9]){2}",
            datestr)
        if m:
            return datetime.timestamp(
                datetime.strptime(m.group(0), '%Y-%m-%dT%H:%M:%S'))
        return None
