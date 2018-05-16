# vim:set shiftwidth=4 softtabstop=4 expandtab:
# pylint: disable=R0903
"""
Module: targets.jira

Create and update issues with JIRA REST API

Created: 08.May.2018
Created by: Morten Hersson, <mhersson@gmail.com>
"""
from jira.client import JIRA
from jira.exceptions import JIRAError
from app import LOGGER


class Incident(object):
    def __init__(self, server, username, password, project_key, assignee):
        LOGGER.debug("Initiating jira incident")
        self._server = server
        self._username = username
        self._password = password
        self._project_key = project_key
        self._assignee = assignee

    def _connect(self):
        LOGGER.debug("Connecting to JIRA")
        try:
            conn = JIRA(options={'server': self._server},
                        basic_auth=(self._username, self._password))
            return conn
        except JIRAError as err:
            LOGGER.error("Failed connecting to JIRA")
            LOGGER.error(err)
        return None

    def _create(self, alert):
        issue_dict = {'project': {'key': self._project_key},
                      'summary': alert.id,
                      'description': alert.message,
                      # 'assignee': {'name': self._assignee},
                      'components': [{'name': self._assignee}],
                      'issuetype': {'name': 'Incident'},
                      'security': {'name': 'Internal Issue'}}
        jira = self._connect()
        if jira:
            try:
                LOGGER.info("Creating JIRA ticket")
                issue = jira.create_issue(fields=issue_dict)
                if issue:
                    return issue.key
            except JIRAError as err:
                LOGGER.error("Failed creating JIRA ticket")
                LOGGER.error(err)
        return None

    @staticmethod
    def _get_transistion_id(jira, issue, name):
        try:
            LOGGER.debug("Getting available transistions")
            transitions = jira.transitions(issue)
            t = [t['id'] for t in transitions if t['name'] == name]
            if t:
                return t[0]
        except JIRAError as err:
            LOGGER.error(err)
        return None

    def _resolve(self, jira, issue):
        try:
            LOGGER.debug("Resolving JIRA ticket")
            t = self._get_transistion_id(jira, issue, 'Resolve Issue')
            if t:
                jira.transition_issue(issue, t)
                LOGGER.info("JIRA ticket resolved")
        except JIRAError as err:
            LOGGER.error("Failed resolving JIRA ticket")
            LOGGER.error(err)

    def _close(self, jira, issue):
        try:
            LOGGER.debug("Closing JIRA ticket")
            t = self._get_transistion_id(jira, issue, 'Close Issue')
            if t and len(issue.fields.comment.comments) <= 0:
                jira.transition_issue(issue, t)
                LOGGER.info("JIRA ticket closed")
        except JIRAError as err:
            LOGGER.error("Failed closing JIRA ticket")
            LOGGER.error(err)

    def _resolve_and_close(self, key):
        jira = self._connect()
        if jira:
            issue = jira.issue(key)
            if not issue:
                LOGGER.error("Failed to get issue")
                return
            self._resolve(jira, issue)
            self._close(jira, issue)

    def post(self, alert):
        key = None
        if alert.level != alert.previouslevel:
            if alert.level == 'CRITICAL':
                key = self._create(alert)
            elif alert.level != 'CRITICAL' and alert.jira_issue is not None:
                self._resolve_and_close(key=alert.jira_issue)
        return key
