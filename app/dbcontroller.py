# pylint: disable=C0413,R0904
# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: dbcontroller.py

Created: 20.Dec.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''
import os
import time
import sqlite3
from app import app, INSTALLDIR, LOGGER
from app.alert import Alert


class DBController():
    """Documentation for DBController

    """

    def __init__(self):
        super(DBController, self).__init__()
        self.db = os.path.join(INSTALLDIR, 'db/kap.db')
        self.flapping_window = app.config['FLAPPING_WINDOW']

    def create_tables(self):
        LOGGER.info("Creating database tables")
        con = sqlite3.connect(self.db)
        with con:
            cur = con.cursor()
            cur.executescript(CREATE_TABLES_SQL)

    def select(self, query, fetchone=True, use_column_name=False):
        con = sqlite3.connect(self.db)
        with con:
            if use_column_name:
                con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute(query)
            if fetchone:
                res = cur.fetchone()
            else:
                res = cur.fetchall()
            if res:
                return res
        return None

    def execute_query(self, query, values=None):
        con = sqlite3.connect(self.db)
        with con:
            cur = con.cursor()
            if values:
                cur.execute(query, values)
            else:
                cur.execute(query)
            return cur.rowcount

    def execute_many(self, query, values):
        con = sqlite3.connect(self.db)
        with con:
            cur = con.cursor()
            cur.executemany(query, values)
            return cur.rowcount

    def get_tickets_and_keys(self, al):
        LOGGER.info("Add tickets and keys")
        query = "select pagerduty, jira, grafana, sent " + \
            "from active_alerts where hash = '{}'".format(al.alhash)
        res = self.select(query, use_column_name=True)
        if res:
            al.pd_incident_key = res['pagerduty']
            al.jira_issue = res['jira']
            al.grafana_url = res['grafana']
            al.sent = bool(res['sent'])
        return al

    def activate_alert(self, al):
        LOGGER.info("Activate alert")
        query = ("INSERT INTO active_alerts (hash, time, id, message,"
                 "previouslevel, level, duration, pagerduty, jira, grafana, "
                 "state_duration, sent) VALUES(?, ?, ?, ?, ?, ?, ? ,? , "
                 "?, ?, ?, ?)")
        values = (al.alhash, al.time, al.id, al.message,
                  al.previouslevel, al.level, al.duration,
                  al.pd_incident_key, al.jira_issue, al.grafana_url,
                  al.state_duration, al.sent)
        self.execute_query(query, values)
        query = "INSERT OR IGNORE INTO active_alert_tags " + \
            "(hash, key, value) VALUES (?, ?, ?)"
        tags = [(al.alhash, x['key'], x['value']) for x in al.tags]
        self.execute_many(query, tags)

    def update_alert(self, al):
        LOGGER.info("Update alert")
        query = ("UPDATE active_alerts set time = ? ,message = ?, "
                 "previouslevel = ?, level = ?, duration = ?,"
                 "pagerduty = ?, jira = ?, grafana = ?, state_duration = ?,"
                 "sent = ? where hash = ?")
        values = (al.time, al.message,
                  al.previouslevel, al.level, al.duration,
                  al.pd_incident_key, al.jira_issue, al.grafana_url,
                  al.state_duration, al.sent, al.alhash)
        self.execute_query(query, values)

    def deactivate_alert(self, al):
        LOGGER.info("Deactivate alert")
        query = "DELETE FROM active_alerts where hash = '{}'".format(al.alhash)
        self.execute_query(query)

    def is_active(self, al):
        query = "SELECT 1 FROM active_alerts where hash = '{}'".format(
            al.alhash)
        res = self.select(query)
        if res:
            return True
        return False

    def state_duration(self, al):
        LOGGER.info("Checking state duration")
        query = "SELECT state_duration FROM active_alerts " + \
            "where hash = '{}'".format(al.alhash)
        res = self.select(query)
        if res:
            return bool(res[0])
        return False

    def get_active_alerts(self):
        LOGGER.info("Get active alerts")
        query = "select id, duration, message, level, previouslevel, " + \
            "time, grafana, jira, pagerduty from active_alerts"
        result = self.select(query, fetchone=False)
        res = []
        if result:
            for r in result:
                a = Alert(r[0], r[1], r[2], r[3], r[4], r[5], None)
                a.grafana_url = r[6]
                a.jira_issue = r[7]
                a.pd_incident_key = r[8]
                a.tags = self.get_tags(a.alhash)
                res.append(a)
        return res

    def get_tags(self, alhash):
        query = "select key, value from active_alert_tags where " + \
            "hash = '{}'".format(alhash)
        result = self.select(query, fetchone=False)
        tags = []
        if result:
            for r in result:
                tags.append({'key': r[0], 'value': r[1]})
        return tags

    def log_alert(self, al):
        LOGGER.info("Logging alert")
        envir = None
        host = None
        for tag in al.tags:
            if tag['key'] == 'Environment':
                envir = tag['value']
            if tag['key'] == 'host':
                host = tag['value']
        query = ("INSERT OR IGNORE INTO alert_log(hash, time, id, "
                 "message, previouslevel, level, environment, host, duration, "
                 "pagerduty, jira) VALUES( ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
        values = (al.alhash, al.time, al.id, al.message, al.previouslevel,
                  al.level, envir, host, al.duration, al.pd_incident_key,
                  al.jira_issue)
        self.execute_query(query, values)

    def get_log_count_interval(self):
        # LOGGER.info("Getting alert occurences from alert log")
        now = int(time.time())
        query = ("select hash, id, environment, count(*) as num, "
                 "max(diff) as diff "
                 "from (select l.hash, l.id, l.environment, "
                 "l.time - (select max(i_l.time) "
                 "from alert_log i_l where i_l.time < l.time and "
                 "i_l.id = l.id and i_l.time >= {tlimit} and "
                 "i_l.previouslevel = 'OK' and i_l.level != 'OK') as diff "
                 "from alert_log l where l.time >= {tlimit}  and "
                 "l.previouslevel = 'OK' and l.level != 'OK') "
                 "group by id;".format(tlimit=now - (self.flapping_window * 60)))
        result = self.select(query, fetchone=False)
        if result:
            return result
        return []

    def get_statistics(self, hours):
        tm = int(time.time() - hours * 3600)
        query = "select id, previouslevel, environment, avg(duration), " + \
            "count(*) from alert_log where level = 'OK' and " + \
            "time >= {} group by id, level, environment".format(tm)
        result = self.select(query, fetchone=False)
        if result:
            return result
        return []

    def get_log_records(self, hours, environment=None):
        tm = int(time.time() - hours * 3600)
        query = "select time, id, previouslevel, level, environment " + \
            " from alert_log where time >= {} order by time desc".format(tm)
        if environment:
            query = ("select time, id, previouslevel, level, environment "
                     "from alert_log where time >= {} and environment = '{}' "
                     "order by time desc".format(tm, environment))
        result = self.select(query, fetchone=False)
        if result:
            return result
        return []

    def get_alert_summary(self, hours=1):
        tm = int(time.time() - hours * 3600)
        query = ("select environment, count(*) "
                 "from alert_log where time >= {} and level != 'OK' "
                 "group by environment".format(tm))
        result = self.select(query, fetchone=False)
        if result:
            return result
        return []

    def is_flapping(self, al):
        query = "SELECT 1 FROM flapping_alerts where hash = '{}'".format(
            al.alhash)
        res = self.select(query)
        if res:
            return True
        return False

    def get_flapping_alerts(self):
        # LOGGER.info("Get all alerts marked as flapping")
        query = "select hash, id, time, quarantine, modified " + \
            "from flapping_alerts"
        result = self.select(query, fetchone=False)
        if result:
            return result
        return []

    def set_flapping(self, alhash, alid, environment, interval):
        LOGGER.info("Setting flapping on %s", alid)
        now = int(time.time())
        quarantine = int(interval * 1.2)
        query = "INSERT INTO flapping_alerts (hash, id, environment, " + \
            "time, quarantine, modified) VALUES (?, ?, ?, ?, ?, ?)"
        values = (alhash, alid, environment, now, quarantine, now)
        self.execute_query(query, values)

    def update_flapping(self, alhash, interval):
        LOGGER.debug("Updating flapping quarantine interval")
        now = int(time.time())
        quarantine = int(interval * 1.2)
        query = "UPDATE flapping_alerts set quarantine = ?, modified = ? " + \
            "where hash = ?"
        values = (quarantine, now, alhash)
        self.execute_query(query, values)

    def unset_flapping(self, alhash, alid):
        LOGGER.info("Unsetting flapping on %s", alid)
        query = "DELETE FROM flapping_alerts where hash = '{}'".format(alhash)
        self.execute_query(query)

    def activate_maintenance(self, key, value, duration, comment):
        LOGGER.info("Activate maintenance on %s %s for %s",
                    key, value, duration)
        duration_secs = {'m': 60, 'h': 3600, 'd': 86400, 'w': 604800}
        start = int(time.time())
        stop = int(start + (int(duration[:-1]) * duration_secs[duration[-1]]))
        query = "INSERT  INTO active_maintenance " + \
            "(start, stop, key, value, comment) VALUES (?, ?, ?, ?, ?)"
        values = (start, stop, key, value, comment)
        self.execute_query(query, values)

    def deactive_maintenance(self, start, stop, key, value):
        LOGGER.info("Deactivate maintenance on %s %s", key, value)
        query = ("DELETE FROM active_maintenance where "
                 "start = {start} and stop = {stop} and key = '{key}' "
                 "and value = '{value}'".format(
                     start=start, stop=stop, key=key, value=value))
        self.execute_query(query)

    def get_active_maintenance_rules(self):
        # LOGGER.info("Get maintenance rules")
        mrules = []
        query = "select start, stop, key, value, comment " + \
            "from active_maintenance"
        result = self.select(query, fetchone=False)
        if result:
            for r in result:
                mrules.append({'start': r[0], 'stop': r[1],
                               'key': r[2], 'value': r[3],
                               'comment': r[4]})
        if mrules:
            tmp = mrules
            for i, mr in enumerate(mrules):
                if not mr['start'] <= int(time.time()) <= mr['stop']:
                    del tmp[i]
                    self.deactive_maintenance(mr['start'], mr['stop'],
                                              mr['key'], mr['value'])
            mrules = tmp
        return mrules

    def add_maintenance_schedule(self, starttime, duration,
                                 key, value, comment, repeat, days):
        LOGGER.info("Add maintenance schedule for %s %s", key, value)
        schedule_id = int(time.time() * 10**7)  # python 3.7 use time.time_ns()
        days = [(schedule_id, day, 0) for day in days]
        query = ("INSERT INTO maintenance_schedule (schedule_id, "
                 "starttime, duration, key, value, comment, repeat) VALUES ("
                 "?, ?, ?, ?, ?, ?, ?)")
        values = (schedule_id, starttime, duration,
                  key, value, comment, repeat)
        if self.execute_query(query, values):
            query = ("INSERT INTO maintenance_schedule_days "
                     "(schedule_id, day, runcounter) VALUES (?, ?, ?)")
            self.execute_many(query, days)

    def get_maintenance_schedule(self):
        result = self.select(
            "SELECT * from maintenance_schedule", fetchone=False)
        schedule = []
        if result:
            for r in result:
                sched = {'schedule_id': r[0], 'starttime': r[1],
                         'duration': r[2], 'key': r[3], 'value': r[4],
                         'comment': r[5], 'repeat': bool(r[6])}
                sched['days'] = self.get_schedule_days(r[0])
                schedule.append(sched)
        return schedule

    def get_schedule_days(self, schedule_id):
        query = "select day from maintenance_schedule_days " + \
            "where schedule_id = %d" % schedule_id
        result = self.select(query, fetchone=False)
        if result:
            return [x[0] for x in result]
        return []

    def get_schedule_runcounter(self, schedule_id):
        query = "select runcounter from maintenance_schedule_days " + \
            "where schedule_id = %d" % schedule_id
        result = self.select(query, fetchone=False)
        if result:
            return [x[0] for x in result]
        return []

    def update_day_runcounter(self, schedule_id, day):
        query = "update maintenance_schedule_days " + \
            "set runcounter = runcounter + 1 " + \
            "where schedule_id = ? and day = ?"
        values = (schedule_id, day)
        self.execute_query(query, values)

    def delete_maintenance_schedule(self, schedule_id):
        LOGGER.info("Deleting maintenance schedule")
        query = "DELETE FROM maintenance_schedule " + \
            "WHERE schedule_id = %d" % schedule_id
        self.execute_query(query)

    def get_aws_instance_info(self):
        query = "SELECT host, environment, state " + \
            "from aws_instances"
        result = self.select(query, fetchone=False)
        if result:
            return result
        return []

    def insert_aws_instance_info(self, info):
        query = "INSERT INTO aws_instances (host, environment, state) " + \
            "VALUES(?, ?, ?)"
        rows = self.execute_many(query, info)
        LOGGER.debug("Inserted %d instance records", rows)

    def update_aws_instance_info(self, info):
        host_last = []
        for x in info:
            host_last.append(x[1:] + x[:1])
        query = "UPDATE aws_instances set environment = ?, state = ? " + \
            "where host = ?"
        rows = self.execute_many(query, host_last)
        LOGGER.debug("Updated %d instance records", rows)

    def delete_aws_instance_info(self, info):
        instances = [[x[0]] for x in info]
        query = "DELETE from aws_instances where host = ?"
        rows = self.execute_many(query, instances)
        LOGGER.debug("Deleted %d instance records", rows)


CREATE_TABLES_SQL = '''

-- DROP TABLE IF EXISTS active_alerts;
-- DROP TABLE IF EXISTS active_alert_tags;
-- DROP TRIGGER IF EXISTS delete_active_alert_tags;

CREATE TABLE IF NOT EXISTS active_alerts(hash TEXT PRIMARY KEY,
time INTEGER, id TEXT, message TEXT, previouslevel TEXT,
level TEXT, duration INTEGER, pagerduty TEXT,
jira TEXT, grafana TEXT, state_duration INTEGER, sent INTEGER);

CREATE TABLE IF NOT EXISTS active_alert_tags(hash TEXT,
key TEXT, value TEXT,
UNIQUE(hash, key, value)
FOREIGN KEY (hash) REFERENCES active_alerts(hash));

CREATE TABLE IF NOT EXISTS flapping_alerts
(hash TEXT PRIMARY KEY, id TEXT, environment TEXT, time INTEGER,
quarantine INTEGER, modified INTEGER);

CREATE TABLE IF NOT EXISTS active_maintenance
(start INTEGER, stop INTEGER, key TEXT, value TEXT, comment TEXT);

CREATE TABLE IF NOT EXISTS maintenance_schedule
(schedule_id INTEGER PRIMARY KEY,
starttime TEXT, duration TEXT, key TEXT, value TEXT, comment TEXT,
repeat INTEGER);

CREATE TABLE IF NOT EXISTS maintenance_schedule_days
(schedule_id INTEGER, day INTEGER, runcounter INTEGER,
FOREIGN KEY (schedule_id) REFERENCES maintenance_schedule(schedule_id));

CREATE TABLE IF NOT EXISTS alert_log(hash TEXT, time INTEGER, id TEXT,
message TEXT, environment TEXT, host TEXT, previouslevel TEXT, level TEXT,
duration INTEGER, pagerduty TEXT, jira TEXT,
UNIQUE (hash, time));

CREATE TABLE IF NOT EXISTS aws_instances
(host TEXT PRIMARY KEY, environment TEXT, state INTEGER,
modified default CURRENT_TIMESTAMP);

CREATE TRIGGER IF NOT EXISTS delete_active_alert_tags
AFTER DELETE on active_alerts
BEGIN
DELETE FROM active_alert_tags where hash = OLD.hash;
END;

CREATE TRIGGER IF NOT EXISTS delete_maintenance_schedule_days
AFTER DELETE on maintenance_schedule
BEGIN
DELETE FROM maintenance_schedule_days where schedule_id = OLD.schedule_id;
END;

CREATE TRIGGER IF NOT EXISTS update_aws_instance_info_modified_time
AFTER UPDATE on aws_instances
BEGIN
UPDATE aws_instances set modified = CURRENT_TIMESTAMP where host = new.host;
END;
'''
