import secrets

import firebase_admin
from firebase_admin import exceptions, messaging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from mimoza.models import MobilePushMessage, StaffProfile


class Command(BaseCommand):
    help = 'Send queued mobile push notifications using Firebase credentials.'

    def handle(self, *args, **options):
        try:
            app = firebase_admin.get_app()
        except ValueError:
            app = firebase_admin.initialize_app(options={'httpTimeout': 10})

        sent = 0
        failures = 0
        message_ids = MobilePushMessage.objects.filter(sent_at__isnull=True).order_by(
            'created_at', 'pk',
        ).values_list('pk', flat=True)
        for message_id in message_ids.iterator():
            with transaction.atomic():
                message = (
                    MobilePushMessage.objects.select_for_update()
                    .select_related('device__access_token__user')
                    .filter(pk=message_id, sent_at__isnull=True)
                    .first()
                )
                if message is None:
                    continue
                device = message.device
                access = device.access_token
                user = access.user
                if (
                    not user.is_active
                    or access.expires_at <= timezone.now()
                    or not secrets.compare_digest(access.auth_hash, user.get_session_auth_hash())
                ):
                    device.delete()
                    continue
                if message.kind == MobilePushMessage.Kind.ADMIN:
                    allowed = user.is_staff and (
                        user.is_superuser or StaffProfile.objects.filter(
                            user=user, is_active_worker=True,
                            role__in=(StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER),
                        ).exists()
                    )
                    if not allowed:
                        message.delete()
                        continue
                try:
                    messaging.send(
                        messaging.Message(
                            token=device.registration_token,
                            notification=messaging.Notification(title=message.title, body=message.body),
                        ),
                        app=app,
                    )
                except messaging.UnregisteredError:
                    device.delete()
                    continue
                except exceptions.FirebaseError as error:
                    failures += 1
                    self.stderr.write(f'Firebase xabarni yubora olmadi: {error.code}')
                    continue
                message.sent_at = timezone.now()
                message.save(update_fields=['sent_at'])
                sent += 1
        self.stdout.write(f'{sent} ta mobil bildirishnoma yuborildi.')
        if failures:
            raise CommandError(f'{failures} ta bildirishnoma yuborilmadi; keyin qayta uriniladi.')
