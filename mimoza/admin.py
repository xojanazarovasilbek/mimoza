from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html

from .models import (
    Category,
    Customer,
    DeliveryTariff,
    ImportantDate,
    MimozaSettings,
    Order,
    OrderItem,
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
        'id', 'customer_name', 'phone', 'delivery_required', 'status', 'payment_method',
        'payment_status', 'assigned_florist', 'assigned_courier', 'total', 'created_at',
    )
    list_filter = ('status', 'payment_method', 'payment_status', 'created_at')
    search_fields = ('customer_name', 'phone', 'address')
    list_editable = ('status',)
    inlines = (OrderItemInline,)
    readonly_fields = ('total', 'created_at')


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
