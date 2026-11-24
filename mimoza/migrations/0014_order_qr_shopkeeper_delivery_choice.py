import uuid

from django.db import migrations, models


def populate_order_qr_tokens(apps, schema_editor):
    Order = apps.get_model('mimoza', 'Order')
    database = schema_editor.connection.alias
    for order in Order.objects.using(database).filter(qr_token__isnull=True).iterator():
        Order.objects.using(database).filter(pk=order.pk).update(qr_token=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ('mimoza', '0013_story_hls_playlist'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='qr_token',
            field=models.UUIDField(
                blank=True,
                editable=False,
                null=True,
                verbose_name='QR kodi',
            ),
        ),
        migrations.RunPython(populate_order_qr_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='order',
            name='qr_token',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name='QR kodi',
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='delivery_required',
            field=models.BooleanField(
                blank=True,
                default=None,
                null=True,
                verbose_name='Yetkazib berish kerak',
            ),
        ),
    ]
