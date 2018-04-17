# vim:set shiftwidth=4 softtabstop=4 expandtab:
"""
Module: targets.pagerduty

Send events to pagerduty event API

Created: 17.Apr.2018
Created by: Morten Hersson, <mhersson@gmail.com>
"""
import json
import requests
from app import LOGGER


class Pagerduty(object):
    def __init__(self, url, service_key, state_change_only):
        LOGGER.debug("Initiating pagerduty")
        self._url = url
        self._service_key = service_key
        self._state_change_only = state_change_only

    def _create_event(self, alert, event_type="trigger"):
        LOGGER.debug("Creating event")

        if event_type == "trigger":
            LOGGER.debug("Type trigger event")
            pd_json = {
                "service_key": self._service_key,
                "event_type": event_type,
                "description": alert.id,
                "client": "KAP",
                "details": {
                    "message": alert.message
                }
            }
        elif event_type == "resolve":
            LOGGER.debug("Type resolve event")
            pd_json = {
                "service_key": self._service_key,
                "event_type": event_type,
                "incident_key": alert.pd_incident_key
            }

        return pd_json

    def post(self, alert):
        if self._state_change_only and alert.level == alert.previouslevel:
            LOGGER.debug("No state change")
        else:
            if alert.level == 'CRITICAL':
                message = self._create_event(alert)
            elif (alert.level != 'CRITICAL' and
                  alert.pd_incident_key is not None):
                message = self._create_event(alert, event_type="resolve")
            else:
                LOGGER.info("None critical event")
                return alert.pd_incident_key
            LOGGER.info("Sending event")
            res = requests.post(self._url, json=message)
            if res:
                LOGGER.info("Response from server: %d %s",
                            res.status_code, res.content.decode())
                return json.loads(res.content.decode()).get('incident_key')
        return alert.pd_incident_key
