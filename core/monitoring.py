import os
import shutil
from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from .models import AuditLog


def _check(name, status, message, severity="info", details=None):
    return {
        "name": name,
        "status": status,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def _parse_datetime(value):
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone=datetime_timezone.utc)
    return parsed


def _database_check():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:
        return _check("Database", "error", "Database connectivity failed.", "critical", {"error": str(exc)})
    return _check("Database", "ok", "Database connectivity is healthy.")


def _migration_check():
    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    except Exception as exc:
        return _check("Migrations", "error", "Migration state could not be checked.", "critical", {"error": str(exc)})
    if plan:
        return _check(
            "Migrations",
            "warning",
            "Pending migrations detected.",
            "high",
            {"pending_count": len(plan)},
        )
    return _check("Migrations", "ok", "No pending migrations detected.")


def _sentry_check():
    configured = bool(getattr(settings, "SENTRY_DSN", ""))
    if configured:
        return _check(
            "Error Tracking",
            "ok",
            "Sentry DSN is configured for backend exception capture.",
            details={
                "environment": os.getenv("SENTRY_ENVIRONMENT", "production" if not settings.DEBUG else "development"),
                "release": os.getenv("SENTRY_RELEASE", ""),
            },
        )
    return _check(
        "Error Tracking",
        "warning",
        "SENTRY_DSN is not configured. Exceptions will only appear in server logs.",
        "high",
    )


def _security_check():
    warnings = []
    if settings.DEBUG:
        warnings.append("DJANGO_DEBUG is enabled.")
    if not settings.SESSION_COOKIE_SECURE:
        warnings.append("SESSION_COOKIE_SECURE is disabled.")
    if not settings.CSRF_COOKIE_SECURE:
        warnings.append("CSRF_COOKIE_SECURE is disabled.")
    if settings.SECURE_HSTS_SECONDS <= 0:
        warnings.append("HSTS is disabled.")
    if warnings:
        return _check("Security Flags", "warning", "Production security flags need review.", "high", {"warnings": warnings})
    return _check("Security Flags", "ok", "Core HTTPS cookie and HSTS flags are enabled.")


def _backup_check():
    raw_value = os.getenv("BACKUP_LAST_SUCCESS_AT", "").strip()
    threshold_hours = int(os.getenv("BACKUP_STALE_AFTER_HOURS", "30"))
    parsed = _parse_datetime(raw_value)
    if not parsed:
        return _check(
            "Backups",
            "warning",
            "BACKUP_LAST_SUCCESS_AT is not set. Backup freshness cannot be confirmed.",
            "high",
            {"env_var": "BACKUP_LAST_SUCCESS_AT"},
        )
    age_hours = (timezone.now() - parsed).total_seconds() / 3600
    if age_hours > threshold_hours:
        return _check(
            "Backups",
            "warning",
            "Last successful backup is stale.",
            "high",
            {"last_success_at": parsed.isoformat(), "age_hours": round(age_hours, 2), "threshold_hours": threshold_hours},
        )
    return _check(
        "Backups",
        "ok",
        "Backup freshness marker is within the expected window.",
        details={"last_success_at": parsed.isoformat(), "age_hours": round(age_hours, 2)},
    )


def _disk_check():
    target = getattr(settings, "PRIVATE_MEDIA_ROOT", settings.BASE_DIR)
    try:
        usage = shutil.disk_usage(target)
    except Exception as exc:
        return _check("Disk Space", "warning", "Disk usage could not be checked.", "medium", {"error": str(exc)})
    free_percent = round((usage.free / usage.total) * 100, 2) if usage.total else 0
    details = {
        "path": str(target),
        "free_percent": free_percent,
        "total_gb": round(usage.total / (1024 ** 3), 2),
        "free_gb": round(usage.free / (1024 ** 3), 2),
    }
    if free_percent < 10:
        return _check("Disk Space", "error", "Disk free space is critically low.", "critical", details)
    if free_percent < 20:
        return _check("Disk Space", "warning", "Disk free space is below the warning threshold.", "medium", details)
    return _check("Disk Space", "ok", "Disk free space is healthy.", details=details)


def _audit_activity():
    now = timezone.now()
    last_24h = now - timezone.timedelta(hours=24)
    last_7d = now - timezone.timedelta(days=7)
    latest = AuditLog.objects.order_by("-created_at").first()
    return {
        "last_24h": AuditLog.objects.filter(created_at__gte=last_24h).count(),
        "last_7d": AuditLog.objects.filter(created_at__gte=last_7d).count(),
        "latest_action": latest.action if latest else "",
        "latest_at": latest.created_at.isoformat() if latest else None,
    }


def build_production_monitoring_status():
    checks = [
        _database_check(),
        _migration_check(),
        _sentry_check(),
        _security_check(),
        _backup_check(),
        _disk_check(),
    ]
    if any(item["status"] == "error" for item in checks):
        overall = "error"
    elif any(item["status"] == "warning" for item in checks):
        overall = "warning"
    else:
        overall = "ok"

    return {
        "generated_at": timezone.now().isoformat(),
        "overall_status": overall,
        "checks": checks,
        "audit_activity": _audit_activity(),
        "runtime": {
            "debug": settings.DEBUG,
            "database_engine": settings.DATABASES["default"]["ENGINE"],
            "allowed_hosts_count": len(settings.ALLOWED_HOSTS),
            "sentry_configured": bool(getattr(settings, "SENTRY_DSN", "")),
            "private_storage": "s3" if getattr(settings, "USE_S3_PRIVATE_STORAGE", False) else "local",
        },
    }
