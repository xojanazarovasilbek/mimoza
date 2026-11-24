import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Order, OrderItem, PaymentTransaction, Product


PAYMENT_TTL = timedelta(minutes=30)


def enabled_providers():
    enabled = []
    if all((
        settings.CLICK_MERCHANT_ID,
        settings.CLICK_SERVICE_ID,
        settings.CLICK_SECRET_KEY,
    )):
        enabled.append(PaymentTransaction.Provider.CLICK)
    try:
        payme_merchant_id = int(settings.PAYME_MERCHANT_ID)
    except (TypeError, ValueError):
        payme_merchant_id = 0
    if payme_merchant_id > 0 and all((
        settings.PAYME_MERCHANT_LOGIN,
        settings.PAYME_MERCHANT_KEY,
    )):
        enabled.append(PaymentTransaction.Provider.PAYME)
    return enabled


def advance_amount_tiyin(total):
    return total * 30


def _click_checkout_url(request, order, amount_tiyin):
    return_url = request.build_absolute_uri(reverse('payment_return', args=[order.pk]))
    if not settings.DEBUG and urlsplit(return_url).scheme != 'https':
        raise ValueError('Click uchun HTTPS qaytish manzili kerak.')
    params = {
        'service_id': settings.CLICK_SERVICE_ID,
        'merchant_id': settings.CLICK_MERCHANT_ID,
        'amount': f'{amount_tiyin // 100}.{amount_tiyin % 100:02d}',
        'transaction_param': order.pk,
        'return_url': return_url,
    }
    return 'https://my.click.uz/services/pay?' + urlencode(params)


def _payme_checkout_url(request, order, amount_tiyin):
    response_url = request.build_absolute_uri(reverse('payment_return', args=[order.pk]))
    callback_url = request.build_absolute_uri(reverse('payme_payment_callback'))
    if not settings.DEBUG and (
        urlsplit(response_url).scheme != 'https'
        or urlsplit(callback_url).scheme != 'https'
    ):
        raise ValueError('Payme uchun HTTPS qaytish va callback manzillari kerak.')
    params = {
        'version': '1.0.1',
        'order_id': str(order.pk),
        'currency': 'UZS',
        'merchant_id': int(settings.PAYME_MERCHANT_ID),
        'order_desc': f'Mimoza buyurtma {order.order_code}',
        'amount': amount_tiyin,
        'response_url': response_url,
        'server_callback_url': callback_url,
        'lifetime': int(PAYMENT_TTL.total_seconds()),
    }
    signed_params = [settings.PAYME_MERCHANT_KEY]
    signed_params.extend(
        str(params[key])
        for key in sorted(params)
        if params[key] is not None and params[key] != ''
    )
    params['signature'] = hashlib.sha1('|'.join(signed_params).encode('utf-8')).hexdigest()
    request_body = json.dumps({'request': params}).encode('utf-8')
    provider_request = Request(
        'https://pay.payme.uz/api/checkout/url',
        data=request_body,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST',
    )
    try:
        with urlopen(provider_request, timeout=10) as response:
            result = json.loads(response.read(65536))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError('Payme to‘lov sahifasini hozir yaratib bo‘lmadi.') from error
    provider_response = result.get('response') if isinstance(result, dict) else None
    if (
        not isinstance(provider_response, dict)
        or provider_response.get('response_status') != 'success'
    ):
        raise ValueError('Payme to‘lov sahifasini yaratishni rad etdi.')
    checkout_url = provider_response.get('checkout_url')
    try:
        parsed_url = urlsplit(checkout_url) if isinstance(checkout_url, str) else None
    except ValueError as error:
        raise ValueError('Payme serveridan noto‘g‘ri checkout javobi keldi.') from error
    if (
        not parsed_url
        or parsed_url.scheme != 'https'
        or parsed_url.hostname != 'pay.payme.uz'
    ):
        raise ValueError('Payme serveridan noto‘g‘ri checkout javobi keldi.')
    return checkout_url


def create_payment_transaction(request, order, provider):
    if provider not in enabled_providers():
        raise ValueError('Bu to‘lov xizmati hali sozlanmagan.')
    if provider not in PaymentTransaction.Provider.values:
        raise ValueError('To‘lov xizmati noto‘g‘ri.')
    amount = advance_amount_tiyin(order.total)
    if amount <= 0:
        raise ValueError('Buyurtma summasi noto‘g‘ri.')
    payment = PaymentTransaction.objects.create(
        order=order,
        provider=provider,
        amount_tiyin=amount,
        expires_at=timezone.now() + PAYMENT_TTL,
    )
    checkout_url = payment_checkout_url(request, order, provider, amount)
    payment.checkout_url = checkout_url
    payment.save(update_fields=['checkout_url'])
    return payment, checkout_url


def payment_checkout_url(request, order, provider, amount_tiyin=None, payment=None):
    if payment and payment.checkout_url:
        return payment.checkout_url
    if amount_tiyin is None:
        amount_tiyin = advance_amount_tiyin(order.total)
    if provider == PaymentTransaction.Provider.CLICK:
        checkout_url = _click_checkout_url(request, order, amount_tiyin)
    else:
        checkout_url = _payme_checkout_url(request, order, amount_tiyin)
    return checkout_url


def create_order_for_payment(
    request,
    *,
    customer,
    customer_name,
    phone,
    address,
    items,
    provider,
    delivery_note='',
    card_message='',
    anonymous_delivery=False,
    mobile_request_key=None,
    mobile_request_hash='',
    web_payment_key=None,
):
    with transaction.atomic():
        product_ids = [product_id for product_id, _ in items]
        products = {
            product.pk: product
            for product in Product.objects.select_for_update().filter(pk__in=product_ids, in_stock=True)
        }
        if len(products) != len(set(product_ids)):
            raise ValueError('Savatdagi mahsulotlardan biri sotuvda yo‘q.')
        total = 0
        for product_id, quantity in items:
            product = products[product_id]
            if quantity > product.stock_quantity:
                raise ValueError(f'{product.name} mahsulotidan yetarli miqdor qolmagan.')
            total += product.price * quantity
        if total <= 0:
            raise ValueError('Buyurtma summasi noto‘g‘ri.')
        order = Order.objects.create(
            customer=customer,
            customer_name=customer_name,
            phone=phone,
            address=address,
            delivery_note=delivery_note,
            card_message=card_message,
            anonymous_delivery=anonymous_delivery,
            payment_method=provider,
            payment_status=Order.PaymentStatus.PENDING,
            total=total,
            mobile_request_key=mobile_request_key,
            mobile_request_hash=mobile_request_hash,
            web_payment_key=web_payment_key,
        )
        for product_id, quantity in items:
            product = products[product_id]
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                price=product.price,
            )
            product.stock_quantity -= quantity
            product.in_stock = product.stock_quantity > 0
            product.save(update_fields=['stock_quantity', 'in_stock'])
        payment, checkout_url = create_payment_transaction(request, order, provider)
    return order, payment, checkout_url


def retry_payment_transaction(request, order):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.payment_method not in enabled_providers():
            raise ValueError('Tanlangan to‘lov xizmati hozir sozlanmagan.')
        pending_payments = list(
            PaymentTransaction.objects.select_for_update()
            .filter(order=order, status=PaymentTransaction.Status.PENDING)
            .order_by('-created_at')
        )
        now = timezone.now()
        active = next((payment for payment in pending_payments if payment.expires_at > now), None)
        if active:
            return active, payment_checkout_url(
                request, order, active.provider, active.amount_tiyin, active,
            )
        for payment in pending_payments:
            payment.status = PaymentTransaction.Status.EXPIRED
            payment.cancelled_at = now
            payment.cancel_reason = 4
            payment.save(update_fields=['status', 'cancelled_at', 'cancel_reason'])
        if pending_payments and order.payment_status == Order.PaymentStatus.PENDING:
            _release_reserved_stock(order)
            order.payment_status = Order.PaymentStatus.FAILED
            order.save(update_fields=['payment_status'])

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        pending = (
            PaymentTransaction.objects.select_for_update()
            .filter(
                order=order,
                status=PaymentTransaction.Status.PENDING,
                expires_at__gt=timezone.now(),
            )
            .order_by('-created_at')
            .first()
        )
        if pending:
            return pending, payment_checkout_url(
                request, order, pending.provider, pending.amount_tiyin, pending,
            )
        if (
            order.payment_status != Order.PaymentStatus.FAILED
            or order.status == Order.Status.CANCELLED
        ):
            raise ValueError('Bu buyurtma uchun qayta to‘lov qilib bo‘lmaydi.')
        items = list(order.items.values_list('product_id', 'quantity'))
        products = {
            product.pk: product
            for product in Product.objects.select_for_update().filter(
                pk__in=[product_id for product_id, _ in items],
                in_stock=True,
            )
        }
        if len(products) != len({product_id for product_id, _ in items}) or any(
            products[product_id].stock_quantity < quantity
            for product_id, quantity in items
        ):
            raise ValueError('Savatdagi mahsulotlardan biri hozir yetarli emas.')
        for product_id, quantity in items:
            product = products[product_id]
            product.stock_quantity -= quantity
            product.in_stock = product.stock_quantity > 0
            product.save(update_fields=['stock_quantity', 'in_stock'])
        order.payment_status = Order.PaymentStatus.PENDING
        order.save(update_fields=['payment_status'])
        return create_payment_transaction(request, order, order.payment_method)


def _amount_from_soums(value):
    try:
        amount = Decimal(str(value)) * 100
        if not amount.is_finite() or amount != amount.to_integral_value():
            return None
        return int(amount)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None


def _click_response(data, error=0, note='Success', complete=False):
    response = {
        'click_trans_id': data.get('click_trans_id', ''),
        'merchant_trans_id': data.get('merchant_trans_id', ''),
        'error': error,
        'error_note': note,
    }
    if complete:
        response['merchant_confirm_id'] = data.get('merchant_prepare_id', '')
    else:
        response['merchant_prepare_id'] = data.get('merchant_prepare_id', '')
    return JsonResponse(response)


def _click_signature_is_valid(data, action):
    signature = data.get('sign_string', '')
    parts = (
        data.get('click_trans_id', ''),
        data.get('service_id', ''),
        settings.CLICK_SECRET_KEY,
        data.get('merchant_trans_id', ''),
    )
    if action == '1':
        parts += (data.get('merchant_prepare_id', ''),)
    parts += (data.get('amount', ''), action, data.get('sign_time', ''))
    expected = hashlib.md5(''.join(map(str, parts)).encode('utf-8')).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)


def _release_reserved_stock(order):
    for item in order.items.all():
        Product.objects.filter(pk=item.product_id).update(
            stock_quantity=F('stock_quantity') + item.quantity,
            in_stock=True,
        )


def expire_pending_payments():
    now = timezone.now()
    expired_ids = list(PaymentTransaction.objects.filter(
        status=PaymentTransaction.Status.PENDING,
        expires_at__lte=now,
    ).values_list('pk', flat=True))
    expired_count = 0
    for payment_id in expired_ids:
        with transaction.atomic():
            order_id = PaymentTransaction.objects.filter(pk=payment_id).values_list('order_id', flat=True).first()
            if order_id is None:
                continue
            order = Order.objects.select_for_update().filter(pk=order_id).first()
            if order is None:
                continue
            payment = PaymentTransaction.objects.select_for_update().select_related('order').filter(
                pk=payment_id,
                status=PaymentTransaction.Status.PENDING,
                expires_at__lte=now,
            ).first()
            if payment is None:
                continue
            payment.status = PaymentTransaction.Status.EXPIRED
            payment.cancelled_at = now
            payment.cancel_reason = 4
            payment.save(update_fields=['status', 'cancelled_at', 'cancel_reason'])
            expired_count += 1
            if (
                order.payment_status == Order.PaymentStatus.PENDING
                and not order.payment_transactions.filter(status=PaymentTransaction.Status.PENDING).exists()
            ):
                order.payment_status = Order.PaymentStatus.FAILED
                order.save(update_fields=['payment_status'])
                _release_reserved_stock(order)
    return expired_count


@csrf_exempt
@require_POST
def click_callback(request):
    data = request.POST
    if not settings.CLICK_SECRET_KEY or not _click_signature_is_valid(data, data.get('action', '')):
        return _click_response(data, -1, 'Invalid sign_string')
    if data.get('service_id') != settings.CLICK_SERVICE_ID:
        return _click_response(data, -3, 'Service not found')
    try:
        order_id = int(data.get('merchant_trans_id', ''))
    except (TypeError, ValueError):
        return _click_response(data, -5, 'Order not found')
    if order_id < 1:
        return _click_response(data, -5, 'Order not found')
    order = Order.objects.filter(pk=order_id, payment_method=Order.Payment.CLICK).first()
    if order is None:
        return _click_response(data, -5, 'Order not found')
    amount = _amount_from_soums(data.get('amount'))
    if amount is None:
        return _click_response(data, -2, 'Invalid amount')
    action = data.get('action')
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        payment = (
            PaymentTransaction.objects.select_for_update()
            .filter(order=order, provider=PaymentTransaction.Provider.CLICK)
            .order_by('-created_at')
            .first()
        )
        if payment is None or amount != payment.amount_tiyin:
            return _click_response(data, -2, 'Invalid amount')
        click_id = data.get('click_trans_id', '')
        if not click_id or len(click_id) > 100 or not data.get('sign_time'):
            return _click_response(data, -8, 'Invalid transaction')
        if action == '0':
            if payment.status != PaymentTransaction.Status.PENDING or payment.expires_at <= timezone.now():
                return _click_response(data, -9, 'Payment expired or cancelled')
            if payment.provider_transaction_id and payment.provider_transaction_id != click_id:
                return _click_response(data, -8, 'Transaction mismatch')
            payment.provider_transaction_id = click_id
            payment.provider_prepare_id = str(payment.pk)
            payment.expires_at = timezone.now() + PAYMENT_TTL
            payment.save(update_fields=[
                'provider_transaction_id',
                'provider_prepare_id',
                'expires_at',
            ])
            return _click_response({**data, 'merchant_prepare_id': payment.provider_prepare_id})
        if action != '1':
            return _click_response(data, -3, 'Action not found')
        if data.get('merchant_prepare_id') != payment.provider_prepare_id:
            return _click_response(data, -6, 'Transaction not found', complete=True)
        if payment.provider_transaction_id != click_id:
            return _click_response(data, -6, 'Transaction not found', complete=True)
        if order.payment_status == Order.PaymentStatus.PAID:
            return _click_response(
                {**data, 'merchant_prepare_id': payment.provider_prepare_id},
                -4,
                'Already paid',
                complete=True,
            )
        if payment.status != PaymentTransaction.Status.PENDING or payment.expires_at <= timezone.now():
            return _click_response(data, -9, 'Payment expired or cancelled', complete=True)
        if data.get('error', '0') != '0':
            payment.status = PaymentTransaction.Status.FAILED
            payment.save(update_fields=['status'])
            if not order.payment_transactions.filter(status=PaymentTransaction.Status.PENDING).exclude(
                pk=payment.pk,
            ).exists():
                order.payment_status = Order.PaymentStatus.FAILED
                order.save(update_fields=['payment_status'])
                _release_reserved_stock(order)
            return _click_response(data, 0, 'Transaction failed', complete=True)
        payment.status = PaymentTransaction.Status.PAID
        payment.paid_at = timezone.now()
        payment.save(update_fields=['status', 'paid_at'])
        order.payment_status = Order.PaymentStatus.PAID
        order.save(update_fields=['payment_status'])
    return _click_response(
        {**data, 'merchant_prepare_id': payment.provider_prepare_id},
        complete=True,
    )


def _payme_error(request_id, code, message, data=None):
    error = {
        'code': code,
        'message': {'uz': message, 'ru': message, 'en': message},
    }
    if data is not None:
        error['data'] = data
    return JsonResponse({'jsonrpc': '2.0', 'id': request_id, 'error': error})


def _payme_result(request_id, result):
    return JsonResponse({'jsonrpc': '2.0', 'id': request_id, 'result': result})


def _payme_authenticated(request):
    expected = base64.b64encode(
        f'{settings.PAYME_MERCHANT_LOGIN}:{settings.PAYME_MERCHANT_KEY}'.encode('utf-8'),
    ).decode('ascii')
    authorization = request.headers.get('Authorization', '')
    return bool(settings.PAYME_MERCHANT_LOGIN and settings.PAYME_MERCHANT_KEY) and hmac.compare_digest(
        authorization, f'Basic {expected}',
    )


def _payme_transaction_for(transaction_id):
    return (
        PaymentTransaction.objects.select_related('order')
        .filter(provider=PaymentTransaction.Provider.PAYME, provider_transaction_id=str(transaction_id))
        .first()
    )


def _payme_order(params):
    account = params.get('account')
    if not isinstance(account, dict):
        return None
    order_id = account.get(settings.PAYME_ACCOUNT_FIELD)
    if type(order_id) not in (int, str):
        return None
    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        return None
    if order_id < 1:
        return None
    return Order.objects.filter(pk=order_id, payment_method=Order.Payment.PAYME).first()


def _payme_transaction_payload(payment):
    state = {
        PaymentTransaction.Status.PENDING: 1,
        PaymentTransaction.Status.PAID: 2,
        PaymentTransaction.Status.FAILED: -1,
        PaymentTransaction.Status.EXPIRED: -1,
        PaymentTransaction.Status.CANCELLED: -2 if payment.paid_at else -1,
    }[payment.status]
    reason = payment.cancel_reason
    if reason is None and payment.status == PaymentTransaction.Status.EXPIRED:
        reason = 4
    return {
        'transaction': str(payment.pk),
        'state': state,
        'create_time': int((payment.provider_created_at or payment.created_at).timestamp() * 1000),
        'perform_time': int(payment.paid_at.timestamp() * 1000) if payment.paid_at else 0,
        'cancel_time': int(payment.cancelled_at.timestamp() * 1000) if payment.cancelled_at else 0,
        'reason': reason,
    }


@csrf_exempt
@require_POST
def payme_callback(request):
    if len(request.body) > 65536:
        return _payme_error(None, -32600, 'Invalid request')
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _payme_error(None, -32700, 'Invalid JSON')
    if not isinstance(body, dict):
        return _payme_error(None, -32600, 'Invalid request')
    request_id = body.get('id')
    if not _payme_authenticated(request):
        response = _payme_error(request_id, -32504, 'Insufficient privilege')
        response.status_code = 200
        return response
    method = body.get('method')
    params = body.get('params')
    if not isinstance(params, dict):
        return _payme_error(request_id, -32600, 'Invalid params')

    if method in ('CheckPerformTransaction', 'CreateTransaction'):
        order = _payme_order(params)
        amount = params.get('amount')
        if order is None:
            return _payme_error(request_id, -31050, 'Order not found')
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order.pk)
            latest = (
                PaymentTransaction.objects.select_for_update()
                .filter(order=locked_order, provider=PaymentTransaction.Provider.PAYME)
                .order_by('-created_at')
                .first()
            )
            if latest is None or type(amount) is not int or amount != latest.amount_tiyin:
                return _payme_error(request_id, -31001, 'Invalid amount')
            if method == 'CheckPerformTransaction':
                if latest.expires_at <= timezone.now() or locked_order.payment_status != Order.PaymentStatus.PENDING:
                    return _payme_error(request_id, -31008, 'Order is not payable')
                return _payme_result(request_id, {'allow': True})
            transaction_id = params.get('id')
            if not isinstance(transaction_id, str) or not transaction_id or len(transaction_id) > 100:
                return _payme_error(request_id, -32602, 'Invalid transaction ID')
            transaction_time = params.get('time')
            if type(transaction_time) is not int or transaction_time <= 0:
                return _payme_error(request_id, -32602, 'Invalid transaction time')
            try:
                provider_created_at = datetime.fromtimestamp(
                    transaction_time / 1000,
                    tz=timezone.get_current_timezone(),
                )
            except (OverflowError, OSError, ValueError):
                return _payme_error(request_id, -32602, 'Invalid transaction time')
            payment = _payme_transaction_for(transaction_id)
            if payment:
                if payment.order_id != locked_order.pk or payment.amount_tiyin != amount:
                    return _payme_error(request_id, -31008, 'Transaction mismatch')
                state = _payme_transaction_payload(payment)
                return _payme_result(request_id, {
                    'create_time': state['create_time'],
                    'transaction': str(payment.pk),
                    'state': state['state'],
                })
            else:
                if latest.expires_at <= timezone.now() or locked_order.payment_status != Order.PaymentStatus.PENDING:
                    return _payme_error(request_id, -31008, 'Order is not payable')
                if latest.provider_transaction_id:
                    return _payme_error(request_id, -31008, 'Transaction mismatch')
                latest.provider_transaction_id = str(transaction_id)
                latest.provider_created_at = provider_created_at
                latest.save(update_fields=['provider_transaction_id', 'provider_created_at'])
                payment = latest
            state = _payme_transaction_payload(payment)
            return _payme_result(request_id, {
                'create_time': state['create_time'],
                'transaction': str(payment.pk),
                'state': state['state'],
            })

    if method == 'PerformTransaction':
        payment = _payme_transaction_for(params.get('id'))
        if payment is None:
            return _payme_error(request_id, -31003, 'Transaction not found')
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=payment.order_id)
            locked = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
            if order.payment_status == Order.PaymentStatus.PAID:
                return _payme_result(request_id, {
                    'transaction': str(locked.pk),
                    'perform_time': int((locked.paid_at or timezone.now()).timestamp() * 1000),
                    'state': 2,
                })
            if locked.status != PaymentTransaction.Status.PENDING or locked.expires_at <= timezone.now():
                return _payme_error(request_id, -31008, 'Transaction cannot be performed')
            locked.status = PaymentTransaction.Status.PAID
            locked.paid_at = timezone.now()
            locked.save(update_fields=['status', 'paid_at'])
            order.payment_status = Order.PaymentStatus.PAID
            order.save(update_fields=['payment_status'])
            return _payme_result(request_id, {
                'transaction': str(locked.pk),
                'perform_time': int(locked.paid_at.timestamp() * 1000),
                'state': 2,
            })

    if method == 'CancelTransaction':
        payment = _payme_transaction_for(params.get('id'))
        if payment is None:
            return _payme_error(request_id, -31003, 'Transaction not found')
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=payment.order_id)
            locked = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
            if locked.status == PaymentTransaction.Status.CANCELLED:
                return _payme_result(request_id, {
                    'transaction': str(locked.pk),
                    'cancel_time': int((locked.cancelled_at or timezone.now()).timestamp() * 1000),
                    'state': -2 if locked.paid_at else -1,
                })
            if locked.status in (
                PaymentTransaction.Status.EXPIRED,
                PaymentTransaction.Status.FAILED,
            ):
                return _payme_result(request_id, {
                    'transaction': str(locked.pk),
                    'cancel_time': int((locked.cancelled_at or timezone.now()).timestamp() * 1000),
                    'state': -1,
                })
            if locked.status == PaymentTransaction.Status.PAID and order.status != Order.Status.PENDING:
                return _payme_error(request_id, -31007, 'Order is already being fulfilled')
            if locked.status not in (PaymentTransaction.Status.PENDING, PaymentTransaction.Status.PAID):
                return _payme_error(request_id, -31008, 'Transaction cannot be cancelled')
            was_paid = locked.status == PaymentTransaction.Status.PAID
            locked.status = PaymentTransaction.Status.CANCELLED
            locked.cancelled_at = timezone.now()
            locked.cancel_reason = params.get('reason') if type(params.get('reason')) is int else None
            locked.save(update_fields=['status', 'cancelled_at', 'cancel_reason'])
            order.payment_status = Order.PaymentStatus.FAILED
            if was_paid:
                order.status = Order.Status.CANCELLED
                order.save(update_fields=['payment_status', 'status'])
            else:
                order.save(update_fields=['payment_status'])
            if not order.payment_transactions.filter(status=PaymentTransaction.Status.PENDING).exists():
                _release_reserved_stock(order)
            return _payme_result(request_id, {
                'transaction': str(locked.pk),
                'cancel_time': int(locked.cancelled_at.timestamp() * 1000),
                'state': -2 if was_paid else -1,
            })

    if method == 'CheckTransaction':
        payment = _payme_transaction_for(params.get('id'))
        if payment is None:
            return _payme_error(request_id, -31003, 'Transaction not found')
        return _payme_result(request_id, _payme_transaction_payload(payment))

    if method == 'GetStatement':
        from_time, to_time = params.get('from'), params.get('to')
        if type(from_time) is not int or type(to_time) is not int:
            return _payme_error(request_id, -32602, 'Invalid time range')
        try:
            from_datetime = datetime.fromtimestamp(
                from_time / 1000,
                tz=timezone.get_current_timezone(),
            )
            to_datetime = datetime.fromtimestamp(
                to_time / 1000,
                tz=timezone.get_current_timezone(),
            )
        except (OverflowError, OSError, ValueError):
            return _payme_error(request_id, -32602, 'Invalid time range')
        if from_datetime > to_datetime:
            return _payme_error(request_id, -32602, 'Invalid time range')
        payments = PaymentTransaction.objects.filter(
            provider=PaymentTransaction.Provider.PAYME,
            provider_transaction_id__isnull=False,
            provider_created_at__gte=from_datetime,
            provider_created_at__lte=to_datetime,
        ).order_by('provider_created_at')
        rows = []
        for payment in payments:
            row = _payme_transaction_payload(payment)
            row.update({
                'id': payment.provider_transaction_id,
                'time': int(payment.provider_created_at.timestamp() * 1000),
                'amount': payment.amount_tiyin,
                'account': {settings.PAYME_ACCOUNT_FIELD: payment.order_id},
            })
            rows.append(row)
        return _payme_result(request_id, {'transactions': rows})

    return _payme_error(request_id, -32601, 'Method not found')
