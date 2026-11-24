import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mimoza_mobile/models/product.dart';
import 'package:mimoza_mobile/screens/cart_screen.dart';
import 'package:mimoza_mobile/screens/checkout_screen.dart';
import 'package:mimoza_mobile/services/store_api.dart';
import 'package:mimoza_mobile/services/token_store.dart';
import 'package:mimoza_mobile/state/account_controller.dart';
import 'package:mimoza_mobile/state/cart_model.dart';

const _product = Product(
  id: 1,
  name: 'Qizil gul',
  slug: 'qizil-gul',
  category: ProductCategory(name: 'Gullar', slug: 'gullar'),
  description: '',
  price: 250000,
  stockQuantity: 4,
  imageUrl: '',
);

class _TokenStore implements TokenStore {
  _TokenStore(this.token);
  String? token;
  @override
  Future<String?> read() async => token;
  @override
  Future<void> write(String value) async => token = value;
  @override
  Future<void> delete() async => token = null;
}

void main() {
  testWidgets(
    'checkout shows the advance and lets the customer select a provider',
    (tester) async {
      var requests = 0;
      final api = StoreApi(
        baseUrl: Uri.parse('https://api.example.test'),
        client: MockClient((request) async {
          requests++;
          return http.Response(
            '{"payment_methods":[{"value":"click","label":"Click"}]}',
            200,
          );
        }),
      );
      final cart = CartModel()..add(_product);
      final account = AccountController(api, _TokenStore(null));
      await account.restore();
      addTearDown(api.close);
      addTearDown(cart.dispose);
      addTearDown(account.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: CheckoutScreen(api: api, account: account, cart: cart),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Oldindan 30%: 75 000 so‘m'), findsOneWidget);
      expect(find.text('Topshirishda 70%: 175 000 so‘m'), findsOneWidget);
      expect(
        tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
        isNotNull,
      );
      expect(cart.itemCount, 1);
      expect(requests, 1);
    },
  );

  testWidgets('advance and remainder retain fractional som', (tester) async {
    const product = Product(
      id: 2,
      name: 'Gul',
      slug: 'gul',
      category: ProductCategory(name: 'Gullar', slug: 'gullar'),
      description: '',
      price: 1,
      stockQuantity: 1,
      imageUrl: '',
    );
    final api = StoreApi(
      client: MockClient((_) async => http.Response('{}', 200)),
    );
    final account = AccountController(api, _TokenStore(null));
    final cart = CartModel()..add(product);
    addTearDown(api.close);
    addTearDown(account.dispose);
    addTearDown(cart.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: CheckoutScreen(api: api, account: account, cart: cart),
      ),
    );
    expect(find.text('Oldindan 30%: 0,30 so‘m'), findsOneWidget);
    expect(find.text('Topshirishda 70%: 0,70 so‘m'), findsOneWidget);
  });

  testWidgets('guest must sign in before checkout', (tester) async {
    var openedProfile = false;
    final api = StoreApi(
      client: MockClient((_) async => http.Response('{}', 200)),
    );
    final cart = CartModel()..add(_product);
    final account = AccountController(api, _TokenStore(null));
    await account.restore();
    addTearDown(api.close);
    addTearDown(cart.dispose);
    addTearDown(account.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CartScreen(
            api: api,
            cart: cart,
            account: account,
            onOpenProfile: () => openedProfile = true,
          ),
        ),
      ),
    );
    await tester.tap(find.text('Buyurtma berish'));
    await tester.pump();
    expect(openedProfile, isTrue);
    expect(
      find.text('Buyurtma berish uchun akkauntga kiring.'),
      findsOneWidget,
    );
  });
}
