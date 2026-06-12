# EC2 Backend Deployment

This folder is for deploying `liablebackend` on Ubuntu EC2.

## First Server Setup

```bash
export REPO_URL=https://github.com/althaf0309/liablebackend.git
export APP_DIR=/var/www/liablebackend
bash deploy/aws/ec2/setup-ubuntu.sh
```

Create the production env file:

```bash
cp deploy/aws/ec2/env.production.ec2.example .env
nano .env
```

Install systemd + Nginx:

```bash
export DOMAIN=api.liablegroupservices.com
bash deploy/aws/ec2/install-service.sh
```

Enable HTTPS:

```bash
sudo certbot --nginx -d api.liablegroupservices.com
```

## Later Deploys

```bash
bash deploy/aws/ec2/deploy-backend.sh
```

## Redis + Celery Setup

Install Redis on the server:

```bash
sudo apt-get install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

Install and enable Celery worker + beat as systemd services:

```bash
sudo cp deploy/aws/ec2/celery-worker.service /etc/systemd/system/
sudo cp deploy/aws/ec2/celery-beat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable celery-worker celery-beat
sudo systemctl start celery-worker celery-beat
sudo mkdir -p /var/log/liable
sudo chown ubuntu:ubuntu /var/log/liable
```

## Automated Backup Cron

```bash
chmod +x deploy/aws/ec2/backup.sh
# Add to crontab (runs at 02:00 UTC daily):
(crontab -l 2>/dev/null; echo "0 2 * * * /home/ubuntu/liablewebsite/deploy/aws/ec2/backup.sh >> /var/log/liable/backup.log 2>&1") | crontab -
```

Ensure these env vars are set in `.env`:
- `AWS_ACCESS_KEY_ID` — IAM key with S3 write access
- `AWS_SECRET_ACCESS_KEY`
- `BACKUP_S3_BUCKET` — separate bucket from document storage recommended
- `BACKUP_LAST_SUCCESS_AT` — updated automatically by backup.sh after each success

## Logs

```bash
sudo journalctl -u liablebackend -f
sudo journalctl -u celery-worker -f
sudo journalctl -u celery-beat -f
sudo tail -f /var/log/liable/backup.log
sudo tail -f /var/log/nginx/error.log
```
