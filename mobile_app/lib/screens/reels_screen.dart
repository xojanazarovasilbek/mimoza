import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:video_player/video_player.dart';

import '../models/product.dart';
import '../services/store_api.dart';
import '../state/account_controller.dart';
import '../state/cart_model.dart';
import '../widgets/product_card.dart';
import '../widgets/product_image.dart';
import 'product_detail_screen.dart';

class ReelsScreen extends StatefulWidget {
  const ReelsScreen({
    required this.api,
    required this.cart,
    required this.account,
    required this.onOpenProfile,
    required this.active,
    super.key,
  });

  final StoreApi api;
  final CartModel cart;
  final AccountController account;
  final VoidCallback onOpenProfile;
  final bool active;

  @override
  State<ReelsScreen> createState() => _ReelsScreenState();
}

class _ReelsScreenState extends State<ReelsScreen> with WidgetsBindingObserver {
  final List<Product> _products = [];
  final Map<int, ({bool isLiked, int likesCount})> _likes = {};
  final Set<int> _liking = {};
  int _seed = Random().nextInt(2147483647);
  String? _accountToken;
  bool _refreshPending = false;
  int _currentIndex = 0;
  int _nextPage = 1;
  bool _hasNext = true;
  bool _loading = false;
  bool _loaded = false;
  bool _appActive = true;
  bool _showingProduct = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _accountToken = widget.account.accessToken;
    widget.account.addListener(_onAccountChanged);
    if (widget.active) _loadNextPage();
  }

  @override
  void didUpdateWidget(covariant ReelsScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.account != oldWidget.account) {
      oldWidget.account.removeListener(_onAccountChanged);
      widget.account.addListener(_onAccountChanged);
      _onAccountChanged();
    }
    if (widget.active && !oldWidget.active && _products.isEmpty && !_loading) {
      if (_loaded) {
        _refresh();
      } else {
        _loadNextPage();
      }
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final active = state == AppLifecycleState.resumed;
    if (_appActive != active) setState(() => _appActive = active);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.account.removeListener(_onAccountChanged);
    super.dispose();
  }

  void _onAccountChanged() {
    final token = widget.account.accessToken;
    if (_accountToken == token) return;
    _accountToken = token;
    if (_loading) {
      _refreshPending = true;
    } else if (_loaded || _products.isNotEmpty) {
      _refresh();
    }
  }

  Future<void> _loadNextPage() async {
    if (_loading || !_hasNext) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await widget.api.fetchReels(
        page: _nextPage,
        seed: _seed,
        accessToken: _accountToken,
      );
      if (!mounted) return;
      if (_refreshPending) return;
      setState(() {
        final seen = _products.map((product) => product.id).toSet();
        for (final product in page.products) {
          if (seen.add(product.id)) {
            _products.add(product);
            _likes[product.id] = (
              isLiked: product.isLiked,
              likesCount: product.likesCount,
            );
          }
        }
        _hasNext = page.hasNext;
        _nextPage++;
        _loaded = true;
      });
    } on StoreApiException catch (exception) {
      if (!mounted || _refreshPending) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) {
        setState(() => _loading = false);
        if (_refreshPending) {
          _refreshPending = false;
          _refresh();
        } else if (_error == null &&
            _hasNext &&
            _currentIndex >= _products.length) {
          _loadNextPage();
        }
      }
    }
  }

  void _refresh() {
    if (_loading) return;
    _products.clear();
    _likes.clear();
    _currentIndex = 0;
    _nextPage = 1;
    _hasNext = true;
    _loaded = false;
    _error = null;
    _seed = Random().nextInt(2147483647);
    _loadNextPage();
  }

  Future<void> _setLike(Product product) async {
    final token = _accountToken;
    if (token == null) {
      if (widget.account.isRestoring || widget.account.isLoading) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Akkaunt tekshirilmoqda.')),
        );
      } else {
        widget.onOpenProfile();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Like bosish uchun akkauntga kiring.')),
        );
      }
      return;
    }
    final current = _likes[product.id];
    if (current == null || _liking.contains(product.id)) return;
    setState(() => _liking.add(product.id));
    try {
      final result = await widget.api.setProductLike(
        productId: product.id,
        liked: !current.isLiked,
        accessToken: token,
      );
      if (mounted && _accountToken == token && _likes.containsKey(product.id)) {
        setState(() => _likes[product.id] = result);
      }
    } on StoreApiException catch (exception) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(exception.message)));
      }
    } finally {
      if (mounted) setState(() => _liking.remove(product.id));
    }
  }

  Future<void> _openProduct(Product product) async {
    setState(() => _showingProduct = true);
    try {
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => ProductDetailScreen(
            api: widget.api,
            cart: widget.cart,
            product: product,
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _showingProduct = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_products.isEmpty) {
      if (!widget.active) {
        return const SizedBox.shrink();
      }
      if (_loading || (!_loaded && _error == null)) {
        return const Center(
          child: CircularProgressIndicator(color: mimozaGold),
        );
      }
      if (_error != null) {
        return _ReelsMessage(
          message: _error!,
          button: 'Qayta urinish',
          onPressed: _loadNextPage,
        );
      }
      return _ReelsMessage(
        message: 'Hozircha Reels videolari yo‘q.',
        detail: 'Mahsulotga video qo‘shilgach, shu yerda ko‘rinadi.',
        button: 'Yangilash',
        onPressed: _refresh,
      );
    }

    return Stack(
      children: [
        _buildFeed(),
        Positioned(
          top: 8,
          right: 8,
          child: IconButton(
            tooltip: 'Yangilash',
            color: Colors.white,
            onPressed: _loading ? null : _refresh,
            icon: const Icon(Icons.refresh),
          ),
        ),
      ],
    );
  }

  Widget _buildFeed() {
    return PageView.builder(
      scrollDirection: Axis.vertical,
      itemCount: _products.length + (_hasNext ? 1 : 0),
      onPageChanged: (index) {
        setState(() => _currentIndex = index);
        if (index >= _products.length - 2 && _error == null) {
          _loadNextPage();
        }
      },
      itemBuilder: (context, index) {
        if (index == _products.length) {
          if (_error != null) {
            return _ReelsMessage(
              message: _error!,
              button: 'Qayta urinish',
              onPressed: _loadNextPage,
            );
          }
          return const Center(
            child: CircularProgressIndicator(color: mimozaGold),
          );
        }
        final product = _products[index];
        return _ReelCard(
          key: ValueKey(product.id),
          product: product,
          like: _likes[product.id]!,
          liking: _liking.contains(product.id),
          onLike: () => _setLike(product),
          active:
              widget.active &&
              _appActive &&
              !_showingProduct &&
              index == _currentIndex,
          onOpenProduct: () => _openProduct(product),
        );
      },
    );
  }
}

class _ReelCard extends StatefulWidget {
  const _ReelCard({
    required this.product,
    required this.active,
    required this.onOpenProduct,
    required this.like,
    required this.liking,
    required this.onLike,
    super.key,
  });

  final Product product;
  final bool active;
  final VoidCallback onOpenProduct;
  final ({bool isLiked, int likesCount}) like;
  final bool liking;
  final VoidCallback onLike;

  @override
  State<_ReelCard> createState() => _ReelCardState();
}

class _ReelCardState extends State<_ReelCard> {
  VideoPlayerController? _controller;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.active) _start();
  }

  @override
  void didUpdateWidget(covariant _ReelCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.active && !oldWidget.active) {
      _start();
    } else if (!widget.active && oldWidget.active) {
      _stop();
    }
  }

  @override
  void dispose() {
    _stop();
    super.dispose();
  }

  Future<void> _start() async {
    if (widget.product.videoIsEmbed) return;
    final uri = Uri.tryParse(widget.product.videoUrl);
    if (uri == null ||
        !uri.hasAuthority ||
        (uri.scheme != 'https' && uri.scheme != 'http')) {
      setState(() => _error = 'Video havolasi noto‘g‘ri.');
      return;
    }

    setState(() => _error = null);
    final controller = VideoPlayerController.networkUrl(uri);
    _controller = controller;
    controller.addListener(_onVideoChanged);
    try {
      await controller.initialize();
      if (!mounted || !identical(_controller, controller)) return;
      await controller.setLooping(true);
      if (!mounted || !identical(_controller, controller)) return;
      await controller.play();
    } on PlatformException {
      if (mounted && identical(_controller, controller)) {
        setState(() => _error = 'Videoni ochib bo‘lmadi.');
      }
    }
  }

  void _onVideoChanged() {
    final controller = _controller;
    if (mounted && controller != null) {
      setState(() {
        if (controller.value.hasError) {
          _error = 'Videoni ochib bo‘lmadi.';
        }
      });
    }
  }

  void _stop() {
    final controller = _controller;
    _controller = null;
    if (controller != null) {
      controller.removeListener(_onVideoChanged);
      unawaited(_release(controller));
    }
  }

  Future<void> _release(VideoPlayerController controller) async {
    try {
      if (controller.value.isInitialized) await controller.pause();
    } on PlatformException catch (exception, stackTrace) {
      FlutterError.reportError(
        FlutterErrorDetails(
          exception: exception,
          stack: stackTrace,
          library: 'reels',
          context: ErrorDescription('video to‘xtatilayotganda'),
        ),
      );
    } finally {
      await controller.dispose();
    }
  }

  Future<void> _openExternalVideo() async {
    final uri = Uri.tryParse(widget.product.videoUrl);
    if (uri == null ||
        !uri.hasAuthority ||
        (uri.scheme != 'https' && uri.scheme != 'http')) {
      setState(() => _error = 'Video havolasi noto‘g‘ri.');
      return;
    }
    try {
      final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!opened && mounted) {
        setState(() => _error = 'Video havolasini ochib bo‘lmadi.');
      }
    } on PlatformException {
      if (mounted) setState(() => _error = 'Video havolasini ochib bo‘lmadi.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final product = widget.product;
    final controller = _controller;
    final ready = controller != null && controller.value.isInitialized;
    return Stack(
      fit: StackFit.expand,
      children: [
        ProductImage(url: product.imageUrl),
        if (ready)
          Center(
            child: AspectRatio(
              aspectRatio: controller.value.aspectRatio,
              child: VideoPlayer(controller),
            ),
          ),
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0x66000000), Color(0x22000000), Color(0xDD000000)],
              stops: [0, .45, 1],
            ),
          ),
        ),
        if (product.videoIsEmbed)
          Center(
            child: FilledButton.icon(
              onPressed: _openExternalVideo,
              icon: const Icon(Icons.open_in_new),
              label: const Text('Videoni ochish'),
            ),
          )
        else if (_error != null)
          Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(_error!, style: const TextStyle(color: Colors.white)),
                  TextButton(
                    onPressed: () {
                      _stop();
                      _start();
                    },
                    child: const Text('Qayta urinish'),
                  ),
                ],
              ),
            ),
          )
        else if (ready)
          Center(
            child: IconButton.filledTonal(
              tooltip: controller.value.isPlaying ? 'To‘xtatish' : 'Ijro etish',
              onPressed: () => controller.value.isPlaying
                  ? controller.pause()
                  : controller.play(),
              iconSize: 36,
              icon: Icon(
                controller.value.isPlaying ? Icons.pause : Icons.play_arrow,
              ),
            ),
          )
        else if (widget.active)
          const Center(child: CircularProgressIndicator(color: mimozaGold)),
        if (product.videoIsEmbed && _error != null)
          Positioned(
            top: 50,
            left: 16,
            right: 16,
            child: Text(
              _error!,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white),
            ),
          ),
        const Positioned(
          top: 16,
          left: 16,
          child: Text(
            'Reels',
            style: TextStyle(
              color: Colors.white,
              fontSize: 24,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        Positioned(
          right: 12,
          bottom: 150,
          child: Column(
            children: [
              IconButton(
                tooltip: widget.like.isLiked
                    ? 'Like olib tashlash'
                    : 'Like bosish',
                onPressed: widget.liking ? null : widget.onLike,
                icon: Icon(
                  widget.like.isLiked ? Icons.favorite : Icons.favorite_border,
                  color: widget.like.isLiked ? Colors.redAccent : Colors.white,
                  size: 32,
                ),
              ),
              Text(
                '${widget.like.likesCount}',
                style: const TextStyle(color: Colors.white),
              ),
            ],
          ),
        ),
        Positioned(
          left: 16,
          right: 72,
          bottom: 20,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                product.category.name,
                style: const TextStyle(color: mimozaGold),
              ),
              const SizedBox(height: 4),
              Text(
                product.name,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                formatUzs(product.price),
                style: const TextStyle(color: mimozaGold),
              ),
              const SizedBox(height: 10),
              FilledButton(
                onPressed: widget.onOpenProduct,
                child: const Text('Mahsulotni ko‘rish'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ReelsMessage extends StatelessWidget {
  const _ReelsMessage({
    required this.message,
    this.detail,
    this.button,
    this.onPressed,
  });

  final String message;
  final String? detail;
  final String? button;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.play_circle_outline, color: mimozaGold, size: 60),
            const SizedBox(height: 16),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: mimozaCream, fontSize: 18),
            ),
            if (detail != null) ...[
              const SizedBox(height: 8),
              Text(
                detail!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xFFD7C7BF)),
              ),
            ],
            if (button != null) ...[
              const SizedBox(height: 12),
              OutlinedButton(onPressed: onPressed, child: Text(button!)),
            ],
          ],
        ),
      ),
    );
  }
}
