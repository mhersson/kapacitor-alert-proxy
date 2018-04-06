#!/usr/bin/env python
# pylint: disable=R0903,C0301
# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: config.py

Created: 23.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''


class Config(object):
    # Server settings
    SERVER_ADDRESS = "0.0.0.0"
    SERVER_PORT = 9095
    SECRET_KEY = 'Something-really-clever'

    # Tag used in most or all of kapacitor queries as .groupBy()
    # I use 'Environment' to split between test, staging and produciton
    # host would normally be a sane default if using Telegraf
    MAIN_GROUP_TAG = 'Environment'

    # Maintenance tags (value, displayed text)
    MAINTENANCE_TAGS = [('Environment', 'Environment'),
                        ('host', 'Host'),
                        ('id', 'Id')]   # This is the alert id

    # Slack
    SLACK_ENABLED = False
    # Slack incoming webhook url
    SLACK_URL = ""
    SLACK_CHANNEL = "#alerts"
    SLACK_USERNAME = "kapacitor"
    # Only send alerts when the state changes
    SLACK_STATE_CHANGE_ONLY = True
    # Send alerts to slack even if maintenance is sat
    SLACK_IGNORE_MAINTENANCE = False
