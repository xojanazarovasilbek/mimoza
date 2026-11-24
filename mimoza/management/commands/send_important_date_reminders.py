import calendar
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from mimoza.models import ImportantDate
from mimoza.push_notifications import send_push_notification


def reminder_date_filter(reminder_date):
    date_filter = Q(date__month=reminder_date.month, date__day=reminder_date.day)
    if (
        reminder_date.month == 2
        and reminder_date.day == 28
        and not calendar.isleap(reminder_date.year)
    ):
        date_filter |= Q(date__month=2, date__day=29)
    return date_filter


class Command(BaseCommand):
    help = 'Send annual important-date push reminders two days in advance.'

    def handle(self, *args, **options):
        reminder_date = timezone.localdate() + timedelta(days=2)
        date_filter = reminder_date_filter(reminder_date)

        candidates = ImportantDate.objects.filter(
            date_filter,
            reminder_enabled=True,
            customer__user__isnull=False,
        ).exclude(last_reminded_for=reminder_date).values_list('pk', flat=True)

        sent = 0
        skipped = 0
        for date_id in candidates.iterator():
            with transaction.atomic():
                important_date = (
                    ImportantDate.objects.select_for_update()
                    .select_related('customer__user')
                    .filter(pk=date_id, reminder_enabled=True)
                    .first()
                )
                if important_date is None or important_date.last_reminded_for == reminder_date:
                    continue
                delivered_count = send_push_notification(
                    important_date.customer.user,
                    'Muhim sana yaqinlashmoqda',
                    f'{important_date.label} sanasiga ikki kun qoldi.',
                    '/account/',
                )
                if delivered_count:
                    important_date.last_reminded_for = reminder_date
                    important_date.save(update_fields=['last_reminded_for'])
                    sent += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'{reminder_date}: {sent} ta eslatma yuborildi, {skipped} ta push qurilmasi topilmagani uchun yuborilmadi.'
        ))
