import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mimoza_mobile/services/store_api.dart';
import 'package:mimoza_mobile/services/token_store.dart';
import 'package:mimoza_mobile/state/account_controller.dart';

class _TokenStore implements TokenStore {
  String? token = 'access-token';
  @override
  Future<String?> read() async => token;
  @override
  Future<void> write(String value) async => token = value;
  @override
  Future<void> delete() async => token = null;
}

void main() {
  test('registers a push token with the authenticated account', () async {
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/push/device/');
        expect(request.headers['authorization'], 'Bearer access-token');
        expect(jsonDecode(request.body), {'token': 'device-token'});
        return http.Response('{"success":true}', 200);
      }),
    );
    addTearDown(api.close);
    await api.registerPushDevice('access-token', 'device-token');
  });

  test(
    'failed logout keeps the session so its push device can be removed',
    () async {
      final store = _TokenStore();
      final api = StoreApi(
        baseUrl: Uri.parse('https://api.example.test'),
        client: MockClient((request) async {
          if (request.url.path == '/api/v1/account/') {
            return http.Response('{"username":"customer","orders":[]}', 200);
          }
          return http.Response('{"error":"Server unavailable"}', 503);
        }),
      );
      final account = AccountController(api, store);
      addTearDown(api.close);
      addTearDown(account.dispose);
      await account.restore();
      await account.signOut();
      expect(store.token, 'access-token');
      expect(account.accessToken, 'access-token');
      expect(account.error, isNotNull);
    },
  );
}
