import hashlib
import json
from functools import wraps

from django import forms
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import AuditLog, Category, Order, Product, StaffProfile
from .views import (
    _crm_analytics_context,
    _filter_crm_orders,
    _mobile_json_body,
    get_staff_role,
    mobile_api_auth_required,
)

User = get_user_model()
ADMIN_ROLES = (StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER)


def mobile_admin_required(*roles):
    def decorator(view):
        @wraps(view)
        @mobile_api_auth_required
        def wrapped(request, *args, **kwargs):
            user = request.mobile_user
            role = get_staff_role(user) if user.is_staff else None
            if role not in roles:
                return JsonResponse({'error': 'Bu bo‘lim uchun ruxsatingiz yo‘q.'}, status=403)
            request.mobile_role = role
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def _page(request, queryset):
    raw = request.GET.get('page', '1')
    if not raw.isascii() or not raw.isdigit() or len(raw) > 9 or int(raw) < 1:
        return None, JsonResponse({'error': 'Sahifa raqami noto‘g‘ri.'}, status=400)
    page = Paginator(queryset, 25).get_page(int(raw))
    return page, None


def _order(order):
    return {
        'id': order.pk,
        'code': order.order_code,
        'customer_name': order.customer_name,
        'phone': order.phone,
        'created_at': order.created_at.isoformat(),
        'status': order.status,
        'total': order.total,
        'delivery_required': order.delivery_required,
        'payment': order.get_payment_method_display(),
        'payment_status': order.get_payment_status_display(),
        'florist_id': order.assigned_florist_id,
        'courier_id': order.assigned_courier_id,
        'items': [
            {'product_id': item.product_id, 'name': item.product.name, 'quantity': item.quantity}
            for item in order.items.all()
        ],
    }


@require_GET
@mobile_admin_required(*ADMIN_ROLES)
def orders(request):
    status = request.GET.get('status', '').strip()
    if status and status not in Order.Status.values:
        return JsonResponse({'error': 'Buyurtma holati noto‘g‘ri.'}, status=400)
    query = request.GET.get('q', '').strip()
    queryset = _filter_crm_orders(
        Order.objects.prefetch_related('items__product').order_by('-created_at', '-pk'),
        status, query,
    )
    page, error = _page(request, queryset)
    if error:
        return error
    workers = User.objects.filter(
        is_staff=True, is_active=True, mimoza_profile__is_active_worker=True,
        mimoza_profile__role__in=(StaffProfile.Role.FLORIST, StaffProfile.Role.COURIER),
    ).select_related('mimoza_profile').order_by('username')
    return JsonResponse({
        'orders': [_order(order) for order in page],
        'has_next': page.has_next(),
        'statuses': [{'value': value, 'label': label} for value, label in Order.Status.choices],
        'workers': [
            {'id': user.pk, 'name': user.get_full_name() or user.username, 'role': user.mimoza_profile.role}
            for user in workers
        ],
    })


@csrf_exempt
@require_POST
@mobile_admin_required(*ADMIN_ROLES)
def order_update(request, order_id):
    body, error = _mobile_json_body(request)
    if error:
        return error
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return JsonResponse({'error': 'Buyurtma topilmadi.'}, status=404)
    status = body.get('status')
    if status not in Order.Status.values:
        return JsonResponse({'error': 'Buyurtma holati noto‘g‘ri.'}, status=400)
    if (
        order.payment_method in (Order.Payment.CLICK, Order.Payment.PAYME, Order.Payment.UZUM)
        and order.payment_status != Order.PaymentStatus.PAID
        and status != order.status
    ):
        return JsonResponse({'error': 'Avans to‘lovi tasdiqlanmaguncha buyurtmani tayyorlash mumkin emas.'}, status=409)
    workers = {}
    for key, role in (('florist_id', StaffProfile.Role.FLORIST), ('courier_id', StaffProfile.Role.COURIER)):
        worker_id = body.get(key)
        if worker_id is not None and (type(worker_id) is not int or worker_id < 1):
            return JsonResponse({'error': 'Xodim tanlovi noto‘g‘ri.'}, status=400)
        if worker_id is not None:
            worker = User.objects.filter(
                pk=worker_id, is_staff=True, is_active=True,
                mimoza_profile__role=role, mimoza_profile__is_active_worker=True,
            ).first()
            if worker is None:
                return JsonResponse({'error': 'Xodim topilmadi yoki faol emas.'}, status=400)
        workers[key] = worker_id
    order.status = status
    order.assigned_florist_id = workers['florist_id']
    order.assigned_courier_id = workers['courier_id']
    order.save(update_fields=['status', 'assigned_florist', 'assigned_courier'])
    order = Order.objects.prefetch_related('items__product').get(pk=order.pk)
    return JsonResponse({'order': _order(order)})


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            'name', 'slug', 'category', 'description', 'price', 'old_price',
            'image', 'image_url', 'video', 'video_url', 'stock_quantity',
            'in_stock', 'is_featured',
        )


def _product(product):
    result = {
        'id': product.pk, 'name': product.name, 'slug': product.slug,
        'category_id': product.category_id, 'category': product.category.name,
        'description': product.description, 'price': product.price, 'old_price': product.old_price,
        'image_url': product.image_url, 'video_url': product.video_url,
        'has_image': bool(product.image), 'has_video': bool(product.video),
        'stock_quantity': product.stock_quantity, 'in_stock': product.in_stock,
        'is_featured': product.is_featured,
    }
    fingerprint = {
        **result,
        'image_file': product.image.name,
        'video_file': product.video.name,
        'hls_file': product.hls_playlist.name,
    }
    result['version'] = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()
    return result


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@mobile_admin_required(*ADMIN_ROLES)
def products(request):
    if request.method == 'POST':
        return _save_product(request)
    query = request.GET.get('q', '').strip()
    queryset = Product.objects.select_related('category').order_by('-created_at', '-pk')
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(category__name__icontains=query))
    page, error = _page(request, queryset)
    if error:
        return error
    return JsonResponse({
        'products': [_product(product) for product in page],
        'has_next': page.has_next(),
        'categories': list(Category.objects.values('id', 'name')),
    })


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@mobile_admin_required(*ADMIN_ROLES)
def product_detail(request, product_id):
    product = Product.objects.select_related('category').filter(pk=product_id).first()
    if product is None:
        return JsonResponse({'error': 'Mahsulot topilmadi.'}, status=404)
    if request.method == 'POST':
        return _save_product(request, product)
    return JsonResponse({'product': _product(product), 'categories': list(Category.objects.values('id', 'name'))})


def _save_product(request, product=None):
    if request.content_type not in ('multipart/form-data', 'application/x-www-form-urlencoded'):
        return JsonResponse({'error': 'Mahsulot formati noto‘g‘ri.'}, status=415)
    with transaction.atomic():
        if product is not None:
            product = Product.objects.select_for_update().select_related('category').filter(pk=product.pk).first()
            if product is None:
                return JsonResponse({'error': 'Mahsulot topilmadi.'}, status=404)
            if request.POST.get('version') != _product(product)['version']:
                return JsonResponse({'error': 'Mahsulot o‘zgargan. Ro‘yxatni yangilab qayta urinib ko‘ring.'}, status=409)
        form = ProductForm(request.POST, request.FILES, instance=product)
        if not form.is_valid():
            field, errors = next(iter(form.errors.items()))
            return JsonResponse({'error': f'{field}: {errors[0]}'}, status=400)
        updated = form.save(commit=False)
        if product is not None and ('video' in request.FILES or 'video-clear' in request.POST):
            updated.hls_playlist = ''
        updated.save()
        return JsonResponse({'product': _product(updated)}, status=200 if product else 201)


@require_GET
@mobile_admin_required(StaffProfile.Role.SUPER_ADMIN)
def users(request):
    queryset = User.objects.filter(is_staff=True).select_related('mimoza_profile').order_by('username', 'pk')
    page, error = _page(request, queryset)
    if error:
        return error
    result = []
    for user in page:
        profile = getattr(user, 'mimoza_profile', None)
        result.append({
            'id': user.pk, 'username': user.username, 'name': user.get_full_name(),
            'role': StaffProfile.Role.SUPER_ADMIN if user.is_superuser else (profile.role if profile else None),
            'active': user.is_active and (profile is None or profile.is_active_worker),
            'is_superuser': user.is_superuser,
        })
    return JsonResponse({
        'users': result, 'has_next': page.has_next(),
        'roles': [{'value': value, 'label': label} for value, label in StaffProfile.Role.choices],
    })


@csrf_exempt
@require_POST
@mobile_admin_required(StaffProfile.Role.SUPER_ADMIN)
def user_role(request, user_id):
    body, error = _mobile_json_body(request)
    if error:
        return error
    user = User.objects.filter(pk=user_id, is_staff=True).first()
    if user is None:
        return JsonResponse({'error': 'Xodim topilmadi.'}, status=404)
    if user.is_superuser:
        return JsonResponse({'error': 'Superuser rolini bu yerda o‘zgartirib bo‘lmaydi.'}, status=403)
    role = body.get('role')
    if role not in StaffProfile.Role.values:
        return JsonResponse({'error': 'Rol noto‘g‘ri.'}, status=400)
    StaffProfile.objects.update_or_create(user=user, defaults={'role': role})
    return JsonResponse({'success': True})


@require_GET
@mobile_admin_required(*ADMIN_ROLES)
def analytics(request):
    days = request.GET.get('days', '30')
    if days not in ('7', '30', '90'):
        return JsonResponse({'error': 'Davr noto‘g‘ri.'}, status=400)
    context = _crm_analytics_context(int(days))
    return JsonResponse({
        'days': context['days'], 'sales_total': context['sales_total'],
        'orders_count': context['orders_count'], 'average_order': context['average_order'],
        'cancelled_count': context['cancelled_count'],
        'daily_sales': list(context['daily_sales']), 'top_products': list(context['top_products']),
    })


@require_GET
@mobile_admin_required(StaffProfile.Role.SUPER_ADMIN)
def audit_history(request):
    page, error = _page(request, AuditLog.objects.order_by('-created_at', '-id'))
    if error:
        return error
    return JsonResponse({
        'entries': [{
            'id': entry.pk, 'created_at': entry.created_at.isoformat(),
            'actor': entry.actor_username, 'action': entry.get_action_display(),
            'model': entry.model_label, 'object': entry.object_repr, 'changes': entry.changes,
        } for entry in page],
        'has_next': page.has_next(),
    })
