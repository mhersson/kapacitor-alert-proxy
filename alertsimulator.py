import time
import requests

json_body = {"id": "test.host test",
             "message": "This is a generated test message, please ignore",
             "duration": 60,
             "level": "CRITICAL",
             "previousLevel": "OK",
             "time": time.strftime("2018-05-31T12:04:30"),
             "data": {"series": [{"tags": {'Environment': 'test',
                                  "host": 'collector.test.borsen.cue.cloud'}}]}}

requests.post(url="http://localhost:9095/kap/alert", json=json_body)
