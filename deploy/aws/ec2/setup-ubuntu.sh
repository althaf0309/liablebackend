#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/liablebackend}"
APP_USER="${APP_USER:-ubuntu}"
REPO_URL="${REPO_URL:-https://github.com/althaf0309/liablebackend.git}"

sudo apt update
sudo apt upgrade -y
sudo apt install -y \
  build-essential \
  certbot \
  git \
  libpq-dev \
  nginx \
  python3-certbot-nginx \
  python3-dev \
  python3-pip \
  python3-venv

sudo mkdir -p "$(dirname "$APP_DIR")"
sudo chown "$APP_USER:$APP_USER" "$(dirname "$APP_DIR")"

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Base EC2 setup complete."
echo "Next:"
echo "1. Copy deploy/aws/ec2/env.production.ec2.example to $APP_DIR/.env and edit secrets."
echo "2. Run: bash deploy/aws/ec2/install-service.sh"
