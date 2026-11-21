import json
from datetime import timedelta
from functools import wraps
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import CustomerAuthenticationForm, CustomerRegistrationForm, ImportantDateForm
from .models import (
    Category,
    Customer,
    ImportantDate,
    Order,
    OrderItem,
    Product,
    ProductComment,
    ProductLike,
    PushSubscription,
    StaffProfile,
    Story,
)

User = get_user_model()


def get_staff_role(user):
    if user.is_superuser:
        return StaffProfile.Role.SUPER_ADMIN
    profile = StaffProfile.objects.filter(user=user).first()
    if not profile or not profile.is_active_worker:
        return None
    return profile.role


def get_staff_notification_count(role, user):
    orders = Order.objects.all()
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
    cart = request.session.get('cart', {})
    items = []
    total = 0
    for product_id, quantity in cart.items():
        product = Product.objects.filter(pk=product_id).first()
        if product:
            subtotal = product.price * quantity
            total += subtotal
            items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
    payment_error = ''
    delivery_error = ''
    stock_error = ''
    if request.method == 'POST' and items:
        payment_method = request.POST.get('payment_method', Order.Payment.CASH)
        if payment_method != Order.Payment.CASH:
            payment_error = (
                'Click, Payme va Uzum hisoblari hali ochilmagani uchun elektron to‘lov vaqtincha ishlamaydi. '
                'Hozircha kuryerga naqd to‘lovni tanlang.'
            )
        delivery_choice = request.POST.get('delivery_required')
        if delivery_choice not in ('yes', 'no'):
            delivery_error = 'Yetkazib berish kerak yoki kerak emasligini tanlang.'
        if payment_error or delivery_error:
            return render(request, 'mimoza/checkout.html', {
                'items': items,
                'total': total,
                'payment_error': payment_error,
                'delivery_error': delivery_error,
                'telegram_contact_url': settings.TELEGRAM_CONTACT_URL,
                'telegram_contact_username': settings.TELEGRAM_CONTACT_USERNAME,
                'form_data': request.POST,
            })
        with transaction.atomic():
            locked_products = {
                product.pk: product
                for product in Product.objects.select_for_update()
                .filter(pk__in=[item['product'].pk for item in items])
                .order_by('pk')
            }
            for item in items:
                product = locked_products.get(item['product'].pk)
                if (
                    product is None
                    or not product.in_stock
                    or item['quantity'] > product.stock_quantity
                ):
                    available = product.stock_quantity if product and product.in_stock else 0
                    stock_error = (
                        f'{item["product"].name} uchun omborda {available} ta qoldi. '
                        'Savatdagi miqdorni yangilang.'
                    )
                    break

            if not stock_error:
                customer = None
                if request.user.is_authenticated:
                    customer = Customer.objects.filter(user=request.user).first()
                total = sum(
                    locked_products[item['product'].pk].price * item['quantity']
                    for item in items
                )
                order = Order.objects.create(
                    customer=customer,
                    customer_name=request.POST.get('customer_name', '').strip(),
                    phone=request.POST.get('phone', '').strip(),
                    address='',
                    delivery_required=delivery_choice == 'yes',
                    delivery_note=request.POST.get('delivery_note', '').strip(),
                    card_message=request.POST.get('card_message', '').strip(),
                    anonymous_delivery=request.POST.get('anonymous_delivery') == 'on',
                    payment_method=payment_method,
                    payment_status=Order.PaymentStatus.UNPAID,
                    total=total,
                )
                for item in items:
                    product = locked_products[item['product'].pk]
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=item['quantity'],
                        price=product.price,
                    )
                    product.stock_quantity -= item['quantity']
                    if product.stock_quantity == 0:
                        product.in_stock = False
                    product.save(update_fields=['stock_quantity', 'in_stock'])

        if stock_error:
            return render(request, 'mimoza/checkout.html', {
                'items': items,
                'total': total,
                'stock_error': stock_error,
                'telegram_contact_url': settings.TELEGRAM_CONTACT_URL,
                'telegram_contact_username': settings.TELEGRAM_CONTACT_USERNAME,
                'form_data': request.POST,
            })
        request.session['cart'] = {}
        return render(request, 'mimoza/order_success.html', {
            'order': order,
            'telegram_contact_url': settings.TELEGRAM_CONTACT_URL,
            'telegram_contact_username': settings.TELEGRAM_CONTACT_USERNAME,
        })
    return render(request, 'mimoza/checkout.html', {
        'items': items,
        'total': total,
        'telegram_contact_url': settings.TELEGRAM_CONTACT_URL,
        'telegram_contact_username': settings.TELEGRAM_CONTACT_USERNAME,
    })


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


@role_required(*StaffProfile.Role.values)
def crm_dashboard(request):
    today = timezone.localdate()
    orders = Order.objects.all()
    if request.crm_role == StaffProfile.Role.FLORIST:
        orders = orders.filter(assigned_florist=request.user)
    elif request.crm_role == StaffProfile.Role.COURIER:
        orders = orders.filter(assigned_courier=request.user)
    today_orders = orders.filter(created_at__date=today)
    recent_orders = orders.order_by('-created_at')[:8]
    low_stock = Product.objects.filter(stock_quantity__lte=5).select_related('category').order_by('stock_quantity')[:6]
    context = {
        'orders_today': today_orders.count(),
        'pending_orders': orders.filter(status=Order.Status.PENDING).count(),
        'today_revenue': (
            today_orders.exclude(status=Order.Status.CANCELLED).aggregate(total=Sum('total'))['total'] or 0
            if request.crm_role in (StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER)
            else 0
        ),
        'products_count': Product.objects.count(),
        'low_stock': low_stock,
        'can_view_finance': request.crm_role in (StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER),
        'can_view_inventory': request.crm_role != StaffProfile.Role.COURIER,
        'recent_orders': recent_orders,
    }
    return render(request, 'mimoza/crm_dashboard.html', context)


@role_required(*StaffProfile.Role.values)
def crm_orders(request):
    orders = Order.objects.select_related('assigned_florist', 'assigned_courier')
    if request.crm_role == StaffProfile.Role.FLORIST:
        orders = orders.filter(assigned_florist=request.user)
    elif request.crm_role == StaffProfile.Role.COURIER:
        orders = orders.filter(assigned_courier=request.user)
    status = request.GET.get('status', '').strip()
    query = request.GET.get('q', '').strip()
    if status in Order.Status.values:
        orders = orders.filter(status=status)
    if query:
        orders = orders.filter(
            Q(customer_name__icontains=query) | Q(phone__icontains=query) | Q(address__icontains=query)
        )
    return render(request, 'mimoza/crm_orders.html', {
        'orders': orders[:100],
        'statuses': (
            [(Order.Status.PROCESSING, Order.Status.PROCESSING.label)]
            if request.crm_role == StaffProfile.Role.FLORIST
            else [
                (Order.Status.SHIPPED, Order.Status.SHIPPED.label),
                (Order.Status.DELIVERED, Order.Status.DELIVERED.label),
            ]
            if request.crm_role == StaffProfile.Role.COURIER
            else Order.Status.choices
        ),
        'can_assign': request.crm_role in (StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER),
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
    if request.crm_role == StaffProfile.Role.FLORIST:
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
    start_date = timezone.localdate() - timedelta(days=days - 1)
    orders = Order.objects.filter(created_at__date__gte=start_date)
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
    return render(request, 'mimoza/crm_analytics.html', context)


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
@require_POST
def crm_user_role(request, user_id):
    staff_user = get_object_or_404(User, pk=user_id, is_staff=True)
    role = request.POST.get('role')
    if role not in StaffProfile.Role.values:
        messages.error(request, 'Xodim roli noto‘g‘ri.')
        return redirect('crm_users')
    StaffProfile.objects.update_or_create(user=staff_user, defaults={'role': role})
    return redirect('crm_users')
