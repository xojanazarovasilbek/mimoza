from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html

from .models import (
    AuditLog,
    Category,
    Customer,
    DeliveryTariff,
    ImportantDate,
    MimozaSettings,
    Order,
    OrderItem,
    PaymentTransaction,
    Product,
    ProductComment,
    ProductLike,
    StaffProfile,
    Story,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock_quantity', 'video_preview', 'in_stock', 'is_featured')
    list_filter = ('category', 'in_stock', 'is_featured')
    search_fields = ('name', 'description')
    list_editable = ('price', 'in_stock')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        ('Asosiy ma’lumotlar', {
            'fields': ('name', 'slug', 'category', 'description', 'price', 'old_price'),
        }),
        ('Media', {
            'fields': ('image', 'image_url', 'video', 'video_url', 'hls_playlist'),
        }),
        ('Holati', {
            'fields': ('stock_quantity', 'in_stock', 'is_featured'),
        }),
    )
    readonly_fields = ('hls_playlist',)

    @admin.display(description='Video')
    def video_preview(self, obj):
        if obj.video:
            return format_html('<video src="{}" style="width:90px;height:55px;object-fit:cover" muted></video>', obj.video.url)
        if obj.video_url:
            return format_html('<span style="color:#3D0C11;font-weight:bold">Video havola bor</span>')
        return '—'


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'product', 'is_active', 'created_at', 'expires_at')
    list_filter = ('is_active', 'expires_at')
    search_fields = ('title', 'product__name')
    autocomplete_fields = ('product',)
    readonly_fields = ('hls_playlist',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'user', 'cashback', 'is_vip')
    list_filter = ('is_vip',)
    search_fields = ('name', 'phone', 'email')


@admin.register(ImportantDate)
class ImportantDateAdmin(admin.ModelAdmin):
    list_display = ('label', 'customer', 'date', 'reminder_enabled', 'last_reminded_for')
    list_filter = ('reminder_enabled',)
    search_fields = ('label', 'customer__name', 'customer__phone')
    readonly_fields = ('last_reminded_for',)


@admin.register(ProductComment)
class ProductCommentAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'text', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('product__name', 'user__username', 'text')
    readonly_fields = ('product', 'user', 'text', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(ProductLike)
class ProductLikeAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('product__name', 'user__username')
    readonly_fields = ('product', 'user', 'created_at')

    def has_add_permission(self, request):
        return False


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'order_code', 'customer_name', 'phone', 'delivery_required', 'status', 'payment_method',
        'payment_status', 'assigned_florist', 'assigned_courier', 'total', 'created_at',
    )
    list_filter = ('status', 'payment_method', 'payment_status', 'created_at')
    search_fields = ('customer_name', 'phone', 'address')
    inlines = (OrderItemInline,)
    readonly_fields = ('total', 'created_at')

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if (
            obj
            and obj.payment_method in (Order.Payment.CLICK, Order.Payment.PAYME, Order.Payment.UZUM)
            and obj.payment_status != Order.PaymentStatus.PAID
        ):
            fields.extend(('status', 'payment_status', 'payment_method'))
        return tuple(fields)


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'provider', 'status', 'amount_tiyin', 'provider_transaction_id', 'created_at', 'expires_at')
    list_filter = ('provider', 'status', 'created_at')
    search_fields = ('order__order_code', 'provider_transaction_id', 'provider_prepare_id')
    exclude = ('checkout_url',)
    readonly_fields = (
        'order',
        'provider',
        'status',
        'amount_tiyin',
        'provider_transaction_id',
        'provider_prepare_id',
        'created_at',
        'expires_at',
        'paid_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    can_delete = False
    extra = 0
    fields = ('role', 'phone', 'is_active_worker')


admin.site.unregister(User)


@admin.register(User)
class MimozaUserAdmin(DjangoUserAdmin):
    inlines = (StaffProfileInline,)
    list_display = ('username', 'get_full_name', 'email', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'groups')
    search_fields = ('username', 'first_name', 'last_name', 'email')


@admin.register(DeliveryTariff)
class DeliveryTariffAdmin(admin.ModelAdmin):
    list_display = ('name', 'district', 'distance_km', 'price', 'is_active')
    list_editable = ('price', 'is_active')
    list_filter = ('is_active', 'district')
    search_fields = ('name', 'district')


@admin.register(MimozaSettings)
class MimozaSettingsAdmin(admin.ModelAdmin):
    list_display = ('shop_name', 'phone', 'updated_at')
    fieldsets = (
        ('Do‘kon', {
            'fields': ('shop_name', 'phone', 'address'),
        }),
        ('To‘lov xizmatlari', {
            'fields': ('click_api_key', 'payme_api_key', 'uzum_api_key'),
            'classes': ('collapse',),
            'description': (
                'Bu eski maydonlar to‘lovlarda ishlatilmaydi. Kalitlarni administrator '
                'paneliga emas, serverdagi himoyalangan muhit sozlamalariga kiriting; '
                'Click va Payme to‘liq sozlanganda yoqiladi. Uzum vaqtincha o‘chiq.'
            ),
        }),
        ('SMS integratsiyasi', {
            'fields': ('sms_login', 'sms_password'),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        return not MimozaSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor_username', 'action', 'model_label', 'object_id', 'object_repr')
    list_filter = ('action', 'model_label', 'created_at')
    search_fields = ('actor_username', 'model_label', 'object_id', 'object_repr')
    readonly_fields = (
        'actor',
        'actor_username',
        'action',
        'model_label',
        'object_id',
        'object_repr',
        'changes',
        'created_at',
    )
    date_hierarchy = 'created_at'

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
