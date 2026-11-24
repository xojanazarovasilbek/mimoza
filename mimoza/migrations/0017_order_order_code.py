from django.db import migrations, models


def populate_order_codes(apps, schema_editor):
    Order = apps.get_model('mimoza', 'Order')
    database = schema_editor.connection.alias
    orders = (
        Order.objects.using(database)
        .order_by('pk')
        .only('pk', 'order_code')
        .iterator()
    )
    batch = []
    for index, order in enumerate(orders):
        if index >= 90000:
            raise RuntimeError('90,000 dan ortiq mavjud buyurtmaga 5 xonali kod ajratib bo‘lmaydi.')
        order.order_code = f'{index + 10000:05d}'
        batch.append(order)
        if len(batch) == 250:
            Order.objects.using(database).bulk_update(batch, ('order_code',))
            batch.clear()
    if batch:
        Order.objects.using(database).bulk_update(batch, ('order_code',))


class Migration(migrations.Migration):

    dependencies = [
        ('mimoza', '0016_auditlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='order_code',
            field=models.CharField(
                blank=True,
                max_length=5,
                null=True,
                verbose_name='5 xonali buyurtma kodi',
            ),
        ),
        migrations.RunPython(populate_order_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='order',
            name='order_code',
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=5,
                unique=True,
                verbose_name='5 xonali buyurtma kodi',
            ),
        ),
    ]
