import 'dart:async';

import 'package:flutter/material.dart';

import 'screens/admin_dashboard_screen.dart';
import 'screens/cart_screen.dart';
import 'screens/catalog_screen.dart';
import 'screens/home_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/reels_screen.dart';
import 'services/mobile_push.dart';
import 'services/store_api.dart';
import 'services/token_store.dart';
import 'state/account_controller.dart';
import 'state/cart_model.dart';
import 'widgets/product_image.dart';

void main() {
  runApp(const MimozaApp());
}

class MimozaApp extends StatefulWidget {
  const MimozaApp({this.api, this.tokenStore, super.key});

  final StoreApi? api;
  final TokenStore? tokenStore;

  @override
  State<MimozaApp> createState() => _MimozaAppState();
}

class _MimozaAppState extends State<MimozaApp> with WidgetsBindingObserver {
  late final StoreApi _api = widget.api ?? StoreApi();
  late final AccountController _account = AccountController(
    _api,
    widget.tokenStore ?? const SecureTokenStore(),
  );
  final _cart = CartModel();
  final _messengerKey = GlobalKey<ScaffoldMessengerState>();
  late final _push = MobilePush(_api, _account, (message) {
    if (message.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          _messengerKey.currentState?.showSnackBar(
            SnackBar(content: Text(message)),
          );
        }
      });
    }
  });

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _account.restore();
    unawaited(_push.start());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_push.sync());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _push.dispose();
    _api.close();
    _account.dispose();
    _cart.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      scaffoldMessengerKey: _messengerKey,
      title: 'Mimoza Floral',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme:
            ColorScheme.fromSeed(
              seedColor: mimozaGold,
              brightness: Brightness.dark,
            ).copyWith(
              primary: mimozaGold,
              onPrimary: mimozaMaroon,
              surface: const Color(0xFF3B111A),
            ),
        scaffoldBackgroundColor: mimozaMaroon,
        appBarTheme: const AppBarTheme(
          backgroundColor: mimozaMaroon,
          foregroundColor: mimozaCream,
          centerTitle: false,
        ),
        cardTheme: CardThemeData(
          color: mimozaCream,
          margin: EdgeInsets.zero,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFF4A1722),
          hintStyle: const TextStyle(color: Color(0xFFCCBFC0)),
          prefixIconColor: mimozaGold,
          suffixIconColor: mimozaGold,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: BorderSide(color: mimozaGold.withValues(alpha: .3)),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: BorderSide(color: mimozaGold.withValues(alpha: .3)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: const BorderSide(color: mimozaGold),
          ),
        ),
        navigationBarTheme: const NavigationBarThemeData(
          backgroundColor: Color(0xFF3B111A),
          indicatorColor: mimozaGold,
          labelTextStyle: WidgetStatePropertyAll(
            TextStyle(color: mimozaCream, fontSize: 11),
          ),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: mimozaGold,
            foregroundColor: mimozaMaroon,
            minimumSize: const Size(48, 48),
            textStyle: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            foregroundColor: mimozaGold,
            side: const BorderSide(color: mimozaGold),
          ),
        ),
      ),
      home: _AppShell(api: _api, account: _account, cart: _cart),
    );
  }
}

class _AppShell extends StatefulWidget {
  const _AppShell({
    required this.api,
    required this.account,
    required this.cart,
  });

  final StoreApi api;
  final AccountController account;
  final CartModel cart;

  @override
  State<_AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<_AppShell> {
  int _selectedIndex = 0;
  late bool _isAdmin;

  @override
  void initState() {
    super.initState();
    _isAdmin = widget.account.account?.isAdmin == true;
    if (_isAdmin) _selectedIndex = 5;
    widget.account.addListener(_onAccountChanged);
  }

  @override
  void didUpdateWidget(covariant _AppShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.account != widget.account) {
      oldWidget.account.removeListener(_onAccountChanged);
      widget.account.addListener(_onAccountChanged);
      _onAccountChanged();
    }
  }

  @override
  void dispose() {
    widget.account.removeListener(_onAccountChanged);
    super.dispose();
  }

  void _onAccountChanged() {
    final isAdmin = widget.account.account?.isAdmin == true;
    if (isAdmin == _isAdmin) return;
    setState(() {
      _isAdmin = isAdmin;
      _selectedIndex = isAdmin ? 5 : 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.account,
      builder: (context, _) => _buildCustomerShell(),
    );
  }

  Widget _buildCustomerShell() {
    return Scaffold(
      body: SafeArea(
        child: IndexedStack(
          index: _selectedIndex,
          children: [
            HomeScreen(onOpenCatalog: () => _selectTab(1)),
            CatalogScreen(api: widget.api, cart: widget.cart),
            ReelsScreen(
              api: widget.api,
              cart: widget.cart,
              account: widget.account,
              onOpenProfile: () => _selectTab(4),
              active: _selectedIndex == 2,
            ),
            CartScreen(
              cart: widget.cart,
              api: widget.api,
              account: widget.account,
              onOpenProfile: () => _selectTab(4),
            ),
            ProfileScreen(accountController: widget.account, api: widget.api),
            if (_isAdmin)
              AdminDashboardScreen(api: widget.api, account: widget.account),
          ],
        ),
      ),
      bottomNavigationBar: AnimatedBuilder(
        animation: widget.cart,
        builder: (context, _) {
          return NavigationBar(
            selectedIndex: _selectedIndex,
            onDestinationSelected: _selectTab,
            destinations: [
              const NavigationDestination(
                key: ValueKey('nav-home'),
                icon: Icon(Icons.home_outlined),
                selectedIcon: Icon(Icons.home),
                label: 'Bosh sahifa',
              ),
              const NavigationDestination(
                key: ValueKey('nav-catalog'),
                icon: Icon(Icons.local_florist_outlined),
                selectedIcon: Icon(Icons.local_florist),
                label: 'Katalog',
              ),
              const NavigationDestination(
                key: ValueKey('nav-reels'),
                icon: Icon(Icons.play_circle_outline),
                selectedIcon: Icon(Icons.play_circle),
                label: 'Reels',
              ),
              NavigationDestination(
                key: const ValueKey('nav-cart'),
                icon: widget.cart.itemCount == 0
                    ? const Icon(Icons.shopping_bag_outlined)
                    : Badge(
                        label: Text('${widget.cart.itemCount}'),
                        child: const Icon(Icons.shopping_bag_outlined),
                      ),
                selectedIcon: widget.cart.itemCount == 0
                    ? const Icon(Icons.shopping_bag)
                    : Badge(
                        label: Text('${widget.cart.itemCount}'),
                        child: const Icon(Icons.shopping_bag),
                      ),
                label: 'Savat',
              ),
              const NavigationDestination(
                key: ValueKey('nav-profile'),
                icon: Icon(Icons.person_outline),
                selectedIcon: Icon(Icons.person),
                label: 'Profil',
              ),
              if (_isAdmin)
                const NavigationDestination(
                  key: ValueKey('nav-admin'),
                  icon: Icon(Icons.admin_panel_settings_outlined),
                  selectedIcon: Icon(Icons.admin_panel_settings),
                  label: 'Admin',
                ),
            ],
          );
        },
      ),
    );
  }

  void _selectTab(int index) {
    setState(() => _selectedIndex = index);
    if (index == 4 &&
        widget.account.account != null &&
        !widget.account.isLoading) {
      widget.account.restore(force: true);
    }
  }
}
