"""
Module: tasks

Created: 28.Sep.2018
Created by: Morten Hersson, <morten@escenic.com>

Copyright (c) 2018 Morten Hersson
"""
import os
import time
import calendar
import datetime
import re
import json
import requests

from app import app, routes, INSTALLDIR, LOGGER


class KAOS():
    def __init__(self):
        LOGGER.debug("Initiating KAOS scheduler")

    def run(self):
        kaos_report = {app.config['KAOS_CUSTOMER']: []}
        mrules = routes.load_mrules()
        for v in routes.getActiveAlerts():
            if (app.config['KAOS_IGNORE_MAINTENANCE'] or
                    not routes.affected_by_mrules(mrules, v)):
                if routes.contains_excluded_tags(
                        app.config['KAOS_EXCLUDED_TAGS'], v.tags):
                    continue
                # Create a copy we can play with
                al_dict = dict(v.__dict__)
                al_dict['message'] = routes.truncate_string(al_dict['message'])
                al_dict['time'] = self._fixtimezone(al_dict['time'])
                # GO-lint complains about underscores in variables
                # and there is no way do selectivly disable it,
                # so to make the go linter shut up when developing KAOS
                # I just renamed the keys here.
                al_dict['GrafanaURL'] = al_dict.pop('grafana_url')
                al_dict['PDIncidentKey'] = al_dict.pop('pd_incident_key')
                al_dict['JiraIssue'] = al_dict.pop('jira_issue')
                kaos_report[app.config['KAOS_CUSTOMER']].append(al_dict)
        self._send_report(kaos_report)

    @staticmethod
    def _send_report(kaos_report):
        LOGGER.debug("Sending KAOS report")
        try:
            requests.post(app.config['KAOS_URL'],
                          verify=app.config['KAOS_CERT'],
                          json=kaos_report, timeout=5)
        except requests.exceptions.RequestException:
            LOGGER.exception("Failed posting to KAOS")

    @staticmethod
    def _fixtimezone(s):
        tzdiff = calendar.timegm(
            time.localtime()) - calendar.timegm(time.gmtime())
        return s + tzdiff


class MaintenanceScheduler():
    def __init__(self):
        LOGGER.debug("Initiating maintenance scheduler")
        self._scheduledir = os.path.join(INSTALLDIR, "maintenance/schedule")

    def run(self):
        now = datetime.datetime.today()
        LOGGER.debug("Checking maintenance schedule")
        for sf in os.listdir(self._scheduledir):
            m = re.match("schedule_([0-9]{10}).json", sf)
            if m:
                filename = os.path.join(self._scheduledir, sf)
                schedule = self._read_file(filename)
                if (self._check_day(now, schedule['days'])
                        and self._check_starttime(now, schedule['starttime'])):
                    LOGGER.debug("Activating scheduled maintenance")
                    LOGGER.debug("Schedule: %s", str(schedule))
                    routes.activate_maintenance(schedule['key'],
                                                schedule['value'],
                                                schedule['duration'])
                    schedule['runcounter'] = self._update_run_counter(
                        now, schedule['runcounter'])
                    self._write_file(filename, schedule)
                    if (self._schedule_completed(schedule['runcounter'])
                            and not schedule['repeat']):
                        LOGGER.debug("Deleting completed schedule")
                        os.remove(os.path.join(self._scheduledir, sf))

    @staticmethod
    def _read_file(path):
        try:
            with open(path, 'r') as f:
                return json.loads(f.read())
        except (OSError, json.JSONDecodeError):
            LOGGER.error("Failed to open file, %s", path)

    @staticmethod
    def _write_file(path, content):
        try:
            with open(path, 'w') as f:
                return f.write(json.dumps(content) + "\n")
        except OSError:
            LOGGER.debug("Failed writing file, %s", path)

    @staticmethod
    def _check_day(now, days):
        return True if str(now.weekday()) in days else False

    @staticmethod
    def _check_starttime(now, starttime):
        hour, minute = starttime.split(":")
        if int(hour) == now.hour and int(minute) == now.minute:
            return True
        return False

    @staticmethod
    def _update_run_counter(now, runcounter):
        LOGGER.debug("Updating schedule run counter")
        runcounter[str(now.weekday())] = runcounter[str(now.weekday())] + 1
        return runcounter

    @staticmethod
    def _schedule_completed(runcounter):
        return 0 not in set(v for v in runcounter.values())
