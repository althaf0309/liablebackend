from django.core.management.base import BaseCommand

from core.assist import process_due_assist_reminders


class Command(BaseCommand):
    help = "Process all due AssistReminder records and fire student notifications."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many reminders are due without processing them.",
        )

    def handle(self, *args, **options):
        from django.utils import timezone
        from core.models import AssistReminder, AssistReminderStatus

        now = timezone.now()
        due_count = AssistReminder.objects.filter(
            status=AssistReminderStatus.SCHEDULED,
            due_at__lte=now,
        ).count()

        if options["dry_run"]:
            self.stdout.write(f"Dry run: {due_count} reminder(s) are due.")
            return

        processed = process_due_assist_reminders(now=now)
        self.stdout.write(
            self.style.SUCCESS(f"Processed {len(processed)} due assist reminder(s).")
        )
