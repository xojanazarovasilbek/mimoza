import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mimoza_mobile/screens/admin_orders_screen.dart';
import 'package:mimoza_mobile/screens/admin_products_screen.dart';
import 'package:mimoza_mobile/screens/admin_reports_screen.dart';
import 'package:mimoza_mobile/services/store_api.dart';

http.Response jsonResponse(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

StoreApi apiFor(Future<http.Response> Function(http.Request) handler) =>
    StoreApi(
      baseUrl: Uri.parse('https://example.test'),
      client: MockClient(handler),
    );

void main() {
  testWidgets('updates order status and assigns a florist', (tester) async {
    Map<String, dynamic>? submitted;
    final api = apiFor((request) async {
      if (request.method == 'POST') {
        submitted = jsonDecode(request.body) as Map<String, dynamic>;
        return jsonResponse({'ok': true});
      }
      return jsonResponse({
        'orders': [
          {
            'id': 1,
            'code': '12345',
            'customer_name': 'Ali',
            'phone': '123',
            'status': 'pending',
            'total': 100,
            'delivery_required': null,
            'payment': 'Naqd',
            'payment_status': 'Kutilmoqda',
            'florist_id': null,
            'courier_id': null,
            'items': [],
          },
        ],
        'workers': [
          {'id': 3, 'name': 'Florist', 'role': 'florist'},
        ],
        'statuses': [
          {'value': 'pending', 'label': 'Kutilmoqda'},
          {'value': 'processing', 'label': 'Tayyorlanmoqda'},
        ],
        'has_next': false,
      });
    });
    await tester.pumpWidget(
      MaterialApp(
        home: AdminOrdersScreen(api: api, token: 'token'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Boshqarish'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Kutilmoqda').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tayyorlanmoqda').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tanlanmagan').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Florist').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Saqlash'));
    await tester.pumpAndSettle();
    expect(submitted, {
      'status': 'processing',
      'florist_id': 3,
      'courier_id': null,
    });
  });

  testWidgets('stale product edit shows error and refreshes on return', (
    tester,
  ) async {
    var loads = 0;
    var sentVersion = false;
    final api = apiFor((request) async {
      if (request.method == 'POST') {
        sentVersion =
            request.body.contains('version') &&
            request.body.contains('version-1');
        return jsonResponse({'error': 'Mahsulot o‘zgargan.'}, 409);
      }
      loads++;
      return jsonResponse({
        'products': [
          {
            'id': 1,
            'name': 'Gul',
            'slug': 'gul',
            'category_id': 1,
            'category': 'Gullar',
            'description': '',
            'price': 100,
            'old_price': null,
            'image_url': '',
            'video_url': '',
            'has_image': false,
            'has_video': false,
            'stock_quantity': 3,
            'in_stock': true,
            'is_featured': false,
            'version': 'version-1',
          },
        ],
        'categories': [
          {'id': 1, 'name': 'Gullar'},
        ],
        'has_next': false,
      });
    });
    await tester.pumpWidget(
      MaterialApp(
        home: AdminProductsScreen(api: api, token: 'token'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Gul'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Saqlash'),
      400,
      scrollable: find
          .descendant(
            of: find.byType(ListView).last,
            matching: find.byType(Scrollable),
          )
          .first,
    );
    await tester.drag(find.byType(ListView).last, const Offset(0, -150));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Saqlash'));
    await tester.pumpAndSettle();
    expect(sentVersion, isTrue);
    expect(find.text('Mahsulot o‘zgargan.'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(loads, 2);
  });

  testWidgets('renders analytics and audit changes', (tester) async {
    final api = apiFor((request) async {
      if (request.url.path.contains('analytics')) {
        return jsonResponse({
          'sales_total': 100,
          'orders_count': 1,
          'average_order': 100,
          'cancelled_count': 0,
          'daily_sales': [
            {
              'created_at__date': '2026-03-10',
              'revenue': 100,
              'orders_count': 1,
            },
          ],
          'top_products': [
            {'product__name': 'Gul', 'quantity': 1, 'revenue': 100},
          ],
        });
      }
      return jsonResponse({
        'entries': [
          {
            'actor': 'admin',
            'action': 'Yangilandi',
            'object': 'Gul',
            'created_at': '2026-03-10',
            'changes': {
              'Narx': {'old': 50, 'new': 100},
            },
          },
        ],
        'has_next': false,
      });
    });
    await tester.pumpWidget(
      MaterialApp(
        home: AdminAnalyticsScreen(api: api, token: 'token'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Buyurtmalar: 1'), findsOneWidget);
    expect(find.text('2026-03-10'), findsOneWidget);
    await tester.pumpWidget(
      MaterialApp(
        home: AdminAuditScreen(api: api, token: 'token'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Yangilandi: Gul'));
    await tester.pumpAndSettle();
    expect(find.text('50 → 100'), findsOneWidget);
  });

  testWidgets('changes staff role but does not edit a superuser', (
    tester,
  ) async {
    Map<String, dynamic>? submitted;
    final api = apiFor((request) async {
      if (request.method == 'POST') {
        submitted = jsonDecode(request.body) as Map<String, dynamic>;
        return jsonResponse({'success': true});
      }
      return jsonResponse({
        'users': [
          {
            'id': 1,
            'username': 'root',
            'name': '',
            'role': 'super_admin',
            'active': true,
            'is_superuser': true,
          },
          {
            'id': 2,
            'username': 'worker',
            'name': '',
            'role': 'florist',
            'active': true,
            'is_superuser': false,
          },
        ],
        'roles': [
          {'value': 'super_admin', 'label': 'Admin'},
          {'value': 'florist', 'label': 'Florist'},
          {'value': 'courier', 'label': 'Kuryer'},
        ],
        'has_next': false,
      });
    });
    await tester.pumpWidget(
      MaterialApp(
        home: AdminUsersScreen(api: api, token: 'token'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('root'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    await tester.tap(find.text('worker'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Florist').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Kuryer').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Saqlash'));
    await tester.pumpAndSettle();
    expect(submitted, {'role': 'courier'});
  });
}
