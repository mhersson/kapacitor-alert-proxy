# Kapacitor-Alert-Proxy

## README


## Features
* Set instances or groups of instances in maintenance
* Schedule maintenance in advance, and repeat on regular intervals
* Supports multiple targets Slack, PagerDuty, Jira and KAOS
* Configurable per target. e.g continue sending to Slack, while stop sending to PagerDuty.
* Exclude alerts on tags or alert id
* Write status logs and status to Influxdb
* Show links to Grafana in the alert message from the exact time the alert occured


## KAOS
Running multiple instances of KAP
Take a look at KAOS: https://gitlab.com/mhersson/kaos

Kapacitor Alert Overview System, consolidate alert statuses from multiple KAP instances into one overview


## Install
Clone repo and install the requirements `pip install -r requirements.txt`
Edit `config.py`. Defaults should be fine just to get started,
but KAP won't forward anything before targets are enabled.
Start KAP by running the `python kapacitoralertproxy.py`.

Configure your kapacitor tick scripts or topic handlers to use the  `post` handler,
aim it at `http://localhost:9095/kap/alert`

Example topic handler
```
topic:   MyAlerts
id:      my-alerts-to-kap
kind:    post
options:
  url:   http://localhost:9095/kap/alert
```

Navigate your browser to `http://localhost:9095/kap/maintenance`
Duration has to be set using this format: `<number>[d|h|m|w]`

There is also a status page showing current active alerts
`http://localhost:9095/kap/status`

and a statistics page
`http://localhost:9095/kap/statistics`

