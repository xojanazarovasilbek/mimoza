import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/account.dart';
import '../models/admin_dashboard.dart';
import '../models/admin_management.dart';
import '../models/order_receipt.dart';
import '../models/product.dart';

class StoreApiException implements Exception {
  const StoreApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class StoreApi {
  StoreApi({http.Client? client, Uri? baseUrl})
    : _client = client ?? http.Client(),
      _configuredBaseUrl = baseUrl;

  final http.Client _client;
  final Uri? _configuredBaseUrl;
  static const _apiBaseUrl = String.fromEnvironment('API_BASE_URL');

  Uri get _baseUrl {
    final configured = _configuredBaseUrl;
    if (configured != null) return _withTrailingSlash(configured);
    if (_apiBaseUrl.isNotEmpty) {
      return _withTrailingSlash(Uri.parse(_apiBaseUrl));
    }
    if (defaultTargetPlatform == TargetPlatform.iOS) {
      throw const StoreApiException(
        'iOS uchun API_BASE_URL server manzili sozlanmagan.',
      );
    }
    return Uri.parse('http://10.0.2.2:8000/');
  }

  static Uri _withTrailingSlash(Uri uri) {
    if (uri.path.endsWith('/')) return uri;
    return uri.replace(path: '${uri.path}/');
  }

  Future<ProductCatalog> fetchProducts({
    String query = '',
    String? category,
  }) async {
    final parameters = <String, String>{'page': '1', 'page_size': '24'};
    if (query.trim().isNotEmpty) parameters['q'] = query.trim();
    if (category != null && category.isNotEmpty) {
      parameters['category'] = category;
    }

    final json = await _getJson(
      _baseUrl.resolve('api/v1/products/').replace(queryParameters: parameters),
    );
    return ProductCatalog.fromJson(json);
  }

  Future<Product> fetchProduct(String slug) async {
    final json = await _getJson(_baseUrl.resolve('api/v1/products/$slug/'));
    return Product.fromJson(json);
  }

  Future<ReelsPage> fetchReels({
    int page = 1,
    required int seed,
    String? accessToken,
  }) async {
    final json = await _getJson(
      _baseUrl
          .resolve('api/v1/reels/')
          .replace(queryParameters: {'page': '$page', 'seed': '$seed'}),
      accessToken: accessToken,
    );
    try {
      return ReelsPage.fromJson(json);
    } on FormatException catch (exception) {
      throw StoreApiException(exception.message.toString());
    }
  }

  Future<({bool isLiked, int likesCount})> setProductLike({
    required int productId,
    required bool liked,
    required String accessToken,
  }) async {
    final json = await _postJson(
      _baseUrl.resolve('api/v1/products/$productId/like/'),
      {'liked': liked},
      accessToken: accessToken,
    );
    final isLiked = json['is_liked'];
    final count = json['likes_count'];
    if (isLiked is! bool || count is! int || count < 0) {
      throw const StoreApiException('Serverdan noto‘g‘ri javob keldi.');
    }
    return (isLiked: isLiked, likesCount: count);
  }

  Future<String> login({
    required String username,
    required String password,
  }) async {
    final json = await _postJson(_baseUrl.resolve('api/v1/auth/login/'), {
      'username': username,
      'password': password,
    });
    return _requiredString(json, 'access_token');
  }

  Future<String> register({
    required String fullName,
    required String phone,
    required String email,
    required String username,
    required String password,
    required String passwordConfirmation,
  }) async {
    final json = await _postJson(_baseUrl.resolve('api/v1/auth/register/'), {
      'full_name': fullName,
      'phone': phone,
      'email': email,
      'username': username,
      'password1': password,
      'password2': passwordConfirmation,
    });
    return _requiredString(json, 'access_token');
  }

  Future<CustomerAccount> fetchAccount(String token) async {
    final json = await _getJson(
      _baseUrl.resolve('api/v1/account/'),
      accessToken: token,
    );
    try {
      return CustomerAccount.fromJson(json);
    } on FormatException catch (exception) {
      throw StoreApiException(exception.message.toString());
    }
  }

  Future<AdminDashboard> fetchAdminDashboard(String token) async {
    final json = await _getJson(
      _baseUrl.resolve('api/v1/admin/dashboard/'),
      accessToken: token,
    );
    try {
      return AdminDashboard.fromJson(json);
    } on FormatException catch (exception) {
      throw StoreApiException(exception.message.toString());
    }
  }

  Future<AdminOrdersPage> fetchAdminOrders(
    String token, {
    int page = 1,
    String query = '',
    String status = '',
  }) async {
    final json = await _getJson(
      _baseUrl
          .resolve('api/v1/admin/orders/')
          .replace(
            queryParameters: {'page': '$page', 'q': query, 'status': status},
          ),
      accessToken: token,
    );
    return _parse(json, AdminOrdersPage.fromJson);
  }

  Future<void> updateAdminOrder(
    String token,
    int id, {
    required String status,
    required int? floristId,
    required int? courierId,
  }) async {
    await _postJson(_baseUrl.resolve('api/v1/admin/orders/$id/'), {
      'status': status,
      'florist_id': floristId,
      'courier_id': courierId,
    }, accessToken: token);
  }

  Future<AdminProductsPage> fetchAdminProducts(
    String token, {
    int page = 1,
    String query = '',
  }) async {
    final json = await _getJson(
      _baseUrl
          .resolve('api/v1/admin/products/')
          .replace(queryParameters: {'page': '$page', 'q': query}),
      accessToken: token,
    );
    return _parse(json, AdminProductsPage.fromJson);
  }

  Future<void> saveAdminProduct(
    String token, {
    int? id,
    required Map<String, String> fields,
    String? imagePath,
    String? videoPath,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      _baseUrl.resolve(
        id == null ? 'api/v1/admin/products/' : 'api/v1/admin/products/$id/',
      ),
    );
    request.headers['Authorization'] = 'Bearer $token';
    request.headers['Accept'] = 'application/json';
    request.fields.addAll(fields);
    try {
      if (imagePath != null) {
        request.files.add(
          await http.MultipartFile.fromPath('image', imagePath),
        );
      }
      if (videoPath != null) {
        request.files.add(
          await http.MultipartFile.fromPath('video', videoPath),
        );
      }
    } on FileSystemException {
      throw const StoreApiException('Tanlangan faylni o‘qib bo‘lmadi.');
    }
    await _sendJson(
      () async => http.Response.fromStream(await _client.send(request)),
      timeout: const Duration(minutes: 2),
    );
  }

  Future<AdminUsersPage> fetchAdminUsers(String token, {int page = 1}) async {
    final json = await _getJson(
      _baseUrl
          .resolve('api/v1/admin/users/')
          .replace(queryParameters: {'page': '$page'}),
      accessToken: token,
    );
    return _parse(json, AdminUsersPage.fromJson);
  }

  Future<void> setAdminUserRole(String token, int id, String role) async {
    await _postJson(_baseUrl.resolve('api/v1/admin/users/$id/role/'), {
      'role': role,
    }, accessToken: token);
  }

  Future<AdminAnalytics> fetchAdminAnalytics(String token, int days) async {
    final json = await _getJson(
      _baseUrl
          .resolve('api/v1/admin/analytics/')
          .replace(queryParameters: {'days': '$days'}),
      accessToken: token,
    );
    return _parse(json, AdminAnalytics.fromJson);
  }

  Future<AuditPage> fetchAdminAudit(String token, {int page = 1}) async {
    final json = await _getJson(
      _baseUrl
          .resolve('api/v1/admin/audit/')
          .replace(queryParameters: {'page': '$page'}),
      accessToken: token,
    );
    return _parse(json, AuditPage.fromJson);
  }

  T _parse<T>(
    Map<String, dynamic> json,
    T Function(Map<String, dynamic>) parse,
  ) {
    try {
      return parse(json);
    } on FormatException catch (exception) {
      throw StoreApiException(exception.message.toString());
    }
  }

  Future<void> logout(String token) async {
    await _postJson(
      _baseUrl.resolve('api/v1/auth/logout/'),
      const {},
      accessToken: token,
    );
  }

  Future<OrderReceipt> createOrder({
    required String accessToken,
    required Map<String, dynamic> body,
  }) async {
    final json = await _postJson(
      _baseUrl.resolve('api/v1/orders/'),
      body,
      accessToken: accessToken,
    );
    return _parseReceipt(json);
  }

  Future<List<String>> fetchPaymentMethods() async {
    final json = await _getJson(_baseUrl.resolve('api/v1/payment-methods/'));
    final methods = json['payment_methods'];
    if (methods is! List) {
      throw const StoreApiException('To‘lov usullari ro‘yxati noto‘g‘ri.');
    }
    return methods
        .map((item) {
          if (item is! Map<String, dynamic> || item['value'] is! String) {
            throw const StoreApiException('To‘lov usuli noto‘g‘ri.');
          }
          return item['value'] as String;
        })
        .where((method) => method == 'click' || method == 'payme')
        .toList(growable: false);
  }

  Future<OrderReceipt> fetchOrder(int id, String accessToken) async {
    final json = await _getJson(
      _baseUrl.resolve('api/v1/orders/$id/'),
      accessToken: accessToken,
    );
    return _parseReceipt(json);
  }

  Future<OrderReceipt> retryOrderPayment(int id, String accessToken) async {
    final json = await _postJson(
      _baseUrl.resolve('api/v1/orders/$id/payments/retry/'),
      const {},
      accessToken: accessToken,
    );
    return _parseReceipt(json);
  }

  Future<OrderReceipt> setOrderDelivery(
    int id,
    bool delivery,
    String accessToken,
  ) async {
    final json = await _postJson(
      _baseUrl.resolve('api/v1/orders/$id/delivery/'),
      {'delivery_required': delivery},
      accessToken: accessToken,
    );
    return _parseReceipt(json);
  }

  OrderReceipt _parseReceipt(Map<String, dynamic> json) {
    try {
      return OrderReceipt.fromJson(json);
    } on FormatException catch (exception) {
      throw StoreApiException(exception.message.toString());
    }
  }

  Future<Map<String, dynamic>> _getJson(Uri uri, {String? accessToken}) {
    return _sendJson(() => _client.get(uri, headers: _headers(accessToken)));
  }

  Future<Map<String, dynamic>> _postJson(
    Uri uri,
    Map<String, dynamic> body, {
    String? accessToken,
  }) {
    return _sendJson(
      () => _client.post(
        uri,
        headers: _headers(accessToken),
        body: jsonEncode(body),
      ),
    );
  }

  Map<String, String> _headers(String? accessToken) => {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    if (accessToken != null) 'Authorization': 'Bearer $accessToken',
  };

  Future<Map<String, dynamic>> _sendJson(
    Future<http.Response> Function() send, {
    Duration timeout = const Duration(seconds: 15),
  }) async {
    late final http.Response response;
    try {
      response = await send().timeout(timeout);
    } on TimeoutException {
      throw const StoreApiException(
        'Server javobi kechikdi. Qayta urinib ko‘ring.',
      );
    } on http.ClientException {
      throw const StoreApiException(
        'Serverga ulanib bo‘lmadi. Internetni tekshiring.',
      );
    }

    final dynamic decoded;
    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw const StoreApiException('Serverdan noto‘g‘ri javob keldi.');
    }
    if (decoded is! Map<String, dynamic>) {
      throw const StoreApiException('Serverdan noto‘g‘ri javob keldi.');
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final error = decoded['error'];
      throw StoreApiException(
        error is String
            ? error
            : 'So‘rov bajarilmadi (${response.statusCode}).',
        statusCode: response.statusCode,
      );
    }
    return decoded;
  }

  String _requiredString(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value is! String || value.isEmpty) {
      throw const StoreApiException('Serverdan noto‘g‘ri javob keldi.');
    }
    return value;
  }

  void close() => _client.close();
}
