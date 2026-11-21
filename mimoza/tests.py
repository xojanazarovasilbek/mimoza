import base64
import json
import tempfile
from datetime import date, timedelta
from io import BytesIO, StringIO
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from PIL import Image

from django.contrib.auth.models import User

from .models import (
    Category,
    Customer,
    ImportantDate,
    Order,
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

    def test_checkout_shows_delivery_choice_and_telegram_contact(self):
        user = User.objects.create_user(username='delivery-customer', password='test-pass')
        self.client.force_login(user)
        session = self.client.session
        session['cart'] = {str(self.product.pk): 1}
        session.save()

        response = self.client.get(reverse('checkout'))
        self.assertContains(response, 'Yetkazib berish kerakmi?')
        self.assertContains(response, 'id="delivery-help"')
        self.assertContains(response, 'hidden')
        self.assertContains(response, settings.TELEGRAM_CONTACT_URL)
        self.assertContains(response, f'Gul №{self.product.pk}')
        self.assertNotContains(response, 'delivery-map')

    def test_cart_and_checkout_require_customer_account(self):
        guest_add = self.client.post(reverse('cart_add', args=[self.product.id]), {'next': 'cart'})
        self.assertRedirects(
            guest_add,
            f"{reverse('account_login')}?next={reverse('cart_add', args=[self.product.id])}",
        )
        self.assertNotIn(str(self.product.id), self.client.session.get('cart', {}))

        user = User.objects.create_user(username='store-customer', password='test-pass')
        customer = Customer.objects.create(user=user, name='Test mijoz', phone='+998901234567')
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
        }
        failed_payment = self.client.post(
            reverse('checkout'),
            {**order_data, 'payment_method': 'click'},
        )
        self.assertContains(failed_payment, 'merchant hisobi')
        self.assertEqual(Order.objects.count(), 0)

        checkout = self.client.post(
            reverse('checkout'),
            {**order_data, 'payment_method': 'cash'},
        )
        self.assertEqual(checkout.status_code, 200)
        self.assertContains(checkout, 'Buyurtmangiz qabul qilindi')
        self.assertContains(checkout, settings.TELEGRAM_CONTACT_URL)
        self.assertContains(checkout, f'Gul №{self.product.pk}')
        order = Order.objects.get()
        self.assertEqual(order.customer, customer)
        self.assertTrue(order.delivery_required)
        self.assertEqual(order.address, '')
        self.assertIsNone(order.latitude)
        self.assertIsNone(order.longitude)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 19)
        self.assertTrue(self.product.in_stock)

    def test_checkout_decrements_requested_quantity_and_marks_last_item_out_of_stock(self):
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
        })

        self.assertContains(response, 'Buyurtmangiz qabul qilindi')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)
        self.assertFalse(self.product.in_stock)

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
        })

        self.assertContains(response, 'Oq atirgul uchun omborda 1 ta qoldi')
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        second_product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 20)
        self.assertEqual(second_product.stock_quantity, 1)
        self.assertEqual(self.client.session['cart'][str(self.product.pk)], 1)

    def test_pickup_order_does_not_show_telegram_location_prompt(self):
        user = User.objects.create_user(username='pickup-customer', password='test-pass')
        self.client.force_login(user)
        session = self.client.session
        session['cart'] = {str(self.product.pk): 1}
        session.save()

        response = self.client.post(reverse('checkout'), {
            'customer_name': 'Olib ketuvchi',
            'phone': '+998901234567',
            'delivery_required': 'no',
            'payment_method': 'cash',
        })

        self.assertContains(response, 'do‘kondan olib ketishingiz mumkin')
        order = Order.objects.get()
        self.assertFalse(order.delivery_required)

    def test_checkout_rejects_missing_delivery_choice(self):
        user = User.objects.create_user(username='missing-choice', password='test-pass')
        self.client.force_login(user)
        session = self.client.session
        session['cart'] = {str(self.product.pk): 1}
        session.save()

        response = self.client.post(reverse('checkout'), {
            'customer_name': 'Mijoz',
            'phone': '+998901234567',
            'payment_method': 'cash',
        })

        self.assertContains(response, 'Yetkazib berish kerak yoki kerak emasligini tanlang')
        self.assertEqual(Order.objects.count(), 0)


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
