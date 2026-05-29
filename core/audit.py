from .models import AuditLog


def write_audit_log(request, action, target=None, metadata=None):
    target_type = target.__class__.__name__ if target is not None else ""
    target_id = str(getattr(target, "id", "")) if target is not None else ""
    actor = getattr(request, "user", None)
    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata or {},
    )

