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

Verify the worker stack:

```bash
sudo systemctl status redis-server --no-pager
sudo systemctl status celery-worker celery-beat --no-pager
sudo journalctl -u celery-worker -n 80 --no-pager
```

The `.env` file must point Celery at Redis:

```bash
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

## Malware Scanner

Install ClamAV before enabling real private document uploads:

```bash
sudo apt-get install -y clamav clamav-daemon
sudo freshclam
clamscan --version
```

Production `.env`:

```bash
MALWARE_SCAN_REQUIRED=true
MALWARE_SCAN_COMMAND=clamscan --no-summary
MALWARE_SCAN_TIMEOUT=30
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

## Restore Test

Run the restore test against a disposable PostgreSQL database, never production:

```bash
chmod +x deploy/aws/ec2/restore-test.sh
export RESTORE_DATABASE_URL=postgres://liable_restore:password@restore-db.example.com:5432/liable_restore
export BACKUP_S3_URI=s3://liable-backups/db-backups/liable_backup_YYYY-MM-DD_HH-MM-SS.dump
bash deploy/aws/ec2/restore-test.sh
```

After success, record the backup filename, restore database, operator, and timestamp in the operational log.

## Logs

```bash
sudo journalctl -u liablebackend -f
sudo journalctl -u celery-worker -f
sudo journalctl -u celery-beat -f
sudo tail -f /var/log/liable/backup.log
sudo tail -f /var/log/nginx/error.log
```
