class Choice {
  const Choice(this.value, this.label);
  final String value;
  final String label;
  factory Choice.fromJson(Map<String, dynamic> json) =>
      Choice(_string(json, 'value'), _string(json, 'label'));
}

class AdminWorker {
  const AdminWorker(this.id, this.name, this.role);
  final int id;
  final String name;
  final String role;
  factory AdminWorker.fromJson(Map<String, dynamic> json) => AdminWorker(
    _int(json, 'id'),
    _string(json, 'name'),
    _string(json, 'role'),
  );
}

class AdminOrder {
  const AdminOrder({
    required this.id,
    required this.code,
    required this.name,
    required this.phone,
    required this.status,
    required this.total,
    required this.delivery,
    required this.payment,
    required this.paymentStatus,
    required this.items,
    required this.floristId,
    required this.courierId,
  });
  final int id, total;
  final String code, name, phone, status, payment, paymentStatus;
  final bool? delivery;
  final int? floristId, courierId;
  final List<AdminOrderItem> items;

  factory AdminOrder.fromJson(Map<String, dynamic> json) {
    final delivery = json['delivery_required'];
    if (delivery != null && delivery is! bool) {
      throw const FormatException('Yetkazish ma’lumoti noto‘g‘ri.');
    }
    return AdminOrder(
      id: _int(json, 'id'),
      code: _string(json, 'code'),
      name: _string(json, 'customer_name'),
      phone: _string(json, 'phone'),
      status: _string(json, 'status'),
      total: _int(json, 'total'),
      delivery: delivery as bool?,
      payment: _string(json, 'payment'),
      paymentStatus: _string(json, 'payment_status'),
      floristId: _nullableInt(json, 'florist_id'),
      courierId: _nullableInt(json, 'courier_id'),
      items: _list(json, 'items', AdminOrderItem.fromJson),
    );
  }
}

class AdminOrderItem {
  const AdminOrderItem(this.id, this.name, this.quantity);
  final int id, quantity;
  final String name;
  factory AdminOrderItem.fromJson(Map<String, dynamic> json) => AdminOrderItem(
    _int(json, 'product_id'),
    _string(json, 'name'),
    _int(json, 'quantity'),
  );
}

class AdminOrdersPage {
  const AdminOrdersPage(this.orders, this.workers, this.statuses, this.hasNext);
  final List<AdminOrder> orders;
  final List<AdminWorker> workers;
  final List<Choice> statuses;
  final bool hasNext;
  factory AdminOrdersPage.fromJson(Map<String, dynamic> json) =>
      AdminOrdersPage(
        _list(json, 'orders', AdminOrder.fromJson),
        _list(json, 'workers', AdminWorker.fromJson),
        _list(json, 'statuses', Choice.fromJson),
        _bool(json, 'has_next'),
      );
}

class AdminCategory {
  const AdminCategory(this.id, this.name);
  final int id;
  final String name;
  factory AdminCategory.fromJson(Map<String, dynamic> json) =>
      AdminCategory(_int(json, 'id'), _string(json, 'name'));
}

class AdminProduct {
  const AdminProduct({
    required this.id,
    required this.name,
    required this.slug,
    required this.categoryId,
    required this.category,
    required this.description,
    required this.price,
    required this.oldPrice,
    required this.imageUrl,
    required this.videoUrl,
    required this.hasImage,
    required this.hasVideo,
    required this.quantity,
    required this.inStock,
    required this.featured,
    required this.version,
  });
  final int id, categoryId, price, quantity;
  final int? oldPrice;
  final String name, slug, category, description, imageUrl, videoUrl;
  final String version;
  final bool hasImage, hasVideo, inStock, featured;
  factory AdminProduct.fromJson(Map<String, dynamic> json) => AdminProduct(
    id: _int(json, 'id'),
    name: _string(json, 'name'),
    slug: _string(json, 'slug'),
    categoryId: _int(json, 'category_id'),
    category: _string(json, 'category'),
    description: _string(json, 'description'),
    price: _int(json, 'price'),
    oldPrice: _nullableInt(json, 'old_price'),
    imageUrl: _string(json, 'image_url'),
    videoUrl: _string(json, 'video_url'),
    hasImage: _bool(json, 'has_image'),
    hasVideo: _bool(json, 'has_video'),
    quantity: _int(json, 'stock_quantity'),
    inStock: _bool(json, 'in_stock'),
    featured: _bool(json, 'is_featured'),
    version: _string(json, 'version'),
  );
}

class AdminProductsPage {
  const AdminProductsPage(this.products, this.categories, this.hasNext);
  final List<AdminProduct> products;
  final List<AdminCategory> categories;
  final bool hasNext;
  factory AdminProductsPage.fromJson(Map<String, dynamic> json) =>
      AdminProductsPage(
        _list(json, 'products', AdminProduct.fromJson),
        _list(json, 'categories', AdminCategory.fromJson),
        _bool(json, 'has_next'),
      );
}

class AdminUser {
  const AdminUser(
    this.id,
    this.username,
    this.name,
    this.role,
    this.active,
    this.isSuperuser,
  );
  final int id;
  final String username, name;
  final String? role;
  final bool active, isSuperuser;
  factory AdminUser.fromJson(Map<String, dynamic> json) {
    final role = json['role'];
    if (role != null && role is! String) {
      throw const FormatException('Xodim roli noto‘g‘ri.');
    }
    return AdminUser(
      _int(json, 'id'),
      _string(json, 'username'),
      _string(json, 'name'),
      role as String?,
      _bool(json, 'active'),
      _bool(json, 'is_superuser'),
    );
  }
}

class AdminUsersPage {
  const AdminUsersPage(this.users, this.roles, this.hasNext);
  final List<AdminUser> users;
  final List<Choice> roles;
  final bool hasNext;
  factory AdminUsersPage.fromJson(Map<String, dynamic> json) => AdminUsersPage(
    _list(json, 'users', AdminUser.fromJson),
    _list(json, 'roles', Choice.fromJson),
    _bool(json, 'has_next'),
  );
}

class AdminAnalytics {
  const AdminAnalytics(
    this.total,
    this.count,
    this.average,
    this.cancelled,
    this.daily,
    this.top,
  );
  final int total, count, average, cancelled;
  final List<DailySale> daily;
  final List<TopProduct> top;
  factory AdminAnalytics.fromJson(Map<String, dynamic> json) => AdminAnalytics(
    _int(json, 'sales_total'),
    _int(json, 'orders_count'),
    _int(json, 'average_order'),
    _int(json, 'cancelled_count'),
    _list(json, 'daily_sales', DailySale.fromJson),
    _list(json, 'top_products', TopProduct.fromJson),
  );
}

class DailySale {
  const DailySale(this.date, this.revenue, this.count);
  final String date;
  final int revenue, count;
  factory DailySale.fromJson(Map<String, dynamic> json) => DailySale(
    _string(json, 'created_at__date'),
    _int(json, 'revenue'),
    _int(json, 'orders_count'),
  );
}

class TopProduct {
  const TopProduct(this.name, this.quantity, this.revenue);
  final String name;
  final int quantity, revenue;
  factory TopProduct.fromJson(Map<String, dynamic> json) => TopProduct(
    _string(json, 'product__name'),
    _int(json, 'quantity'),
    _int(json, 'revenue'),
  );
}

class AuditEntry {
  const AuditEntry(
    this.actor,
    this.action,
    this.object,
    this.createdAt,
    this.changes,
  );
  final String actor, action, object, createdAt;
  final Map<String, AuditChange> changes;
  factory AuditEntry.fromJson(Map<String, dynamic> json) {
    final data = json['changes'];
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Tarix ma’lumotlari noto‘g‘ri.');
    }
    return AuditEntry(
      _string(json, 'actor'),
      _string(json, 'action'),
      _string(json, 'object'),
      _string(json, 'created_at'),
      data.map((key, value) {
        if (value is! Map<String, dynamic>) {
          throw const FormatException('Tarix ma’lumotlari noto‘g‘ri.');
        }
        return MapEntry(key, AuditChange(value['old'], value['new']));
      }),
    );
  }
}

class AuditChange {
  const AuditChange(this.oldValue, this.newValue);
  final Object? oldValue, newValue;
}

class AuditPage {
  const AuditPage(this.entries, this.hasNext);
  final List<AuditEntry> entries;
  final bool hasNext;
  factory AuditPage.fromJson(Map<String, dynamic> json) => AuditPage(
    _list(json, 'entries', AuditEntry.fromJson),
    _bool(json, 'has_next'),
  );
}

int _int(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! int) {
    throw const FormatException('Server ma’lumotlari noto‘g‘ri.');
  }
  return value;
}

int? _nullableInt(Map<String, dynamic> json, String key) {
  if (json[key] == null) return null;
  return _int(json, key);
}

String _string(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String) {
    throw const FormatException('Server ma’lumotlari noto‘g‘ri.');
  }
  return value;
}

bool _bool(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! bool) {
    throw const FormatException('Server ma’lumotlari noto‘g‘ri.');
  }
  return value;
}

List<T> _list<T>(
  Map<String, dynamic> json,
  String key,
  T Function(Map<String, dynamic>) parse,
) {
  final value = json[key];
  if (value is! List) {
    throw const FormatException('Server ma’lumotlari noto‘g‘ri.');
  }
  return value
      .map((item) {
        if (item is! Map<String, dynamic>) {
          throw const FormatException('Server ma’lumotlari noto‘g‘ri.');
        }
        return parse(item);
      })
      .toList(growable: false);
}
