#!/usr/bin/env bash
# ESPHomeCLI AddOn entrypoint - options are in /data/options.json, app reads them
exec uvicorn main:app --host 0.0.0.0 --port 8099
