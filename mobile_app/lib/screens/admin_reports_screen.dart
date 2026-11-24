import 'dart:convert';

import 'package:flutter/material.dart';

import '../models/admin_management.dart';
import '../services/store_api.dart';
import '../widgets/product_card.dart';

class AdminAnalyticsScreen extends StatefulWidget {
  const AdminAnalyticsScreen({
    required this.api,
    required this.token,
    super.key,
  });
  final StoreApi api;
  final String token;
  @override
  State<AdminAnalyticsScreen> createState() => _AdminAnalyticsScreenState();
}

class _AdminAnalyticsScreenState extends State<AdminAnalyticsScreen> {
  AdminAnalytics? _data;
  int _days = 30;
  bool _loading = false;
  String? _error;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _data = null;
    });
    try {
      final result = await widget.api.fetchAdminAnalytics(widget.token, _days);
      if (mounted) setState(() => _data = result);
    } on StoreApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return Scaffold(
      appBar: AppBar(title: const Text('Analitika')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          DropdownButtonFormField<int>(
            initialValue: _days,
            decoration: const InputDecoration(labelText: 'Davr'),
            items: [7, 30, 90]
                .map(
                  (days) =>
                      DropdownMenuItem(value: days, child: Text('$days kun')),
                )
                .toList(),
            onChanged: _loading
                ? null
                : (value) {
                    setState(() => _days = value ?? 30);
                    _load();
                  },
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
            const SizedBox(height: 12),
            Text('Jami tushum: ${formatUzs(data.total)}'),
            Text('Buyurtmalar: ${data.count}'),
            Text('O‘rtacha chek: ${formatUzs(data.average)}'),
            Text('Bekor qilingan: ${data.cancelled}'),
            const SizedBox(height: 20),
            const Text(
              'Kunlik tushum',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            if (data.daily.isEmpty) const Text('Ma’lumot yo‘q.'),
            ...data.daily.map(
              (day) => ListTile(
                title: Text(day.date),
                subtitle: Text('${day.count} ta buyurtma'),
                trailing: Text(formatUzs(day.revenue)),
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Ko‘p sotilgan mahsulotlar',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            if (data.top.isEmpty) const Text('Ma’lumot yo‘q.'),
            ...data.top.map(
              (item) => ListTile(
                title: Text(item.name),
                subtitle: Text('${item.quantity} ta'),
                trailing: Text(formatUzs(item.revenue)),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class AdminAuditScreen extends StatefulWidget {
  const AdminAuditScreen({required this.api, required this.token, super.key});
  final StoreApi api;
  final String token;
  @override
  State<AdminAuditScreen> createState() => _AdminAuditScreenState();
}

class _AdminAuditScreenState extends State<AdminAuditScreen> {
  AuditPage? _data;
  int _page = 1;
  bool _loading = false;
  String? _error;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _data = null;
    });
    try {
      final result = await widget.api.fetchAdminAudit(
        widget.token,
        page: _page,
      );
      if (mounted) setState(() => _data = result);
    } on StoreApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _value(Object? value) => value == null
      ? '—'
      : value is String
      ? value
      : jsonEncode(value);

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return Scaffold(
      appBar: AppBar(title: const Text('Harakatlar tarixi')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) ...[
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
            TextButton(
              onPressed: _loading ? null : _load,
              child: const Text('Qayta urinish'),
            ),
          ],
          if (data != null) ...[
            if (data.entries.isEmpty) const Text('Harakatlar tarixi bo‘sh.'),
            ...data.entries.map(
              (entry) => Card(
                margin: const EdgeInsets.only(bottom: 10),
                child: ExpansionTile(
                  title: Text(
                    '${entry.action}: ${entry.object}',
                    style: const TextStyle(color: Color(0xFF3B111A)),
                  ),
                  subtitle: Text(
                    '${entry.actor} · ${entry.createdAt}',
                    style: const TextStyle(color: Color(0xFF786B64)),
                  ),
                  children: entry.changes.entries
                      .map(
                        (change) => ListTile(
                          title: Text(
                            change.key,
                            style: const TextStyle(color: Color(0xFF3B111A)),
                          ),
                          subtitle: Text(
                            '${_value(change.value.oldValue)} → ${_value(change.value.newValue)}',
                            style: const TextStyle(color: Color(0xFF786B64)),
                          ),
                        ),
                      )
                      .toList(),
                ),
              ),
            ),
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

class AdminUsersScreen extends StatefulWidget {
  const AdminUsersScreen({required this.api, required this.token, super.key});
  final StoreApi api;
  final String token;
  @override
  State<AdminUsersScreen> createState() => _AdminUsersScreenState();
}

class _AdminUsersScreenState extends State<AdminUsersScreen> {
  AdminUsersPage? _data;
  int _page = 1;
  bool _loading = false;
  String? _error;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _data = null;
    });
    try {
      final result = await widget.api.fetchAdminUsers(
        widget.token,
        page: _page,
      );
      if (mounted) setState(() => _data = result);
    } on StoreApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _edit(AdminUser user, List<Choice> roles) async {
    String? selected = user.role;
    final role = await showDialog<String>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: Text(user.username),
          content: DropdownButtonFormField<String>(
            initialValue: selected,
            decoration: const InputDecoration(labelText: 'Rol tanlang'),
            items: roles
                .map(
                  (role) => DropdownMenuItem(
                    value: role.value,
                    child: Text(role.label),
                  ),
                )
                .toList(),
            onChanged: (value) => update(() => selected = value),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Bekor qilish'),
            ),
            FilledButton(
              onPressed: selected == null
                  ? null
                  : () => Navigator.pop(context, selected),
              child: const Text('Saqlash'),
            ),
          ],
        ),
      ),
    );
    if (role == null || !mounted) return;
    setState(() => _loading = true);
    try {
      await widget.api.setAdminUserRole(widget.token, user.id, role);
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
      appBar: AppBar(title: const Text('Xodimlar va rollar')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) ...[
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
            TextButton(
              onPressed: _loading ? null : _load,
              child: const Text('Qayta urinish'),
            ),
          ],
          if (data != null) ...[
            if (data.users.isEmpty) const Text('Xodimlar topilmadi.'),
            ...data.users.map((user) {
              final role =
                  data.roles
                      .where((item) => item.value == user.role)
                      .map((item) => item.label)
                      .firstOrNull ??
                  'Rol belgilanmagan';
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  title: Text(
                    user.name.isEmpty
                        ? user.username
                        : '${user.name} (@${user.username})',
                    style: const TextStyle(color: Color(0xFF3B111A)),
                  ),
                  subtitle: Text(
                    '$role · ${user.active ? 'Faol' : 'Faol emas'}',
                    style: const TextStyle(color: Color(0xFF786B64)),
                  ),
                  trailing: user.isSuperuser
                      ? null
                      : const Icon(Icons.edit, color: Color(0xFF3B111A)),
                  onTap: _loading || user.isSuperuser
                      ? null
                      : () => _edit(user, data.roles),
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
