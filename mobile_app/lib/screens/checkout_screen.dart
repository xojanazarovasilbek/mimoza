import 'dart:math';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/store_api.dart';
import '../state/account_controller.dart';
import '../state/cart_model.dart';
import 'order_receipt_screen.dart';
import '../widgets/product_card.dart';

class CheckoutScreen extends StatefulWidget {
  const CheckoutScreen({
    required this.api,
    required this.account,
    required this.cart,
    super.key,
  });

  final StoreApi api;
  final AccountController account;
  final CartModel cart;

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  late final TextEditingController _nameController;
  late final TextEditingController _phoneController;
  String _paymentMethod = 'click';
  List<String> _providers = const [];
  String? _requestKey;
  String? _error;
  bool _isSubmitting = false;
  bool _isLoadingProviders = true;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(
      text: widget.account.account?.name ?? '',
    );
    _phoneController = TextEditingController(
      text: widget.account.account?.phone ?? '',
    );
    _loadProviders();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  String _formatTiyin(int amount) {
    final sum = formatUzs(amount ~/ 100).replaceFirst(' so‘m', '');
    final fraction = amount % 100;
    return fraction == 0
        ? '$sum so‘m'
        : '$sum,${fraction.toString().padLeft(2, '0')} so‘m';
  }

  String _createRequestKey() {
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex = bytes
        .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
        .join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
        '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  Future<void> _loadProviders() async {
    try {
      final methods = await widget.api.fetchPaymentMethods();
      if (!mounted) return;
      setState(() {
        _providers = methods;
        if (!_providers.contains(_paymentMethod) && _providers.isNotEmpty) {
          _paymentMethod = _providers.first;
        }
      });
    } on StoreApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _isLoadingProviders = false);
    }
  }

  Future<void> _submit() async {
    final accessToken = widget.account.accessToken;
    if (accessToken == null) {
      setState(() => _error = 'Buyurtma berish uchun akkauntga kiring.');
      return;
    }
    if (_nameController.text.trim().isEmpty ||
        _phoneController.text.trim().isEmpty) {
      setState(() => _error = 'Ism va telefon raqamini kiriting.');
      return;
    }

    setState(() {
      _isSubmitting = true;
      _error = null;
      _requestKey ??= _createRequestKey();
    });
    try {
      final receipt = await widget.api.createOrder(
        accessToken: accessToken,
        body: {
          'request_key': _requestKey,
          'customer_name': _nameController.text.trim(),
          'phone': _phoneController.text.trim(),
          'payment_method': _paymentMethod,
          'items': widget.cart.lines
              .map(
                (line) => {
                  'product_id': line.product.id,
                  'quantity': line.quantity,
                  'price': line.product.price,
                },
              )
              .toList(growable: false),
        },
      );
      final checkoutUri = Uri.tryParse(receipt.checkoutUrl);
      if (checkoutUri == null ||
          !checkoutUri.hasScheme ||
          !await launchUrl(checkoutUri, mode: LaunchMode.externalApplication)) {
        setState(() {
          _error = 'To‘lov sahifasini ochib bo‘lmadi. Qayta urinib ko‘ring.';
        });
        return;
      }
      widget.cart.clear();
      _requestKey = null;
      if (mounted) {
        await Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => OrderReceiptScreen(
              api: widget.api,
              account: widget.account,
              orderId: receipt.id,
              initialReceipt: receipt,
            ),
          ),
        );
      }
    } on StoreApiException catch (exception) {
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Buyurtma berish')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        TextFormField(
          controller: _nameController,
          decoration: const InputDecoration(labelText: 'Ism'),
          textCapitalization: TextCapitalization.words,
        ),
        const SizedBox(height: 8),
        TextFormField(
          controller: _phoneController,
          decoration: const InputDecoration(labelText: 'Telefon'),
          keyboardType: TextInputType.phone,
        ),
        const SizedBox(height: 16),
        Text('Jami: ${formatUzs(widget.cart.total)}'),
        const SizedBox(height: 8),
        Text('Oldindan 30%: ${_formatTiyin(widget.cart.total * 30)}'),
        const SizedBox(height: 8),
        Text('Topshirishda 70%: ${_formatTiyin(widget.cart.total * 70)}'),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          initialValue: _providers.contains(_paymentMethod)
              ? _paymentMethod
              : null,
          decoration: const InputDecoration(labelText: 'Avans to‘lovi'),
          items: [
            for (final provider in _providers)
              DropdownMenuItem(
                value: provider,
                child: Text(provider == 'click' ? 'Click' : 'Payme'),
              ),
          ],
          onChanged: _isSubmitting || _providers.isEmpty
              ? null
              : (value) {
                  if (value != null) setState(() => _paymentMethod = value);
                },
        ),
        if (!_isLoadingProviders && _providers.isEmpty)
          const Padding(
            padding: EdgeInsets.only(top: 12),
            child: Text(
              'Click yoki Payme serverda sozlanmaguncha buyurtma qabul qilinmaydi.',
            ),
          ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          Text(
            _error!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        const SizedBox(height: 16),
        FilledButton(
          onPressed:
              _isSubmitting ||
                  _isLoadingProviders ||
                  _providers.isEmpty ||
                  widget.cart.itemCount == 0
              ? null
              : _submit,
          child: Text(
            _isSubmitting
                ? 'Kutilmoqda…'
                : _isLoadingProviders
                ? 'To‘lov usullari yuklanmoqda…'
                : '30% avansni to‘lash',
          ),
        ),
      ],
    ),
  );
}
