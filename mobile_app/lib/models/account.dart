class CustomerAccount {
  const CustomerAccount({
    required this.username,
    required this.name,
    required this.phone,
    required this.email,
    required this.cashback,
    required this.orders,
    this.staffRole,
  });

  final String username;
  final String name;
  final String phone;
  final String email;
  final int cashback;
  final List<CustomerOrder> orders;
  final String? staffRole;

  bool get isAdmin => staffRole == 'super_admin' || staffRole == 'manager';

  factory CustomerAccount.fromJson(Map<String, dynamic> json) {
    final customer = json['customer'];
    if (customer != null && customer is! Map<String, dynamic>) {
      throw const FormatException('Mijoz profili noto‘g‘ri.');
    }
    final orderItems = json['orders'];
    if (orderItems is! List) {
      throw const FormatException('Buyurtmalar ro‘yxati noto‘g‘ri.');
    }

    final customerData = customer as Map<String, dynamic>?;
    final username = _optionalString(json, 'username');
    final fullName = _optionalString(json, 'full_name');
    final customerName = customerData == null
        ? ''
        : _optionalString(customerData, 'name');

    return CustomerAccount(
      username: username,
      name: customerName.isNotEmpty
          ? customerName
          : (fullName.isNotEmpty ? fullName : username),
      phone: customerData == null ? '' : _optionalString(customerData, 'phone'),
      email: customerData == null
          ? _optionalString(json, 'email')
          : _optionalString(customerData, 'email'),
      cashback: customerData?['cashback'] is num
          ? (customerData!['cashback'] as num).toInt()
          : 0,
      orders: orderItems
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Buyurtma ma’lumoti noto‘g‘ri.');
            }
            return CustomerOrder.fromJson(item);
          })
          .toList(growable: false),
      staffRole: json['staff_role'] is String
          ? json['staff_role'] as String
          : null,
    );
  }
}

class CustomerOrder {
  const CustomerOrder({
    required this.id,
    required this.code,
    required this.createdAt,
    required this.status,
    required this.total,
    this.paymentStatus = 'unpaid',
    this.paymentMethod = 'cash',
    required this.items,
  });

  final int id;
  final String code;
  final DateTime createdAt;
  final String status;
  final int total;
  final String paymentStatus;
  final String paymentMethod;
  final List<CustomerOrderItem> items;

  factory CustomerOrder.fromJson(Map<String, dynamic> json) {
    final itemList = json['items'];
    final createdAtValue = json['created_at'];
    if (itemList is! List || createdAtValue is! String) {
      throw const FormatException('Buyurtma ma’lumoti to‘liq emas.');
    }
    final createdAt = DateTime.tryParse(createdAtValue);
    if (createdAt == null) {
      throw const FormatException('Buyurtma sanasi noto‘g‘ri.');
    }

    return CustomerOrder(
      id: _requiredInt(json, 'id'),
      code: _optionalString(json, 'order_code'),
      createdAt: createdAt,
      status: _optionalString(json, 'status'),
      total: _requiredInt(json, 'total'),
      paymentStatus: _optionalString(json, 'payment_status'),
      paymentMethod: _optionalString(json, 'payment_method'),
      items: itemList
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Buyurtma tarkibi noto‘g‘ri.');
            }
            return CustomerOrderItem.fromJson(item);
          })
          .toList(growable: false),
    );
  }
}

class CustomerOrderItem {
  const CustomerOrderItem({
    required this.name,
    required this.quantity,
    required this.price,
  });

  final String name;
  final int quantity;
  final int price;

  factory CustomerOrderItem.fromJson(Map<String, dynamic> json) {
    return CustomerOrderItem(
      name: _optionalString(json, 'name'),
      quantity: _requiredInt(json, 'quantity'),
      price: _requiredInt(json, 'price'),
    );
  }
}

String _optionalString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value == null) return '';
  if (value is! String) {
    throw FormatException('Hisob ma’lumotida "$key" maydoni noto‘g‘ri.');
  }
  return value;
}

int _requiredInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! num) {
    throw FormatException('Hisob ma’lumotida "$key" maydoni noto‘g‘ri.');
  }
  return value.toInt();
}
