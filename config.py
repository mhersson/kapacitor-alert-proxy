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
    SECRET_KEY = "Something-really-clever"

    # This is used to gather instance info, suppress alerts from
    # terminated auto-scaling instances, and remove stale alerts from
    # all types of terminated instances - AWS API Gateway prices apply
    # https://aws.amazon.com/api-gateway/pricing/
    AWS_API_ENABLED = False
    AWS_REGION = "eu-west-1"

    # Tag used in most or all of kapacitor queries as .groupBy()
    # I use 'Environment' to split between test, staging and produciton
    # host would normally be a sane default if using Telegraf
    MAIN_GROUP_TAG = 'Environment'

    # Maintenance tags (value, displayed text)
    MAINTENANCE_TAGS = [('Environment', 'Environment'),
                        ('host', 'Host'),
                        ('id', 'Id')]   # This is the alert id

    # With flapping detection enabled KAP will not forward alerts to targets
    # unless it receives the number of consecutive alerts defined by the
    # FLAPPING_DETECTION_COUNT setting
    # If both FLAPPING_DETECTION and STATE_DURATION is active STATE_DURATION
    # will kick in after the consecutive count has been reach and could
    # further delay the alert
    FLAPPING_DETECTION_ENABLED = False
    FLAPPING_DETECTION_COUNT = 2
    # Delay forwarding alerts until they have been in
    # alerting state for the given number of seconds
    # {"match string", delay secs} - match string must be part of the alert id
    STATE_DURATION = {}

    # Send Active Alerts to KAOS
    KAOS_ENABLED = False
    KAOS_CUSTOMER = "Test-Customer"
    KAOS_URL = "https://localhost/kaos/update/"
    KAOS_CERT = "server_bundle.pem"
    KAOS_IGNORE_MAINTENANCE = False
    KAOS_EXCLUDED_TAGS = []

    # Write stats to influxdb
    INFLUXDB_ENABLED = False
    INFLUXDB_HOST = 'localhost'
    INFLUXDB_PORT = 8086

    # Slack
    SLACK_ENABLED = False
    # Slack incoming webhook url
    SLACK_URL = ""
    SLACK_CHANNEL = "#alerts"
    SLACK_USERNAME = "kapacitor"
    # Only send alerts when the state changes
    SLACK_STATE_CHANGE_ONLY = True
    # Send alerts to slack even during maintenance
    SLACK_IGNORE_MAINTENANCE = False

    # Pagerduty
    PAGERDUTY_ENABLED = False
    PAGERDUTY_URL = "https://events.pagerduty.com/generic/2010-04-15/create_event.json"  # noqa
    PAGERDUTY_SERVICE_KEY = ""
    # Only send events when the alert state changes
    PAGERDUTY_STATE_CHANGE_ONLY = True
    # Send events to pagerduty even during maintenance
    PAGERDUTY_IGNORE_MAINTENANCE = False
    # List of tagkey tagkey/value dictionaries that will not trigger pagerduty
    PAGERDUTY_EXCLUDED_TAGS = [{'key': 'Environment', 'value': 'test'},
                               {'key': 'Environment', 'value': 'staging'}]
    # List if tick scripts that will not trigger pagerduty
    PAGERDUTY_EXCLUDED_TICKS = []

    # JIRA
    JIRA_ENABLED = False
    JIRA_SERVER = ""
    JIRA_USERNAME = ""
    JIRA_PASSWORD = ""
    JIRA_PROJECT_KEY = ""
    JIRA_ASSIGNEE = ""
    # List of tagkey tagvalue dictionaries that will not trigger an alert
    JIRA_EXCLUDED_TAGS = [{'key': 'Environment', 'value': 'test'},
                          {'key': 'Environment', 'value': 'staging'}]

    GRAFANA_ENABLED = False
    # For this to work the url vars in Grafana must be among the tag
    # values of the incoming alerts.
    # Copy the link to the dashboard you want use replace the
    # var-values with {}, and add the name to the GRAFANA_URL_VARS list
    # in the precise same order as the appear in the url.
    # Make sure the url ends with &from={}&to={} since KAP will always
    # add start time and stop time to the url
    GRAFANA_URL = ""
    GRAFANA_URL_VARS = []
