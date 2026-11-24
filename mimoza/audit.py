import json
from contextvars import ContextVar
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Model
from django.db.models.signals import m2m_changed, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import AuditLog, MobileAccessToken, MobilePushDevice, MobilePushMessage


_current_actor = ContextVar('mimoza_audit_actor', default=None)
_SENSITIVE_FIELD_PARTS = (
    'password',
    'secret',
    'sms_login',
    'api_key',
    'private_key',
    'token',
    'auth',
    'p256dh',
    'endpoint',
)
_REDACTED = '[maxfiy]'


def set_audit_actor(actor):
    return _current_actor.set(actor)


def reset_audit_actor(token):
    _current_actor.reset(token)


def _tracked_model(model):
    return (
        model not in (AuditLog, MobileAccessToken, MobilePushDevice, MobilePushMessage)
        and (
            model._meta.app_label == 'mimoza'
            or model in (get_user_model(), Group)
        )
    )


def _tracked_fields(model, update_fields=None):
    fields = []
    for field in model._meta.concrete_fields:
        if update_fields is not None and not {
            field.name,
            field.attname,
        }.intersection(update_fields):
            continue
        fields.append(field)
    return fields


def _is_sensitive(field):
    name = field.name.lower()
    return any(part in name for part in _SENSITIVE_FIELD_PARTS)


def _display_value(field, value):
    return _REDACTED if _is_sensitive(field) else value


def _json_value(value):
    if isinstance(value, Model):
        value = value.pk
    elif hasattr(value, 'name') and hasattr(value, 'storage'):
        value = value.name
    elif isinstance(value, (date, datetime, time, Decimal, UUID)):
        value = str(value)
    return json.loads(json.dumps(value, default=str))


def _snapshot(instance, fields):
    return {
        field.name: _json_value(field.value_from_object(instance))
        for field in fields
    }


def _record(instance, action, changes, using):
    actor = _current_actor.get()
    if actor is not None and not getattr(actor, 'is_authenticated', False):
        actor = None
    AuditLog.objects.using(using).create(
        actor=actor,
        actor_username=actor.get_username() if actor else 'Tizim',
        action=action,
        model_label=instance._meta.label,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        changes=changes,
    )


@receiver(pre_save)
def capture_previous_values(
    sender,
    instance,
    raw=False,
    using='default',
    update_fields=None,
    **kwargs,
):
    if raw or not _tracked_model(sender):
        return
    instance._audit_fields = _tracked_fields(sender, update_fields)
    if instance._state.adding:
        instance._audit_previous = None
        return
    field_names = [field.name for field in instance._audit_fields]
    instance._audit_previous = (
        sender._base_manager.using(using)
        .filter(pk=instance.pk)
        .values(*field_names)
        .first()
    )


@receiver(post_save)
def record_saved_values(sender, instance, created=False, raw=False, using='default', **kwargs):
    if raw or not _tracked_model(sender):
        return
    fields = getattr(instance, '_audit_fields', None)
    if fields is None:
        fields = _tracked_fields(sender)
    current = _snapshot(instance, fields)
    if created:
        changes = {
            str(field.verbose_name): {
                'old': None,
                'new': _display_value(field, current[field.name]),
            }
            for field in fields
        }
        _record(instance, AuditLog.Action.CREATE, changes, using)
        return

    previous = getattr(instance, '_audit_previous', None)
    if previous is None:
        return
    changes = {}
    for field in fields:
        old_value = _json_value(previous[field.name])
        new_value = current[field.name]
        if old_value != new_value:
            changes[str(field.verbose_name)] = {
                'old': _display_value(field, old_value),
                'new': _display_value(field, new_value),
            }
    if changes:
        _record(instance, AuditLog.Action.UPDATE, changes, using)


@receiver(pre_delete)
def record_deleted_values(sender, instance, using='default', **kwargs):
    if not _tracked_model(sender):
        return
    fields = _tracked_fields(sender)
    snapshot = _snapshot(instance, fields)
    changes = {
        str(field.verbose_name): {
            'old': _display_value(field, snapshot[field.name]),
            'new': None,
        }
        for field in fields
    }
    _record(instance, AuditLog.Action.DELETE, changes, using)


@receiver(m2m_changed)
def record_many_to_many_changes(
    sender,
    instance,
    action,
    reverse,
    model,
    pk_set,
    using='default',
    **kwargs,
):
    if not _tracked_model(instance.__class__):
        return
    if action not in (
        'pre_add',
        'pre_remove',
        'pre_clear',
        'post_add',
        'post_remove',
        'post_clear',
    ):
        return

    relation_owner = model if reverse else instance.__class__
    field = next(
        field
        for field in relation_owner._meta.many_to_many
        if field.remote_field.through is sender
    )
    manager_name = field.remote_field.get_accessor_name() if reverse else field.name
    manager = getattr(instance, manager_name)
    state_key = f'{sender._meta.label}:{reverse}:{field.name}'
    states = getattr(instance, '_audit_m2m_states', {})

    if action.startswith('pre_'):
        states[state_key] = list(manager.using(using).values_list('pk', flat=True))
        instance._audit_m2m_states = states
        return

    previous = states.pop(state_key, [])
    instance._audit_m2m_states = states
    current = list(manager.using(using).values_list('pk', flat=True))
    if previous != current:
        _record(
            instance,
            AuditLog.Action.UPDATE,
            {
                str(field.verbose_name): {
                    'old': sorted(previous),
                    'new': sorted(current),
                },
            },
            using,
        )
