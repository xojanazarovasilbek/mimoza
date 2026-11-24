import base64
import hashlib
import json
import secrets
from datetime import timedelta
from decimal import Decimal
from functools import wraps
from io import BytesIO
from urllib.parse import urlencode, urlparse
import uuid

import qrcode
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import CharField, Count, Exists, F, OuterRef, Q, Sum, Value
from django.db.models.functions import Cast, Concat, SHA256
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import CustomerAuthenticationForm, CustomerRegistrationForm, ImportantDateForm
from .audit import reset_audit_actor, set_audit_actor
from .models import (
    AuditLog,
    Category,
    Customer,
    ImportantDate,
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
from .payments import (
    advance_amount_tiyin,
    create_order_for_payment,
    enabled_providers,
    payme_callback,
    payment_checkout_url,
    retry_payment_transaction,
    click_callback,
)

User = get_user_model()

PAYMENT_UNAVAILABLE_MESSAGE = (
    'Tanlangan onlayn to‘lov xizmati hali ulanmagan yoki serverda to‘liq sozlanmagan. '
    'Hozircha yangi buyurtma qabul qilinmaydi.'
)

ONLINE_PAYMENT_METHODS = (
    Order.Payment.CLICK,
    Order.Payment.PAYME,
    Order.Payment.UZUM,
)


@require_GET
def api_payment_methods(request):
    labels = {
        PaymentTransaction.Provider.CLICK: 'Click',
        PaymentTransaction.Provider.PAYME: 'Payme',
    }
    return JsonResponse({
        'payment_methods': [
            {'value': provider, 'label': labels[provider]}
            for provider in enabled_providers()
        ],
    })


def _orders_ready_for_fulfillment(queryset):
    return queryset.filter(
        Q(payment_method__in=ONLINE_PAYMENT_METHODS, payment_status=Order.PaymentStatus.PAID)
        | ~Q(payment_method__in=ONLINE_PAYMENT_METHODS),
    )


def get_staff_role(user):
    if user.is_superuser:
        return StaffProfile.Role.SUPER_ADMIN
    profile = StaffProfile.objects.filter(user=user).first()
    if not profile or not profile.is_active_worker:
        return None
    return profile.role


def get_staff_notification_count(role, user):
    orders = _orders_ready_for_fulfillment(Order.objects.all())
    if role == StaffProfile.Role.FLORIST:
        orders = orders.filter(assigned_florist=user, status=Order.Status.PENDING)
    elif role == StaffProfile.Role.COURIER:
        orders = orders.filter(
            assigned_courier=user,
            status__in=(Order.Status.PROCESSING, Order.Status.SHIPPED),
        )
    else:
        orders = orders.filter(status=Order.Status.PENDING)
    return orders.count()


def order_qr_png(order):
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(f'MIMOZA-ORDER:{order.qr_token.hex.upper()}')
    qr.make(fit=True)
    image = qr.make_image(fill_color='#31010D', back_color='#FAF7F2')
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def order_qr_data_url(order):
    encoded = base64.b64encode(order_qr_png(order)).decode('ascii')
    return f'data:image/png;base64,{encoded}'


def order_telegram_url(order):
    products = '\n'.join(
        f'Gul №{item.product_id} — {item.product.name} × {item.quantity}'
        for item in order.items.select_related('product')
    )
    message = (
        f'Buyurtma #{order.pk}\n'
        f'5 xonali kod: {order.order_code}\n'
        f'QR kodi: MIMOZA-ORDER:{order.qr_token.hex.upper()}\n'
        f'Ism: {order.customer_name}\n'
        f'Telefon: {order.phone}\n'
        f'{products}\n'
        'Lokatsiyamni yuboryapman.'
    )
    return f'{settings.TELEGRAM_CONTACT_URL}?{urlencode({"text": message})}'


def allowed_order_statuses(order, role, user):
    if (
        order.payment_method in ONLINE_PAYMENT_METHODS
        and order.payment_status != Order.PaymentStatus.PAID
    ):
        return []
    if role in (StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER):
        return [value for value, _ in Order.Status.choices]
    if role == StaffProfile.Role.SHOPKEEPER:
        transitions = {
            Order.Status.PENDING: (Order.Status.PROCESSING, Order.Status.CANCELLED),
            Order.Status.PROCESSING: (Order.Status.SHIPPED, Order.Status.CANCELLED),
            Order.Status.SHIPPED: (Order.Status.DELIVERED, Order.Status.CANCELLED),
        }
        return list(transitions.get(order.status, ()))
    if role == StaffProfile.Role.FLORIST:
        if order.assigned_florist_id == user.id and order.status == Order.Status.PENDING:
            return [Order.Status.PROCESSING]
    if role == StaffProfile.Role.COURIER and order.assigned_courier_id == user.id:
        if order.status == Order.Status.PROCESSING:
            return [Order.Status.SHIPPED]
        if order.status == Order.Status.SHIPPED:
            return [Order.Status.DELIVERED]
    return []


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @user_passes_test(lambda user: user.is_authenticated and user.is_staff, login_url='admin:login')
        def wrapped(request, *args, **kwargs):
            role = get_staff_role(request.user)
            if role not in allowed_roles:
                return HttpResponseForbidden('Bu bo‘lim uchun ruxsatingiz yo‘q.')
            request.crm_role = role
            request.crm_notification_count = get_staff_notification_count(role, request.user)
            request.user.crm_role = role
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def home(request):
    products = Product.objects.filter(in_stock=True, stock_quantity__gt=0).select_related('category')
    featured = products.filter(is_featured=True)[:8]
    categories = Category.objects.all()
    return render(request, 'mimoza/home.html', {
        'featured': featured,
        'categories': categories,
        'products': products[:12],
        'stories': Story.objects.filter(is_active=True, expires_at__gt=timezone.now())[:12],
    })


def catalog(request):
    products = Product.objects.filter(in_stock=True, stock_quantity__gt=0).select_related('category')
    category_slug = request.GET.get('category')
    query = request.GET.get('q', '').strip()
    if category_slug:
        products = products.filter(category__slug=category_slug)
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))
    sort = request.GET.get('sort')
    if sort == 'price_asc':
        products = products.order_by('price')
    elif sort == 'price_desc':
        products = products.order_by('-price')
    elif sort == 'new':
        products = products.order_by('-created_at')
    return render(request, 'mimoza/catalog.html', {
        'products': products,
        'categories': Category.objects.all(),
        'selected_category': category_slug,
        'selected_sort': request.GET.get('sort', 'new'),
        'query': query,
    })


def api_product_payload(request, product):
    image_url = product.image.url if product.image else product.image_url
    video_url = product.hls_playlist.url if product.hls_playlist else (
        product.video.url if product.video else product.video_url
    )
    return {
        'id': product.pk,
        'name': product.name,
        'slug': product.slug,
        'category': {
            'name': product.category.name,
            'slug': product.category.slug,
        },
        'description': product.description,
        'price': product.price,
        'old_price': product.old_price,
        'image_url': request.build_absolute_uri(image_url) if image_url else '',
        'video_url': request.build_absolute_uri(video_url) if video_url else '',
        'stock_quantity': product.stock_quantity,
        'is_featured': product.is_featured,
    }


@require_GET
def api_products(request):
    products = Product.objects.filter(
        in_stock=True,
        stock_quantity__gt=0,
    ).select_related('category')
    category_slug = request.GET.get('category', '').strip()
    query = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'new')
    try:
        page = int(request.GET.get('page', '1'))
        page_size = int(request.GET.get('page_size', '24'))
    except ValueError:
        return JsonResponse({'error': 'Sahifa yoki sahifa hajmi noto‘g‘ri.'}, status=400)
    if page < 1 or page_size < 1:
        return JsonResponse({'error': 'Sahifa va sahifa hajmi musbat bo‘lishi kerak.'}, status=400)
    page_size = min(page_size, 50)

    if category_slug:
        products = products.filter(category__slug=category_slug)
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if sort == 'price_asc':
        products = products.order_by('price')
    elif sort == 'price_desc':
        products = products.order_by('-price')
    elif sort == 'new':
        products = products.order_by('-created_at')
    else:
        return JsonResponse({'error': 'Saralash turi noto‘g‘ri.'}, status=400)

    total = products.count()
    start = (page - 1) * page_size
    return JsonResponse({
        'count': total,
        'page': page,
        'page_size': page_size,
        'categories': list(Category.objects.values('name', 'slug')),
        'products': [
            api_product_payload(request, product)
            for product in products[start:start + page_size]
        ],
    })


@require_GET
def api_product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related('category'),
        slug=slug,
        in_stock=True,
        stock_quantity__gt=0,
    )
    return JsonResponse(api_product_payload(request, product))


@require_GET
def api_reels(request):
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        return JsonResponse({'error': 'Sahifa raqami noto‘g‘ri.'}, status=400)
    if page < 1 or page > 214748364:
        return JsonResponse({'error': 'Sahifa raqami noto‘g‘ri.'}, status=400)

    seed = request.GET.get('seed')
    if seed is not None and (not seed.isascii() or not seed.isdigit() or len(seed) > 10):
        return JsonResponse({'error': 'Aralashtirish qiymati noto‘g‘ri.'}, status=400)

    user = None
    if request.headers.get('Authorization'):
        token, error = _mobile_authenticate(request)
        if error:
            return error
        user = token.user

    products = (
        Product.objects.filter(in_stock=True, stock_quantity__gt=0)
        .filter(Q(video__gt='') | Q(hls_playlist__gt='') | Q(video_url__gt=''))
        .select_related('category')
        .annotate(likes_count=Count('likes'))
    )
    if user:
        products = products.annotate(is_liked=Exists(
            ProductLike.objects.filter(product_id=OuterRef('pk'), user=user)
        ))
    if seed is not None:
        products = products.annotate(
            shuffle_key=SHA256(Concat(Value(seed + ':'), Cast('pk', CharField())))
        ).order_by('shuffle_key', 'pk')
    else:
        products = products.order_by('-created_at', '-pk')
    page_size = 10
    start = (page - 1) * page_size
    batch = list(products[start:start + page_size + 1])
    results = []
    for product in batch[:page_size]:
        payload = api_product_payload(request, product)
        path = urlparse(payload['video_url']).path.lower()
        payload['video_is_embed'] = not (
            product.hls_playlist or product.video
            or path.endswith(('.m3u8', '.mp4', '.m4v', '.webm', '.mov'))
        )
        payload['likes_count'] = product.likes_count
        payload['is_liked'] = product.is_liked if user else False
        results.append(payload)
    return JsonResponse({'products': results, 'has_next': len(batch) > page_size})


def _mobile_authenticate(request):
    authorization = request.headers.get('Authorization', '')
    scheme, separator, raw_token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not separator or not raw_token or ' ' in raw_token:
        return None, JsonResponse({'error': 'Akkauntga kiring.'}, status=401)

    token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
    token = MobileAccessToken.objects.select_related('user').filter(
        token_hash=token_hash,
        expires_at__gt=timezone.now(),
        user__is_active=True,
    ).first()
    if token is None:
        return None, JsonResponse({'error': 'Kirish tokeni yaroqsiz yoki muddati tugagan.'}, status=401)
    if not secrets.compare_digest(token.auth_hash, token.user.get_session_auth_hash()):
        token.delete()
        return None, JsonResponse({'error': 'Akkaunt paroli o‘zgargan. Qayta kiring.'}, status=401)
    return token, None


def mobile_api_auth_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        token, error = _mobile_authenticate(request)
        if error:
            return error
        request.mobile_user = token.user
        request.mobile_access_token = token
        actor_token = set_audit_actor(token.user)
        try:
            return view_func(request, *args, **kwargs)
        finally:
            reset_audit_actor(actor_token)

    return wrapped


def _mobile_json_body(request):
    if request.content_type != 'application/json':
        return None, JsonResponse({'error': 'So‘rov JSON formatida bo‘lishi kerak.'}, status=415)
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({'error': 'JSON so‘rov ma’lumoti noto‘g‘ri.'}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({'error': 'So‘rov ma’lumoti obyekt bo‘lishi kerak.'}, status=400)
    return payload, None


@csrf_exempt
@require_POST
@mobile_api_auth_required
def api_mobile_product_like(request, product_id):
    payload, error = _mobile_json_body(request)
    if error:
        return error
    liked = payload.get('liked')
    if not isinstance(liked, bool):
        return JsonResponse({'error': 'Like holati noto‘g‘ri.'}, status=400)
    product = get_object_or_404(
        Product, pk=product_id, in_stock=True, stock_quantity__gt=0,
    )
    if liked:
        ProductLike.objects.get_or_create(product=product, user=request.mobile_user)
    else:
        ProductLike.objects.filter(product=product, user=request.mobile_user).delete()
    return JsonResponse({'is_liked': liked, 'likes_count': product.likes.count()})


def _mobile_order_payload(order):
    return {
        'id': order.pk,
        'order_code': order.order_code,
        'status': order.get_status_display(),
        'status_code': order.status,
        'total': order.total,
        'payment_status': order.payment_status,
        'payment_method': order.payment_method,
        'payment_status': order.payment_status,
        'payment_method': order.payment_method,
        'advance_tiyin': advance_amount_tiyin(order.total),
        'remaining_tiyin': order.total * 70,
        'delivery_required': order.delivery_required,
        'qr_base64': base64.b64encode(order_qr_png(order)).decode('ascii'),
        'telegram_url': order_telegram_url(order) if order.delivery_required else '',
    }


@csrf_exempt
@require_POST
@mobile_api_auth_required
def api_mobile_order_create(request):
    payload, error = _mobile_json_body(request)
    if error:
        return error
    try:
        request_key = uuid.UUID(payload.get('request_key', ''))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Buyurtma so‘rovi noto‘g‘ri.'}, status=400)

    name = payload.get('customer_name')
    phone = payload.get('phone')
    note = payload.get('delivery_note', '')
    message = payload.get('card_message', '')
    anonymous = payload.get('anonymous_delivery', False)
    items = payload.get('items')
    if (
        not isinstance(name, str) or not name.strip() or len(name.strip()) > 150
        or not isinstance(phone, str) or not phone.strip() or len(phone.strip()) > 30
        or not isinstance(note, str) or len(note) > 255
        or not isinstance(message, str) or len(message) > 1000
        or not isinstance(anonymous, bool)
        or payload.get('payment_method') not in (
            Order.Payment.CASH, Order.Payment.CLICK, Order.Payment.PAYME, Order.Payment.UZUM,
        )
        or not isinstance(items, list) or not 1 <= len(items) <= 50
    ):
        return JsonResponse({'error': 'Buyurtma ma’lumotlarini tekshiring.'}, status=400)

    quantities = {}
    prices = {}
    for item in items:
        if not isinstance(item, dict):
            return JsonResponse({'error': 'Savat ma’lumotlari noto‘g‘ri.'}, status=400)
        product_id, quantity, price = item.get('product_id'), item.get('quantity'), item.get('price')
        if (
            type(product_id) is not int or product_id < 1
            or type(quantity) is not int or not 1 <= quantity <= 1000
            or type(price) is not int or price < 0
            or product_id in quantities
        ):
            return JsonResponse({'error': 'Savat ma’lumotlari noto‘g‘ri.'}, status=400)
        quantities[product_id] = quantity
        prices[product_id] = price

    normalized = {
        'customer_name': name.strip(), 'phone': phone.strip(), 'delivery_note': note,
        'card_message': message, 'anonymous_delivery': anonymous,
        'items': sorted((pk, quantities[pk], prices[pk]) for pk in quantities),
        'payment_method': payload['payment_method'],
    }
    fingerprint = hashlib.sha256(json.dumps(
        normalized, sort_keys=True, ensure_ascii=False,
    ).encode('utf-8')).hexdigest()

    def existing_response(order):
        if (
            order.customer_id is None or order.customer.user_id != request.mobile_user.pk
            or order.mobile_request_hash != fingerprint
        ):
            return JsonResponse({'error': 'Buyurtma so‘rovi avval ishlatilgan.'}, status=409)
        response = _mobile_order_payload(order)
        if order.payment_status == Order.PaymentStatus.PENDING:
            payment = order.payment_transactions.filter(
                status=PaymentTransaction.Status.PENDING,
                expires_at__gt=timezone.now(),
            ).order_by('-created_at').first()
            if payment:
                response['checkout_url'] = payment_checkout_url(
                    request, order, payment.provider, payment.amount_tiyin, payment,
                )
                response['payment_id'] = payment.pk
        return JsonResponse(response)

    existing = Order.objects.select_related('customer').filter(mobile_request_key=request_key).first()
    if existing:
        return existing_response(existing)
    provider = payload['payment_method']
    if provider == Order.Payment.UZUM or provider not in enabled_providers():
        return JsonResponse({'error': PAYMENT_UNAVAILABLE_MESSAGE}, status=409)
    customer, _ = Customer.objects.get_or_create(
        user=request.mobile_user,
        defaults={'name': name.strip(), 'phone': phone.strip()},
    )
    try:
        order, payment, checkout_url = create_order_for_payment(
            request,
            customer=customer,
            customer_name=name.strip(),
            phone=phone.strip(),
            address='',
            delivery_note=note,
            card_message=message,
            anonymous_delivery=anonymous,
            items=list(quantities.items()),
            provider=provider,
            mobile_request_key=request_key,
            mobile_request_hash=fingerprint,
        )
    except ValueError as error:
        return JsonResponse({'error': str(error)}, status=409)
    except IntegrityError:
        existing = Order.objects.select_related('customer').filter(mobile_request_key=request_key).first()
        if existing:
            return existing_response(existing)
        raise
    response = _mobile_order_payload(order)
    response.update({'checkout_url': checkout_url, 'payment_id': payment.pk})
    return JsonResponse(response, status=201)


@require_GET
@mobile_api_auth_required
def api_mobile_order_detail(request, order_id):
    order = Order.objects.filter(pk=order_id, customer__user=request.mobile_user).first()
    if order is None:
        return JsonResponse({'error': 'Buyurtma topilmadi.'}, status=404)
    payload = _mobile_order_payload(order)
    payment = order.payment_transactions.filter(
        status=PaymentTransaction.Status.PENDING,
        expires_at__gt=timezone.now(),
    ).order_by('-created_at').first()
    if payment:
        payload['checkout_url'] = payment_checkout_url(
            request, order, payment.provider, payment.amount_tiyin, payment,
        )
    return JsonResponse(payload)


@csrf_exempt
@require_POST
@mobile_api_auth_required
def api_mobile_order_payment_retry(request, order_id):
    order = Order.objects.filter(pk=order_id, customer__user=request.mobile_user).first()
    if order is None:
        return JsonResponse({'error': 'Buyurtma topilmadi.'}, status=404)
    try:
        payment, checkout_url = retry_payment_transaction(request, order)
    except ValueError as error:
        return JsonResponse({'error': str(error)}, status=409)
    order.refresh_from_db()
    payload = _mobile_order_payload(order)
    payload.update({'checkout_url': checkout_url, 'payment_id': payment.pk})
    return JsonResponse(payload)


@csrf_exempt
@require_POST
@mobile_api_auth_required
def api_mobile_order_delivery(request, order_id):
    payload, error = _mobile_json_body(request)
    if error:
        return error
    delivery = payload.get('delivery_required')
    if not isinstance(delivery, bool):
        return JsonResponse({'error': 'Yetkazib berish turini tanlang.'}, status=400)
    order = Order.objects.filter(pk=order_id, customer__user=request.mobile_user).first()
    if order is None:
        return JsonResponse({'error': 'Buyurtma topilmadi.'}, status=404)
    if (
        order.payment_method in ONLINE_PAYMENT_METHODS
        and order.payment_status != Order.PaymentStatus.PAID
    ):
        return JsonResponse({'error': 'Avans to‘lovi tasdiqlanmagan.'}, status=409)
    order.delivery_required = delivery
    order.save(update_fields=['delivery_required'])
    return JsonResponse(_mobile_order_payload(order))


def _create_mobile_access_token(user):
    raw_token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(days=30)
    token = MobileAccessToken.objects.create(
        user=user,
        token_hash=hashlib.sha256(raw_token.encode('utf-8')).hexdigest(),
        auth_hash=user.get_session_auth_hash(),
        expires_at=expires_at,
    )
    return raw_token, token


def _mobile_token_payload(raw_token, token):
    return {
        'access_token': raw_token,
        'token_type': 'Bearer',
        'expires_at': token.expires_at.isoformat(),
    }


@csrf_exempt
@require_POST
def api_mobile_login(request):
    payload, error_response = _mobile_json_body(request)
    if error_response:
        return error_response
    username = payload.get('username')
    password = payload.get('password')
    if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password:
        return JsonResponse({'error': 'Foydalanuvchi nomi va parolni kiriting.'}, status=400)

    user = authenticate(request, username=username.strip(), password=password)
    if user is None:
        return JsonResponse({'error': 'Foydalanuvchi nomi yoki parol noto‘g‘ri.'}, status=401)

    raw_token, token = _create_mobile_access_token(user)
    return JsonResponse(_mobile_token_payload(raw_token, token))


@csrf_exempt
@require_POST
def api_mobile_register(request):
    payload, error_response = _mobile_json_body(request)
    if error_response:
        return error_response

    form = CustomerRegistrationForm(data=payload)
    if not form.is_valid():
        error_list = next(iter(form.errors.values()), [])
        error_message = str(error_list[0]) if error_list else 'Ro‘yxatdan o‘tish ma’lumoti noto‘g‘ri.'
        return JsonResponse({'error': error_message}, status=400)

    with transaction.atomic():
        user = form.save()
        raw_token, token = _create_mobile_access_token(user)
    return JsonResponse(_mobile_token_payload(raw_token, token), status=201)


@require_GET
@mobile_api_auth_required
def api_mobile_account(request):
    user = request.mobile_user
    staff_role = get_staff_role(user) if user.is_staff else None
    customer = Customer.objects.filter(user=user).first()
    orders = (
        Order.objects.filter(customer=customer)
        .prefetch_related('items__product')[:20]
        if customer is not None
        else ()
    )
    return JsonResponse({
        'username': user.username,
        'full_name': user.get_full_name(),
        'email': user.email,
        'staff_role': staff_role if staff_role in (
            StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER,
        ) else None,
        'customer': {
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'cashback': customer.cashback,
        } if customer is not None else None,
        'orders': [
            {
                'id': order.pk,
                'order_code': order.order_code,
                'created_at': timezone.localtime(order.created_at).isoformat(),
                'status': order.get_status_display(),
                'status_code': order.status,
                'total': order.total,
                'items': [
                    {
                        'name': item.product.name,
                        'quantity': item.quantity,
                        'price': item.price,
                    }
                    for item in order.items.all()
                ],
            }
            for order in orders
        ],
    })


@require_GET
@mobile_api_auth_required
def api_mobile_dashboard(request):
    user = request.mobile_user
    role = get_staff_role(user) if user.is_staff else None
    if role not in (StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER):
        return JsonResponse({'error': 'Bu bo‘lim uchun ruxsatingiz yo‘q.'}, status=403)
    dashboard = _crm_dashboard_context(user, role)
    return JsonResponse({
        'orders_today': dashboard['orders_today'],
        'pending_orders': dashboard['pending_orders'],
        'today_revenue': dashboard['today_revenue'],
        'products_count': dashboard['products_count'],
        'recent_orders': [
            {
                'id': order.pk,
                'order_code': order.order_code,
                'customer_name': order.customer_name,
                'created_at': timezone.localtime(order.created_at).isoformat(),
                'status': order.get_status_display(),
                'total': order.total,
            }
            for order in dashboard['recent_orders']
        ],
        'low_stock': [
            {'name': product.name, 'category': product.category.name, 'quantity': product.stock_quantity}
            for product in dashboard['low_stock']
        ],
    })


@csrf_exempt
@require_POST
@mobile_api_auth_required
def api_mobile_logout(request):
    _, error_response = _mobile_json_body(request)
    if error_response:
        return error_response
    request.mobile_access_token.delete()
    return JsonResponse({'success': True})


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.annotate(likes_count=Count('likes')),
        slug=slug,
        in_stock=True,
        stock_quantity__gt=0,
    )
    related = Product.objects.filter(
        category=product.category,
        in_stock=True,
        stock_quantity__gt=0,
    ).exclude(pk=product.pk)[:4]
    return render(request, 'mimoza/product_detail.html', {
        'product': product,
        'related': related,
        'comments': product.comments.select_related('user')[:50],
        'is_liked': request.user.is_authenticated and product.likes.filter(user=request.user).exists(),
    })


def story_detail(request, story_id):
    story = get_object_or_404(
        Story.objects.select_related('product'),
        pk=story_id,
        is_active=True,
        expires_at__gt=timezone.now(),
    )
    return render(request, 'mimoza/story_detail.html', {'story': story})


def reels(request):
    products = (
        Product.objects.filter(in_stock=True, stock_quantity__gt=0)
        .exclude(video='')
        .select_related('category')
        .annotate(likes_count=Count('likes'))
    )
    linked_video_products = (
        Product.objects.filter(in_stock=True, stock_quantity__gt=0, video_url__gt='')
        .exclude(pk__in=products.values('pk'))
        .select_related('category')
        .annotate(likes_count=Count('likes'))
    )
    video_products = list(products) + list(linked_video_products)
    liked_product_ids = (
        set(
            ProductLike.objects.filter(user=request.user, product__in=video_products)
            .values_list('product_id', flat=True)
        )
        if request.user.is_authenticated
        else set()
    )
    return render(request, 'mimoza/reels.html', {
        'video_products': video_products,
        'liked_product_ids': liked_product_ids,
    })


@login_required(login_url='account_login')
@require_POST
def product_like_toggle(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    like, created = ProductLike.objects.get_or_create(product=product, user=request.user)
    if not created:
        like.delete()
    return redirect('product_detail', slug=product.slug)


@login_required(login_url='account_login')
@require_POST
def product_comment_create(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    text = request.POST.get('text', '').strip()
    if not text:
        messages.error(request, 'Izoh matnini kiriting.')
    elif len(text) > 1000:
        messages.error(request, 'Izoh 1000 ta belgidan oshmasligi kerak.')
    else:
        ProductComment.objects.create(product=product, user=request.user, text=text)
        messages.success(request, 'Izohingiz qo‘shildi.')
    return redirect(f'{reverse("product_detail", args=(product.slug,))}#product-comments')


def contact(request):
    phone_digits = ''.join(character for character in settings.CONTACT_PHONE if character.isdigit())
    if len(phone_digits) == 9:
        phone_digits = f'998{phone_digits}'
    phone_number = f'+{phone_digits}' if phone_digits.startswith('998') else settings.CONTACT_PHONE
    return render(request, 'mimoza/contact.html', {
        'contact_phone': settings.CONTACT_PHONE,
        'contact_phone_link': f'tel:{phone_number}',
        'instagram_contact_username': settings.INSTAGRAM_CONTACT_USERNAME,
        'instagram_contact_url': settings.INSTAGRAM_CONTACT_URL,
        'telegram_contact_username': settings.TELEGRAM_CONTACT_USERNAME,
        'telegram_contact_url': settings.TELEGRAM_CONTACT_URL,
        'shop_location_url': settings.SHOP_LOCATION_URL,
        'shop_location_embed_url': settings.SHOP_LOCATION_EMBED_URL,
    })


@login_required(login_url='account_login')
@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, in_stock=True, stock_quantity__gt=0)
    cart = request.session.get('cart', {})
    key = str(product.pk)
    cart[key] = cart.get(key, 0) + 1
    request.session['cart'] = cart
    destination = request.POST.get('next')
    if destination in ('catalog', 'home', 'cart'):
        return redirect(destination)
    return redirect('cart')


@login_required(login_url='account_login')
@require_POST
def cart_update(request, product_id):
    cart = request.session.get('cart', {})
    quantity = int(request.POST.get('quantity', 1))
    key = str(product_id)
    if quantity > 0:
        cart[key] = quantity
    else:
        cart.pop(key, None)
    request.session['cart'] = cart
    return redirect('cart')


@login_required(login_url='account_login')
def cart(request):
    cart = request.session.get('cart', {})
    items = []
    total = 0
    for product_id, quantity in cart.items():
        product = Product.objects.filter(pk=product_id, in_stock=True, stock_quantity__gt=0).first()
        if product:
            subtotal = product.price * quantity
            total += subtotal
            items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
    return render(request, 'mimoza/cart.html', {'items': items, 'total': total})


@login_required(login_url='account_login')
def checkout(request):
    web_payment_key = str(uuid.uuid4()) if request.method == 'GET' else request.POST.get('web_payment_key', '')
    cart = request.session.get('cart', {})
    items = []
    total = 0
    for product_id, quantity in cart.items():
        product = Product.objects.filter(pk=product_id).first()
        if product:
            subtotal = product.price * quantity
            total += subtotal
            items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
    providers = enabled_providers()
    provider_labels = {
        PaymentTransaction.Provider.CLICK: 'Click',
        PaymentTransaction.Provider.PAYME: 'Payme',
    }
    payment_error = ''
    if request.method == 'POST':
        try:
            request_key = uuid.UUID(web_payment_key)
        except (TypeError, ValueError):
            request_key = None
        provider = request.POST.get('payment_method', '')
        name = request.POST.get('customer_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()
        existing = (
            Order.objects.select_related('customer')
            .filter(web_payment_key=request_key).first()
            if request_key else None
        )
        if not request_key:
            payment_error = 'Sahifa yangilang va qayta urinib ko‘ring.'
        elif existing:
            if (
                existing.customer_id
                and existing.customer.user_id == request.user.pk
                and existing.payment_method == provider
            ):
                if existing.payment_status == Order.PaymentStatus.PAID:
                    return redirect('payment_return', order_id=existing.pk)
                payment = existing.payment_transactions.filter(
                    status=PaymentTransaction.Status.PENDING,
                    expires_at__gt=timezone.now(),
                ).order_by('-created_at').first()
                if payment:
                    return redirect(payment.checkout_url)
                return redirect('payment_return', order_id=existing.pk)
            payment_error = 'Bu to‘lov so‘rovidan foydalanib bo‘lmaydi. Sahifani yangilang.'
        elif provider not in providers:
            payment_error = PAYMENT_UNAVAILABLE_MESSAGE
        elif not items or not name or len(name) > 150 or not phone or len(phone) > 30 or len(address) > 1000:
            payment_error = 'Mijoz ma’lumotlari va savatni tekshiring.'
        else:
            try:
                customer, _ = Customer.objects.get_or_create(
                    user=request.user,
                    defaults={'name': name, 'phone': phone, 'address': address},
                )
                order, _, checkout_url = create_order_for_payment(
                    request,
                    customer=customer,
                    customer_name=name,
                    phone=phone,
                    address=address,
                    items=[(item['product'].pk, item['quantity']) for item in items],
                    provider=provider,
                    web_payment_key=request_key,
                )
            except ValueError as error:
                payment_error = str(error)
            except IntegrityError:
                existing = Order.objects.select_related('customer').filter(
                    web_payment_key=request_key,
                ).first()
                if not (
                    existing
                    and existing.customer_id
                    and existing.customer.user_id == request.user.pk
                    and existing.payment_method == provider
                ):
                    raise
                payment = existing.payment_transactions.filter(
                    status=PaymentTransaction.Status.PENDING,
                    expires_at__gt=timezone.now(),
                ).order_by('-created_at').first()
                if payment:
                    return redirect(payment.checkout_url)
                return redirect('payment_return', order_id=existing.pk)
            else:
                request.session.pop('cart', None)
                return redirect(checkout_url)
    if request.method == 'POST' and payment_error:
        response_status = 409 if payment_error == PAYMENT_UNAVAILABLE_MESSAGE else 400
    else:
        response_status = 200
    customer = Customer.objects.filter(user=request.user).first()
    response = render(request, 'mimoza/checkout.html', {
        'items': items,
        'total': total,
        'advance': Decimal(total) * Decimal('0.30'),
        'remaining': Decimal(total) * Decimal('0.70'),
        'payment_error': payment_error,
        'web_payment_key': web_payment_key,
        'providers': [(provider, provider_labels[provider]) for provider in providers],
        'customer_name': request.POST.get('customer_name', customer.name if customer else request.user.get_full_name()),
        'customer_phone': request.POST.get('phone', customer.phone if customer else ''),
        'customer_address': request.POST.get('address', customer.address if customer else ''),
    }, status=response_status)
    return response


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def payment_return(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    is_owner = order.customer_id and order.customer.user_id == request.user.pk
    return render(request, 'mimoza/payment_return.html', {
        'order': order if is_owner else None,
    })


@login_required(login_url='account_login')
@require_POST
def retry_order_payment(request, order_id):
    order = get_object_or_404(Order, pk=order_id, customer__user=request.user)
    try:
        _, checkout_url = retry_payment_transaction(request, order)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect('payment_return', order_id=order.pk)
    return redirect(checkout_url)


@login_required(login_url='account_login')
@require_POST
def order_delivery_choice(request, order_id):
    order = get_object_or_404(Order, pk=order_id, customer__user=request.user)
    if (
        order.payment_method in (Order.Payment.CLICK, Order.Payment.PAYME, Order.Payment.UZUM)
        and order.payment_status != Order.PaymentStatus.PAID
    ):
        messages.error(request, 'Avans to‘lovi tasdiqlanmaguncha buyurtma davom ettirilmaydi.')
        return redirect('account')
    choice = request.POST.get('delivery_required')
    if choice not in ('yes', 'no'):
        messages.error(request, 'Yetkazib berish yoki do‘kondan olib ketishni tanlang.')
        return redirect('account')

    order.delivery_required = choice == 'yes'
    order.save(update_fields=['delivery_required'])
    if order.delivery_required:
        messages.success(request, 'Buyurtma yetkazib berish uchun belgilandi. Telegram’da lokatsiyangizni yuboring.')
    else:
        messages.success(request, 'Buyurtma do‘kondan olib ketish uchun belgilandi.')
    return render(request, 'mimoza/order_success.html', {
        'order': order,
        'order_qr_data_url': order_qr_data_url(order),
        'telegram_order_url': order_telegram_url(order) if order.delivery_required else '',
        'telegram_contact_username': settings.TELEGRAM_CONTACT_USERNAME,
    })


@login_required(login_url='account_login')
@require_GET
def order_qr(request, order_id):
    order = get_object_or_404(Order, pk=order_id, customer__user=request.user)
    return HttpResponse(order_qr_png(order), content_type='image/png')


def redirect_after_account_authentication(request):
    next_url = request.GET.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect('account')


def account_login(request):
    form = CustomerAuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect_after_account_authentication(request)
    return render(request, 'mimoza/account_login.html', {'form': form})


def account_register(request):
    if request.user.is_authenticated:
        return redirect('account')
    form = CustomerRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect_after_account_authentication(request)
    return render(request, 'mimoza/account_register.html', {'form': form})


@login_required(login_url='account_login')
def account(request):
    customer = Customer.objects.filter(user=request.user).first()
    orders = customer.orders.prefetch_related('items__product') if customer else Order.objects.none()
    important_dates = customer.important_dates.all() if customer else ImportantDate.objects.none()
    return render(request, 'mimoza/account.html', {
        'customer': customer,
        'orders': orders[:20],
        'important_dates': important_dates,
        'important_date_form': ImportantDateForm(),
        'web_push_public_key': settings.WEBPUSH_VAPID_PUBLIC_KEY,
        'web_push_configured': bool(
            settings.WEBPUSH_VAPID_PUBLIC_KEY
            and settings.WEBPUSH_VAPID_PRIVATE_KEY
            and settings.WEBPUSH_VAPID_SUBJECT
        ),
    })


@login_required(login_url='account_login')
@require_POST
def important_date_create(request):
    customer = Customer.objects.filter(user=request.user).first()
    if customer is None:
        messages.error(request, 'Muhim sana saqlash uchun mijoz profili topilmadi.')
        return redirect('account')
    form = ImportantDateForm(request.POST)
    if form.is_valid():
        important_date = form.save(commit=False)
        important_date.customer = customer
        important_date.save()
        messages.success(request, 'Muhim sana saqlandi.')
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect('account')


@login_required(login_url='account_login')
@require_POST
def important_date_update(request, date_id):
    important_date = get_object_or_404(
        ImportantDate,
        pk=date_id,
        customer__user=request.user,
    )
    form = ImportantDateForm(request.POST, instance=important_date)
    if form.is_valid():
        form.save()
        messages.success(request, 'Muhim sana yangilandi.')
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect('account')


@login_required(login_url='account_login')
@require_POST
def important_date_delete(request, date_id):
    important_date = get_object_or_404(
        ImportantDate,
        pk=date_id,
        customer__user=request.user,
    )
    important_date.delete()
    messages.success(request, 'Muhim sana o‘chirildi.')
    return redirect('account')


def is_supported_push_endpoint(endpoint):
    parsed = urlparse(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in (None, 443) or len(endpoint) > 2048:
        return False
    hostname = parsed.hostname.lower()
    return (
        hostname == 'fcm.googleapis.com'
        or hostname == 'web.push.apple.com'
        or hostname.endswith('.push.services.mozilla.com')
        or hostname.endswith('.notify.windows.com')
    )


@login_required(login_url='account_login')
@require_POST
def push_subscription_create(request):
    if len(request.body) > 8192:
        return JsonResponse({'error': 'Push ma’lumoti juda katta.'}, status=413)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Push ma’lumoti noto‘g‘ri JSON formatida.'}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({'error': 'Push ma’lumoti noto‘g‘ri.'}, status=400)

    subscription = data.get('subscription')
    if not isinstance(subscription, dict):
        return JsonResponse({'error': 'Brauzer obunasi topilmadi.'}, status=400)
    endpoint = subscription.get('endpoint')
    keys = subscription.get('keys')
    if not isinstance(endpoint, str) or not isinstance(keys, dict):
        return JsonResponse({'error': 'Push obunasi ma’lumotlari to‘liq emas.'}, status=400)
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')
    if (
        not is_supported_push_endpoint(endpoint)
        or not isinstance(p256dh, str)
        or not p256dh
        or len(p256dh) > 255
        or not isinstance(auth, str)
        or not auth
        or len(auth) > 255
    ):
        return JsonResponse({'error': 'Push obunasi ma’lumotlari noto‘g‘ri.'}, status=400)

    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={'user': request.user, 'p256dh': p256dh, 'auth': auth},
    )
    return JsonResponse({'subscribed': True}, status=201)


@login_required(login_url='account_login')
@require_POST
def push_subscription_delete(request):
    if len(request.body) > 8192:
        return JsonResponse({'error': 'Push ma’lumoti juda katta.'}, status=413)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Push ma’lumoti noto‘g‘ri JSON formatida.'}, status=400)
    endpoint = data.get('endpoint') if isinstance(data, dict) else None
    if not isinstance(endpoint, str) or not is_supported_push_endpoint(endpoint):
        return JsonResponse({'error': 'Push manzili noto‘g‘ri.'}, status=400)
    PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    return JsonResponse({'subscribed': False})


@require_GET
def service_worker(request):
    worker_path = settings.BASE_DIR / 'static' / 'js' / 'service-worker.js'
    response = HttpResponse(worker_path.read_text(encoding='utf-8'), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


@require_POST
def account_logout(request):
    logout(request)
    return redirect('home')


@role_required(
    StaffProfile.Role.SUPER_ADMIN,
    StaffProfile.Role.MANAGER,
    StaffProfile.Role.FLORIST,
    StaffProfile.Role.COURIER,
)
def crm_dashboard(request):
    return render(request, 'mimoza/crm_dashboard.html', _crm_dashboard_context(request.user, request.crm_role))


def _crm_dashboard_context(user, role):
    today = timezone.localdate()
    orders = _orders_ready_for_fulfillment(Order.objects.all())
    if role == StaffProfile.Role.FLORIST:
        orders = orders.filter(assigned_florist=user)
    elif role == StaffProfile.Role.COURIER:
        orders = orders.filter(assigned_courier=user)
    today_orders = orders.filter(created_at__date=today)
    recent_orders = orders.order_by('-created_at')[:8]
    low_stock = Product.objects.filter(stock_quantity__lte=5).select_related('category').order_by('stock_quantity')[:6]
    context = {
        'orders_today': today_orders.count(),
        'pending_orders': orders.filter(status=Order.Status.PENDING).count(),
        'today_revenue': (
            today_orders.exclude(status=Order.Status.CANCELLED).aggregate(total=Sum('total'))['total'] or 0
            if role in (StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER)
            else 0
        ),
        'products_count': Product.objects.count(),
        'low_stock': low_stock,
        'can_view_finance': role in (StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER),
        'can_view_inventory': role != StaffProfile.Role.COURIER,
        'recent_orders': recent_orders,
    }
    return context


@role_required(*StaffProfile.Role.values)
def crm_orders(request):
    orders = Order.objects.select_related(
        'assigned_florist',
        'assigned_courier',
    ).prefetch_related('items__product')
    if request.crm_role == StaffProfile.Role.FLORIST:
        orders = orders.filter(assigned_florist=request.user)
    elif request.crm_role == StaffProfile.Role.COURIER:
        orders = orders.filter(assigned_courier=request.user)
    status = request.GET.get('status', '').strip()
    query = request.GET.get('q', '').strip()
    orders = _filter_crm_orders(orders, status, query)
    can_assign = request.crm_role in (StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER)
    can_view_finance = request.crm_role not in (StaffProfile.Role.COURIER, StaffProfile.Role.SHOPKEEPER)
    orders = list(orders[:100])
    for order in orders:
        order.allowed_statuses = allowed_order_statuses(order, request.crm_role, request.user)
    return render(request, 'mimoza/crm_orders.html', {
        'orders': orders,
        'statuses': Order.Status.choices,
        'can_assign': can_assign,
        'can_view_finance': can_view_finance,
        'florists': User.objects.filter(
            is_staff=True,
            mimoza_profile__role=StaffProfile.Role.FLORIST,
            mimoza_profile__is_active_worker=True,
        ).order_by('username'),
        'couriers': User.objects.filter(
            is_staff=True,
            mimoza_profile__role=StaffProfile.Role.COURIER,
            mimoza_profile__is_active_worker=True,
        ).order_by('username'),
        'selected_status': status,
        'query': query,
    })


def _filter_crm_orders(orders, status, query):
    if status in Order.Status.values:
        orders = orders.filter(status=status)
    if query:
        qr_value = query.upper()
        for prefix in ('MIMOZA-ORDER:', 'MIMOZA:'):
            if qr_value.startswith(prefix):
                qr_value = qr_value[len(prefix):].strip()
                break
        if qr_value.startswith('MZ-'):
            qr_value = qr_value[3:]
        if qr_value.startswith('#'):
            qr_value = qr_value[1:]
        search_filter = (
            Q(customer_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(address__icontains=query)
            | Q(items__product__name__icontains=query)
        )
        if qr_value.isdecimal() and len(qr_value) <= 18:
            search_id = int(qr_value)
            search_filter |= Q(pk=search_id) | Q(items__product_id=search_id)
            if len(qr_value) == 5:
                search_filter |= Q(order_code=qr_value)
        try:
            search_filter |= Q(qr_token=uuid.UUID(qr_value))
        except ValueError:
            pass
        orders = orders.filter(search_filter).distinct()
    return orders


@role_required(*StaffProfile.Role.values)
def crm_order_notification_count(request):
    return JsonResponse({'count': request.crm_notification_count})


@role_required(*StaffProfile.Role.values)
@require_POST
def crm_order_status(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    status = request.POST.get('status')
    if status not in Order.Status.values:
        messages.error(request, 'Buyurtma holati noto‘g‘ri.')
        return redirect('crm_orders')
    if (
        order.payment_method in ONLINE_PAYMENT_METHODS
        and order.payment_status != Order.PaymentStatus.PAID
        and status != order.status
    ):
        messages.error(request, 'Avans to‘lovi tasdiqlanmaguncha buyurtmani tayyorlash mumkin emas.')
        return redirect('crm_orders')
    if request.crm_role == StaffProfile.Role.SHOPKEEPER:
        if status not in allowed_order_statuses(order, request.crm_role, request.user):
            return HttpResponseForbidden('Buyurtma holatini bu bosqichdan o‘zgartirib bo‘lmaydi.')
    elif request.crm_role == StaffProfile.Role.FLORIST:
        if (
            order.assigned_florist_id != request.user.id
            or order.status != Order.Status.PENDING
            or status != Order.Status.PROCESSING
        ):
            return HttpResponseForbidden('Bu buyurtma sizga biriktirilmagan yoki holatni o‘zgartirishga ruxsatingiz yo‘q.')
    elif request.crm_role == StaffProfile.Role.COURIER:
        valid_transition = (
            order.assigned_courier_id == request.user.id
            and (
                (order.status == Order.Status.PROCESSING and status == Order.Status.SHIPPED)
                or (order.status == Order.Status.SHIPPED and status == Order.Status.DELIVERED)
            )
        )
        if not valid_transition:
            return HttpResponseForbidden('Faqat o‘zingizga biriktirilgan yetkazmani keyingi holatga o‘tkaza olasiz.')
    order.status = status
    order.save(update_fields=['status'])
    return redirect(request.POST.get('next') or 'crm_orders')


@role_required(StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER)
@require_POST
def crm_order_assignments(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    assignments = (
        ('assigned_florist', 'florist_id', StaffProfile.Role.FLORIST, 'Florist'),
        ('assigned_courier', 'courier_id', StaffProfile.Role.COURIER, 'Kuryer'),
    )
    for field, request_key, role, label in assignments:
        user_id = request.POST.get(request_key, '').strip()
        if not user_id:
            setattr(order, field, None)
            continue
        worker = User.objects.filter(
            pk=user_id,
            is_staff=True,
            mimoza_profile__role=role,
            mimoza_profile__is_active_worker=True,
        ).first()
        if worker is None:
            messages.error(request, f'{label} tanlovi noto‘g‘ri yoki xodim faol emas.')
            return redirect('crm_orders')
        setattr(order, field, worker)
    order.save(update_fields=['assigned_florist', 'assigned_courier'])
    messages.success(request, 'Buyurtma xodimlarga biriktirildi.')
    return redirect('crm_orders')


@role_required(StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER, StaffProfile.Role.FLORIST)
def crm_products(request):
    query = request.GET.get('q', '').strip()
    products = Product.objects.select_related('category')
    if query:
        products = products.filter(Q(name__icontains=query) | Q(category__name__icontains=query))
    return render(request, 'mimoza/crm_products.html', {
        'products': products[:100],
        'query': query,
        'low_stock_count': Product.objects.filter(stock_quantity__lte=5).count(),
        'can_manage_catalog': request.crm_role in (StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER),
    })


@role_required(StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER, StaffProfile.Role.FLORIST)
@require_POST
def crm_product_stock(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    try:
        quantity = int(request.POST.get('stock_quantity', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Ombor miqdorini butun son bilan kiriting.')
        return redirect('crm_products')
    if quantity < 0:
        messages.error(request, 'Ombor miqdori manfiy bo‘lishi mumkin emas.')
        return redirect('crm_products')
    product.stock_quantity = quantity
    product.in_stock = quantity > 0
    product.save(update_fields=['stock_quantity', 'in_stock'])
    return redirect('crm_products')


@role_required(StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER)
def crm_analytics(request):
    try:
        days = int(request.GET.get('days', '30'))
    except (TypeError, ValueError):
        days = 30
    if days not in (7, 30, 90):
        days = 30
    return render(request, 'mimoza/crm_analytics.html', _crm_analytics_context(days))


def _crm_analytics_context(days):
    start_date = timezone.localdate() - timedelta(days=days - 1)
    orders = _orders_ready_for_fulfillment(
        Order.objects.filter(created_at__date__gte=start_date),
    )
    completed = orders.exclude(status=Order.Status.CANCELLED)
    daily_sales = (
        completed.values('created_at__date')
        .annotate(revenue=Sum('total'), orders_count=Count('id'))
        .order_by('created_at__date')
    )
    context = {
        'days': days,
        'sales_total': completed.aggregate(total=Sum('total'))['total'] or 0,
        'orders_count': orders.count(),
        'average_order': completed.aggregate(total=Sum('total'), count=Count('id')),
        'cancelled_count': orders.filter(status=Order.Status.CANCELLED).count(),
        'daily_sales': daily_sales,
        'top_products': OrderItem.objects.filter(order__in=completed)
        .annotate(line_revenue=F('price') * F('quantity'))
        .values('product__name')
        .annotate(
            quantity=Sum('quantity'),
            revenue=Sum('line_revenue'),
        )
        .order_by('-quantity')[:5],
    }
    completed_count = context['average_order']['count'] or 0
    context['average_order'] = (
        context['average_order']['total'] // completed_count if completed_count else 0
    )
    return context


@role_required(StaffProfile.Role.SUPER_ADMIN)
def crm_users(request):
    staff_users = User.objects.filter(is_staff=True).select_related('mimoza_profile').order_by('username')
    profiles = {profile.user_id: profile for profile in StaffProfile.objects.filter(user__in=staff_users)}
    for staff_user in staff_users:
        profile = profiles.get(staff_user.pk)
        staff_user.staff_profile = profile
        staff_user.role_value = (
            profile.role if profile
            else StaffProfile.Role.SUPER_ADMIN if staff_user.is_superuser
            else StaffProfile.Role.MANAGER
        )
        staff_user.staff_phone = profile.phone if profile else ''
        staff_user.worker_active = profile.is_active_worker if profile else staff_user.is_active
    return render(request, 'mimoza/crm_users.html', {
        'staff_users': staff_users,
        'roles': StaffProfile.Role.choices,
    })


@role_required(StaffProfile.Role.SUPER_ADMIN)
def crm_audit_history(request):
    entries = AuditLog.objects.select_related('actor').all()
    page_obj = Paginator(entries, 50).get_page(request.GET.get('page'))
    return render(request, 'mimoza/crm_audit_history.html', {'page_obj': page_obj})


@role_required(StaffProfile.Role.SUPER_ADMIN)
@require_POST
def crm_user_role(request, user_id):
    staff_user = get_object_or_404(User, pk=user_id, is_staff=True)
    role = request.POST.get('role')
    if role not in StaffProfile.Role.values:
        messages.error(request, 'Xodim roli noto‘g‘ri.')
        return redirect('crm_users')
    StaffProfile.objects.update_or_create(user=staff_user, defaults={'role': role})
    return redirect('crm_users')
