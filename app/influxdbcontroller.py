#!/usr/bin/env python
# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: influxcontroller.py

Created: 27.Dec.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''
import requests
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError

from app import app, LOGGER


class InfluxDBController():
    def __init__(self):
        super(InfluxDBController, self).__init__()
        self._db = InfluxDBClient(host=app.config['INFLUXDB_HOST'],
                                  port=app.config['INFLUXDB_PORT'],
                                  database='kap')

    @staticmethod
    def _influxify(al, alhash, measurement, zero_time=False):
        LOGGER.debug("Creating InfluxDB json data")
        # Used to count currently active alerts
        if zero_time:
            LOGGER.debug("Creating zero time data")
            try:
                env = [tag['value'] for tag in al.tags
                       if tag['key'] == 'Environment'][0]
            except KeyError:
                env = None
            if env == ['']:
                env = None
            json_body = {
                "measurement": measurement,
                "tags": {
                    "hash": alhash,
                    "Environment": env},
                "fields": {
                    "level": al.level,
                    "id": al.id},
                "time": 0
            }
        else:
            json_body = {
                "measurement": measurement,
                "tags": {
                    "id": al.id,
                    "level": al.level,
                    "previousLevel": al.previouslevel},
                "fields": {
                    "id": al.id,
                    "duration": al.duration,
                    "message": al.message}
            }
            tags = json_body['tags']
            for t in al.tags:
                tags[t['key']] = t['value']
            json_body['tags'] = tags

        return json_body

    def update(self, al):
        if app.config['INFLUXDB_ENABLED'] is True:
            LOGGER.info("Updating InfluxDB")
            if al.level != al.previouslevel:
                self._update_db(self._influxify(al, al.alhash, "logs"))
                if al.level == 'OK':
                    self.delete_active(al)
                else:
                    self._update_db(self._influxify(
                        al, al.alhash, "active", True))
            else:
                self._update_db(self._influxify(al, al.alhash, "active", True))

    def _update_db(self, data):
        LOGGER.debug("Running insert or update")
        try:
            self._db.write_points([data])
        except InfluxDBClientError as err:
            LOGGER.error("Error(%s) - %s", err.code, err.content)
        except requests.ConnectionError as err:
            LOGGER.error(err)

    def delete_active(self, al):
        if app.config['INFLUXDB_ENABLED'] is True:
            LOGGER.debug("Running delete series")
            try:
                self._db.delete_series(measurement="active",
                                       tags={"hash": al.alhash})
            except InfluxDBClientError as err:
                LOGGER.error("Error(%s) - %s", err.code, err.content)
