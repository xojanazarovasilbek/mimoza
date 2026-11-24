import 'dart:async';
import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/services.dart';

import '../state/account_controller.dart';
import 'store_api.dart';

class MobilePush {
  MobilePush(this.api, this.account, this.onMessage);

  final StoreApi api;
  final AccountController account;
  final void Function(String message) onMessage;
  static const enabled = bool.fromEnvironment('FIREBASE_ENABLED');
  static const _apiKey = String.fromEnvironment('FIREBASE_API_KEY');
  static const _appId = String.fromEnvironment('FIREBASE_APP_ID');
  static const _senderId = String.fromEnvironment('FIREBASE_SENDER_ID');
  static const _projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
  static const _iosBundleId = String.fromEnvironment('FIREBASE_IOS_BUNDLE_ID');

  FirebaseMessaging? _messaging;
  StreamSubscription<String>? _tokenSubscription;
  StreamSubscription<RemoteMessage>? _messageSubscription;
  bool _syncing = false;
  bool _syncAgain = false;
  bool _disposed = false;
  String? _registeredAccessToken;
  String? _registeredDeviceToken;

  Future<void> start() async {
    if (!enabled || !(Platform.isAndroid || Platform.isIOS)) return;
    if ([
          _apiKey,
          _appId,
          _senderId,
          _projectId,
        ].any((value) => value.isEmpty) ||
        (Platform.isIOS && _iosBundleId.isEmpty)) {
      onMessage('Firebase bildirishnoma sozlamalari to‘liq emas.');
      return;
    }
    try {
      await Firebase.initializeApp(
        options: FirebaseOptions(
          apiKey: _apiKey,
          appId: _appId,
          messagingSenderId: _senderId,
          projectId: _projectId,
          iosBundleId: Platform.isIOS ? _iosBundleId : null,
        ),
      );
      if (_disposed) return;
      _messaging = FirebaseMessaging.instance;
      await _messaging!.setForegroundNotificationPresentationOptions(
        alert: true,
        badge: true,
        sound: true,
      );
      _tokenSubscription = _messaging!.onTokenRefresh.listen((_) {
        _registeredDeviceToken = null;
        unawaited(sync());
      });
      _messageSubscription = FirebaseMessaging.onMessage.listen((message) {
        if (Platform.isAndroid && message.notification != null) {
          onMessage(
            message.notification!.body ?? message.notification!.title ?? '',
          );
        }
      });
      account.addListener(_accountChanged);
      await sync();
    } on FirebaseException catch (error) {
      onMessage('Bildirishnomani ishga tushirib bo‘lmadi: ${error.code}');
    } on PlatformException catch (error) {
      onMessage('Bildirishnomani ishga tushirib bo‘lmadi: ${error.code}');
    }
  }

  void _accountChanged() {
    if (account.accessToken != _registeredAccessToken) {
      unawaited(sync());
    }
  }

  Future<void> sync() async {
    if (_disposed || _messaging == null) return;
    if (_syncing) {
      _syncAgain = true;
      return;
    }
    _syncing = true;
    try {
      do {
        _syncAgain = false;
        final accessToken = account.accessToken;
        if (accessToken == null) {
          _registeredAccessToken = null;
          _registeredDeviceToken = null;
          continue;
        }
        final permission = await _messaging!.requestPermission();
        if (permission.authorizationStatus == AuthorizationStatus.denied) {
          onMessage(
            'Bildirishnomalar uchun telefon sozlamalarida ruxsat bering.',
          );
          continue;
        }
        if (Platform.isIOS && await _messaging!.getAPNSToken() == null) {
          onMessage(
            'Apple bildirishnoma tokeni hali tayyor emas. Ilovani qayta oching.',
          );
          continue;
        }
        final deviceToken = await _messaging!.getToken();
        if (deviceToken == null) {
          onMessage('Bildirishnoma qurilmasini ro‘yxatdan o‘tkazib bo‘lmadi.');
          continue;
        }
        if (accessToken != account.accessToken) {
          _syncAgain = true;
          continue;
        }
        if (_registeredAccessToken != accessToken ||
            _registeredDeviceToken != deviceToken) {
          await api.registerPushDevice(accessToken, deviceToken);
          _registeredAccessToken = accessToken;
          _registeredDeviceToken = deviceToken;
        }
      } while (_syncAgain && !_disposed);
    } on FirebaseException catch (error) {
      onMessage('Bildirishnomani sozlab bo‘lmadi: ${error.code}');
    } on PlatformException catch (error) {
      onMessage('Bildirishnomani sozlab bo‘lmadi: ${error.code}');
    } on StoreApiException catch (error) {
      onMessage('Bildirishnomani sozlab bo‘lmadi: ${error.message}');
    } finally {
      _syncing = false;
    }
  }

  void dispose() {
    _disposed = true;
    account.removeListener(_accountChanged);
    unawaited(_tokenSubscription?.cancel());
    unawaited(_messageSubscription?.cancel());
  }
}
