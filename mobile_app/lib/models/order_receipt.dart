import 'dart:convert';
import 'dart:typed_data';

class OrderReceipt {
  const OrderReceipt({
    required this.id,
    required this.code,
    required this.status,
    required this.total,
    required this.deliveryRequired,
    required this.qr,
    required this.telegramUrl,
    this.paymentStatus = 'unpaid',
    this.paymentMethod = 'cash',
    this.checkoutUrl = '',
  });

  final int id;
  final String code;
  final String status;
  final int total;
  final bool? deliveryRequired;
  final Uint8List qr;
  final String telegramUrl;
  final String paymentStatus;
  final String paymentMethod;
  final String checkoutUrl;

  factory OrderReceipt.fromJson(Map<String, dynamic> json) {
    final id = json['id'];
    final code = json['order_code'];
    final status = json['status'];
    final total = json['total'];
    final delivery = json['delivery_required'];
    final encodedQr = json['qr_base64'];
    final telegramUrl = json['telegram_url'];
    final checkoutUrl = json['checkout_url'];
    final paymentStatus = json['payment_status'];
    final paymentMethod = json['payment_method'];
    if (id is! int ||
        code is! String ||
        status is! String ||
        total is! int ||
        (delivery != null && delivery is! bool) ||
        encodedQr is! String ||
        telegramUrl is! String ||
        (paymentStatus != null && paymentStatus is! String) ||
        (paymentMethod != null && paymentMethod is! String) ||
        (checkoutUrl != null && checkoutUrl is! String)) {
      throw const FormatException('Buyurtma ma’lumotlari noto‘g‘ri.');
    }
    return OrderReceipt(
      id: id,
      code: code,
      status: status,
      total: total,
      deliveryRequired: delivery as bool?,
      qr: base64Decode(encodedQr),
      telegramUrl: telegramUrl,
      paymentStatus: paymentStatus as String? ?? 'unpaid',
      paymentMethod: paymentMethod as String? ?? 'cash',
      checkoutUrl: checkoutUrl as String? ?? '',
    );
  }
}
