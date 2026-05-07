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

## Logs

```bash
sudo journalctl -u liablebackend -f
sudo tail -f /var/log/nginx/error.log
```
