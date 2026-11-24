import 'package:flutter/material.dart';

import '../models/product.dart';
import '../services/store_api.dart';
import '../state/cart_model.dart';
import '../widgets/product_card.dart';
import '../widgets/product_image.dart';
import 'product_detail_screen.dart';

class CatalogScreen extends StatefulWidget {
  const CatalogScreen({required this.api, required this.cart, super.key});

  final StoreApi api;
  final CartModel cart;

  @override
  State<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends State<CatalogScreen> {
  final _searchController = TextEditingController();
  late Future<ProductCatalog> _catalog;
  String? _selectedCategory;

  @override
  void initState() {
    super.initState();
    _catalog = widget.api.fetchProducts();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _catalog = widget.api.fetchProducts(
        query: _searchController.text,
        category: _selectedCategory,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 14),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  border: Border.all(color: mimozaGold.withValues(alpha: .6)),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.local_florist, color: mimozaGold),
              ),
              const SizedBox(width: 12),
              const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'MIMOZA FLORAL',
                    style: TextStyle(
                      color: mimozaGold,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 2.2,
                    ),
                  ),
                  SizedBox(height: 3),
                  Text(
                    'Gullar bilan quvonch ulashing',
                    style: TextStyle(color: mimozaCream, fontSize: 12),
                  ),
                ],
              ),
              const Spacer(),
              const Icon(
                Icons.location_on_outlined,
                color: mimozaGold,
                size: 18,
              ),
              const SizedBox(width: 4),
              const Text(
                'Toshkent',
                style: TextStyle(color: mimozaCream, fontSize: 12),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: TextField(
            controller: _searchController,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _reload(),
            decoration: InputDecoration(
              hintText: 'Gullarni qidiring',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: IconButton(
                tooltip: 'Qidirish',
                onPressed: _reload,
                icon: const Icon(Icons.arrow_forward),
              ),
            ),
          ),
        ),
        const Padding(
          padding: EdgeInsets.fromLTRB(20, 22, 20, 10),
          child: Text(
            'Gullar katalogi',
            style: TextStyle(
              color: mimozaCream,
              fontSize: 24,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Expanded(
          child: FutureBuilder<ProductCatalog>(
            future: _catalog,
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return const Center(
                  child: CircularProgressIndicator(color: mimozaGold),
                );
              }
              if (snapshot.hasError) {
                return _ErrorPanel(
                  message: snapshot.error.toString(),
                  onRetry: _reload,
                );
              }
              final catalog = snapshot.data!;
              return Column(
                children: [
                  if (catalog.categories.isNotEmpty)
                    SizedBox(
                      height: 48,
                      child: ListView(
                        scrollDirection: Axis.horizontal,
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        children: [
                          _CategoryChip(
                            label: 'Barchasi',
                            selected: _selectedCategory == null,
                            onTap: () {
                              setState(() => _selectedCategory = null);
                              _reload();
                            },
                          ),
                          for (final category in catalog.categories)
                            _CategoryChip(
                              label: category.name,
                              selected: _selectedCategory == category.slug,
                              onTap: () {
                                setState(
                                  () => _selectedCategory = category.slug,
                                );
                                _reload();
                              },
                            ),
                        ],
                      ),
                    ),
                  Expanded(
                    child: catalog.products.isEmpty
                        ? const Center(
                            child: Text(
                              'Hozircha mahsulot topilmadi.',
                              style: TextStyle(color: mimozaCream),
                            ),
                          )
                        : RefreshIndicator(
                            color: mimozaMaroon,
                            backgroundColor: mimozaGold,
                            onRefresh: () async => _reload(),
                            child: GridView.builder(
                              padding: const EdgeInsets.fromLTRB(14, 8, 14, 20),
                              physics: const AlwaysScrollableScrollPhysics(),
                              gridDelegate:
                                  const SliverGridDelegateWithFixedCrossAxisCount(
                                    crossAxisCount: 2,
                                    crossAxisSpacing: 10,
                                    mainAxisSpacing: 10,
                                    childAspectRatio: .63,
                                  ),
                              itemCount: catalog.products.length,
                              itemBuilder: (context, index) {
                                final product = catalog.products[index];
                                return ProductCard(
                                  product: product,
                                  onTap: () {
                                    Navigator.of(context).push(
                                      MaterialPageRoute<void>(
                                        builder: (_) => ProductDetailScreen(
                                          api: widget.api,
                                          cart: widget.cart,
                                          product: product,
                                        ),
                                      ),
                                    );
                                  },
                                );
                              },
                            ),
                          ),
                  ),
                ],
              );
            },
          ),
        ),
      ],
    );
  }
}

class _CategoryChip extends StatelessWidget {
  const _CategoryChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: ChoiceChip(
        label: Text(label),
        selected: selected,
        onSelected: (_) => onTap(),
        selectedColor: mimozaGold,
        backgroundColor: const Color(0xFF4A1722),
        labelStyle: TextStyle(
          color: selected ? mimozaMaroon : mimozaCream,
          fontSize: 12,
        ),
        side: BorderSide(color: mimozaGold.withValues(alpha: .25)),
      ),
    );
  }
}

class _ErrorPanel extends StatelessWidget {
  const _ErrorPanel({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined, color: mimozaGold, size: 38),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: mimozaCream),
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Qayta urinish'),
            ),
          ],
        ),
      ),
    );
  }
}
