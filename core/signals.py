import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="core.HousingApplication")
def create_lifecycle_record_on_application(sender, instance, created, **kwargs):
    """Auto-create a LifecycleRecord at INQUIRY when a HousingApplication is created."""
    if not created:
        return
    try:
        from core.models import LifecycleRecord, LifecycleStage
        if not LifecycleRecord.objects.filter(application=instance).exists():
            LifecycleRecord.objects.create(
                student=instance.user,
                current_stage=LifecycleStage.INQUIRY,
                application=instance,
            )
    except Exception:
        logger.exception("Failed to create LifecycleRecord for application %s", instance.id)
