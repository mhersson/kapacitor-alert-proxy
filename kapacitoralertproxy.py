#!/usr/bin/env python
# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: kapacitoralertproxy.py

Created: 27.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''
from app import app
from app.dbcontroller import DBController
from app.tasks import MaintenanceScheduler, KAOS, FlapDetective
from apscheduler.schedulers.background import BackgroundScheduler


if __name__ == '__main__':
    DBController().create_tables()
    scheduler = BackgroundScheduler()
    ms = MaintenanceScheduler()
    scheduler.add_job(ms.run, 'interval', seconds=60)
    if app.config['FLAPPING_DETECTION_ENABLED']:
        fp = FlapDetective()
        scheduler.add_job(fp.run, 'interval', seconds=60)
    if app.config['KAOS_ENABLED']:
        kaos = KAOS()
        scheduler.add_job(kaos.run, 'interval', seconds=30)
    scheduler.start()
    app.run(host=app.config['SERVER_ADDRESS'], port=app.config['SERVER_PORT'],
            debug=False, threaded=True)
    scheduler.shutdown()
