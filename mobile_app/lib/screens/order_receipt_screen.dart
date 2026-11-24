import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/order_receipt.dart';
import '../services/store_api.dart';
import '../state/account_controller.dart';
import '../widgets/product_card.dart';

class OrderReceiptScreen extends StatefulWidget {
  const OrderReceiptScreen({
    required this.api,
    required this.account,
    required this.orderId,
    this.initialReceipt,
    super.key,
  });

  final StoreApi api;
  final AccountController account;
  final int orderId;
  final OrderReceipt? initialReceipt;

  @override
  State<OrderReceiptScreen> createState() => _OrderReceiptScreenState();
}

class _OrderReceiptScreenState extends State<OrderReceiptScreen> {
  OrderReceipt? _receipt;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _receipt = widget.initialReceipt;
    if (_receipt == null) _load();
  }

  Future<void> _load({bool? delivery}) async {
    final token = widget.account.accessToken;
    if (token == null) {
      setState(() => _error = 'Akkauntga qayta kiring.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final receipt = delivery == null
          ? await widget.api.fetchOrder(widget.orderId, token)
          : await widget.api.setOrderDelivery(widget.orderId, delivery, token);
      if (mounted) setState(() => _receipt = receipt);
    } on StoreApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openTelegram(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null || !uri.hasAuthority || uri.scheme != 'https') {
      setState(() => _error = 'Telegram havolasi noto‘g‘ri.');
      return;
    }
    try {
      if (!await launchUrl(uri, mode: LaunchMode.externalApplication) &&
          mounted) {
        setState(() => _error = 'Telegram’ni ochib bo‘lmadi.');
      }
    } on PlatformException {
      if (mounted) setState(() => _error = 'Telegram’ni ochib bo‘lmadi.');
    }
  }

  Future<void> _openPayment(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null ||
        uri.scheme != 'https' ||
        !{'my.click.uz', 'pay.payme.uz'}.contains(uri.host)) {
      setState(() => _error = 'To‘lov havolasi noto‘g‘ri.');
      return;
    }
    try {
      if (!await launchUrl(uri, mode: LaunchMode.externalApplication) &&
          mounted) {
        setState(() => _error = 'To‘lov sahifasini ochib bo‘lmadi.');
      }
    } on PlatformException {
      if (mounted) setState(() => _error = 'To‘lov sahifasini ochib bo‘lmadi.');
    }
  }

  Future<void> _continuePayment() async {
    final receipt = _receipt;
    final token = widget.account.accessToken;
    if (receipt == null || token == null) {
      setState(() => _error = 'Akkauntga qayta kiring.');
      return;
    }
    if (receipt.checkoutUrl.isNotEmpty) {
      await _openPayment(receipt.checkoutUrl);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final updated = await widget.api.retryOrderPayment(widget.orderId, token);
      if (mounted) setState(() => _receipt = updated);
      await _openPayment(updated.checkoutUrl);
    } on StoreApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final receipt = _receipt;
    final requiresAdvance =
        receipt != null &&
        const {'click', 'payme', 'uzum'}.contains(receipt.paymentMethod) &&
        receipt.paymentStatus != 'paid';
    return Scaffold(
      appBar: AppBar(
        title: const Text('Buyurtma'),
        actions: [
          IconButton(
            tooltip: 'Yangilash',
            onPressed: _loading ? null : () => _load(),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) ...[
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
            const SizedBox(height: 12),
            if (receipt == null)
              OutlinedButton(
                onPressed: _loading ? null : () => _load(),
                child: const Text('Qayta urinish'),
              ),
          ],
          if (receipt != null) ...[
            const Text(
              'Buyurtma ma’lumotlari',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 12),
            Text(
              '5 xonali kod: ${receipt.code}',
              style: const TextStyle(fontSize: 20),
            ),
            const SizedBox(height: 6),
            Text('Holati: ${receipt.status}'),
            Text('Jami: ${formatUzs(receipt.total)}'),
            Text(
              receipt.paymentStatus == 'paid'
                  ? '30% avans to‘landi; qolgan 70% topshirishda.'
                  : requiresAdvance
                  ? '30% avans to‘lovi kutilmoqda.'
                  : 'To‘lov topshirishda amalga oshiriladi.',
            ),
            if (requiresAdvance) ...[
              const SizedBox(height: 10),
              FilledButton(
                onPressed: _loading ? null : _continuePayment,
                child: const Text('To‘lovni davom ettirish yoki qayta urinish'),
              ),
            ],
            const SizedBox(height: 20),
            if (!requiresAdvance) ...[
              Center(
                child: Container(
                  color: Colors.white,
                  padding: const EdgeInsets.all(8),
                  child: Image.memory(receipt.qr, width: 220, height: 220),
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                'QR kodni yoki buyurtma raqamini do‘konchiga ko‘rsating.',
              ),
              const SizedBox(height: 20),
              if (receipt.deliveryRequired == null) ...[
                const Text('Yetkazib berish kerakmi?'),
                const SizedBox(height: 10),
                FilledButton(
                  onPressed: _loading ? null : () => _load(delivery: true),
                  child: const Text('Ha, yetkazib berilsin'),
                ),
                OutlinedButton(
                  onPressed: _loading ? null : () => _load(delivery: false),
                  child: const Text('Yo‘q, do‘kondan olib ketaman'),
                ),
              ] else if (receipt.deliveryRequired!) ...[
                const Text(
                  'Telegram’da buyurtma kodi va lokatsiyangizni yuboring.',
                ),
                const SizedBox(height: 10),
                FilledButton(
                  onPressed: () => _openTelegram(receipt.telegramUrl),
                  child: const Text('Telegram’da yuborish'),
                ),
              ] else
                const Text('Buyurtmangizni do‘kondan olib ketishingiz mumkin.'),
            ] else
              const Text(
                'To‘lov tasdiqlangach, yangilash tugmasi orqali QR kodni oching.',
              ),
          ],
        ],
      ),
    );
  }
}
