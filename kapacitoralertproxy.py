#!/usr/bin/env python
# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: kapacitoralertproxy.py

Created: 27.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''
from app import app


if __name__ == '__main__':
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(host=app.config['SERVER_ADDRESS'], port=app.config['SERVER_PORT'],
            debug=False, threaded=True)
