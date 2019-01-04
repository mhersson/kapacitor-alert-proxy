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
        self._colors = {"OK": "good", "INFO": "#439FE0",
                        "WARNING": "warning", "CRITICAL": "danger"}

    def post(self, alert):
        '''Post alert to slack'''
        slack_json = {"username": self._username,
                      "channel": self._channel,
                      "attachments": [{"fallback": alert.message,
                                       "color": self._colors[alert.level],
                                       "text": alert.message}]}
        LOGGER.info("Posting to channel %s", self._channel)
        res = requests.post(self._url, json=slack_json)
        if res:
            LOGGER.debug("Response from server: %d %s",
                         res.status_code, res.content.decode())

    def post_message(self, title, message, color='INFO'):
        '''Post message with title to slack '''
        slack_json = {"username": self._username,
                      "channel": self._channel,
                      "attachments": [{"title": title,
                                       "color": self._colors[color],
                                       "text": message}]}
        LOGGER.info("Posting to channel %s", self._channel)
        res = requests.post(self._url, json=slack_json)
        if res:
            LOGGER.debug("Response from server: %d %s",
                         res.status_code, res.content.decode())
