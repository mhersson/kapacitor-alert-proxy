# pylint: disable=R0903
'''
Module: alert.py

Created: 17.Apr.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''


class Alert(object):
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

    def __repr__(self):
        return ("Alert(id={}, duration={}, message={}, level={}, "
                "previouslevel={}, time={}, tags={}, "
                "pd_incident_key={})".format(
                    self.id,
                    self.duration,
                    self.message,
                    self.level,
                    self.previouslevel,
                    self.time,
                    self.tags,
                    self.pd_incident_key
                ))
