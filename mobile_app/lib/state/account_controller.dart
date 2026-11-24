import 'package:flutter/foundation.dart';

import '../models/account.dart';
import '../services/store_api.dart';
import '../services/token_store.dart';

class AccountController extends ChangeNotifier {
  AccountController(this._api, this._tokenStore);

  final StoreApi _api;
  final TokenStore _tokenStore;

  CustomerAccount? account;
  String? error;
  bool isLoading = false;
  bool isRestoring = true;
  bool _restored = false;
  String? _accessToken;
  String? get accessToken => account == null ? null : _accessToken;

  Future<void> restore({bool force = false}) async {
    if (_restored && !force) return;
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      _accessToken = await _tokenStore.read();
      if (_accessToken != null) {
        account = await _api.fetchAccount(_accessToken!);
      }
    } on StoreApiException catch (exception) {
      if (exception.statusCode == 401) {
        await _tokenStore.delete();
        _accessToken = null;
        account = null;
      } else {
        error = exception.message;
      }
    } finally {
      _restored = true;
      isRestoring = false;
      isLoading = false;
      notifyListeners();
    }
  }

  Future<void> signIn({
    required String username,
    required String password,
  }) async {
    await _authenticate(
      () => _api.login(username: username, password: password),
    );
  }

  Future<void> register({
    required String fullName,
    required String phone,
    required String email,
    required String username,
    required String password,
    required String passwordConfirmation,
  }) async {
    await _authenticate(
      () => _api.register(
        fullName: fullName,
        phone: phone,
        email: email,
        username: username,
        password: password,
        passwordConfirmation: passwordConfirmation,
      ),
    );
  }

  Future<void> _authenticate(Future<String> Function() requestToken) async {
    error = null;
    isLoading = true;
    notifyListeners();
    String? newToken;
    try {
      newToken = await requestToken();
      await _tokenStore.write(newToken);
      _accessToken = newToken;
      account = await _api.fetchAccount(newToken);
    } on StoreApiException catch (exception) {
      error = exception.message;
      if (newToken != null) {
        await _tokenStore.delete();
        _accessToken = null;
        account = null;
      }
    } finally {
      isRestoring = false;
      isLoading = false;
      _restored = true;
      notifyListeners();
    }
  }

  Future<void> signOut() async {
    final token = _accessToken;
    error = null;
    isLoading = true;
    notifyListeners();
    try {
      if (token != null) await _api.logout(token);
    } on StoreApiException catch (exception) {
      error = exception.message;
    } finally {
      await _tokenStore.delete();
      _accessToken = null;
      account = null;
      isLoading = false;
      notifyListeners();
    }
  }
}
