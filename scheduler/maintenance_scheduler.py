"""
Module: maintenace_scheduler

Created: 24.Sep.2018
Created by: Morten Hersson, <morten@escenic.com>

Copyright (c) 2018 Morten Hersson
"""
import os
import sys
import time
import signal
import logging
import logging.handlers

LOGGER = logging.getLogger(__name__)


class MaintenanceScheduler():
    def __init__(self):
        super(MaintenanceScheduler, self).__init__()
        self._installdir = os.path.dirname(os.path.abspath(__file__))
        self._logfile = os.path.join(self._installdir, os.pardir,
                                     "logs/maintenace_scheduler.log")

    @staticmethod
    def _sigterm_handler(signum, frame):
        """Simple sigterm handler"""
        LOGGER.info('Received sigterm (%d) - program terminating', signum)
        sys.exit()

    def _setup_logging(self, loglevel=logging.INFO):
        """Configures logging, rolling file appender and console stream"""
        LOGGER.setLevel(logging.DEBUG)
        file_handler = logging.handlers.RotatingFileHandler(self._logfile, 'a',
                                                            2000000, 5)
        file_handler.setLevel(loglevel)
        formatter = logging.Formatter("%(asctime)s - %(module)s.%(funcName)s:"
                                      "%(lineno)d:%(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        LOGGER.addHandler(file_handler)

    def run(self):
        try:
            self._setup_logging()
            signal.signal(signal.SIGTERM, self._sigterm_handler)
            while True:
                time.sleep(30)
        except (KeyboardInterrupt, SystemExit):
            LOGGER.info("Program exit")


if __name__ == '__main__':
    APP = MaintenanceScheduler()
    APP.run()
