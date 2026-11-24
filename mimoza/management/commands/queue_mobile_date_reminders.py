from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from mimoza.management.commands.send_important_date_reminders import reminder_date_filter
from mimoza.mobile_notifications import queue_mobile_notification
from mimoza.models import ImportantDate


class Command(BaseCommand):
    help = 'Queue mobile important-date reminders two days in advance.'

    def handle(self, *args, **options):
        reminder_date = timezone.localdate() + timedelta(days=2)
        candidates = ImportantDate.objects.filter(
            reminder_date_filter(reminder_date),
            reminder_enabled=True,
            customer__user__isnull=False,
        ).exclude(last_mobile_reminded_for=reminder_date).values_list('pk', flat=True)
        queued = 0
        for date_id in candidates.iterator():
            with transaction.atomic():
                important_date = (
                    ImportantDate.objects.select_for_update()
                    .select_related('customer__user')
                    .filter(pk=date_id, reminder_enabled=True)
                    .first()
                )
                if important_date is None or important_date.last_mobile_reminded_for == reminder_date:
                    continue
                count = queue_mobile_notification(
                    important_date.customer.user,
                    'Muhim sana yaqinlashmoqda',
                    'Muhim sanangizga ikki kun qoldi.',
                )
                if count:
                    important_date.last_mobile_reminded_for = reminder_date
                    important_date.save(update_fields=['last_mobile_reminded_for'])
                    queued += count
        self.stdout.write(f'{queued} ta mobil eslatma navbatga qo‘shildi.')
