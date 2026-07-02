#!/usr/bin/env bash
# Restore a selected backup into a non-production database and run Django checks.
# Usage:
#   RESTORE_DATABASE_URL=postgres://... BACKUP_S3_URI=s3://liable-backups/db-backups/file.dump bash deploy/aws/ec2/restore-test.sh

set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/liablebackend}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
LOG_PREFIX="[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] RESTORE_TEST"

if [ ! -f "$ENV_FILE" ]; then
  echo "$LOG_PREFIX ERROR: .env not found at $ENV_FILE"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL must point to a disposable restore-test database}"
: "${BACKUP_S3_URI:?BACKUP_S3_URI must point to a .dump backup in S3}"
: "${AWS_S3_REGION_NAME:=eu-west-2}"

TMPFILE="/tmp/liable_restore_test_$(date -u '+%Y%m%d_%H%M%S').dump"

echo "$LOG_PREFIX Downloading $BACKUP_S3_URI"
aws s3 cp "$BACKUP_S3_URI" "$TMPFILE" --region "$AWS_S3_REGION_NAME"

echo "$LOG_PREFIX Restoring into disposable database"
pg_restore --clean --if-exists --no-owner --no-privileges --dbname "$RESTORE_DATABASE_URL" "$TMPFILE"

echo "$LOG_PREFIX Running Django validation against restored database"
cd "$APP_DIR"
DATABASE_URL="$RESTORE_DATABASE_URL" "$APP_DIR/venv/bin/python" manage.py check
DATABASE_URL="$RESTORE_DATABASE_URL" "$APP_DIR/venv/bin/python" manage.py migrate --check

rm -f "$TMPFILE"
echo "$LOG_PREFIX SUCCESS: restore test completed"
