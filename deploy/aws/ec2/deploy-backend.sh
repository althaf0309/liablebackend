#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/liablebackend}"

cd "$APP_DIR"
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart liablebackend
sudo systemctl status liablebackend --no-pager
