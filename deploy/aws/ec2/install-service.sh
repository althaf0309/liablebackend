#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/liablebackend}"
DOMAIN="${DOMAIN:-api.liablegroupservices.com}"

if [ ! -f "$APP_DIR/.env" ]; then
  echo "Missing $APP_DIR/.env"
  echo "Copy deploy/aws/ec2/env.production.ec2.example to $APP_DIR/.env and edit it first."
  exit 1
fi

sudo cp "$APP_DIR/deploy/aws/ec2/liablebackend.service" /etc/systemd/system/liablebackend.service
sudo systemctl daemon-reload
sudo systemctl enable liablebackend

cd "$APP_DIR"
source venv/bin/activate
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput

sudo systemctl restart liablebackend

sudo sed "s/api.liablegroupservices.com/$DOMAIN/g" \
  "$APP_DIR/deploy/aws/ec2/nginx-liablebackend.conf" | sudo tee /etc/nginx/sites-available/liablebackend >/dev/null

if [ ! -L /etc/nginx/sites-enabled/liablebackend ]; then
  sudo ln -s /etc/nginx/sites-available/liablebackend /etc/nginx/sites-enabled/liablebackend
fi

sudo nginx -t
sudo systemctl restart nginx

echo "Service and Nginx installed."
echo "Test: curl http://$DOMAIN/api/core/health/"
echo "For HTTPS run: sudo certbot --nginx -d $DOMAIN"
