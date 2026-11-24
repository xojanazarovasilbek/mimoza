import secrets

from django.db.models import Q
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import MobilePushDevice, MobilePushMessage, Order, StaffProfile


ONLINE_METHODS = (Order.Payment.CLICK, Order.Payment.PAYME, Order.Payment.UZUM)


def queue_mobile_notification(user, title, body, kind=MobilePushMessage.Kind.CUSTOMER):
    devices = MobilePushDevice.objects.filter(
        access_token__user=user,
        access_token__expires_at__gt=timezone.now(),
        access_token__user__is_active=True,
    )
    messages = [
        MobilePushMessage(device=device, kind=kind, title=title, body=body)
        for device in devices.select_related('access_token__user')
        if secrets.compare_digest(
            device.access_token.auth_hash, device.access_token.user.get_session_auth_hash(),
        )
    ]
    MobilePushMessage.objects.bulk_create(messages)
    return len(messages)


def queue_admin_order():
    devices = MobilePushDevice.objects.filter(
        access_token__expires_at__gt=timezone.now(),
        access_token__user__is_active=True,
        access_token__user__is_staff=True,
    ).filter(
        Q(access_token__user__is_superuser=True)
        | Q(
            access_token__user__mimoza_profile__role__in=(
                StaffProfile.Role.SUPER_ADMIN, StaffProfile.Role.MANAGER,
            ),
            access_token__user__mimoza_profile__is_active_worker=True,
        )
    ).select_related('access_token__user')
    messages = [
        MobilePushMessage(
            device=device,
            kind=MobilePushMessage.Kind.ADMIN,
            title='Yangi buyurtma',
            body='Yangi buyurtma qabul qilindi.',
        )
        for device in devices
        if secrets.compare_digest(
            device.access_token.auth_hash, device.access_token.user.get_session_auth_hash(),
        )
    ]
    MobilePushMessage.objects.bulk_create(messages)


@receiver(pre_save, sender=Order)
def capture_order_notification_state(sender, instance, raw=False, using='default', **kwargs):
    if raw or instance._state.adding:
        instance._notification_previous = None
        return
    instance._notification_previous = sender.objects.using(using).filter(pk=instance.pk).values(
        'status', 'payment_status',
    ).first()


@receiver(post_save, sender=Order)
def queue_order_notifications(sender, instance, created=False, raw=False, update_fields=None, **kwargs):
    if raw:
        return
    previous = getattr(instance, '_notification_previous', None)
    if created:
        if instance.payment_method not in ONLINE_METHODS:
            queue_admin_order()
        return
    if previous is None:
        return
    if instance.customer_id and instance.customer.user_id:
        if (update_fields is None or 'status' in update_fields) and previous['status'] != instance.status:
            queue_mobile_notification(
                instance.customer.user,
                'Buyurtma holati',
                f'Buyurtmangiz: {instance.get_status_display()}.',
            )
        if (update_fields is None or 'payment_status' in update_fields) and previous['payment_status'] != instance.payment_status:
            queue_mobile_notification(
                instance.customer.user,
                'To‘lov holati',
                f'To‘lovingiz: {instance.get_payment_status_display()}.',
            )
    if (
        instance.payment_method in ONLINE_METHODS
        and (update_fields is None or 'payment_status' in update_fields)
        and previous['payment_status'] != Order.PaymentStatus.PAID
        and instance.payment_status == Order.PaymentStatus.PAID
    ):
        queue_admin_order()
