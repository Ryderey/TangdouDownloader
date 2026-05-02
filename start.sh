#!/bin/bash
cd "/home/ryl/script/tangdou-web"
source .venv/bin/activate
exec .venv/bin/gunicorn     --bind "0.0.0.0:18080"     --workers 2     --timeout 300     --access-logfile "/home/ryl/script/tangdou-web/logs/access.log"     --error-logfile "/home/ryl/script/tangdou-web/logs/error.log"     wsgi:app
