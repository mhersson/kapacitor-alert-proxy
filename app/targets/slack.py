# vim:set shiftwidth=4 softtabstop=4 expandtab:
"""
Module: targets.slack

Send messages to slack using webhooks

Created:24.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
"""
import requests
from app import LOGGER


class Slack(object):
    def __init__(self, url, channel, username, state_change_only):
        LOGGER.debug("Initiating slack")
        self._url = url
        self._channel = channel
        self._username = username
        self._state_change_only = state_change_only

    def _create_message(self, alert):
        LOGGER.debug("Creating message")
        colors = {"OK": "good", "INFO": "#439FE0",
                  "WARNING": "warning", "CRITICAL": "danger"}

        slack_json = {"username": self._username,
                      "channel": self._channel,
                      "attachments": [{"fallback": alert.message,
                                       "color": colors[alert.level],
                                       "text": alert.message}]}
        return slack_json

    def post(self, alert):
        if self._state_change_only and alert.level == alert.previouslevel:
            LOGGER.debug("No state change")
        else:
            message = self._create_message(alert)
            LOGGER.info("Posting to channel %s", self._channel)
            res = requests.post(self._url, json=message)
            if res:
                LOGGER.info("Response from server: %d %s",
                            res.status_code, res.content.decode())
