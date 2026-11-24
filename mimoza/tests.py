import base64
import hashlib
import json
import tempfile
from datetime import date, timedelta
from io import BytesIO, StringIO
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from PIL import Image

from django.contrib.auth.models import Group, User

from .audit import reset_audit_actor, set_audit_actor
from .models import (
    AuditLog,
    Category,
    Customer,
    ImportantDate,
    MimozaSettings,
    MobileAccessToken,
    Order,
    OrderItem,
    PaymentTransaction,
    Product,
    ProductComment,
    ProductLike,
    PushSubscription,
    StaffProfile,
    Story,
)
from .push_notifications import send_push_notification


class StoreTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Romantika', slug='romantika')
        self.product = Product.objects.create(
            name='101 qizil atirgul',
            slug='101-qizil-atirgul',
            category=self.category,
            description='Hashamatli romantik buket',
            price=850000,
            in_stock=True,
            stock_quantity=20,
        )

    def test_catalog_lists_available_product(self):
        response = self.client.get(reverse('catalog'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '101 qizil atirgul')

    def test_home_shows_active_stories_and_expired_stories_are_hidden(self):
        active_story = Story.objects.create(
            title='Yangi gullar',
            image='stories/new-flowers.webp',
            product=self.product,
        )
        expired_story = Story.objects.create(
            title='Eski aksiya',
            image='stories/old-sale.webp',
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Yangi gullar')
        self.assertNotContains(response, 'Eski aksiya')
        self.assertContains(response, reverse('story_detail', args=[active_story.pk]))

        expired_response = self.client.get(reverse('story_detail', args=[expired_story.pk]))
        self.assertEqual(expired_response.status_code, 404)

    def test_reels_feed_lists_only_in_stock_products_with_videos(self):
        video_product = Product.objects.create(
            name='Video buket',
            slug='video-buket',
            category=self.category,
            price=700000,
            stock_quantity=2,
            video_url='https://cdn.example.com/video-buket.mp4',
        )
        Product.objects.create(
            name='Videosiz buket',
            slug='videosiz-buket',
            category=self.category,
            price=300000,
            stock_quantity=2,
        )

        response = self.client.get(reverse('reels'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, video_product.name)
        self.assertContains(response, video_product.video_url)
        self.assertNotContains(response, 'Videosiz buket')

    def test_guest_can_read_product_comments_but_must_sign_in_to_interact(self):
        response = self.client.get(reverse('product_detail', args=[self.product.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '♡ Yoqtirish uchun kiring')
        self.assertContains(response, 'Izoh qoldirish uchun')
        self.assertContains(response, '0 ta yoqtirish')

        like_response = self.client.post(reverse('product_like_toggle', args=[self.product.pk]))
        comment_response = self.client.post(
            reverse('product_comment_create', args=[self.product.pk]),
            {'text': 'Ajoyib gul'},
        )
        self.assertEqual(like_response.status_code, 302)
        self.assertEqual(comment_response.status_code, 302)
        self.assertEqual(ProductLike.objects.count(), 0)
        self.assertEqual(ProductComment.objects.count(), 0)

    def test_customer_can_like_and_unlike_product(self):
        user = User.objects.create_user(username='flower-fan', password='test-pass')
        self.client.force_login(user)

        like_url = reverse('product_like_toggle', args=[self.product.pk])
        response = self.client.post(like_url)
        self.assertRedirects(response, reverse('product_detail', args=[self.product.slug]))
        self.assertTrue(ProductLike.objects.filter(product=self.product, user=user).exists())
        self.assertContains(
            self.client.get(reverse('product_detail', args=[self.product.slug])),
            '1 ta yoqtirish',
        )

        self.client.post(like_url)
        self.assertFalse(ProductLike.objects.filter(product=self.product, user=user).exists())
        self.assertEqual(ProductLike.objects.count(), 0)

    def test_registration_returns_to_product_page_for_like_or_comment(self):
        product_url = reverse('product_detail', args=[self.product.slug])
        response = self.client.post(
            f"{reverse('account_register')}?next={product_url}",
            {
                'username': 'new-reviewer',
                'full_name': 'Yangi Mijoz',
                'phone': '+998901112233',
                'email': '',
                'password1': 'FloralGarden!2048',
                'password2': 'FloralGarden!2048',
            },
        )
        self.assertRedirects(response, product_url)
        self.assertTrue(User.objects.filter(username='new-reviewer').exists())

    def test_customer_can_comment_and_invalid_comments_show_errors(self):
        user = User.objects.create_user(username='flower-reviewer', password='test-pass')
        self.client.force_login(user)
        comment_url = reverse('product_comment_create', args=[self.product.pk])

        response = self.client.post(comment_url, {'text': '  Juda chiroyli buket  '}, follow=True)
        self.assertContains(response, 'Izohingiz qo‘shildi')
        self.assertContains(response, 'Juda chiroyli buket')
        comment = ProductComment.objects.get()
        self.assertEqual(comment.user, user)
        self.assertEqual(comment.text, 'Juda chiroyli buket')

        response = self.client.post(comment_url, {'text': '   '}, follow=True)
        self.assertContains(response, 'Izoh matnini kiriting')
        self.assertEqual(ProductComment.objects.count(), 1)

        response = self.client.post(comment_url, {'text': 'x' * 1001}, follow=True)
        self.assertContains(response, '1000 ta belgidan oshmasligi kerak')
        self.assertEqual(ProductComment.objects.count(), 1)

    def test_contact_page_shows_phone_social_accounts_and_map(self):
        response = self.client.get(reverse('contact'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, settings.CONTACT_PHONE)
        self.assertContains(response, 'tel:+998992228808')
        self.assertContains(response, settings.INSTAGRAM_CONTACT_URL)
        self.assertContains(response, f'@{settings.INSTAGRAM_CONTACT_USERNAME}')
        self.assertContains(response, settings.TELEGRAM_CONTACT_URL)
        self.assertContains(response, 'https://www.google.com/maps/place/AlmazMed/')
        self.assertContains(response, 'https://maps.google.com/maps?q=41.2720768,69.2320628')

        home_response = self.client.get(reverse('home'))
        self.assertContains(home_response, reverse('contact'))

    def test_checkout_asks_about_delivery_after_accepting_order(self):
        user = User.objects.create_user(username='delivery-customer', password='test-pass')
        self.client.force_login(user)
        session = self.client.session
        session['cart'] = {str(self.product.pk): 1}
        session.save()

        response = self.client.get(reverse('checkout'))
        self.assertNotContains(response, 'Yetkazib berish kerakmi?')
        self.assertNotContains(response, 'delivery_required')
        self.assertNotContains(response, 'delivery-map')

    def test_cart_and_checkout_require_customer_account(self):
        guest_add = self.client.post(reverse('cart_add', args=[self.product.id]), {'next': 'cart'})
        self.assertRedirects(
            guest_add,
            f"{reverse('account_login')}?next={reverse('cart_add', args=[self.product.id])}",
        )
        self.assertNotIn(str(self.product.id), self.client.session.get('cart', {}))

        user = User.objects.create_user(username='store-customer', password='test-pass')
        Customer.objects.create(user=user, name='Test mijoz', phone='+998901234567')
        self.client.force_login(user)

        add = self.client.post(reverse('cart_add', args=[self.product.id]), {'next': 'cart'})
        self.assertRedirects(add, reverse('cart'))
        cart = self.client.get(reverse('cart'))
        self.assertContains(cart, '101 qizil atirgul')

        order_data = {
            'customer_name': 'Test mijoz',
            'phone': '+998901234567',
            'delivery_required': 'yes',
            'card_message': 'Tabriklaymiz',
            'web_payment_key': '11111111-1111-4111-8111-111111111111',
        }
        failed_payment = self.client.post(
            reverse('checkout'),
            {**order_data, 'payment_method': 'click'},
        )
        self.assertContains(failed_payment, 'hali ulanmagan', status_code=409)
        self.assertEqual(Order.objects.count(), 0)

        checkout = self.client.post(
            reverse('checkout'),
            {**order_data, 'payment_method': 'cash'},
        )
        self.assertContains(checkout, 'hali ulanmagan', status_code=409)
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 20)
        self.assertTrue(self.product.in_stock)
        self.assertEqual(self.client.session['cart'][str(self.product.pk)], 1)

    def test_checkout_does_not_decrement_stock_while_payment_is_unavailable(self):
        self.product.stock_quantity = 2
        self.product.save(update_fields=['stock_quantity'])
        user = User.objects.create_user(username='quantity-customer', password='test-pass')
        self.client.force_login(user)
        session = self.client.session
        session['cart'] = {str(self.product.pk): 2}
        session.save()

        response = self.client.post(reverse('checkout'), {
            'customer_name': 'Mijoz',
            'phone': '+998901234567',
            'delivery_required': 'yes',
            'payment_method': 'cash',
            'web_payment_key': '11111111-1111-4111-8111-111111111111',
        })

        self.assertContains(response, 'hali ulanmagan', status_code=409)
        self.assertFalse(Order.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 2)
        self.assertTrue(self.product.in_stock)

    def test_checkout_with_insufficient_stock_creates_no_order_or_partial_deduction(self):
        second_product = Product.objects.create(
            name='Oq atirgul',
            slug='oq-atirgul',
            category=self.category,
            price=500000,
            in_stock=True,
            stock_quantity=1,
        )
        user = User.objects.create_user(username='insufficient-stock', password='test-pass')
        self.client.force_login(user)
        session = self.client.session
        session['cart'] = {
            str(self.product.pk): 1,
            str(second_product.pk): 2,
        }
        session.save()

        response = self.client.post(reverse('checkout'), {
            'customer_name': 'Mijoz',
            'phone': '+998901234567',
            'delivery_required': 'yes',
            'payment_method': 'cash',
            'web_payment_key': '11111111-1111-4111-8111-111111111111',
        })

        self.assertContains(response, 'hali ulanmagan', status_code=409)
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        second_product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 20)
        self.assertEqual(second_product.stock_quantity, 1)
        self.assertEqual(self.client.session['cart'][str(self.product.pk)], 1)

    def test_pickup_order_does_not_show_telegram_location_prompt(self):
        user = User.objects.create_user(username='pickup-customer', password='test-pass')
        self.client.force_login(user)
        customer = Customer.objects.create(user=user, name='Olib ketuvchi', phone='+998901234567')
        order = Order.objects.create(customer=customer, customer_name=customer.name, phone=customer.phone)
        response = self.client.post(
            reverse('order_delivery_choice', args=[order.pk]),
            {'delivery_required': 'no'},
        )
        self.assertContains(response, 'do‘kondan olib ketishingiz mumkin')
        self.assertNotContains(response, settings.TELEGRAM_CONTACT_URL)
        order.refresh_from_db()
        self.assertFalse(order.delivery_required)

    def test_existing_order_delivery_shows_telegram_details(self):
        user = User.objects.create_user(username='delivery-existing', password='test-pass')
        customer = Customer.objects.create(user=user, name='Mijoz', phone='+998901234567')
        order = Order.objects.create(customer=customer, customer_name=customer.name, phone=customer.phone)
        OrderItem.objects.create(order=order, product=self.product, quantity=1, price=self.product.price)
        self.client.force_login(user)
        response = self.client.post(reverse('order_delivery_choice', args=[order.pk]), {'delivery_required': 'yes'})
        self.assertContains(response, settings.TELEGRAM_CONTACT_URL)
        telegram_message = parse_qs(urlsplit(response.context['telegram_order_url']).query)['text'][0]
        self.assertIn(f'5 xonali kod: {order.order_code}', telegram_message)
        self.assertIn(f'Gul №{self.product.pk}', telegram_message)
        order.refresh_from_db()
        self.assertTrue(order.delivery_required)

    def test_checkout_displays_exact_advance_and_remaining(self):
        user = User.objects.create_user(username='missing-choice', password='test-pass')
        self.client.force_login(user)
        session = self.client.session
        session['cart'] = {str(self.product.pk): 1}
        session.save()

        self.product.price = 1
        self.product.save(update_fields=['price'])
        response = self.client.get(reverse('checkout'))
        self.assertContains(response, 'Oldindan 30%')
        self.assertEqual(str(response.context['advance']), '0.30')
        self.assertEqual(str(response.context['remaining']), '0.70')
        self.assertFalse(Order.objects.exists())

    def test_orders_receive_different_five_digit_codes(self):
        first = Order.objects.create(customer_name='Birinchi', phone='998901111111', address='')
        second = Order.objects.create(customer_name='Ikkinchi', phone='998902222222', address='')
        self.assertRegex(first.order_code, r'^\d{5}$')
        self.assertRegex(second.order_code, r'^\d{5}$')
        self.assertNotEqual(first.order_code, second.order_code)

    def test_order_code_generation_retries_on_collision(self):
        Order.objects.create(
            order_code='12345',
            customer_name='Mavjud buyurtma',
            phone='998901111111',
            address='',
        )
        with patch('mimoza.models.generate_order_code', side_effect=('12345', '12346')):
            order = Order.objects.create(
                customer_name='Yangi buyurtma',
                phone='998902222222',
                address='',
            )
        self.assertEqual(order.order_code, '12346')

    def test_delivery_choice_can_only_be_set_by_order_owner(self):
        owner = User.objects.create_user(username='delivery-owner', password='test-pass')
        other_user = User.objects.create_user(username='not-order-owner', password='test-pass')
        owner_customer = Customer.objects.create(
            user=owner,
            name='Buyurtma egasi',
            phone='998901111111',
        )
        order = Order.objects.create(
            customer=owner_customer,
            customer_name='Buyurtma egasi',
            phone='998901111111',
            address='',
        )

        self.client.force_login(other_user)
        private_qr = self.client.get(reverse('order_qr', args=[order.pk]))
        self.assertEqual(private_qr.status_code, 404)
        forbidden_order = self.client.post(
            reverse('order_delivery_choice', args=[order.pk]),
            {'delivery_required': 'yes'},
        )
        self.assertEqual(forbidden_order.status_code, 404)

        self.client.force_login(owner)
        qr_response = self.client.get(reverse('order_qr', args=[order.pk]))
        self.assertEqual(qr_response.status_code, 200)
        self.assertEqual(qr_response['Content-Type'], 'image/png')
        self.assertTrue(qr_response.content.startswith(b'\x89PNG\r\n\x1a\n'))
        invalid_choice = self.client.post(
            reverse('order_delivery_choice', args=[order.pk]),
            {'delivery_required': 'later'},
        )
        self.assertRedirects(invalid_choice, reverse('account'))
        order.refresh_from_db()
        self.assertIsNone(order.delivery_required)


class CrmTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Romantika', slug='romantika')
        self.product = Product.objects.create(
            name='Oq atirgul',
            slug='oq-atirgul',
            category=self.category,
            price=500000,
            stock_quantity=3,
        )
        self.staff = User.objects.create_user(username='manager', password='test-pass', is_staff=True)
        StaffProfile.objects.create(user=self.staff, role=StaffProfile.Role.MANAGER)
        self.client.login(username='manager', password='test-pass')

    def test_staff_can_view_crm_sections(self):
        for name in ('crm_dashboard', 'crm_orders', 'crm_products', 'crm_analytics'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_order_time_is_shown_on_crm_orders_and_dashboard(self):
        order = Order.objects.create(
            customer_name='Vaqti ko‘rinadigan mijoz',
            phone='998901234567',
            address='Toshkent',
        )
        order_time = timezone.localtime(order.created_at).strftime('%d.%m.%Y %H:%M')

        orders_response = self.client.get(reverse('crm_orders'))
        self.assertContains(orders_response, 'Buyurtma vaqti')
        self.assertContains(orders_response, order_time)

        dashboard_response = self.client.get(reverse('crm_dashboard'))
        self.assertContains(dashboard_response, 'Buyurtma vaqti')
        self.assertContains(dashboard_response, order_time)

    def test_mobile_card_fields_keep_order_and_stock_actions(self):
        order = Order.objects.create(
            customer_name='Mobil mijoz', phone='998901234567', address='Toshkent',
        )
        orders = self.client.get(reverse('crm_orders'))
        self.assertContains(orders, 'class="crm-card-table"')
        self.assertContains(orders, 'data-label="Mijoz">Mobil mijoz')
        self.assertContains(orders, f'Kod: {order.order_code}')
        self.assertContains(orders, reverse('crm_order_status', args=[order.pk]))
        self.assertContains(orders, reverse('crm_order_assignments', args=[order.pk]))

        products = self.client.get(reverse('crm_products'))
        self.assertContains(products, 'data-label="Mahsulot"')
        self.assertContains(products, reverse('crm_product_stock', args=[self.product.pk]))

    def test_manager_order_badge_counts_pending_orders_and_updates(self):
        Order.objects.create(customer_name='Yangi buyurtma 1', phone='998901111111', address='Toshkent')
        Order.objects.create(customer_name='Yangi buyurtma 2', phone='998902222222', address='Buxoro')
        Order.objects.create(
            customer_name='Tayyorlanmoqda',
            phone='998903333333',
            address='Samarqand',
            status=Order.Status.PROCESSING,
        )

        dashboard = self.client.get(reverse('crm_dashboard'))
        self.assertContains(dashboard, 'id="crm-order-count"')
        self.assertContains(dashboard, '>2</span>')

        notification = self.client.get(reverse('crm_order_notification_count'))
        self.assertEqual(notification.json(), {'count': 2})

    def test_staff_can_update_stock_and_order_status(self):
        stock_response = self.client.post(
            reverse('crm_product_stock', args=[self.product.pk]),
            {'stock_quantity': '0'},
        )
        self.assertRedirects(stock_response, reverse('crm_products'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)
        self.assertFalse(self.product.in_stock)

        order = Order.objects.create(customer_name='Mijoz', phone='998901234567', address='Toshkent')
        status_response = self.client.post(
            reverse('crm_order_status', args=[order.pk]),
            {'status': Order.Status.PROCESSING},
        )
        self.assertRedirects(status_response, reverse('crm_orders'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PROCESSING)
        stock_log = AuditLog.objects.filter(
            model_label='mimoza.Product',
            object_id=str(self.product.pk),
            action=AuditLog.Action.UPDATE,
        ).latest('id')
        self.assertEqual(stock_log.actor, self.staff)
        self.assertEqual(stock_log.changes['Ombordagi miqdor'], {'old': 3, 'new': 0})

    def test_staff_without_superuser_cannot_manage_staff_accounts(self):
        response = self.client.get(reverse('crm_users'))
        self.assertEqual(response.status_code, 403)

    def test_staff_without_role_cannot_open_crm(self):
        unassigned = User.objects.create_user(username='unassigned', password='test-pass', is_staff=True)
        self.client.force_login(unassigned)
        self.assertEqual(self.client.get(reverse('crm_orders')).status_code, 403)

    def test_superuser_can_view_staff_accounts(self):
        admin = User.objects.create_superuser(username='root', password='test-pass', email='root@example.com')
        StaffProfile.objects.filter(user=self.staff).update(phone='998901234567')
        self.client.logout()
        self.client.force_login(admin)
        response = self.client.get(reverse('crm_users'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'manager')

    def test_audit_history_is_limited_to_super_admin(self):
        AuditLog.objects.create(
            actor_username='manager',
            action=AuditLog.Action.UPDATE,
            model_label='mimoza.Product',
            object_id=str(self.product.pk),
            object_repr=self.product.name,
            changes={'Narxi': {'old': 10, 'new': 20}},
        )
        self.assertEqual(self.client.get(reverse('crm_audit_history')).status_code, 403)

        admin = User.objects.create_superuser(username='root', password='test-pass', email='root@example.com')
        self.client.force_login(admin)
        response = self.client.get(reverse('crm_audit_history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Harakatlar tarixi')
        self.assertContains(response, 'Oq atirgul')
        admin_response = self.client.get(reverse('admin:mimoza_auditlog_changelist'))
        self.assertEqual(admin_response.status_code, 200)
        self.assertFalse(admin_response.context['has_add_permission'])

    def test_audit_records_create_update_delete_and_redacts_sensitive_fields(self):
        token = set_audit_actor(self.staff)
        try:
            category = Category.objects.create(name='Audit category', slug='audit-category')
            category_id = category.pk
            category.name = 'Updated audit category'
            category.save(update_fields=['name'])
            category.delete()
        finally:
            reset_audit_actor(token)

        entries = AuditLog.objects.filter(
            model_label='mimoza.Category',
            object_id=str(category_id),
        ).order_by('id')
        self.assertEqual(
            list(entries.values_list('action', flat=True)),
            [AuditLog.Action.CREATE, AuditLog.Action.UPDATE, AuditLog.Action.DELETE],
        )
        update = entries[1]
        self.assertEqual(update.actor, self.staff)
        self.assertEqual(update.changes['name'], {'old': 'Audit category', 'new': 'Updated audit category'})

        secret_token = set_audit_actor(self.staff)
        try:
            MimozaSettings.objects.create(click_api_key='do-not-store-this')
        finally:
            reset_audit_actor(secret_token)
        settings_log = AuditLog.objects.get(model_label='mimoza.MimozaSettings')
        self.assertEqual(
            settings_log.changes['Click API kaliti'],
            {'old': None, 'new': '[maxfiy]'},
        )
        self.assertNotIn('do-not-store-this', str(settings_log.changes))

        password_token = set_audit_actor(self.staff)
        try:
            self.staff.set_password('new-password-value')
            self.staff.save(update_fields=['password'])
        finally:
            reset_audit_actor(password_token)
        user_logs = AuditLog.objects.filter(
            model_label='auth.User',
            object_id=str(self.staff.pk),
            action=AuditLog.Action.UPDATE,
        ).order_by('id')
        password_logs = [entry for entry in user_logs if 'parol' in entry.changes]
        self.assertTrue(password_logs, list(user_logs.values_list('changes', flat=True)))
        password_log = password_logs[-1]
        self.assertEqual(
            password_log.changes['parol'],
            {'old': '[maxfiy]', 'new': '[maxfiy]'},
        )
        self.assertNotIn('new-password-value', str(password_log.changes))

    def test_audit_records_staff_group_membership_changes(self):
        group = Group.objects.create(name='Audit group')
        token = set_audit_actor(self.staff)
        try:
            self.staff.groups.add(group)
        finally:
            reset_audit_actor(token)

        entry = AuditLog.objects.filter(
            model_label='auth.User',
            object_id=str(self.staff.pk),
            action=AuditLog.Action.UPDATE,
        ).latest('id')
        self.assertEqual(entry.actor, self.staff)
        self.assertEqual(entry.changes['groups'], {'old': [], 'new': [group.pk]})

    def test_florist_only_sees_assigned_orders_and_can_prepare_them(self):
        florist = User.objects.create_user(username='florist', password='test-pass', is_staff=True)
        StaffProfile.objects.create(user=florist, role=StaffProfile.Role.FLORIST)
        assigned = Order.objects.create(
            customer_name='Biriktirilgan mijoz',
            phone='998901111111',
            address='Toshkent',
            assigned_florist=florist,
        )
        Order.objects.create(customer_name='Boshqa mijoz', phone='998902222222', address='Buxoro')
        self.client.force_login(florist)

        response = self.client.get(reverse('crm_orders'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Biriktirilgan mijoz')
        self.assertNotContains(response, 'Boshqa mijoz')
        self.assertEqual(
            self.client.get(reverse('crm_order_notification_count')).json(),
            {'count': 1},
        )

        status_response = self.client.post(
            reverse('crm_order_status', args=[assigned.pk]),
            {'status': Order.Status.PROCESSING},
        )
        self.assertEqual(status_response.status_code, 302)
        assigned.refresh_from_db()
        self.assertEqual(assigned.status, Order.Status.PROCESSING)
        self.assertEqual(
            self.client.get(reverse('crm_order_notification_count')).json(),
            {'count': 0},
        )
        assigned.status = Order.Status.SHIPPED
        assigned.save(update_fields=['status'])
        reverted = self.client.post(
            reverse('crm_order_status', args=[assigned.pk]),
            {'status': Order.Status.PROCESSING},
        )
        self.assertEqual(reverted.status_code, 403)
        self.assertEqual(self.client.get(reverse('crm_analytics')).status_code, 403)

    def test_courier_can_only_advance_assigned_delivery(self):
        courier = User.objects.create_user(username='courier', password='test-pass', is_staff=True)
        StaffProfile.objects.create(user=courier, role=StaffProfile.Role.COURIER)
        assigned = Order.objects.create(
            customer_name='Yetkaziladigan mijoz',
            phone='998901111111',
            address='Toshkent',
            status=Order.Status.PROCESSING,
            assigned_courier=courier,
            total=900000,
        )
        Order.objects.create(customer_name='Boshqa mijoz', phone='998902222222', address='Buxoro')
        self.client.force_login(courier)

        response = self.client.get(reverse('crm_orders'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Yetkaziladigan mijoz')
        self.assertNotContains(response, 'Boshqa mijoz')
        self.assertNotContains(response, '900000')
        self.assertEqual(
            self.client.get(reverse('crm_order_notification_count')).json(),
            {'count': 1},
        )

        status_response = self.client.post(
            reverse('crm_order_status', args=[assigned.pk]),
            {'status': Order.Status.SHIPPED},
        )
        self.assertEqual(status_response.status_code, 302)
        assigned.refresh_from_db()
        self.assertEqual(assigned.status, Order.Status.SHIPPED)

        status_response = self.client.post(
            reverse('crm_order_status', args=[assigned.pk]),
            {'status': Order.Status.DELIVERED},
        )
        self.assertEqual(status_response.status_code, 302)
        assigned.refresh_from_db()
        self.assertEqual(assigned.status, Order.Status.DELIVERED)
        self.assertEqual(
            self.client.get(reverse('crm_order_notification_count')).json(),
            {'count': 0},
        )
        self.assertEqual(self.client.get(reverse('crm_analytics')).status_code, 403)

    def test_inactive_worker_cannot_open_crm(self):
        worker = User.objects.create_user(username='inactive', password='test-pass', is_staff=True)
        StaffProfile.objects.create(
            user=worker,
            role=StaffProfile.Role.COURIER,
            is_active_worker=False,
        )
        self.client.force_login(worker)
        self.assertEqual(self.client.get(reverse('crm_orders')).status_code, 403)

    def test_manager_can_assign_orders_to_active_florist_and_courier(self):
        florist = User.objects.create_user(username='worker-florist', password='test-pass', is_staff=True)
        courier = User.objects.create_user(username='worker-courier', password='test-pass', is_staff=True)
        StaffProfile.objects.create(user=florist, role=StaffProfile.Role.FLORIST)
        StaffProfile.objects.create(user=courier, role=StaffProfile.Role.COURIER)
        order = Order.objects.create(customer_name='Mijoz', phone='998901234567', address='Toshkent')

        response = self.client.post(
            reverse('crm_order_assignments', args=[order.pk]),
            {'florist_id': florist.pk, 'courier_id': courier.pk},
        )
        self.assertRedirects(response, reverse('crm_orders'))
        order.refresh_from_db()
        self.assertEqual(order.assigned_florist, florist)
        self.assertEqual(order.assigned_courier, courier)

    def test_shopkeeper_can_find_orders_by_qr_id_name_and_phone(self):
        shopkeeper = User.objects.create_user(username='shopkeeper', password='test-pass', is_staff=True)
        StaffProfile.objects.create(user=shopkeeper, role=StaffProfile.Role.SHOPKEEPER)
        order = Order.objects.create(
            customer_name='QR orqali topiladigan mijoz',
            phone='+998901234567',
            address='Toshkent',
        )
        flower = Product.objects.create(
            name='Maxsus lola',
            slug='maxsus-lola',
            category=self.category,
            price=150000,
            stock_quantity=3,
        )
        OrderItem.objects.create(order=order, product=flower, quantity=2, price=flower.price)
        self.client.force_login(shopkeeper)

        for query in (
            f'MIMOZA-ORDER:{order.qr_token.hex.upper()}',
            order.order_code,
            f'#{order.pk}',
            str(flower.pk),
            flower.name,
            'topiladigan mijoz',
            '998901234567',
        ):
            with self.subTest(query=query):
                response = self.client.get(reverse('crm_orders'), {'q': query})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, order.customer_name)
                self.assertContains(response, flower.name)
                self.assertNotContains(response, 'Boshqa mijoz')
                self.assertNotContains(response, f'{order.total} UZS')
                if query == order.order_code:
                    self.assertContains(response, f'Kod: {order.order_code}')
                    self.assertNotContains(response, order.qr_token.hex.upper())

        self.assertEqual(
            self.client.get(reverse('crm_order_notification_count')).json(),
            {'count': 1},
        )

    def test_shopkeeper_only_has_order_access_and_can_advance_order_statuses(self):
        shopkeeper = User.objects.create_user(username='order-desk', password='test-pass', is_staff=True)
        StaffProfile.objects.create(user=shopkeeper, role=StaffProfile.Role.SHOPKEEPER)
        order = Order.objects.create(customer_name='Status mijoz', phone='998901234567', address='')
        self.client.force_login(shopkeeper)

        for name in ('crm_dashboard', 'crm_products', 'crm_analytics', 'crm_users'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(
            self.client.get(reverse('crm_orders')).status_code,
            200,
        )

        for status in (
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        ):
            response = self.client.post(
                reverse('crm_order_status', args=[order.pk]),
                {'status': status},
            )
            self.assertRedirects(response, reverse('crm_orders'))
            order.refresh_from_db()
            self.assertEqual(order.status, status)

        rejected = self.client.post(
            reverse('crm_order_status', args=[order.pk]),
            {'status': Order.Status.PENDING},
        )
        self.assertEqual(rejected.status_code, 403)
        cancellable = Order.objects.create(
            customer_name='Bekor qilinadigan buyurtma',
            phone='998901111111',
            address='',
        )
        self.assertEqual(
            self.client.post(
                reverse('crm_order_status', args=[cancellable.pk]),
                {'status': Order.Status.CANCELLED},
            ).status_code,
            302,
        )
        cancellable.refresh_from_db()
        self.assertEqual(cancellable.status, Order.Status.CANCELLED)


class CustomerAccountTests(TestCase):
    def test_account_link_is_visible_and_guest_is_sent_to_login(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Hisob')
        account_response = self.client.get(reverse('account'))
        self.assertRedirects(
            account_response,
            f"{reverse('account_login')}?next={reverse('account')}",
        )

    def test_customer_can_register_and_view_personal_account(self):
        registration_page = self.client.get(reverse('account_register'))
        self.assertContains(registration_page, 'Foydalanuvchi nomi')
        self.assertContains(registration_page, 'Parolni tasdiqlang')
        self.assertContains(registration_page, 'Kamida 8 ta belgi')

        response = self.client.post(reverse('account_register'), {
            'username': 'mimoza_customer',
            'full_name': 'Dilnoza Karimova',
            'phone': '+998901112233',
            'email': 'dilnoza@example.com',
            'password1': 'FloralGarden!2048',
            'password2': 'FloralGarden!2048',
        })
        self.assertRedirects(response, reverse('account'))
        customer = Customer.objects.get(user__username='mimoza_customer')
        self.assertEqual(customer.phone, '+998901112233')
        self.assertContains(self.client.get(reverse('account')), 'Dilnoza')

    def test_registration_password_errors_are_in_uzbek(self):
        response = self.client.post(reverse('account_register'), {
            'username': 'mimoza_customer',
            'full_name': 'Dilnoza Karimova',
            'phone': '+998901112233',
            'password1': 'FloralGarden!2048',
            'password2': 'different',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kiritilgan parollar bir-biriga mos emas.')

        response = self.client.post(reverse('account_register'), {
            'username': 'mimoza_customer',
            'full_name': 'Dilnoza Karimova',
            'phone': '+998901112233',
            'password1': 'short',
            'password2': 'short',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Parol juda qisqa')

    def test_logged_in_customer_sees_only_own_orders(self):
        user = User.objects.create_user(username='account-holder', password='test-pass')
        customer = Customer.objects.create(user=user, name='Account Holder', phone='998901111111')
        own_order = Order.objects.create(
            customer=customer, customer_name='Receiver', phone='998902222222',
            address='Toshkent', total=500000,
        )
        Order.objects.create(customer_name='Boshqa mijoz', phone='998903333333', address='Buxoro')
        self.client.force_login(user)

        response = self.client.get(reverse('account'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'#{own_order.pk}')
        self.assertContains(
            response,
            timezone.localtime(own_order.created_at).strftime('%d.%m.%Y %H:%M'),
        )
        self.assertContains(response, reverse('order_qr', args=[own_order.pk]))
        self.assertNotContains(response, 'Boshqa mijoz')


class ImportantDateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='date-user', password='test-pass')
        self.customer = Customer.objects.create(
            user=self.user,
            name='Muhim mijoz',
            phone='998901234567',
        )
        self.client.force_login(self.user)

    def test_customer_can_add_and_delete_only_their_own_dates(self):
        response = self.client.post(reverse('important_date_create'), {
            'label': 'Tug‘ilgan kun',
            'date': '2000-07-14',
            'reminder_enabled': 'on',
        })
        self.assertRedirects(response, reverse('account'))
        important_date = ImportantDate.objects.get(customer=self.customer)
        self.assertEqual(important_date.date, date(2000, 7, 14))

        response = self.client.post(
            reverse('important_date_update', args=[important_date.pk]),
            {'label': 'Yangilangan sana', 'date': '2000-07-15'},
        )
        self.assertRedirects(response, reverse('account'))
        important_date.refresh_from_db()
        self.assertEqual(important_date.label, 'Yangilangan sana')
        self.assertEqual(important_date.date, date(2000, 7, 15))
        self.assertFalse(important_date.reminder_enabled)

        other_user = User.objects.create_user(username='other-date-user', password='test-pass')
        other_customer = Customer.objects.create(
            user=other_user,
            name='Boshqa mijoz',
            phone='998909876543',
        )
        other_date = ImportantDate.objects.create(
            customer=other_customer,
            label='Boshqa sana',
            date=date(2000, 8, 1),
        )
        response = self.client.post(
            reverse('important_date_delete', args=[other_date.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ImportantDate.objects.filter(pk=other_date.pk).exists())

        response = self.client.post(reverse('important_date_delete', args=[important_date.pk]))
        self.assertRedirects(response, reverse('account'))
        self.assertFalse(ImportantDate.objects.filter(pk=important_date.pk).exists())

    @override_settings(WEBPUSH_VAPID_PUBLIC_KEY='public', WEBPUSH_VAPID_PRIVATE_KEY='private',
                       WEBPUSH_VAPID_SUBJECT='mailto:shop@example.com')
    @patch('mimoza.management.commands.send_important_date_reminders.timezone.localdate')
    @patch('mimoza.management.commands.send_important_date_reminders.send_push_notification', return_value=1)
    def test_reminder_command_sends_once_and_records_only_success(self, send, localdate):
        today = date(2026, 6, 10)
        reminder_date = today + timedelta(days=2)
        localdate.return_value = today
        important_date = ImportantDate.objects.create(
            customer=self.customer,
            label='Yubiley',
            date=date(2000, 6, 12),
        )

        call_command('send_important_date_reminders')
        call_command('send_important_date_reminders')

        important_date.refresh_from_db()
        self.assertEqual(send.call_count, 1)
        self.assertEqual(important_date.last_reminded_for, reminder_date)

    @patch('mimoza.management.commands.send_important_date_reminders.timezone.localdate')
    @patch(
        'mimoza.management.commands.send_important_date_reminders.send_push_notification',
        side_effect=RuntimeError('Push service unavailable'),
    )
    def test_reminder_command_does_not_mark_failed_push_as_sent(self, send, localdate):
        today = date(2026, 6, 10)
        localdate.return_value = today
        important_date = ImportantDate.objects.create(
            customer=self.customer,
            label='Yubiley',
            date=date(2000, 6, 12),
        )

        with self.assertRaisesMessage(RuntimeError, 'Push service unavailable'):
            call_command('send_important_date_reminders')

        important_date.refresh_from_db()
        self.assertIsNone(important_date.last_reminded_for)

    @patch('mimoza.management.commands.send_important_date_reminders.timezone.localdate')
    @patch('mimoza.management.commands.send_important_date_reminders.send_push_notification', return_value=1)
    def test_leap_day_reminder_uses_february_28_in_non_leap_years(self, send, localdate):
        localdate.return_value = date(2025, 2, 26)
        important_date = ImportantDate.objects.create(
            customer=self.customer,
            label='Tug‘ilgan kun',
            date=date(2000, 2, 29),
        )

        call_command('send_important_date_reminders', stdout=StringIO())

        important_date.refresh_from_db()
        self.assertEqual(send.call_count, 1)
        self.assertEqual(important_date.last_reminded_for, date(2025, 2, 28))


class MediaPipelineTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Media', slug='media')

    def test_uploaded_product_images_are_saved_as_webp(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                image_bytes = BytesIO()
                Image.new('RGBA', (2, 2), (200, 30, 50, 128)).save(image_bytes, format='PNG')
                product = Product.objects.create(
                    name='WebP mahsulot',
                    slug='webp-mahsulot',
                    category=self.category,
                    price=1000,
                    image=SimpleUploadedFile('rose.png', image_bytes.getvalue(), content_type='image/png'),
                )
                product.refresh_from_db()
                self.assertTrue(product.image.name.endswith('.webp'))
                with default_storage.open(product.image.name, 'rb') as stored_image:
                    self.assertEqual(Image.open(stored_image).format, 'WEBP')

    def test_uploaded_story_images_are_saved_as_webp(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                image_bytes = BytesIO()
                Image.new('RGB', (2, 2), (200, 30, 50)).save(image_bytes, format='JPEG')
                story = Story.objects.create(
                    title='WebP story',
                    image=SimpleUploadedFile('story.jpg', image_bytes.getvalue(), content_type='image/jpeg'),
                )
                story.refresh_from_db()
                self.assertTrue(story.image.name.endswith('.webp'))
                with default_storage.open(story.image.name, 'rb') as stored_image:
                    self.assertEqual(Image.open(stored_image).format, 'WEBP')

    def test_hls_command_stores_playlist_and_segments(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                product = Product.objects.create(
                    name='HLS mahsulot',
                    slug='hls-mahsulot',
                    category=self.category,
                    price=1000,
                    video=SimpleUploadedFile('flower.mp4', b'fake video', content_type='video/mp4'),
                )

                def fake_ffmpeg(command, **kwargs):
                    playlist_path = command[-1]
                    segment_pattern = command[command.index('-hls_segment_filename') + 1]
                    segment_path = segment_pattern.replace('%05d', '00000')
                    with open(segment_path, 'w', encoding='utf-8') as segment:
                        segment.write('segment')
                    with open(playlist_path, 'w', encoding='utf-8') as playlist:
                        playlist.write('#EXTM3U\n#EXTINF:6.0,\nsegment00000.ts\n#EXT-X-ENDLIST\n')

                with patch('mimoza.management.commands.transcode_video_hls.subprocess.run', side_effect=fake_ffmpeg):
                    call_command('transcode_video_hls', 'product', product.pk)

                product.refresh_from_db()
                self.assertTrue(product.hls_playlist.name.endswith('/index.m3u8'))
                self.assertTrue(default_storage.exists(product.hls_playlist.name))
                segment_name = product.hls_playlist.name.rsplit('/', 1)[0] + '/segment00000.ts'
                self.assertTrue(default_storage.exists(segment_name))


class PaymentIntegrationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='To‘lov testi', slug='tolov-testi')
        self.product = Product.objects.create(
            name='Buket',
            slug='tolov-buketi',
            category=self.category,
            price=101,
            stock_quantity=4,
        )
        self.user = User.objects.create_user(username='payment-customer', password='test-pass')
        self.customer = Customer.objects.create(
            user=self.user,
            name='Mijoz',
            phone='+998901234567',
        )
        self.client.force_login(self.user)
        session = self.client.session
        session['cart'] = {str(self.product.pk): 2}
        session.save()

    def test_click_checkout_uses_exact_30_percent_and_authenticated_callbacks(self):
        with override_settings(
            DEBUG=True,
            CLICK_MERCHANT_ID='click-merchant',
            CLICK_SERVICE_ID='click-service',
            CLICK_SECRET_KEY='click-secret',
        ):
            response = self.client.post(reverse('checkout'), {
                'customer_name': self.customer.name,
                'phone': self.customer.phone,
                'address': '',
                'payment_method': 'click',
                'web_payment_key': '11111111-1111-4111-8111-111111111111',
            })
            self.assertEqual(response.status_code, 302)
            checkout = urlsplit(response['Location'])
            self.assertEqual(checkout.netloc, 'my.click.uz')
            self.assertEqual(parse_qs(checkout.query)['amount'], ['60.60'])

            duplicate = self.client.post(reverse('checkout'), {
                'customer_name': self.customer.name,
                'phone': self.customer.phone,
                'address': '',
                'payment_method': 'click',
                'web_payment_key': '11111111-1111-4111-8111-111111111111',
            })
            self.assertEqual(duplicate.status_code, 302)
            self.assertEqual(duplicate['Location'], response['Location'])
            self.assertEqual(Order.objects.count(), 1)

            order = Order.objects.get()
            payment = PaymentTransaction.objects.get(order=order)
            self.assertEqual(payment.amount_tiyin, 6060)
            self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
            self.product.refresh_from_db()
            self.assertEqual(self.product.stock_quantity, 2)

            click_id = 'click-tx-1'
            sign_time = '2026-06-12 12:00:00'
            prepare = {
                'click_trans_id': click_id,
                'service_id': 'click-service',
                'merchant_trans_id': str(order.pk),
                'amount': '60.60',
                'action': '0',
                'sign_time': sign_time,
            }
            prepare['sign_string'] = hashlib.md5(
                f'{click_id}click-serviceclick-secret{order.pk}60.600{sign_time}'.encode(),
            ).hexdigest()
            invalid_signature = {**prepare, 'sign_string': 'invalid'}
            self.assertEqual(
                self.client.post(
                    reverse('click_payment_callback'),
                    invalid_signature,
                ).json()['error'],
                -1,
            )
            wrong_amount = {**prepare, 'amount': '60.61'}
            wrong_amount['sign_string'] = hashlib.md5(
                f'{click_id}click-serviceclick-secret{order.pk}60.610{sign_time}'.encode(),
            ).hexdigest()
            self.assertEqual(
                self.client.post(
                    reverse('click_payment_callback'),
                    wrong_amount,
                ).json()['error'],
                -2,
            )
            prepared = self.client.post(reverse('click_payment_callback'), prepare)
            self.assertEqual(prepared.json()['error'], 0)
            self.assertEqual(prepared.json()['merchant_prepare_id'], str(payment.pk))

            complete = {
                **prepare,
                'action': '1',
                'merchant_prepare_id': str(payment.pk),
                'error': '0',
            }
            complete['sign_string'] = hashlib.md5(
                f'{click_id}click-serviceclick-secret{order.pk}{payment.pk}60.601{sign_time}'.encode(),
            ).hexdigest()
            confirmed = self.client.post(reverse('click_payment_callback'), complete)
            self.assertEqual(confirmed.json()['error'], 0)
            order.refresh_from_db()
            payment.refresh_from_db()
            self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
            self.assertEqual(payment.status, PaymentTransaction.Status.PAID)

    def test_payme_callbacks_authenticate_and_are_idempotent(self):
        with override_settings(
            DEBUG=True,
            PAYME_MERCHANT_ID='4056281',
            PAYME_MERCHANT_LOGIN='payme-login',
            PAYME_MERCHANT_KEY='payme-secret',
        ):
            provider_response = BytesIO(json.dumps({
                'response': {
                    'response_status': 'success',
                    'checkout_url': 'https://pay.payme.uz/checkout/test-token',
                },
            }).encode())
            with patch('mimoza.payments.urlopen', return_value=provider_response) as urlopen_mock:
                response = self.client.post(reverse('checkout'), {
                    'customer_name': self.customer.name,
                    'phone': self.customer.phone,
                    'address': '',
                    'payment_method': 'payme',
                    'web_payment_key': '11111111-1111-4111-8111-111111111111',
                })
            self.assertEqual(response.status_code, 302, response.content.decode())
            self.assertEqual(response['Location'], 'https://pay.payme.uz/checkout/test-token')
            provider_request = urlopen_mock.call_args.args[0]
            self.assertEqual(provider_request.full_url, 'https://pay.payme.uz/api/checkout/url')
            payload = json.loads(provider_request.data)['request']
            self.assertEqual(payload['amount'], 6060)
            self.assertEqual(payload['order_id'], str(Order.objects.get().pk))
            signed_values = ['payme-secret'] + [
                str(payload[key])
                for key in sorted(payload)
                if key != 'signature' and payload[key] not in ('', None)
            ]
            self.assertEqual(
                payload['signature'],
                hashlib.sha1('|'.join(signed_values).encode()).hexdigest(),
            )

            order = Order.objects.get()
            auth = 'Basic ' + base64.b64encode(b'payme-login:payme-secret').decode()

            def callback(method, params):
                return self.client.post(
                    reverse('payme_payment_callback'),
                    data=json.dumps({'jsonrpc': '2.0', 'id': 42, 'method': method, 'params': params}),
                    content_type='application/json',
                    HTTP_AUTHORIZATION=auth,
                ).json()

            params = {
                'id': 'payme-tx-1',
                'time': 1781265600000,
                'amount': 6060,
                'account': {'order_id': order.pk},
            }
            self.assertEqual(
                callback('CheckPerformTransaction', {**params, 'amount': 6061})['error']['code'],
                -31001,
            )
            self.assertTrue(callback('CheckPerformTransaction', params)['result']['allow'])
            created = callback('CreateTransaction', params)['result']
            self.assertEqual(created['state'], 1)
            performed = callback('PerformTransaction', {'id': params['id']})['result']
            self.assertEqual(performed['state'], 2)
            self.assertEqual(callback('PerformTransaction', {'id': params['id']})['result']['state'], 2)
            order.refresh_from_db()
            self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

            bad_auth = self.client.post(
                reverse('payme_payment_callback'),
                data=json.dumps({'id': 9, 'method': 'PerformTransaction', 'params': {'id': params['id']}}),
                content_type='application/json',
                HTTP_AUTHORIZATION='Basic invalid',
            )
            self.assertEqual(bad_auth.status_code, 200)
            self.assertEqual(bad_auth.json()['error']['code'], -32504)

    def test_expired_payment_restores_reserved_inventory_once(self):
        with override_settings(
            DEBUG=True,
            CLICK_MERCHANT_ID='click-merchant',
            CLICK_SERVICE_ID='click-service',
            CLICK_SECRET_KEY='click-secret',
        ):
            response = self.client.post(reverse('checkout'), {
                'customer_name': self.customer.name,
                'phone': self.customer.phone,
                'address': '',
                'payment_method': 'click',
                'web_payment_key': '11111111-1111-4111-8111-111111111111',
            })
            self.assertEqual(response.status_code, 302)
            order = Order.objects.get()
            payment = PaymentTransaction.objects.get(order=order)
            payment.expires_at = timezone.now() - timedelta(seconds=1)
            payment.save(update_fields=['expires_at'])

            call_command('expire_pending_payments')
            call_command('expire_pending_payments')

            payment.refresh_from_db()
            order.refresh_from_db()
            self.product.refresh_from_db()
            self.assertEqual(payment.status, PaymentTransaction.Status.EXPIRED)
            self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)
            self.assertEqual(self.product.stock_quantity, 4)


class MobileApiTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Romantika', slug='romantika')
        self.available = Product.objects.create(
            name='Qizil atirgul',
            slug='qizil-atirgul',
            category=self.category,
            price=250000,
            stock_quantity=4,
            image_url='https://cdn.example.test/rose.webp',
        )
        self.unavailable = Product.objects.create(
            name='Sotilgan gul',
            slug='sotilgan-gul',
            category=self.category,
            price=100000,
            stock_quantity=0,
            in_stock=False,
        )

    def _order_auth(self, username):
        user = User.objects.create_user(username=username, password='Roses-Bloom-4829!')
        Customer.objects.create(user=user, name=username, phone='+998901234567')
        response = self.client.post(
            reverse('api_mobile_login'),
            data=json.dumps({'username': username, 'password': 'Roses-Bloom-4829!'}),
            content_type='application/json',
        )
        return {'HTTP_AUTHORIZATION': f"Bearer {response.json()['access_token']}"}

    def _order_body(self):
        return {
            'request_key': '7f74d9b2-7a8a-4939-a867-d838bcf432b1',
            'customer_name': 'Mijoz',
            'phone': '+998901234567',
            'payment_method': 'cash',
            'items': [{'product_id': self.available.pk, 'quantity': 2, 'price': self.available.price}],
        }

    def test_existing_mobile_order_retry_qr_and_delivery_are_private(self):
        auth = self._order_auth('order-owner')
        body = self._order_body()
        url = reverse('api_mobile_order_create')
        self.assertEqual(self.client.post(url, data='{}', content_type='application/json').status_code, 401)
        response = self.client.post(url, data=json.dumps(body), content_type='application/json', **auth)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Order.objects.count(), 0)
        normalized = {
            'customer_name': body['customer_name'], 'phone': body['phone'],
            'delivery_note': '', 'card_message': '', 'anonymous_delivery': False,
            'items': [(self.available.pk, 2, self.available.price)], 'payment_method': 'cash',
        }
        fingerprint = hashlib.sha256(json.dumps(
            normalized, sort_keys=True, ensure_ascii=False,
        ).encode('utf-8')).hexdigest()
        customer = Customer.objects.get(user__username='order-owner')
        order = Order.objects.create(
            customer=customer, customer_name=body['customer_name'], phone=body['phone'],
            total=500000, mobile_request_key=body['request_key'], mobile_request_hash=fingerprint,
        )
        OrderItem.objects.create(order=order, product=self.available, quantity=2, price=self.available.price)
        self.available.stock_quantity = 2
        self.available.save(update_fields=['stock_quantity'])
        response = self.client.post(url, data=json.dumps(body), content_type='application/json', **auth)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertRegex(result['order_code'], r'^\d{5}$')
        self.assertTrue(base64.b64decode(result['qr_base64']).startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertIsNone(result['delivery_required'])
        self.assertEqual(result['total'], 500000)
        self.available.refresh_from_db()
        self.assertEqual(self.available.stock_quantity, 2)

        retry = self.client.post(url, data=json.dumps(body), content_type='application/json', **auth)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()['id'], result['id'])
        self.assertEqual(Order.objects.count(), 1)
        self.available.refresh_from_db()
        self.assertEqual(self.available.stock_quantity, 2)
        changed = {**body, 'phone': 'other'}
        self.assertEqual(self.client.post(url, data=json.dumps(changed), content_type='application/json', **auth).status_code, 409)

        detail = reverse('api_mobile_order_detail', args=[result['id']])
        delivery = reverse('api_mobile_order_delivery', args=[result['id']])
        other = self._order_auth('order-other')
        self.assertEqual(self.client.get(detail, **other).status_code, 404)
        self.assertEqual(self.client.post(delivery, data='{"delivery_required": true}', content_type='application/json', **other).status_code, 404)
        self.assertEqual(self.client.get(detail, **auth).json()['order_code'], result['order_code'])
        self.assertEqual(self.client.post(delivery, data='{}', content_type='application/json', **auth).status_code, 400)
        response = self.client.post(delivery, data='{"delivery_required": true}', content_type='application/json', **auth)
        self.assertTrue(response.json()['delivery_required'])
        self.assertIn(result['order_code'], response.json()['telegram_url'])

    def test_mobile_order_is_blocked_without_verified_payment(self):
        auth = self._order_auth('order-buyer')
        url = reverse('api_mobile_order_create')
        body = self._order_body()
        MimozaSettings.objects.create(click_api_key='example', payme_api_key='example', uzum_api_key='example')
        for method in ('cash', 'click', 'payme', 'uzum'):
            body['payment_method'] = method
            response = self.client.post(url, data=json.dumps(body), content_type='application/json', **auth)
            self.assertEqual(response.status_code, 409)
            self.assertIn('hali ulanmagan', response.json()['error'])
        body['payment_method'] = 'cash'
        body['items'][0]['quantity'] = 5
        response = self.client.post(url, data=json.dumps(body), content_type='application/json', **auth)
        self.assertEqual(response.status_code, 409)
        body['items'][0]['quantity'] = 1
        body['items'][0]['price'] = 1
        response = self.client.post(url, data=json.dumps(body), content_type='application/json', **auth)
        self.assertEqual(response.status_code, 409)
        body['items'][0]['quantity'] = True
        self.assertEqual(self.client.post(url, data=json.dumps(body), content_type='application/json', **auth).status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.available.refresh_from_db()
        self.assertEqual(self.available.stock_quantity, 4)

    @override_settings(
        DEBUG=True,
        CLICK_MERCHANT_ID='click-merchant',
        CLICK_SERVICE_ID='click-service',
        CLICK_SECRET_KEY='click-secret',
    )
    def test_mobile_checkout_creates_and_retries_reserved_payment(self):
        auth = self._order_auth('mobile-payment-buyer')
        body = self._order_body()
        body['payment_method'] = 'click'
        url = reverse('api_mobile_order_create')
        response = self.client.post(url, data=json.dumps(body), content_type='application/json', **auth)
        self.assertEqual(response.status_code, 201, response.content.decode())
        payload = response.json()
        self.assertEqual(payload['payment_status'], Order.PaymentStatus.PENDING)
        self.assertEqual(payload['advance_tiyin'], 15000000)
        self.assertTrue(payload['checkout_url'].startswith('https://my.click.uz/'))
        payment = PaymentTransaction.objects.get(order_id=payload['id'])
        self.available.refresh_from_db()
        self.assertEqual(self.available.stock_quantity, 2)

        retry = self.client.post(url, data=json.dumps(body), content_type='application/json', **auth)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()['payment_id'], payment.pk)
        self.available.refresh_from_db()
        self.assertEqual(self.available.stock_quantity, 2)

        payment.expires_at = timezone.now() - timedelta(seconds=1)
        payment.save(update_fields=['expires_at'])
        call_command('expire_pending_payments')
        retry_url = reverse('api_mobile_order_payment_retry', args=[payload['id']])
        retried = self.client.post(retry_url, data='{}', content_type='application/json', **auth)
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()['payment_status'], Order.PaymentStatus.PENDING)
        self.assertNotEqual(retried.json()['payment_id'], payment.pk)
        self.available.refresh_from_db()
        self.assertEqual(self.available.stock_quantity, 2)
        self.assertEqual(PaymentTransaction.objects.count(), 2)

    @override_settings(
        CLICK_MERCHANT_ID='click-merchant',
        CLICK_SERVICE_ID='click-service',
        CLICK_SECRET_KEY='click-secret',
        PAYME_MERCHANT_ID='4056281',
        PAYME_MERCHANT_LOGIN='payme-login',
        PAYME_MERCHANT_KEY='payme-secret',
        UZUM_TERMINAL_ID='uzum-terminal',
        UZUM_API_KEY='uzum-key',
    )
    def test_payment_methods_expose_only_fully_configured_providers(self):
        response = self.client.get(reverse('api_payment_methods'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [method['value'] for method in response.json()['payment_methods']],
            ['click', 'payme'],
        )

    def test_mobile_dashboard_respects_current_staff_permissions(self):
        auth = self._order_auth('mobile-dashboard')
        user = User.objects.get(username='mobile-dashboard')
        dashboard_url = reverse('api_mobile_dashboard')
        account_url = reverse('api_mobile_account')
        self.assertEqual(self.client.get(dashboard_url).status_code, 401)
        self.assertEqual(self.client.get(dashboard_url, **auth).status_code, 403)
        self.assertIsNone(self.client.get(account_url, **auth).json()['staff_role'])

        user.is_staff = True
        user.save(update_fields=['is_staff'])
        profile = StaffProfile.objects.create(user=user, role=StaffProfile.Role.MANAGER)
        Order.objects.create(customer_name='Test mijoz', phone='123', address='', total=5000)
        response = self.client.get(dashboard_url, **auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['orders_today'], 1)
        self.assertEqual(response.json()['pending_orders'], 1)
        self.assertEqual(response.json()['today_revenue'], 5000)
        self.assertEqual(response.json()['recent_orders'][0]['customer_name'], 'Test mijoz')
        self.assertEqual(self.client.get(account_url, **auth).json()['staff_role'], 'manager')

        profile.role = StaffProfile.Role.SHOPKEEPER
        profile.save(update_fields=['role'])
        self.assertEqual(self.client.get(dashboard_url, **auth).status_code, 403)
        self.assertIsNone(self.client.get(account_url, **auth).json()['staff_role'])
        profile.role = StaffProfile.Role.MANAGER
        profile.is_active_worker = False
        profile.save(update_fields=['role', 'is_active_worker'])
        self.assertEqual(self.client.get(dashboard_url, **auth).status_code, 403)
        user.is_superuser = True
        user.save(update_fields=['is_superuser'])
        self.assertEqual(self.client.get(dashboard_url, **auth).status_code, 200)
        self.assertEqual(self.client.get(account_url, **auth).json()['staff_role'], 'super_admin')
        user.is_staff = False
        user.save(update_fields=['is_staff'])
        self.assertEqual(self.client.get(dashboard_url, **auth).status_code, 403)

    def test_mobile_admin_management_permissions_and_audit(self):
        auth = self._order_auth('mobile-manager')
        manager = User.objects.get(username='mobile-manager')
        manager.is_staff = True
        manager.save(update_fields=['is_staff'])
        StaffProfile.objects.create(user=manager, role=StaffProfile.Role.MANAGER)
        order = Order.objects.create(customer_name='Test mijoz', phone='123', address='', total=5000)
        OrderItem.objects.create(order=order, product=self.available, quantity=1, price=5000)
        worker = User.objects.create_user(username='worker', is_staff=True)
        StaffProfile.objects.create(user=worker, role=StaffProfile.Role.FLORIST)

        response = self.client.get(reverse('api_admin_orders'), {'q': order.order_code}, **auth)
        self.assertEqual([item['id'] for item in response.json()['orders']], [order.id])
        response = self.client.post(
            reverse('api_admin_order_update', args=[order.id]),
            data=json.dumps({'status': 'processing', 'florist_id': worker.id, 'courier_id': None}),
            content_type='application/json', **auth,
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.assigned_florist_id, worker.id)
        self.assertEqual(order.status, 'processing')
        self.assertTrue(AuditLog.objects.filter(actor=manager, model_label='mimoza.Order', object_id=order.pk).exists())
        response = self.client.post(
            reverse('api_admin_order_update', args=[order.id]),
            data=json.dumps({'status': 'delivered', 'florist_id': None, 'courier_id': worker.id}),
            content_type='application/json', **auth,
        )
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, 'processing')
        self.assertEqual(self.client.get(reverse('api_admin_analytics'), **auth).status_code, 200)
        self.assertEqual(self.client.get(reverse('api_admin_users'), **auth).status_code, 403)
        self.assertEqual(self.client.get(reverse('api_admin_audit'), **auth).status_code, 403)
        self.assertEqual(self.client.get(reverse('api_admin_products')).status_code, 401)

        super_auth = self._order_auth('mobile-super')
        superuser = User.objects.get(username='mobile-super')
        superuser.is_staff = True
        superuser.is_superuser = True
        superuser.save(update_fields=['is_staff', 'is_superuser'])
        response = self.client.post(
            reverse('api_admin_user_role', args=[worker.id]),
            data=json.dumps({'role': 'courier'}), content_type='application/json', **super_auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(actor=superuser, model_label='mimoza.StaffProfile').exists())
        entries = self.client.get(reverse('api_admin_audit'), **super_auth).json()['entries']
        self.assertTrue(any(entry['actor'] == 'mobile-manager' for entry in entries))

    def test_mobile_admin_create_and_edit_product(self):
        auth = self._order_auth('product-manager')
        user = User.objects.get(username='product-manager')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        StaffProfile.objects.create(user=user, role=StaffProfile.Role.MANAGER)
        data = {
            'name': 'Yangi gul', 'slug': 'yangi-gul', 'category': self.category.pk,
            'description': 'Gul', 'price': '15000', 'stock_quantity': '3',
            'in_stock': 'on', 'is_featured': 'on',
            'video_url': 'https://example.test/flower.mp4',
        }
        response = self.client.post(reverse('api_admin_products'), data, **auth)
        self.assertEqual(response.status_code, 201)
        product = Product.objects.get(slug='yangi-gul')
        self.assertEqual(product.stock_quantity, 3)
        self.assertTrue(product.is_featured)
        self.assertTrue(AuditLog.objects.filter(actor=user, model_label='mimoza.Product', object_id=product.pk).exists())
        data['version'] = response.json()['product']['version']
        data['stock_quantity'] = '0'
        data.pop('in_stock')
        response = self.client.post(reverse('api_admin_product_detail', args=[product.pk]), data, **auth)
        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 0)
        self.assertFalse(product.in_stock)
        stale = self.client.post(reverse('api_admin_product_detail', args=[product.pk]), data, **auth)
        self.assertEqual(stale.status_code, 409)
        data['version'] = response.json()['product']['version']
        data['price'] = '-1'
        self.assertEqual(
            self.client.post(reverse('api_admin_product_detail', args=[product.pk]), data, **auth).status_code, 400,
        )

    def test_mobile_admin_product_media_and_stock_conflict(self):
        auth = self._order_auth('media-manager')
        user = User.objects.get(username='media-manager')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        StaffProfile.objects.create(user=user, role=StaffProfile.Role.MANAGER)
        url = reverse('api_admin_product_detail', args=[self.available.pk])
        data = {
            'name': self.available.name, 'slug': self.available.slug,
            'category': self.category.pk, 'description': '', 'price': '250000',
            'stock_quantity': '4', 'in_stock': 'on',
            'image_url': self.available.image_url, 'video_url': '',
        }
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            image = BytesIO()
            Image.new('RGB', (2, 2), 'red').save(image, format='PNG')
            data['version'] = self.client.get(url, **auth).json()['product']['version']
            data['image'] = SimpleUploadedFile('flower.png', image.getvalue(), content_type='image/png')
            data['video'] = SimpleUploadedFile('flower.mp4', b'video', content_type='video/mp4')
            response = self.client.post(url, data, **auth)
            self.assertEqual(response.status_code, 200)
            self.available.refresh_from_db()
            self.assertTrue(self.available.image.name.endswith('.webp'))
            self.assertTrue(self.available.video)
            self.available.hls_playlist = 'products/hls/old/index.m3u8'
            self.available.save(update_fields=['hls_playlist'])
            data.pop('image')
            data.pop('video')
            data['version'] = self.client.get(url, **auth).json()['product']['version']
            response = self.client.post(url, data, **auth)
            self.assertEqual(response.status_code, 200)
            self.available.refresh_from_db()
            self.assertEqual(self.available.hls_playlist.name, 'products/hls/old/index.m3u8')

            data['version'] = response.json()['product']['version']
            self.available.stock_quantity = 2
            self.available.save(update_fields=['stock_quantity'])
            self.assertEqual(self.client.post(url, data, **auth).status_code, 409)
            self.available.refresh_from_db()
            self.assertEqual(self.available.stock_quantity, 2)

            data['version'] = self.client.get(url, **auth).json()['product']['version']
            data['stock_quantity'] = '2'
            data['image-clear'] = 'on'
            data['video-clear'] = 'on'
            self.assertEqual(self.client.post(url, data, **auth).status_code, 200)
            self.available.refresh_from_db()
            self.assertFalse(self.available.image)
            self.assertFalse(self.available.video)
            self.assertFalse(self.available.hls_playlist)

    def test_mobile_admin_access_pagination_and_superuser_protection(self):
        auth = self._order_auth('limited-staff')
        user = User.objects.get(username='limited-staff')
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        profile = StaffProfile.objects.create(user=user, role=StaffProfile.Role.SHOPKEEPER)
        self.assertEqual(self.client.get(reverse('api_admin_orders'), **auth).status_code, 403)
        profile.role = StaffProfile.Role.MANAGER
        profile.is_active_worker = False
        profile.save()
        self.assertEqual(self.client.get(reverse('api_admin_products'), **auth).status_code, 403)
        profile.is_active_worker = True
        profile.save()
        self.assertEqual(self.client.get(reverse('api_admin_products'), {'page': '0'}, **auth).status_code, 400)
        self.assertEqual(self.client.get(reverse('api_admin_analytics'), {'days': '1'}, **auth).status_code, 400)

        super_auth = self._order_auth('actual-super')
        superuser = User.objects.get(username='actual-super')
        superuser.is_staff = True
        superuser.is_superuser = True
        superuser.save(update_fields=['is_staff', 'is_superuser'])
        response = self.client.post(
            reverse('api_admin_user_role', args=[superuser.pk]),
            data=json.dumps({'role': 'manager'}), content_type='application/json', **super_auth,
        )
        self.assertEqual(response.status_code, 403)

    def test_mobile_catalog_returns_available_products_and_categories(self):
        response = self.client.get(reverse('api_products'), {'q': 'atirgul', 'page_size': 5})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['products'][0]['slug'], self.available.slug)
        self.assertEqual(payload['products'][0]['image_url'], 'https://cdn.example.test/rose.webp')
        self.assertEqual(payload['categories'], [{'name': 'Romantika', 'slug': 'romantika'}])

    def test_mobile_product_detail_hides_unavailable_products(self):
        response = self.client.get(reverse('api_product_detail', args=[self.available.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['stock_quantity'], 4)

        response = self.client.get(reverse('api_product_detail', args=[self.unavailable.slug]))
        self.assertEqual(response.status_code, 404)

    def test_mobile_catalog_rejects_invalid_pagination_and_sort_values(self):
        response = self.client.get(reverse('api_products'), {'page': '0'})
        self.assertEqual(response.status_code, 400)
        response = self.client.get(reverse('api_products'), {'sort': 'random'})
        self.assertEqual(response.status_code, 400)

    def test_mobile_reels_return_playable_videos_and_external_embeds(self):
        uploaded = Product.objects.create(
            name='Video gul', slug='video-gul', category=self.category, price=1000,
            stock_quantity=2, video='products/videos/flower.mp4',
            hls_playlist='products/hls/flower/index.m3u8',
        )
        direct = Product.objects.create(
            name='Direct video', slug='direct-video', category=self.category, price=1000,
            stock_quantity=2, video_url='https://cdn.example.test/video.mp4?token=sample',
        )
        embedded = Product.objects.create(
            name='Embedded video', slug='embedded-video', category=self.category, price=1000,
            stock_quantity=2, video_url='https://example.test/embed/123',
        )
        self.unavailable.video_url = 'https://example.test/embed/sold-out'
        self.unavailable.save()

        response = self.client.get(reverse('api_reels'))
        self.assertEqual(response.status_code, 200)
        reels = {item['id']: item for item in response.json()['products']}
        self.assertEqual(set(reels), {uploaded.pk, direct.pk, embedded.pk})
        self.assertTrue(reels[uploaded.pk]['video_url'].endswith('/products/hls/flower/index.m3u8'))
        self.assertFalse(reels[uploaded.pk]['video_is_embed'])
        self.assertFalse(reels[direct.pk]['video_is_embed'])
        self.assertTrue(reels[embedded.pk]['video_is_embed'])
        self.assertFalse(response.json()['has_next'])

    def test_mobile_reels_paginate_and_reject_invalid_page(self):
        for index in range(11):
            Product.objects.create(
                name=f'Video {index}', slug=f'video-{index}', category=self.category,
                price=1000, stock_quantity=1, video=f'products/videos/{index}.mp4',
            )
        first = self.client.get(reverse('api_reels'), {'page': 1}).json()
        second = self.client.get(reverse('api_reels'), {'page': 2}).json()
        self.assertEqual(len(first['products']), 10)
        self.assertTrue(first['has_next'])
        self.assertEqual(len(second['products']), 1)
        self.assertFalse(second['has_next'])
        self.assertTrue(
            {item['id'] for item in first['products']}.isdisjoint(
                {item['id'] for item in second['products']}
            )
        )
        for page in ('0', 'invalid'):
            self.assertEqual(self.client.get(reverse('api_reels'), {'page': page}).status_code, 400)

    def test_mobile_reels_shuffle_stably_across_pages(self):
        for index in range(25):
            Product.objects.create(
                name=f'Video {index}', slug=f'shuffle-video-{index}', category=self.category,
                price=1000, stock_quantity=1, video=f'products/videos/{index}.mp4',
            )
        def ids(seed, page):
            response = self.client.get(reverse('api_reels'), {'seed': seed, 'page': page})
            self.assertEqual(response.status_code, 200)
            return [item['id'] for item in response.json()['products']]

        pages = [ids('42', page) for page in (1, 2, 3)]
        all_ids = [pk for page in pages for pk in page]
        self.assertEqual(len(set(all_ids)), 25)
        self.assertEqual(pages[0], ids('42', 1))
        self.assertNotEqual(pages[0], ids('43', 1))
        for seed in ('', '-1', '12345678901', 'abc'):
            self.assertEqual(self.client.get(reverse('api_reels'), {'seed': seed}).status_code, 400)

    def test_mobile_likes_are_shared_with_web_and_idempotent(self):
        self.available.video = 'products/videos/flower.mp4'
        self.available.save()
        user = User.objects.create_user(username='reels-user', password='Roses-Bloom-4829!')
        login = self.client.post(
            reverse('api_mobile_login'),
            data=json.dumps({'username': user.username, 'password': 'Roses-Bloom-4829!'}),
            content_type='application/json',
        )
        auth = {'HTTP_AUTHORIZATION': f"Bearer {login.json()['access_token']}"}
        url = reverse('api_mobile_product_like', args=[self.available.pk])
        self.assertEqual(self.client.post(url, data='{}', content_type='application/json').status_code, 401)
        for _ in range(2):
            response = self.client.post(url, data='{"liked": true}', content_type='application/json', **auth)
            self.assertEqual(response.json(), {'is_liked': True, 'likes_count': 1})
        reels = self.client.get(reverse('api_reels'), **auth).json()['products']
        self.assertTrue(reels[0]['is_liked'])
        self.assertEqual(reels[0]['likes_count'], 1)
        self.assertTrue(ProductLike.objects.filter(product=self.available, user=user).exists())
        guest_reel = self.client.get(reverse('api_reels')).json()['products'][0]
        self.assertFalse(guest_reel['is_liked'])
        self.assertEqual(guest_reel['likes_count'], 1)
        response = self.client.post(url, data='{"liked": false}', content_type='application/json', **auth)
        self.assertEqual(response.json(), {'is_liked': False, 'likes_count': 0})
        self.assertFalse(ProductLike.objects.filter(product=self.available, user=user).exists())
        self.assertEqual(
            self.client.post(url, data='{"liked": "yes"}', content_type='application/json', **auth).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(reverse('api_reels'), HTTP_AUTHORIZATION='Bearer invalid').status_code, 401,
        )

    def test_mobile_registration_creates_customer_and_returns_hashed_token(self):
        response = self.client.post(
            reverse('api_mobile_register'),
            data=json.dumps({
                'full_name': 'Ali Valiyev',
                'phone': '+998901234567',
                'email': 'ali@example.com',
                'username': 'gulchi_928',
                'password1': 'Roses-Bloom-4829!',
                'password2': 'Roses-Bloom-4829!',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        user = User.objects.get(username='gulchi_928')
        customer = Customer.objects.get(user=user)
        token = MobileAccessToken.objects.get(user=user)
        self.assertEqual(customer.phone, '+998901234567')
        self.assertEqual(payload['token_type'], 'Bearer')
        self.assertEqual(len(token.token_hash), 64)
        self.assertNotEqual(token.token_hash, payload['access_token'])

        account_response = self.client.get(
            reverse('api_mobile_account'),
            HTTP_AUTHORIZATION=f"Bearer {payload['access_token']}",
        )
        self.assertEqual(account_response.status_code, 200)
        self.assertEqual(account_response.json()['customer']['name'], 'Ali Valiyev')

    def test_mobile_login_rejects_invalid_credentials_and_bad_json(self):
        user = User.objects.create_user(username='mobile-customer', password='Roses-Bloom-4829!')
        Customer.objects.create(user=user, name='Mobil mijoz', phone='+998901234567')

        invalid_response = self.client.post(
            reverse('api_mobile_login'),
            data=json.dumps({'username': user.username, 'password': 'wrong-password'}),
            content_type='application/json',
        )
        self.assertEqual(invalid_response.status_code, 401)
        self.assertEqual(MobileAccessToken.objects.count(), 0)

        malformed_response = self.client.post(
            reverse('api_mobile_login'),
            data='not-json',
            content_type='application/json',
        )
        self.assertEqual(malformed_response.status_code, 400)

    def test_mobile_auth_accepts_json_without_browser_csrf_and_rejects_other_content_types(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse('api_mobile_login')
        non_json_response = client.post(
            url,
            data=json.dumps({'username': 'mobile-user', 'password': 'password'}),
            content_type='text/plain',
        )
        self.assertEqual(non_json_response.status_code, 415)

        json_response = client.post(
            url,
            data=json.dumps({'username': 'mobile-user', 'password': 'password'}),
            content_type='application/json',
        )
        self.assertEqual(json_response.status_code, 401)

    def test_mobile_account_only_returns_the_authenticated_customers_orders(self):
        user = User.objects.create_user(username='order-owner', password='Roses-Bloom-4829!')
        customer = Customer.objects.create(user=user, name='Buyurtmachi', phone='+998901234567')
        other_user = User.objects.create_user(username='other-owner', password='Roses-Bloom-4829!')
        other_customer = Customer.objects.create(user=other_user, name='Boshqa mijoz', phone='+998909876543')
        own_order = Order.objects.create(
            customer=customer,
            customer_name=customer.name,
            phone=customer.phone,
            address='Toshkent',
            total=self.available.price,
        )
        OrderItem.objects.create(order=own_order, product=self.available, quantity=1, price=self.available.price)
        Order.objects.create(
            customer=other_customer,
            customer_name=other_customer.name,
            phone=other_customer.phone,
            address='Samarqand',
            total=100000,
        )
        login_response = self.client.post(
            reverse('api_mobile_login'),
            data=json.dumps({'username': user.username, 'password': 'Roses-Bloom-4829!'}),
            content_type='application/json',
        )
        token = login_response.json()['access_token']

        response = self.client.get(
            reverse('api_mobile_account'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        orders = response.json()['orders']
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['id'], own_order.pk)
        self.assertEqual(orders[0]['items'][0]['name'], self.available.name)

    def test_mobile_token_expiry_and_logout_revoke_access(self):
        user = User.objects.create_user(username='token-owner', password='Roses-Bloom-4829!')
        Customer.objects.create(user=user, name='Token mijoz', phone='+998901234567')
        expired_raw_token = 'expired-mobile-token'
        expired = MobileAccessToken.objects.create(
            user=user,
            token_hash=hashlib.sha256(expired_raw_token.encode('utf-8')).hexdigest(),
            auth_hash=user.get_session_auth_hash(),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        expired_response = self.client.get(
            reverse('api_mobile_account'),
            HTTP_AUTHORIZATION=f'Bearer {expired_raw_token}',
        )
        self.assertEqual(expired_response.status_code, 401)
        expired.delete()

        login_response = self.client.post(
            reverse('api_mobile_login'),
            data=json.dumps({'username': user.username, 'password': 'Roses-Bloom-4829!'}),
            content_type='application/json',
        )
        token = login_response.json()['access_token']
        user.set_password('Fresh-Roses-2583!')
        user.save()
        password_changed_response = self.client.get(
            reverse('api_mobile_account'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(password_changed_response.status_code, 401)

        login_response = self.client.post(
            reverse('api_mobile_login'),
            data=json.dumps({'username': user.username, 'password': 'Fresh-Roses-2583!'}),
            content_type='application/json',
        )
        token = login_response.json()['access_token']
        logout_response = self.client.post(
            reverse('api_mobile_logout'),
            data=json.dumps({}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse('api_mobile_account'),
                HTTP_AUTHORIZATION=f'Bearer {token}',
            ).status_code,
            401,
        )


class PushNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='push-user', password='test-pass')
        self.client.force_login(self.user)
        self.endpoint = 'https://fcm.googleapis.com/fcm/send/test-endpoint'

    def test_account_shows_push_controls_only_when_vapid_is_configured(self):
        response = self.client.get(reverse('account'))
        self.assertContains(response, 'Push kalitlari serverda sozlanmagan')

        with override_settings(
            WEBPUSH_VAPID_PUBLIC_KEY='public-key',
            WEBPUSH_VAPID_PRIVATE_KEY='private-key',
            WEBPUSH_VAPID_SUBJECT='mailto:shop@example.com',
        ):
            response = self.client.get(reverse('account'))
        self.assertContains(response, 'Bildirishnomalarni yoqish')

    def test_customer_can_subscribe_and_unsubscribe_a_browser(self):
        response = self.client.post(
            reverse('push_subscription_create'),
            data=json.dumps({
                'subscription': {
                    'endpoint': self.endpoint,
                    'keys': {'p256dh': 'browser-public-key', 'auth': 'browser-auth-key'},
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        subscription = PushSubscription.objects.get(user=self.user)
        self.assertEqual(subscription.endpoint, self.endpoint)
        self.assertEqual(subscription.p256dh, 'browser-public-key')

        response = self.client.post(
            reverse('push_subscription_delete'),
            data=json.dumps({'endpoint': self.endpoint}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PushSubscription.objects.exists())

    def test_push_subscription_rejects_non_provider_endpoints_and_bad_json(self):
        invalid_endpoints = (
            'https://127.0.0.1/admin',
            'https://fcm.googleapis.com:not-a-port/send',
            f"https://fcm.googleapis.com/{'a' * 2050}",
        )
        for endpoint in invalid_endpoints:
            response = self.client.post(
                reverse('push_subscription_create'),
                data=json.dumps({
                    'subscription': {
                        'endpoint': endpoint,
                        'keys': {'p256dh': 'key', 'auth': 'auth'},
                    },
                }),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 400, endpoint[:80])
        self.assertEqual(PushSubscription.objects.count(), 0)

        response = self.client.post(
            reverse('push_subscription_create'),
            data='not-json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_user_cannot_create_push_subscription(self):
        self.client.logout()
        response = self.client.post(
            reverse('push_subscription_create'),
            data='{}',
            content_type='application/json',
        )
        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next={reverse('push_subscription_create')}",
        )

    @override_settings(
        WEBPUSH_VAPID_PUBLIC_KEY='public-key',
        WEBPUSH_VAPID_PRIVATE_KEY='private-key',
        WEBPUSH_VAPID_SUBJECT='mailto:shop@example.com',
    )
    @patch('mimoza.push_notifications.webpush')
    def test_sender_delivers_payload_to_saved_browser_subscription(self, send):
        PushSubscription.objects.create(
            user=self.user,
            endpoint=self.endpoint,
            p256dh='browser-public-key',
            auth='browser-auth-key',
        )

        sent = send_push_notification(self.user, 'Eslatma', 'Muhim kun yaqinlashmoqda.', '/account/')

        self.assertEqual(sent, 1)
        payload = json.loads(send.call_args.kwargs['data'])
        self.assertEqual(payload, {
            'title': 'Eslatma',
            'body': 'Muhim kun yaqinlashmoqda.',
            'url': '/account/',
        })

    def test_sender_fails_loudly_when_vapid_keys_are_missing(self):
        with self.assertRaises(ImproperlyConfigured):
            send_push_notification(self.user, 'Eslatma', 'Matn')

    def test_service_worker_is_served_from_site_root(self):
        response = self.client.get(reverse('service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/javascript'))
        self.assertEqual(response['Service-Worker-Allowed'], '/')

    def test_vapid_key_command_outputs_environment_values_without_persisting_them(self):
        output = StringIO()
        call_command('generate_vapid_keys', stdout=output)
        variables = {
            line.split('=', 1)[0]: line.split('=', 1)[1]
            for line in output.getvalue().splitlines()
            if '=' in line
        }

        self.assertIn('WEBPUSH_VAPID_PUBLIC_KEY', variables)
        self.assertIn('WEBPUSH_VAPID_PRIVATE_KEY', variables)
        self.assertTrue(variables['WEBPUSH_VAPID_PUBLIC_KEY'])
        self.assertTrue(variables['WEBPUSH_VAPID_PRIVATE_KEY'])
        self.assertEqual(
            len(base64.urlsafe_b64decode(
                variables['WEBPUSH_VAPID_PUBLIC_KEY']
                + '=' * (-len(variables['WEBPUSH_VAPID_PUBLIC_KEY']) % 4)
            )),
            65,
        )
