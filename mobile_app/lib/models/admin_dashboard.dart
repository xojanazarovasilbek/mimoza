class AdminDashboard {
  const AdminDashboard({
    required this.ordersToday,
    required this.pendingOrders,
    required this.todayRevenue,
    required this.productsCount,
    required this.recentOrders,
    required this.lowStock,
  });

  final int ordersToday;
  final int pendingOrders;
  final int todayRevenue;
  final int productsCount;
  final List<DashboardOrder> recentOrders;
  final List<DashboardStock> lowStock;

  factory AdminDashboard.fromJson(Map<String, dynamic> json) {
    final orders = json['recent_orders'];
    final stock = json['low_stock'];
    if (orders is! List || stock is! List) {
      throw const FormatException('Dashboard ma’lumotlari noto‘g‘ri.');
    }
    return AdminDashboard(
      ordersToday: _integer(json, 'orders_today'),
      pendingOrders: _integer(json, 'pending_orders'),
      todayRevenue: _integer(json, 'today_revenue'),
      productsCount: _integer(json, 'products_count'),
      recentOrders: orders
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Buyurtma ma’lumotlari noto‘g‘ri.');
            }
            return DashboardOrder.fromJson(item);
          })
          .toList(growable: false),
      lowStock: stock
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Ombor ma’lumotlari noto‘g‘ri.');
            }
            return DashboardStock.fromJson(item);
          })
          .toList(growable: false),
    );
  }
}

class DashboardOrder {
  const DashboardOrder({
    required this.code,
    required this.customerName,
    required this.status,
    required this.total,
    required this.createdAt,
  });

  final String code;
  final String customerName;
  final String status;
  final int total;
  final DateTime createdAt;

  factory DashboardOrder.fromJson(Map<String, dynamic> json) {
    final createdAt = DateTime.tryParse(_string(json, 'created_at'));
    if (createdAt == null) {
      throw const FormatException('Buyurtma sanasi noto‘g‘ri.');
    }
    return DashboardOrder(
      code: _string(json, 'order_code'),
      customerName: _string(json, 'customer_name'),
      status: _string(json, 'status'),
      total: _integer(json, 'total'),
      createdAt: createdAt,
    );
  }
}

class DashboardStock {
  const DashboardStock({
    required this.name,
    required this.category,
    required this.quantity,
  });

  final String name;
  final String category;
  final int quantity;

  factory DashboardStock.fromJson(Map<String, dynamic> json) => DashboardStock(
    name: _string(json, 'name'),
    category: _string(json, 'category'),
    quantity: _integer(json, 'quantity'),
  );
}

int _integer(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! int) {
    throw const FormatException('Dashboard ma’lumotlari noto‘g‘ri.');
  }
  return value;
}

String _string(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String) {
    throw const FormatException('Dashboard ma’lumotlari noto‘g‘ri.');
  }
  return value;
}
