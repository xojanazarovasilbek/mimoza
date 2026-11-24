from django.core.management.base import BaseCommand

from mimoza.payments import expire_pending_payments


class Command(BaseCommand):
    help = 'Expire unpaid online payment attempts and release reserved stock.'

    def handle(self, *args, **options):
        count = expire_pending_payments()
        self.stdout.write(self.style.SUCCESS(f'Expired {count} payment attempt(s).'))
