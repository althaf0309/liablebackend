from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from accounts.models import User

class Command(BaseCommand):
    help = "Create Verifier group with permissions to approve/reject users."

    def handle(self, *args, **kwargs):
        group, _ = Group.objects.get_or_create(name="Verifier")
        ct = ContentType.objects.get_for_model(User)
        perms = Permission.objects.filter(content_type=ct, codename__in=["view_user", "change_user"])
        group.permissions.add(*perms)
        group.save()
        self.stdout.write(self.style.SUCCESS("✅ Verifier group created/updated"))
