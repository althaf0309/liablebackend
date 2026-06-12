import logging
import os

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import StudentDocument

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete document files whose retained_until date has passed and are not yet purged."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()

        qs = StudentDocument.objects.filter(
            retained_until__lt=now,
            purged_at__isnull=True,
        ).select_related("user")

        total = qs.count()
        if total == 0:
            self.stdout.write("No documents ready for purge.")
            return

        self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}Found {total} document(s) ready for purge.")

        purged = 0
        failed = 0

        for doc in qs.iterator():
            try:
                if not dry_run:
                    # Delete the physical file if it exists
                    if doc.file and doc.file.name:
                        try:
                            doc.file.delete(save=False)
                        except Exception:
                            logger.warning("Could not delete file for document %s", doc.id)

                    doc.purged_at = now
                    doc.save(update_fields=["purged_at"])

                purged += 1
                logger.info(
                    "Purged document %s (type=%s, user=%s)",
                    doc.id,
                    doc.document_type,
                    doc.user_id,
                )
            except Exception:
                failed += 1
                logger.exception("Failed to purge document %s", doc.id)

        verb = "Would purge" if dry_run else "Purged"
        self.stdout.write(self.style.SUCCESS(f"{verb} {purged} document(s). Failed: {failed}."))
