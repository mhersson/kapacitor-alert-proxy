import requests
import argparse
from datetime import datetime


def run(args):
    duration = int(args.duration) * 1000**3

    json_body = {"id": args.hostname + " " + args.test,
                 "message": "This is a generated test message, please ignore",
                 "duration": duration,
                 "level": args.level.upper(),
                 "previousLevel": args.plevel.upper(),
                 "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                 "data": {"series": [{"tags": {'Environment': args.environ,
                                               "host": args.hostname}}]}}

    requests.post(url="http://localhost:9095/kap/alert", json=json_body)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", default="test.host", dest="hostname")
    parser.add_argument("-t", default="kap", dest="test")
    parser.add_argument("-l", default="critical", dest="level")
    parser.add_argument("-p", default="ok", dest="plevel")
    parser.add_argument("-e", default="test", dest="environ")
    parser.add_argument("-d", default=0, dest="duration", type=int)
    options = parser.parse_args()
    run(options)
