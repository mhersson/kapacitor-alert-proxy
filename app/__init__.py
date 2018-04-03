# pylint: disable=C0413
# vim:set shiftwidth=4 softtabstop=4 expandtab:
import os
import logging
import logging.handlers
from flask import Flask

from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']

INSTALLDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          os.path.pardir)

LOGGER = logging.getLogger(name="KAP")
_file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(INSTALLDIR, "logs", "kapacitoralertproxy.log"),
    'a', 2000000, 5)
_formatter = logging.Formatter("%(asctime)s - %(module)s.%(funcName)s:"
                               "%(lineno)d:%(levelname)s - %(message)s")
_file_handler.setFormatter(_formatter)
LOGGER.addHandler(_file_handler)
LOGGER.setLevel(logging.DEBUG)

from app import routes  # noqa
