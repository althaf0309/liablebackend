#!/usr/bin/env bash
# Daily PostgreSQL backup → S3
# Cron: 0 2 * * * /home/ubuntu/liablewebsite/deploy/aws/ec2/backup.sh >> /var/log/liable/backup.log 2>&1

set -euo pipefail

ENV_FILE="/home/ubuntu/liablewebsite/.env"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S UTC')] BACKUP"

if [ ! -f "$ENV_FILE" ]; then
  echo "$LOG_PREFIX ERROR: .env not found at $ENV_FILE"
  exit 1
fi

# Load env vars
set -a
source "$ENV_FILE"
set +a

# Required vars
: "${DATABASE_URL:?DATABASE_URL must be set in .env}"
: "${AWS_STORAGE_BUCKET_NAME:?AWS_STORAGE_BUCKET_NAME must be set in .env}"
: "${AWS_S3_REGION_NAME:=eu-west-2}"

BACKUP_BUCKET="${BACKUP_S3_BUCKET:-$AWS_STORAGE_BUCKET_NAME}"
BACKUP_PREFIX="${BACKUP_S3_PREFIX:-db-backups}"
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
FILENAME="liable_backup_${TIMESTAMP}.dump"
TMPFILE="/tmp/${FILENAME}"

echo "$LOG_PREFIX Starting backup → s3://$BACKUP_BUCKET/$BACKUP_PREFIX/$FILENAME"

# pg_dump in custom format (compressed)
pg_dump --format=custom --no-password "$DATABASE_URL" -f "$TMPFILE"

# Upload to S3
aws s3 cp "$TMPFILE" "s3://$BACKUP_BUCKET/$BACKUP_PREFIX/$FILENAME" \
  --region "$AWS_S3_REGION_NAME" \
  --sse AES256

# Clean up local temp file
rm -f "$TMPFILE"

# Write success timestamp so monitoring endpoint can verify
TIMESTAMP_ISO=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
sed -i "s|^BACKUP_LAST_SUCCESS_AT=.*|BACKUP_LAST_SUCCESS_AT=$TIMESTAMP_ISO|" "$ENV_FILE" || \
  echo "BACKUP_LAST_SUCCESS_AT=$TIMESTAMP_ISO" >> "$ENV_FILE"

echo "$LOG_PREFIX SUCCESS: $FILENAME uploaded. Timestamp: $TIMESTAMP_ISO"

# Retain only last 30 backups in S3
echo "$LOG_PREFIX Pruning backups older than 30 days..."
aws s3 ls "s3://$BACKUP_BUCKET/$BACKUP_PREFIX/" --region "$AWS_S3_REGION_NAME" | \
  awk '{print $4}' | sort | head -n -30 | \
  xargs -I{} aws s3 rm "s3://$BACKUP_BUCKET/$BACKUP_PREFIX/{}" --region "$AWS_S3_REGION_NAME" || true

echo "$LOG_PREFIX Done."
