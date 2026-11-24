import 'package:flutter/material.dart';

import '../models/admin_dashboard.dart';
import '../services/store_api.dart';
import '../state/account_controller.dart';
import '../widgets/product_card.dart';
import '../widgets/product_image.dart';
import 'admin_orders_screen.dart';
import 'admin_products_screen.dart';
import 'admin_reports_screen.dart';

class AdminDashboardScreen extends StatefulWidget {
  const AdminDashboardScreen({
    required this.api,
    required this.account,
    super.key,
  });

  final StoreApi api;
  final AccountController account;

  @override
  State<AdminDashboardScreen> createState() => _AdminDashboardScreenState();
}

class _AdminDashboardScreenState extends State<AdminDashboardScreen> {
  AdminDashboard? _dashboard;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_loading) return;
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
      final dashboard = await widget.api.fetchAdminDashboard(token);
      if (mounted) setState(() => _dashboard = dashboard);
    } on StoreApiException catch (exception) {
      if (mounted) {
        setState(() {
          _error = exception.message;
          if (exception.statusCode == 401 || exception.statusCode == 403) {
            _dashboard = null;
          }
        });
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _open(Widget Function(String token) builder) async {
    final token = widget.account.accessToken;
    if (token == null) {
      setState(() => _error = 'Akkauntga qayta kiring.');
      return;
    }
    await Navigator.of(context)
        .push(MaterialPageRoute<void>(builder: (_) => builder(token)));
    if (mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final dashboard = _dashboard;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Admin dashboard'),
        actions: [
          IconButton(
            tooltip: 'Yangilash',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            tooltip: 'Akkauntdan chiqish',
            onPressed: widget.account.isLoading ? null : widget.account.signOut,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            if (_loading) const LinearProgressIndicator(),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: Colors.redAccent)),
              if (dashboard == null)
                TextButton(
                  onPressed: _loading ? null : _load,
                  child: const Text('Qayta urinish'),
                ),
            ],
            if (dashboard != null) ...[
              LayoutBuilder(
                builder: (context, constraints) {
                  final width = (constraints.maxWidth - 10) / 2;
                  return Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: [
                      _metric(
                        width,
                        'Bugungi buyurtmalar',
                        '${dashboard.ordersToday}',
                      ),
                      _metric(
                        width,
                        'Kutilayotgan buyurtmalar',
                        '${dashboard.pendingOrders}',
                      ),
                      _metric(
                        width,
                        'Bugungi tushum',
                        formatUzs(dashboard.todayRevenue),
                      ),
                      _metric(
                        width,
                        'Mahsulotlar',
                        '${dashboard.productsCount}',
                      ),
                    ],
                  );
                },
              ),
              const SizedBox(height: 24),
              const Text(
                'Boshqaruv',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  FilledButton(
                    onPressed: () => _open(
                      (token) =>
                          AdminOrdersScreen(api: widget.api, token: token),
                    ),
                    child: const Text('Buyurtmalar'),
                  ),
                  FilledButton(
                    onPressed: () => _open(
                      (token) =>
                          AdminProductsScreen(api: widget.api, token: token),
                    ),
                    child: const Text('Mahsulotlar'),
                  ),
                  FilledButton(
                    onPressed: () => _open(
                      (token) =>
                          AdminAnalyticsScreen(api: widget.api, token: token),
                    ),
                    child: const Text('Analitika'),
                  ),
                  if (widget.account.account?.staffRole == 'super_admin') ...[
                    FilledButton(
                      onPressed: () => _open(
                        (token) =>
                            AdminUsersScreen(api: widget.api, token: token),
                      ),
                      child: const Text('Xodimlar'),
                    ),
                    FilledButton(
                      onPressed: () => _open(
                        (token) =>
                            AdminAuditScreen(api: widget.api, token: token),
                      ),
                      child: const Text('Harakatlar tarixi'),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 24),
              const Text(
                'So‘nggi buyurtmalar',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 10),
              if (dashboard.recentOrders.isEmpty)
                const Text('Buyurtmalar hali yo‘q.')
              else
                ...dashboard.recentOrders.map(_orderCard),
              const SizedBox(height: 20),
              const Text(
                'Kam qolgan mahsulotlar',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 10),
              if (dashboard.lowStock.isEmpty)
                const Text('Ombor qoldig‘i yaxshi.')
              else
                ...dashboard.lowStock.map(_stockCard),
            ],
          ],
        ),
      ),
    );
  }

  Widget _metric(double width, String label, String value) => SizedBox(
    width: width,
    child: Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: const TextStyle(color: mimozaMaroon)),
            const SizedBox(height: 8),
            Text(
              value,
              style: const TextStyle(
                color: mimozaMaroon,
                fontSize: 20,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    ),
  );

  Widget _orderCard(DashboardOrder order) {
    final time = order.createdAt.toLocal();
    final date =
        '${time.day.toString().padLeft(2, '0')}.'
        '${time.month.toString().padLeft(2, '0')}.${time.year} '
        '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        title: Text(
          '#${order.code} · ${order.customerName}',
          style: const TextStyle(color: mimozaMaroon),
        ),
        subtitle: Text(
          '$date\n${order.status}',
          style: const TextStyle(color: Color(0xFF786B64)),
        ),
        isThreeLine: true,
        trailing: Text(
          formatUzs(order.total),
          style: const TextStyle(color: mimozaMaroon),
        ),
      ),
    );
  }

  Widget _stockCard(DashboardStock product) => Card(
    margin: const EdgeInsets.only(bottom: 8),
    child: ListTile(
      title: Text(product.name, style: const TextStyle(color: mimozaMaroon)),
      subtitle: Text(
        product.category,
        style: const TextStyle(color: Color(0xFF786B64)),
      ),
      trailing: Text(
        '${product.quantity} ta',
        style: const TextStyle(color: mimozaMaroon),
      ),
    ),
  );
}
