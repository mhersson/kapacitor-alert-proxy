import sys
import requests
from datetime import datetime


if len(sys.argv) < 3:
    print("Needs two params, plevel and level")
    sys.exit(1)
plevel = sys.argv[1].upper()
level = sys.argv[2].upper()
duration = 0
if len(sys.argv) >= 4:
    duration = int(sys.argv[3]) * 1000**3

json_body = {"id": "test.host mytest",
             "message": "This is a generated test message, please ignore",
             "duration": duration,
             "level": level,
             "previousLevel": plevel,
             "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
             "data": {"series": [{"tags": {'Environment': 'test',
                                  "host": 'test.host'}}]}}

requests.post(url="http://localhost:9095/kap/alert", json=json_body)
