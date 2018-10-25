# pylint: disable=R0903
'''
Module: alert.py

Created: 17.Apr.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''


class Alert():
    def __init__(self, alertid, duration, message,
                 level, previouslevel, alerttime, tags):
        self.id = alertid
        self.duration = duration
        self.message = message
        self.level = level
        self.previouslevel = previouslevel
        self.time = alerttime
        self.tags = tags
        self.pd_incident_key = None
        self.jira_issue = None
        self.grafana_url = None
        self.count = 1
        self.state_duration = False
        self.sent = False

    def __repr__(self):
        return ("Alert(id={}, duration={}, message={}, level={}, "
                "previouslevel={}, time={}, tags={}, "
                "pd_incident_key={}, jira_issue={}, "
                "grafana_url={}, count={}, state_duration={}, "
                "sent={})".format(
                    self.id,
                    self.duration,
                    self.message,
                    self.level,
                    self.previouslevel,
                    self.time,
                    self.tags,
                    self.pd_incident_key,
                    self.jira_issue,
                    self.grafana_url,
                    self.count,
                    self.state_duration,
                    self.sent
                ))
