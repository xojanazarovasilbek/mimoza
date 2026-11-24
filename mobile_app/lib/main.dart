import 'package:flutter/material.dart';

import 'screens/admin_dashboard_screen.dart';
import 'screens/cart_screen.dart';
import 'screens/catalog_screen.dart';
import 'screens/home_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/reels_screen.dart';
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

class _MimozaAppState extends State<MimozaApp> {
  late final StoreApi _api = widget.api ?? StoreApi();
  late final AccountController _account = AccountController(
    _api,
    widget.tokenStore ?? const SecureTokenStore(),
  );
  final _cart = CartModel();

  @override
  void initState() {
    super.initState();
    _account.restore();
  }

  @override
  void dispose() {
    _api.close();
    _account.dispose();
    _cart.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
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

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.account,
      builder: (context, _) {
        if (widget.account.account?.isAdmin == true) {
          return AdminDashboardScreen(api: widget.api, account: widget.account);
        }
        return _buildCustomerShell();
      },
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
