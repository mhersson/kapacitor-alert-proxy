#!/usr/bin/env python
# pylint: disable=R0903,C0301
# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: config.py

Created: 23.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''


class Config():
    # Server settings
    SERVER_FQDN = "localhost"
    SERVER_ADDRESS = "0.0.0.0"
    SERVER_PORT = 9095
    SECRET_KEY = "Something-really-clever"

    # This is used to gather instance info, suppress alerts from
    # terminated auto-scaling instances, and remove stale alerts from
    # all types of terminated instances - AWS API Gateway prices apply
    # https://aws.amazon.com/api-gateway/pricing/
    AWS_API_ENABLED = False
    AWS_REGION = "eu-west-1"

    # Maintenance tags (value, displayed text)
    MAINTENANCE_TAGS = [('Environment', 'Environment'),
                        ('host', 'Host'),
                        ('id', 'Id')]   # This is the alert id

    # With flapping detection enabled KAP tries to detect if an alert is
    # flapping and the hold back the alerts, and instead
    # let you know the alert is flapping to reduce the number of messages sent
    FLAPPING_DETECTION_ENABLED = True
    # Size of time window in minutes to check for flapping alerts
    FLAPPING_WINDOW = 60
    # The number of alerts within the FLAPPING_WINDOW
    # before the alert is considered flapping
    FLAPPING_LIMIT = 4
    # Number of seconds to hold back an alert before dispatching to targets
    # This is a global setting and affects all alerts. To hold back individual
    # alerts use STATE_DURATION
    ALERTING_DELAY = 300
    # Delay forwarding alerts until they have been in
    # alerting state for the given number of seconds
    # {"match string", delay secs} - match string must be part of the alert id
    STATE_DURATION = {}

    # Send Active Alerts to KAOS
    KAOS_ENABLED = False
    KAOS_CUSTOMER = "Test-Customer"
    KAOS_URL = "https://localhost/kaos/update/"
    KAOS_CERT = "server_bundle.pem"
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
    # List of tagkey tagkey/value dictionaries that will not trigger slack
    SLACK_EXCLUDED_TAGS = [{'key': 'Environment', 'value': 'test'},
                           {'key': 'Environment', 'value': 'staging'}]
    # Send summary message with stats for the last hour for all environments
    # This will include environments event if they are among the excluded tags
    SLACK_SUMMARY = True

    # Pagerduty
    PAGERDUTY_ENABLED = False
    PAGERDUTY_URL = "https://events.pagerduty.com/generic/2010-04-15/create_event.json"  # noqa
    PAGERDUTY_SERVICE_KEY = ""
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
    # Post the url for newly created tickets to the slack channel
    # (Requires SLACK_ENABLED and a working slack configuration)
    JIRA_URL_TO_SLACK = False

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
