import 'package:flutter/foundation.dart';

import '../models/product.dart';

class CartLine {
  const CartLine({required this.product, required this.quantity});

  final Product product;
  final int quantity;

  int get subtotal => product.price * quantity;
}

class CartModel extends ChangeNotifier {
  final Map<int, CartLine> _lines = {};

  List<CartLine> get lines => List.unmodifiable(_lines.values);
  int get itemCount =>
      _lines.values.fold(0, (total, line) => total + line.quantity);
  int get total => _lines.values.fold(0, (sum, line) => sum + line.subtotal);

  void clear() {
    if (_lines.isEmpty) return;
    _lines.clear();
    notifyListeners();
  }

  void add(Product product) {
    final current = _lines[product.id]?.quantity ?? 0;
    if (current >= product.stockQuantity) return;
    _lines[product.id] = CartLine(product: product, quantity: current + 1);
    notifyListeners();
  }

  void setQuantity(Product product, int quantity) {
    if (quantity <= 0) {
      _lines.remove(product.id);
    } else {
      _lines[product.id] = CartLine(
        product: product,
        quantity: quantity.clamp(1, product.stockQuantity),
      );
    }
    notifyListeners();
  }
}
