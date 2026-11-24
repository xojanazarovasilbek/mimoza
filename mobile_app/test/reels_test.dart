import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mimoza_mobile/screens/reels_screen.dart';
import 'package:mimoza_mobile/services/store_api.dart';
import 'package:mimoza_mobile/services/token_store.dart';
import 'package:mimoza_mobile/state/account_controller.dart';
import 'package:mimoza_mobile/state/cart_model.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

Map<String, dynamic> _product(int id, {bool embed = false}) => {
  'id': id,
  'name': 'Video gul $id',
  'slug': 'video-gul-$id',
  'category': {'name': 'Romantika', 'slug': 'romantika'},
  'description': '',
  'price': 250000,
  'stock_quantity': 1,
  'image_url': '',
  'video_url': embed
      ? 'https://example.test/embed/$id'
      : 'https://example.test/video$id.mp4',
  'video_is_embed': embed,
};

void main() {
  testWidgets('loads a reel, plays only while visible, and swipes to next', (
    tester,
  ) async {
    final previousPlatform = VideoPlayerPlatform.instance;
    final player = _FakeVideoPlayer();
    VideoPlayerPlatform.instance = player;
    addTearDown(() => VideoPlayerPlatform.instance = previousPlatform);
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/reels/');
        return http.Response(
          jsonEncode({
            'products': [_product(1), _product(2, embed: true)],
            'has_next': false,
          }),
          200,
        );
      }),
    );
    final cart = CartModel();
    final account = AccountController(api, _MemoryTokenStore());
    addTearDown(api.close);
    addTearDown(cart.dispose);
    addTearDown(account.dispose);

    Widget screen(bool active) => MaterialApp(
      home: Scaffold(
        body: ReelsScreen(
          api: api,
          cart: cart,
          account: account,
          onOpenProfile: () {},
          active: active,
        ),
      ),
    );
    await tester.pumpWidget(screen(true));
    await tester.pumpAndSettle();
    expect(find.text('Video gul 1'), findsOneWidget);
    expect(player.played, 1);
    expect(find.byTooltip('To‘xtatish'), findsOneWidget);

    final pausesBeforeLeaving = player.paused;
    await tester.pumpWidget(screen(false));
    await tester.pumpAndSettle();
    expect(find.byTooltip('To‘xtatish'), findsNothing);
    expect(player.paused, greaterThan(pausesBeforeLeaving));
    await tester.pumpWidget(screen(true));
    await tester.pumpAndSettle();
    expect(player.played, 2);

    final pausesBeforeSwipe = player.paused;
    await tester.drag(find.byType(PageView), const Offset(0, -600));
    await tester.pumpAndSettle();
    expect(find.text('Video gul 2'), findsOneWidget);
    expect(find.text('Videoni ochish'), findsOneWidget);
    expect(player.paused, greaterThan(pausesBeforeSwipe));
  });

  testWidgets('retries a failed reels request', (tester) async {
    var requests = 0;
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        requests++;
        if (requests == 1) {
          return http.Response(jsonEncode({'error': 'Server xatosi'}), 500);
        }
        return http.Response(
          jsonEncode({
            'products': [_product(2, embed: true)],
            'has_next': false,
          }),
          200,
        );
      }),
    );
    final cart = CartModel();
    final account = AccountController(api, _MemoryTokenStore());
    addTearDown(api.close);
    addTearDown(cart.dispose);
    addTearDown(account.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReelsScreen(
            api: api,
            cart: cart,
            account: account,
            onOpenProfile: () {},
            active: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Server xatosi'), findsOneWidget);
    await tester.tap(find.text('Qayta urinish'));
    await tester.pumpAndSettle();
    expect(find.text('Video gul 2'), findsOneWidget);
    expect(requests, 2);
  });

  testWidgets('loads the next reels page on swipe', (tester) async {
    final pages = <String?>[];
    final seeds = <String?>[];
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        final page = request.url.queryParameters['page'];
        pages.add(page);
        seeds.add(request.url.queryParameters['seed']);
        return http.Response(
          jsonEncode({
            'products': [_product(page == '1' ? 1 : 2, embed: true)],
            'has_next': page == '1',
          }),
          200,
        );
      }),
    );
    final cart = CartModel();
    final account = AccountController(api, _MemoryTokenStore());
    addTearDown(api.close);
    addTearDown(cart.dispose);
    addTearDown(account.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReelsScreen(
            api: api,
            cart: cart,
            account: account,
            onOpenProfile: () {},
            active: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.drag(find.byType(PageView), const Offset(0, -600));
    await tester.pumpAndSettle();
    expect(pages, ['1', '2']);
    expect(seeds[0], seeds[1]);
    expect(find.text('Video gul 2'), findsOneWidget);
  });

  testWidgets('continues past a page of duplicates', (tester) async {
    final pages = <String?>[];
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        final page = request.url.queryParameters['page'];
        pages.add(page);
        return http.Response(
          jsonEncode({
            'products': [_product(page == '3' ? 2 : 1, embed: true)],
            'has_next': page != '3',
          }),
          200,
        );
      }),
    );
    final cart = CartModel();
    final account = AccountController(api, _MemoryTokenStore());
    addTearDown(api.close);
    addTearDown(cart.dispose);
    addTearDown(account.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReelsScreen(
            api: api,
            cart: cart,
            account: account,
            onOpenProfile: () {},
            active: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.drag(find.byType(PageView), const Offset(0, -600));
    await tester.pumpAndSettle();
    expect(pages, ['1', '2', '3']);
    expect(find.text('Video gul 2'), findsOneWidget);
  });

  testWidgets('refreshes an empty feed when reopened', (tester) async {
    var requests = 0;
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        requests++;
        expect(request.url.queryParameters['page'], '1');
        return http.Response(
          jsonEncode({
            'products': requests == 1 ? [] : [_product(1, embed: true)],
            'has_next': false,
          }),
          200,
        );
      }),
    );
    final cart = CartModel();
    final account = AccountController(api, _MemoryTokenStore());
    addTearDown(api.close);
    addTearDown(cart.dispose);
    addTearDown(account.dispose);
    Widget screen(bool active) => MaterialApp(
      home: Scaffold(
        body: ReelsScreen(
          api: api,
          cart: cart,
          account: account,
          onOpenProfile: () {},
          active: active,
        ),
      ),
    );

    await tester.pumpWidget(screen(true));
    await tester.pumpAndSettle();
    expect(find.text('Hozircha Reels videolari yo‘q.'), findsOneWidget);
    await tester.pumpWidget(screen(false));
    await tester.pumpWidget(screen(true));
    await tester.pumpAndSettle();
    expect(find.text('Video gul 1'), findsOneWidget);
    expect(requests, 2);
  });

  testWidgets('refreshes an existing feed from the first page', (tester) async {
    var requests = 0;
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        requests++;
        expect(request.url.queryParameters['page'], '1');
        return http.Response(
          jsonEncode({
            'products': [_product(requests, embed: true)],
            'has_next': false,
          }),
          200,
        );
      }),
    );
    final cart = CartModel();
    final account = AccountController(api, _MemoryTokenStore());
    addTearDown(api.close);
    addTearDown(cart.dispose);
    addTearDown(account.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReelsScreen(
            api: api,
            cart: cart,
            account: account,
            onOpenProfile: () {},
            active: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Video gul 1'), findsOneWidget);
    await tester.tap(find.byTooltip('Yangilash'));
    await tester.pumpAndSettle();
    expect(find.text('Video gul 2'), findsOneWidget);
    expect(find.text('Video gul 1'), findsNothing);
  });

  testWidgets('likes and unlikes a reel with the signed-in account', (
    tester,
  ) async {
    var liked = false;
    var fail = false;
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/account/') {
          return http.Response(
            jsonEncode({'username': 'ali', 'orders': []}),
            200,
          );
        }
        expect(request.headers['authorization'], 'Bearer token');
        if (request.url.path == '/api/v1/reels/') {
          return http.Response(
            jsonEncode({
              'products': [
                {
                  ..._product(1, embed: true),
                  'is_liked': liked,
                  'likes_count': liked ? 1 : 0,
                },
              ],
              'has_next': false,
            }),
            200,
          );
        }
        expect(request.url.path, '/api/v1/products/1/like/');
        if (fail) {
          return http.Response(jsonEncode({'error': 'Like saqlanmadi'}), 500);
        }
        liked = jsonDecode(request.body)['liked'] as bool;
        return http.Response(
          jsonEncode({'is_liked': liked, 'likes_count': liked ? 1 : 0}),
          200,
        );
      }),
    );
    final cart = CartModel();
    final account = AccountController(api, _MemoryTokenStore('token'));
    await account.restore();
    addTearDown(api.close);
    addTearDown(cart.dispose);
    addTearDown(account.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReelsScreen(
            api: api,
            cart: cart,
            account: account,
            onOpenProfile: () {},
            active: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Like bosish'));
    await tester.pumpAndSettle();
    expect(find.byTooltip('Like olib tashlash'), findsOneWidget);
    expect(find.text('1'), findsOneWidget);
    fail = true;
    await tester.tap(find.byTooltip('Like olib tashlash'));
    await tester.pumpAndSettle();
    expect(find.text('Like saqlanmadi'), findsOneWidget);
    expect(find.byTooltip('Like olib tashlash'), findsOneWidget);
    fail = false;
    await tester.tap(find.byTooltip('Like olib tashlash'));
    await tester.pumpAndSettle();
    expect(find.byTooltip('Like bosish'), findsOneWidget);
    expect(liked, isFalse);
  });

  testWidgets('guest is prompted to sign in before liking', (tester) async {
    var openedProfile = false;
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/reels/');
        return http.Response(
          jsonEncode({
            'products': [_product(1, embed: true)],
            'has_next': false,
          }),
          200,
        );
      }),
    );
    final cart = CartModel();
    final account = AccountController(api, _MemoryTokenStore());
    await account.restore();
    addTearDown(api.close);
    addTearDown(cart.dispose);
    addTearDown(account.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReelsScreen(
            api: api,
            cart: cart,
            account: account,
            onOpenProfile: () => openedProfile = true,
            active: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Like bosish'));
    await tester.pump();
    expect(openedProfile, isTrue);
    expect(find.text('Like bosish uchun akkauntga kiring.'), findsOneWidget);
  });

  testWidgets('updates like state after signing in and out', (tester) async {
    final api = StoreApi(
      baseUrl: Uri.parse('https://api.example.test'),
      client: MockClient((request) async {
        switch (request.url.path) {
          case '/api/v1/auth/login/':
            return http.Response(jsonEncode({'access_token': 'token'}), 200);
          case '/api/v1/auth/logout/':
            return http.Response(jsonEncode({'success': true}), 200);
          case '/api/v1/account/':
            return http.Response(
              jsonEncode({'username': 'ali', 'orders': []}),
              200,
            );
          case '/api/v1/reels/':
            return http.Response(
              jsonEncode({
                'products': [
                  {
                    ..._product(1, embed: true),
                    'is_liked': request.headers.containsKey('authorization'),
                    'likes_count': 1,
                  },
                ],
                'has_next': false,
              }),
              200,
            );
        }
        throw StateError('Unexpected URL: ${request.url}');
      }),
    );
    final cart = CartModel();
    final account = AccountController(api, _MemoryTokenStore());
    await account.restore();
    addTearDown(api.close);
    addTearDown(cart.dispose);
    addTearDown(account.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReelsScreen(
            api: api,
            cart: cart,
            account: account,
            onOpenProfile: () {},
            active: true,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byTooltip('Like bosish'), findsOneWidget);
    await account.signIn(username: 'ali', password: 'password');
    await tester.pumpAndSettle();
    expect(find.byTooltip('Like olib tashlash'), findsOneWidget);
    await account.signOut();
    await tester.pumpAndSettle();
    expect(find.byTooltip('Like bosish'), findsOneWidget);
  });
}

class _MemoryTokenStore implements TokenStore {
  _MemoryTokenStore([this.token]);

  String? token;
  @override
  Future<String?> read() async => token;
  @override
  Future<void> write(String token) async => this.token = token;
  @override
  Future<void> delete() async => token = null;
}

class _FakeVideoPlayer extends VideoPlayerPlatform {
  int played = 0;
  int paused = 0;
  int disposed = 0;
  int _nextId = 0;
  final Map<int, StreamController<VideoEvent>> _events = {};

  @override
  Future<void> init() async {}

  @override
  Future<int?> createWithOptions(VideoCreationOptions options) async =>
      ++_nextId;

  @override
  Stream<VideoEvent> videoEventsFor(int playerId) {
    final events = StreamController<VideoEvent>();
    _events[playerId] = events;
    scheduleMicrotask(() {
      events.add(
        VideoEvent(
          eventType: VideoEventType.initialized,
          duration: const Duration(seconds: 30),
          size: const Size(720, 1280),
        ),
      );
    });
    return events.stream;
  }

  @override
  Future<void> dispose(int playerId) async {
    disposed++;
    await _events.remove(playerId)?.close();
  }

  @override
  Future<void> play(int playerId) async => played++;

  @override
  Future<void> pause(int playerId) async => paused++;

  @override
  Future<void> setLooping(int playerId, bool looping) async {}

  @override
  Future<void> setVolume(int playerId, double volume) async {}

  @override
  Future<void> setPlaybackSpeed(int playerId, double speed) async {}

  @override
  Future<void> seekTo(int playerId, Duration position) async {}

  @override
  Future<Duration> getPosition(int playerId) async => Duration.zero;

  @override
  Widget buildViewWithOptions(VideoViewOptions options) => const SizedBox();
}
