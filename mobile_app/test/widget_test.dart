import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mimoza_mobile/main.dart';
import 'package:mimoza_mobile/services/store_api.dart';
import 'package:mimoza_mobile/services/token_store.dart';

void main() {
  test(
    'iOS requires an API address instead of the Android emulator default',
    () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      var requested = false;
      final api = StoreApi(
        client: MockClient((request) async {
          requested = true;
          return http.Response('{}', 200);
        }),
      );
      addTearDown(api.close);
      await expectLater(
        api.fetchProducts(),
        throwsA(
          isA<StoreApiException>().having(
            (error) => error.message,
            'message',
            contains('API_BASE_URL'),
          ),
        ),
      );
      expect(requested, isFalse);

      final configuredApi = StoreApi(
        baseUrl: Uri.parse('https://example.test'),
        client: MockClient((request) async {
          expect(request.url.host, 'example.test');
          return http.Response(
            jsonEncode({
              'count': 0,
              'page': 1,
              'page_size': 24,
              'categories': [],
              'products': [],
            }),
            200,
          );
        }),
      );
      addTearDown(configuredApi.close);
      await configuredApi.fetchProducts();
    },
  );

  test('Android keeps the emulator API address by default', () async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    Uri? requested;
    final api = StoreApi(
      client: MockClient((request) async {
        requested = request.url;
        return http.Response(
          jsonEncode({
            'count': 0,
            'page': 1,
            'page_size': 24,
            'categories': [],
            'products': [],
          }),
          200,
        );
      }),
    );
    addTearDown(api.close);
    await api.fetchProducts();
    expect(requested?.host, '10.0.2.2');
    expect(requested?.port, 8000);
  });

  testWidgets('catalog loads product data from the Django API', (tester) async {
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/reels/') {
          return http.Response(
            jsonEncode({'products': [], 'has_next': false}),
            200,
          );
        }
        expect(request.url.path, '/api/v1/products/');
        return http.Response(
          jsonEncode({
            'count': 1,
            'page': 1,
            'page_size': 24,
            'categories': [
              {'name': 'Romantika', 'slug': 'romantika'},
            ],
            'products': [
              {
                'id': 1,
                'name': 'Qizil atirgul',
                'slug': 'qizil-atirgul',
                'category': {'name': 'Romantika', 'slug': 'romantika'},
                'description': 'Yangi gullar',
                'price': 250000,
                'old_price': null,
                'stock_quantity': 4,
                'image_url': '',
                'video_url': '',
                'is_featured': true,
              },
            ],
          }),
          200,
          headers: const {'content-type': 'application/json'},
        );
      }),
    );

    await tester.pumpWidget(
      MimozaApp(api: api, tokenStore: _MemoryTokenStore()),
    );
    await tester.pumpAndSettle();

    for (final destination in const [
      'nav-home',
      'nav-catalog',
      'nav-reels',
      'nav-cart',
      'nav-profile',
    ]) {
      expect(find.byKey(ValueKey(destination)), findsOneWidget);
    }

    expect(find.text('Har bir buket — o‘ziga xos bir hikoya.'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('nav-catalog')));
    await tester.pumpAndSettle();
    expect(find.text('MIMOZA FLORAL'), findsOneWidget);
    expect(find.text('Qizil atirgul'), findsOneWidget);
    expect(find.text('250 000 so‘m'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('nav-reels')));
    await tester.pumpAndSettle();
    expect(find.text('Hozircha Reels videolari yo‘q.'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('nav-profile')));
    await tester.pumpAndSettle();
    expect(find.text('Buyurtmalarim'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('nav-cart')));
    await tester.pumpAndSettle();
    expect(find.text('Savatingiz hozircha bo‘sh'), findsOneWidget);
  });

  testWidgets('customer can register and see their order history', (
    tester,
  ) async {
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/auth/register/') {
          expect(request.method, 'POST');
          expect(jsonDecode(request.body)['full_name'], 'Ali Valiyev');
          return http.Response(
            jsonEncode({'access_token': 'secure-token'}),
            201,
            headers: const {'content-type': 'application/json'},
          );
        }
        if (request.url.path == '/api/v1/account/') {
          expect(request.headers['authorization'], 'Bearer secure-token');
          return http.Response(
            jsonEncode({
              'username': 'ali',
              'full_name': 'Ali Valiyev',
              'email': 'ali@example.com',
              'customer': {
                'name': 'Ali Valiyev',
                'phone': '+998901234567',
                'email': 'ali@example.com',
                'cashback': 0,
              },
              'orders': [
                {
                  'id': 12,
                  'order_code': '10006',
                  'created_at': '2026-03-10T12:00:00+05:00',
                  'status': 'Qabul qilindi',
                  'status_code': 'pending',
                  'total': 250000,
                  'items': [
                    {'name': 'Qizil atirgul', 'quantity': 1, 'price': 250000},
                  ],
                },
              ],
            }),
            200,
            headers: const {'content-type': 'application/json'},
          );
        }
        throw StateError('Unexpected request: ${request.url}');
      }),
    );
    final tokenStore = _MemoryTokenStore();

    await tester.pumpWidget(MimozaApp(api: api, tokenStore: tokenStore));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('nav-profile')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Yangi akkaunt yaratish'));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey('profile-field-Ism va familiya')),
      'Ali Valiyev',
    );
    await tester.enterText(
      find.byKey(const ValueKey('profile-field-Telefon raqam')),
      '+998901234567',
    );
    await tester.enterText(
      find.byKey(const ValueKey('profile-field-Email (ixtiyoriy)')),
      'ali@example.com',
    );
    await tester.enterText(
      find.byKey(const ValueKey('profile-field-Foydalanuvchi nomi')),
      'ali',
    );
    await tester.enterText(
      find.byKey(const ValueKey('profile-field-Parol')),
      'Roses-Bloom-4829!',
    );
    await tester.enterText(
      find.byKey(const ValueKey('profile-field-Parolni tasdiqlang')),
      'Roses-Bloom-4829!',
    );
    tester.testTextInput.hide();
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView).last, const Offset(0, -600));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ro‘yxatdan o‘tish'));
    await tester.pumpAndSettle();

    expect(tokenStore.token, 'secure-token');
    expect(find.text('Buyurtma #10006'), findsOneWidget);
    expect(find.text('Qizil atirgul  × 1'), findsOneWidget);
    expect(find.text('250 000 so‘m'), findsOneWidget);
  });

  testWidgets(
    'admin login opens the dashboard and logout returns to storefront',
    (tester) async {
      tester.view.physicalSize = const Size(360, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var dashboardRequests = 0;
      final api = StoreApi(
        baseUrl: Uri.parse('https://api.example.test'),
        client: MockClient((request) async {
          switch (request.url.path) {
            case '/api/v1/products/':
              return http.Response(
                jsonEncode({'count': 0, 'products': [], 'categories': []}),
                200,
              );
            case '/api/v1/auth/login/':
              return http.Response(
                jsonEncode({'access_token': 'admin-token'}),
                200,
              );
            case '/api/v1/auth/logout/':
              return http.Response(jsonEncode({'success': true}), 200);
            case '/api/v1/account/':
              return http.Response(
                jsonEncode({
                  'username': 'admin',
                  'staff_role': 'super_admin',
                  'orders': [],
                }),
                200,
              );
            case '/api/v1/admin/dashboard/':
              expect(request.headers['authorization'], 'Bearer admin-token');
              dashboardRequests++;
              return http.Response(
                jsonEncode({
                  'orders_today': dashboardRequests,
                  'pending_orders': 2,
                  'today_revenue': 500000,
                  'products_count': 6,
                  'recent_orders': [
                    {
                      'order_code': '10006',
                      'customer_name': 'Ali',
                      'status': 'Qabul qilindi',
                      'total': 250000,
                      'created_at': '2026-03-10T12:00:00+05:00',
                    },
                  ],
                  'low_stock': [
                    {'name': 'Atirgul', 'category': 'Gullar', 'quantity': 2},
                  ],
                }),
                200,
              );
          }
          throw StateError('Unexpected URL: ${request.url}');
        }),
      );
      final tokenStore = _MemoryTokenStore();
      await tester.pumpWidget(MimozaApp(api: api, tokenStore: tokenStore));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('nav-profile')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const ValueKey('profile-field-Foydalanuvchi nomi')),
        'admin',
      );
      await tester.enterText(
        find.byKey(const ValueKey('profile-field-Parol')),
        'password',
      );
      tester.testTextInput.hide();
      await tester.tap(find.text('Kirish'));
      await tester.pumpAndSettle();
      expect(find.text('Admin dashboard'), findsOneWidget);
      expect(find.text('Bugungi buyurtmalar'), findsOneWidget);
      await tester.drag(find.byType(ListView), const Offset(0, -350));
      await tester.pumpAndSettle();
      expect(find.text('#10006 · Ali'), findsOneWidget);
      for (final name in [
        'home',
        'catalog',
        'reels',
        'cart',
        'profile',
        'admin',
      ]) {
        expect(find.byKey(ValueKey('nav-$name')), findsOneWidget);
      }
      await tester.tap(find.byTooltip('Yangilash'));
      await tester.pumpAndSettle();
      expect(dashboardRequests, 2);
      await tester.tap(find.byKey(const ValueKey('nav-home')));
      await tester.pumpAndSettle();
      expect(find.text('Admin dashboard'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('nav-catalog')));
      await tester.pumpAndSettle();
      expect(find.text('Admin dashboard'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('nav-admin')));
      await tester.pumpAndSettle();
      expect(find.text('Admin dashboard'), findsOneWidget);
      await tester.tap(find.byTooltip('Akkauntdan chiqish'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('nav-catalog')), findsOneWidget);
      expect(find.byKey(const ValueKey('nav-admin')), findsNothing);
      expect(tokenStore.token, isNull);
    },
  );

  testWidgets('restored admin loses dashboard data when access is revoked', (
    tester,
  ) async {
    var revoked = false;
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        switch (request.url.path) {
          case '/api/v1/products/':
            return http.Response(
              jsonEncode({'count': 0, 'products': [], 'categories': []}),
              200,
            );
          case '/api/v1/account/':
            return http.Response(
              jsonEncode({
                'username': 'admin',
                'staff_role': 'manager',
                'orders': [],
              }),
              200,
            );
          case '/api/v1/admin/dashboard/':
            if (revoked) {
              return http.Response(
                jsonEncode({'error': 'Ruxsat yo‘q'}),
                403,
                headers: const {
                  'content-type': 'application/json; charset=utf-8',
                },
              );
            }
            return http.Response(
              jsonEncode({
                'orders_today': 1,
                'pending_orders': 1,
                'today_revenue': 500000,
                'products_count': 1,
                'recent_orders': [],
                'low_stock': [],
              }),
              200,
            );
        }
        throw StateError('Unexpected URL: ${request.url}');
      }),
    );
    final tokenStore = _MemoryTokenStore()..token = 'saved-token';
    await tester.pumpWidget(MimozaApp(api: api, tokenStore: tokenStore));
    await tester.pumpAndSettle();
    expect(find.text('Admin dashboard'), findsOneWidget);
    expect(find.text('Bugungi tushum'), findsOneWidget);
    revoked = true;
    await tester.tap(find.byTooltip('Yangilash'));
    await tester.pumpAndSettle();
    expect(find.text('Ruxsat yo‘q'), findsOneWidget);
    expect(find.text('Bugungi tushum'), findsNothing);
  });
}

class _MemoryTokenStore implements TokenStore {
  String? token;

  @override
  Future<void> delete() async {
    token = null;
  }

  @override
  Future<String?> read() async => token;

  @override
  Future<void> write(String value) async {
    token = value;
  }
}
