import json
from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from firebase_admin import exceptions
from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Customer, ImportantDate, MobileAccessToken, MobilePushDevice, MobilePushMessage,
    Order, StaffProfile,
)


class MobilePushTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='customer', password='test-password')
        self.customer = Customer.objects.create(user=self.user, name='Customer', phone='123')
        self.access = MobileAccessToken.objects.create(
            user=self.user, token_hash='a' * 64, auth_hash=self.user.get_session_auth_hash(),
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.device = MobilePushDevice.objects.create(
            access_token=self.access, registration_token='customer-device',
        )
        self.admin = User.objects.create_user(
            username='manager', password='test-password', is_staff=True,
        )
        StaffProfile.objects.create(user=self.admin, role=StaffProfile.Role.MANAGER)
        admin_access = MobileAccessToken.objects.create(
            user=self.admin, token_hash='b' * 64, auth_hash=self.admin.get_session_auth_hash(),
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.admin_device = MobilePushDevice.objects.create(
            access_token=admin_access, registration_token='admin-device',
        )

    def test_status_and_confirmed_payment_queue_correct_recipients_once(self):
        order = Order.objects.create(
            customer=self.customer, customer_name='Customer', phone='123',
            payment_method=Order.Payment.CLICK, payment_status=Order.PaymentStatus.PENDING,
        )
        self.assertFalse(MobilePushMessage.objects.exists())
        order.payment_status = Order.PaymentStatus.PAID
        order.save(update_fields=['payment_status'])
        self.assertEqual(MobilePushMessage.objects.filter(device=self.device).count(), 1)
        self.assertEqual(MobilePushMessage.objects.filter(device=self.admin_device).count(), 1)
        order.save(update_fields=['payment_status'])
        self.assertEqual(MobilePushMessage.objects.count(), 2)
        order.status = Order.Status.PROCESSING
        order.save(update_fields=['status'])
        self.assertEqual(MobilePushMessage.objects.filter(device=self.device).count(), 2)
        self.assertEqual(MobilePushMessage.objects.filter(device=self.admin_device).count(), 1)

    def test_device_registration_transfers_token_and_logout_removes_it(self):
        login = self.client.post(
            reverse('api_mobile_login'),
            data=json.dumps({'username': self.user.username, 'password': 'test-password'}),
            content_type='application/json',
        )
        auth = {'HTTP_AUTHORIZATION': f"Bearer {login.json()['access_token']}"}
        url = reverse('api_mobile_push_device')
        self.assertEqual(self.client.post(
            url, data=json.dumps({'token': 'customer-device'}), content_type='application/json', **auth,
        ).status_code, 200)
        self.assertFalse(MobilePushDevice.objects.filter(pk=self.device.pk).exists())
        self.assertEqual(MobilePushDevice.objects.filter(registration_token='customer-device').count(), 1)
        self.assertEqual(self.client.post(
            reverse('api_mobile_logout'), data='{}', content_type='application/json', **auth,
        ).status_code, 200)
        self.assertFalse(MobilePushDevice.objects.filter(registration_token='customer-device').exists())

    @patch('mimoza.management.commands.queue_mobile_date_reminders.timezone.localdate')
    def test_mobile_reminder_is_independent_of_web_and_queued_once(self, localdate):
        localdate.return_value = date(2026, 6, 10)
        important_date = ImportantDate.objects.create(
            customer=self.customer, label='Private', date=date(2000, 6, 12),
            last_reminded_for=date(2026, 6, 12),
        )
        call_command('queue_mobile_date_reminders', stdout=StringIO())
        call_command('queue_mobile_date_reminders', stdout=StringIO())
        important_date.refresh_from_db()
        self.assertEqual(important_date.last_mobile_reminded_for, date(2026, 6, 12))
        message = MobilePushMessage.objects.get(device=self.device)
        self.assertNotIn('Private', message.body)

    @patch('mimoza.management.commands.send_mobile_push.messaging.send')
    @patch('mimoza.management.commands.send_mobile_push.firebase_admin.get_app')
    def test_worker_sends_once_and_skips_revoked_admin(self, get_app, send):
        customer_message = MobilePushMessage.objects.create(
            device=self.device, kind=MobilePushMessage.Kind.CUSTOMER, title='Test', body='Text',
        )
        MobilePushMessage.objects.create(
            device=self.admin_device, kind=MobilePushMessage.Kind.ADMIN, title='Admin', body='Text',
        )
        StaffProfile.objects.filter(user=self.admin).update(is_active_worker=False)
        call_command('send_mobile_push', stdout=StringIO())
        call_command('send_mobile_push', stdout=StringIO())
        customer_message.refresh_from_db()
        self.assertIsNotNone(customer_message.sent_at)
        self.assertEqual(send.call_count, 1)
        self.assertFalse(MobilePushMessage.objects.filter(device=self.admin_device).exists())

    @patch('mimoza.management.commands.send_mobile_push.messaging.send')
    @patch('mimoza.management.commands.send_mobile_push.firebase_admin.get_app')
    def test_worker_keeps_failed_message_and_sends_other_devices(self, get_app, send):
        first = MobilePushMessage.objects.create(
            device=self.device, kind=MobilePushMessage.Kind.CUSTOMER, title='Test', body='Text',
        )
        second = MobilePushMessage.objects.create(
            device=self.admin_device, kind=MobilePushMessage.Kind.ADMIN, title='Test', body='Text',
        )
        send.side_effect = [exceptions.UnavailableError('temporary'), 'success']
        with self.assertRaises(CommandError):
            call_command('send_mobile_push', stdout=StringIO(), stderr=StringIO())
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.sent_at)
        self.assertIsNotNone(second.sent_at)
