import 'package:flutter/material.dart';

import '../models/admin_management.dart';
import '../services/store_api.dart';
import '../widgets/product_card.dart';

class AdminOrdersScreen extends StatefulWidget {
  const AdminOrdersScreen({required this.api, required this.token, super.key});
  final StoreApi api;
  final String token;

  @override
  State<AdminOrdersScreen> createState() => _AdminOrdersScreenState();
}

class _AdminOrdersScreenState extends State<AdminOrdersScreen> {
  final _query = TextEditingController();
  AdminOrdersPage? _data;
  int _page = 1;
  String _status = '';
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _data = null;
    });
    try {
      final page = await widget.api.fetchAdminOrders(
        widget.token,
        page: _page,
        query: _query.text.trim(),
        status: _status,
      );
      if (mounted) setState(() => _data = page);
    } on StoreApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _edit(AdminOrder order, AdminOrdersPage data) async {
    var status = order.status;
    var florist = order.floristId;
    var courier = order.courierId;
    List<DropdownMenuItem<int?>> workers(String role, int? selected) {
      final options = data.workers
          .where((worker) => worker.role == role)
          .toList();
      return [
        const DropdownMenuItem<int?>(value: null, child: Text('Tanlanmagan')),
        if (selected != null && !options.any((worker) => worker.id == selected))
          DropdownMenuItem<int?>(
            value: selected,
            child: const Text('Avvalgi xodim faol emas'),
          ),
        ...options.map(
          (worker) => DropdownMenuItem<int?>(
            value: worker.id,
            child: Text(worker.name),
          ),
        ),
      ];
    }

    final result =
        await showDialog<({String status, int? florist, int? courier})>(
          context: context,
          builder: (context) => StatefulBuilder(
            builder: (context, update) => AlertDialog(
              title: Text('Buyurtma ${order.code}'),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    DropdownButtonFormField<String>(
                      initialValue: status,
                      decoration: const InputDecoration(labelText: 'Holat'),
                      items: data.statuses
                          .map(
                            (item) => DropdownMenuItem(
                              value: item.value,
                              child: Text(item.label),
                            ),
                          )
                          .toList(),
                      onChanged: (value) =>
                          update(() => status = value ?? status),
                    ),
                    DropdownButtonFormField<int?>(
                      initialValue: florist,
                      decoration: const InputDecoration(labelText: 'Florist'),
                      items: workers('florist', florist),
                      onChanged: (value) => update(() => florist = value),
                    ),
                    DropdownButtonFormField<int?>(
                      initialValue: courier,
                      decoration: const InputDecoration(labelText: 'Kuryer'),
                      items: workers('courier', courier),
                      onChanged: (value) => update(() => courier = value),
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Bekor qilish'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(context, (
                    status: status,
                    florist: florist,
                    courier: courier,
                  )),
                  child: const Text('Saqlash'),
                ),
              ],
            ),
          ),
        );
    if (result == null || !mounted) return;
    setState(() => _loading = true);
    try {
      await widget.api.updateAdminOrder(
        widget.token,
        order.id,
        status: result.status,
        floristId: result.florist,
        courierId: result.courier,
      );
      if (mounted) {
        setState(() => _loading = false);
        await _load();
      }
    } on StoreApiException catch (exception) {
      if (mounted) {
        setState(() => _loading = false);
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(exception.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return Scaffold(
      appBar: AppBar(title: const Text('Buyurtmalar')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _query,
            enabled: !_loading,
            decoration: const InputDecoration(
              labelText: 'Kod, ID, ism yoki telefon',
            ),
            onSubmitted: (_) {
              _page = 1;
              _load();
            },
          ),
          if (data != null)
            DropdownButtonFormField<String>(
              initialValue: _status,
              decoration: const InputDecoration(labelText: 'Holat'),
              items: [
                const DropdownMenuItem(
                  value: '',
                  child: Text('Barcha holatlar'),
                ),
                ...data.statuses.map(
                  (item) => DropdownMenuItem(
                    value: item.value,
                    child: Text(item.label),
                  ),
                ),
              ],
              onChanged: _loading
                  ? null
                  : (value) {
                      setState(() {
                        _status = value ?? '';
                        _page = 1;
                      });
                      _load();
                    },
            ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: _loading
                ? null
                : () {
                    _page = 1;
                    _load();
                  },
            child: const Text('Qidirish'),
          ),
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) ...[
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
            TextButton(
              onPressed: _loading ? null : _load,
              child: const Text('Qayta urinish'),
            ),
          ],
          if (data != null) ...[
            if (data.orders.isEmpty)
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text('Buyurtma topilmadi.'),
              ),
            ...data.orders.map((order) {
              final label =
                  data.statuses
                      .where((choice) => choice.value == order.status)
                      .map((choice) => choice.label)
                      .firstOrNull ??
                  order.status;
              final delivery = order.delivery == null
                  ? 'Tanlanmagan'
                  : order.delivery!
                  ? 'Yetkazib berish'
                  : 'Olib ketish';
              return Card(
                margin: const EdgeInsets.only(top: 10),
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '#${order.id} · Kod: ${order.code}',
                        style: const TextStyle(
                          color: Color(0xFF3B111A),
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        '${order.name} · ${order.phone}',
                        style: const TextStyle(color: Color(0xFF3B111A)),
                      ),
                      ...order.items.map(
                        (item) => Text(
                          '№${item.id} ${item.name} × ${item.quantity}',
                          style: const TextStyle(color: Color(0xFF3B111A)),
                        ),
                      ),
                      Text(
                        '$delivery · ${order.payment} · ${order.paymentStatus}',
                        style: const TextStyle(color: Color(0xFF3B111A)),
                      ),
                      Text(
                        '$label · ${formatUzs(order.total)}',
                        style: const TextStyle(color: Color(0xFF3B111A)),
                      ),
                      TextButton(
                        onPressed: _loading ? null : () => _edit(order, data),
                        child: const Text('Boshqarish'),
                      ),
                    ],
                  ),
                ),
              );
            }),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                TextButton(
                  onPressed: _loading || _page == 1
                      ? null
                      : () {
                          _page--;
                          _load();
                        },
                  child: const Text('Oldingi'),
                ),
                Text('$_page'),
                TextButton(
                  onPressed: _loading || !data.hasNext
                      ? null
                      : () {
                          _page++;
                          _load();
                        },
                  child: const Text('Keyingi'),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
