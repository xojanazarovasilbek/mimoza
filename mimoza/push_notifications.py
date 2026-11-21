import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from pywebpush import WebPushException, webpush

from .models import PushSubscription


def send_push_notification(user, title, body, url='/account/'):
    if not all((
        settings.WEBPUSH_VAPID_PUBLIC_KEY,
        settings.WEBPUSH_VAPID_PRIVATE_KEY,
        settings.WEBPUSH_VAPID_SUBJECT,
    )):
        raise ImproperlyConfigured(
            'Web Push uchun WEBPUSH_VAPID_PUBLIC_KEY, WEBPUSH_VAPID_PRIVATE_KEY '
            'va WEBPUSH_VAPID_SUBJECT sozlamalarini kiriting.'
        )

    payload = json.dumps({'title': title, 'body': body, 'url': url})
    sent_count = 0
    subscriptions = PushSubscription.objects.filter(user=user)
    for subscription in subscriptions.iterator():
        try:
            webpush(
                subscription_info={
                    'endpoint': subscription.endpoint,
                    'keys': {
                        'p256dh': subscription.p256dh,
                        'auth': subscription.auth,
                    },
                },
                data=payload,
                vapid_private_key=settings.WEBPUSH_VAPID_PRIVATE_KEY,
                vapid_claims={'sub': settings.WEBPUSH_VAPID_SUBJECT},
                ttl=3600,
            )
        except WebPushException as error:
            response = getattr(error, 'response', None)
            if response is not None and response.status_code in (404, 410):
                subscription.delete()
                continue
            raise
        sent_count += 1
    return sent_count
