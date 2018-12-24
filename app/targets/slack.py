# vim:set shiftwidth=4 softtabstop=4 expandtab:
"""
Module: targets.slack

Send messages to slack using webhooks

Created:24.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
"""
import requests
from app import LOGGER


class Slack():
    def __init__(self, url, channel, username):
        LOGGER.info("Initiating slack")
        self._url = url
        self._channel = channel
        self._username = username

    def _create_message(self, alert):
        LOGGER.info("Creating slack message")
        colors = {"OK": "good", "INFO": "#439FE0",
                  "WARNING": "warning", "CRITICAL": "danger"}

        slack_json = {"username": self._username,
                      "channel": self._channel,
                      "attachments": [{"fallback": alert.message,
                                       "color": colors[alert.level],
                                       "text": alert.message}]}
        return slack_json

    def post(self, alert):
        message = self._create_message(alert)
        LOGGER.info("Posting to channel %s", self._channel)
        res = requests.post(self._url, json=message)
        if res:
            LOGGER.debug("Response from server: %d %s",
                         res.status_code, res.content.decode())
