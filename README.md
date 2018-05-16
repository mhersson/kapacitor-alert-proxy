# Kapacitor-Alert-Proxy

## README


## Goals
* Add the ability to set instances or groups of instances in maintenance
* Configurable per target. e.g continue sending to Slack, while stop sending to PagerDuty.
* Support multiple targets, first priority is Slack, PagerDuty and Jira


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
Duration has to be set using this format: `<number>[d|h|m]`

There is also a status page showing current active alerts
`http://localhost:9095/kap/status`

and a statistics page
`http://localhost:9095/kap/statistics`
