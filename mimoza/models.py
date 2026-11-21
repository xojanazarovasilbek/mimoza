from datetime import timedelta

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User

from .media_utils import WebPImageModel

def default_story_expiry():
    return timezone.now() + timedelta(days=1)


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name = 'Kategoriya'
        verbose_name_plural = 'Kategoriyalar'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(WebPImageModel, models.Model):
    webp_image_fields = ('image',)

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    description = models.TextField(blank=True)
    price = models.PositiveIntegerField()
    old_price = models.PositiveIntegerField(null=True, blank=True)
    image = models.ImageField('Mahsulot rasmi', upload_to='products/images/', blank=True)
    image_url = models.URLField(blank=True)
    video = models.FileField('Mahsulot videosi', upload_to='products/videos/', blank=True)
    video_url = models.URLField('Video havolasi', blank=True)
    hls_playlist = models.FileField('HLS pleylisti', upload_to='products/hls/', blank=True)
    in_stock = models.BooleanField(default=True)
    stock_quantity = models.PositiveIntegerField('Ombordagi miqdor', default=0)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Mahsulot'
        verbose_name_plural = 'Mahsulotlar'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Story(WebPImageModel, models.Model):
    webp_image_fields = ('image',)

    title = models.CharField('Sarlavha', max_length=100)
    image = models.ImageField('Rasm', upload_to='stories/images/', blank=True)
    video = models.FileField('Video', upload_to='stories/videos/', blank=True)
    hls_playlist = models.FileField('HLS pleylisti', upload_to='stories/hls/', blank=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        related_name='stories',
        null=True,
        blank=True,
        verbose_name='Mahsulot',
    )
    is_active = models.BooleanField('Faol', default=True)
    expires_at = models.DateTimeField('Tugash vaqti', default=default_story_expiry)
    created_at = models.DateTimeField('Yaratilgan vaqt', default=timezone.now)

    class Meta:
        verbose_name = 'Story'
        verbose_name_plural = 'Stories'
        ordering = ['-created_at']

    def clean(self):
        super().clean()
        if not self.image and not self.video:
            raise ValidationError('Story uchun rasm yoki video yuklang.')

    def __str__(self):
        return self.title


class ProductLike(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_likes')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Mahsulot layki'
        verbose_name_plural = 'Mahsulot layklari'
        constraints = [
            models.UniqueConstraint(fields=('product', 'user'), name='unique_product_like_per_user'),
        ]


class ProductComment(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_comments')
    text = models.CharField('Izoh', max_length=1000)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Mahsulot izohi'
        verbose_name_plural = 'Mahsulot izohlari'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.product.name} — {self.user.username}'


class Customer(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='customer_profile',
        null=True,
        blank=True,
        verbose_name='Akkaunt',
    )
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    cashback = models.PositiveIntegerField(default=0)
    is_vip = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Mijoz'
        verbose_name_plural = 'Mijozlar'

    def __str__(self):
        return f'{self.name} ({self.phone})'


class ImportantDate(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='important_dates')
    label = models.CharField('Sana nomi', max_length=100)
    date = models.DateField('Sana')
    reminder_enabled = models.BooleanField('Eslatma yoqilgan', default=True)
    last_reminded_for = models.DateField('Oxirgi yuborilgan eslatma sanasi', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Muhim sana'
        verbose_name_plural = 'Muhim sanalar'
        ordering = ['date', 'label']

    def __str__(self):
        return f'{self.label} — {self.customer.name}'


class PushSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.URLField(max_length=2048, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Push qurilmasi'
        verbose_name_plural = 'Push qurilmalari'

    def __str__(self):
        return f'{self.user.username} · {self.created_at:%Y-%m-%d}'


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Qabul qilindi'
        PROCESSING = 'processing', 'Florist tayyorlamoqda'
        SHIPPED = 'shipped', 'Kuryer yo\'lda'
        DELIVERED = 'delivered', 'Yetkazildi'
        CANCELLED = 'cancelled', 'Bekor qilindi'

    class Payment(models.TextChoices):
        CASH = 'cash', 'Kuryerga naqd'
        CARD = 'card', 'Visa / Mastercard'
        CLICK = 'click', 'Click'
        PAYME = 'payme', 'Payme'
        UZUM = 'uzum', 'Uzum Bank'

    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', 'To‘lanmagan'
        PENDING = 'pending', 'To‘lov kutilmoqda'
        PAID = 'paid', 'To‘langan'
        FAILED = 'failed', 'To‘lov amalga oshmadi'

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        related_name='orders',
        null=True,
        blank=True,
        verbose_name='Mijoz akkaunti',
    )
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    address = models.TextField()
    delivery_required = models.BooleanField('Yetkazib berish kerak', default=True)
    latitude = models.DecimalField('Kenglik', max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField('Uzunlik', max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_note = models.CharField(max_length=255, blank=True)
    card_message = models.TextField(blank=True)
    anonymous_delivery = models.BooleanField(default=False)
    payment_method = models.CharField(max_length=20, choices=Payment.choices, default=Payment.CASH)
    payment_status = models.CharField(
        'To‘lov holati',
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.PositiveIntegerField(default=0)
    assigned_florist = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='florist_orders',
        verbose_name='Biriktirilgan florist',
    )
    assigned_courier = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courier_orders',
        verbose_name='Biriktirilgan kuryer',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Buyurtma'
        verbose_name_plural = 'Buyurtmalar'
        ordering = ['-created_at']

    def __str__(self):
        return f"#{self.pk} - {self.customer_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    price = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class StaffProfile(models.Model):
    class Role(models.TextChoices):
        SUPER_ADMIN = 'super_admin', 'Super Admin'
        MANAGER = 'manager', 'Menejer'
        FLORIST = 'florist', 'Florist'
        COURIER = 'courier', 'Kuryer'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='mimoza_profile', verbose_name='Foydalanuvchi')
    role = models.CharField('Rol', max_length=20, choices=Role.choices, default=Role.MANAGER)
    phone = models.CharField('Telefon', max_length=30, blank=True)
    is_active_worker = models.BooleanField('Faol xodim', default=True)

    class Meta:
        verbose_name = 'Xodim profili'
        verbose_name_plural = 'Xodimlar va rollar'

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_role_display()}"


class DeliveryTariff(models.Model):
    name = models.CharField('Tarif nomi', max_length=100)
    distance_km = models.PositiveIntegerField('Masofa (km)', default=0)
    district = models.CharField('Tuman', max_length=100, blank=True)
    price = models.PositiveIntegerField('Narxi (UZS)', default=0)
    is_active = models.BooleanField('Faol', default=True)

    class Meta:
        verbose_name = 'Yetkazib berish tarifi'
        verbose_name_plural = 'Yetkazib berish tariflari'
        ordering = ['district', 'distance_km']

    def __str__(self):
        return f"{self.name} - {self.price} UZS"


class MimozaSettings(models.Model):
    shop_name = models.CharField('Do‘kon nomi', max_length=150, default='Mimoza Floral')
    phone = models.CharField('Do‘kon telefoni', max_length=30, blank=True)
    address = models.CharField('Manzil', max_length=255, blank=True)
    click_api_key = models.CharField('Click API kaliti', max_length=255, blank=True)
    payme_api_key = models.CharField('Payme API kaliti', max_length=255, blank=True)
    uzum_api_key = models.CharField('Uzum API kaliti', max_length=255, blank=True)
    sms_login = models.CharField('SMS login', max_length=255, blank=True)
    sms_password = models.CharField('SMS paroli', max_length=255, blank=True)
    updated_at = models.DateTimeField('Yangilangan', auto_now=True)

    class Meta:
        verbose_name = 'Sozlama'
        verbose_name_plural = 'Sozlamalar'

    def __str__(self):
        return self.shop_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]
