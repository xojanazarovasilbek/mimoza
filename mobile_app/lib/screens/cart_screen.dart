import 'package:flutter/material.dart';

import '../services/store_api.dart';
import '../state/account_controller.dart';
import '../state/cart_model.dart';
import '../widgets/product_card.dart';
import '../widgets/product_image.dart';
import 'checkout_screen.dart';

class CartScreen extends StatelessWidget {
  const CartScreen({
    required this.cart,
    required this.api,
    required this.account,
    required this.onOpenProfile,
    super.key,
  });

  final CartModel cart;
  final StoreApi api;
  final AccountController account;
  final VoidCallback onOpenProfile;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: cart,
      builder: (context, _) {
        if (cart.lines.isEmpty) {
          return const Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.shopping_bag_outlined, color: mimozaGold, size: 48),
                SizedBox(height: 12),
                Text(
                  'Savatingiz hozircha bo‘sh',
                  style: TextStyle(color: mimozaCream),
                ),
              ],
            ),
          );
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 24, 20, 14),
              child: Text(
                'Savat',
                style: TextStyle(
                  color: mimozaCream,
                  fontSize: 26,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            Expanded(
              child: ListView.separated(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                itemCount: cart.lines.length,
                separatorBuilder: (_, _) => const SizedBox(height: 10),
                itemBuilder: (context, index) {
                  final line = cart.lines[index];
                  return Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFF4A1722),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(6),
                          child: SizedBox(
                            width: 72,
                            height: 78,
                            child: ProductImage(url: line.product.imageUrl),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                line.product.name,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  color: mimozaCream,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(height: 5),
                              Text(
                                formatUzs(line.subtotal),
                                style: const TextStyle(
                                  color: mimozaGold,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              Row(
                                children: [
                                  IconButton(
                                    visualDensity: VisualDensity.compact,
                                    onPressed: () => cart.setQuantity(
                                      line.product,
                                      line.quantity - 1,
                                    ),
                                    icon: const Icon(
                                      Icons.remove_circle_outline,
                                      color: mimozaCream,
                                    ),
                                  ),
                                  Text(
                                    '${line.quantity}',
                                    style: const TextStyle(color: mimozaCream),
                                  ),
                                  IconButton(
                                    visualDensity: VisualDensity.compact,
                                    onPressed:
                                        line.quantity <
                                            line.product.stockQuantity
                                        ? () => cart.add(line.product)
                                        : null,
                                    icon: const Icon(
                                      Icons.add_circle_outline,
                                      color: mimozaCream,
                                    ),
                                  ),
                                  const Spacer(),
                                  IconButton(
                                    visualDensity: VisualDensity.compact,
                                    tooltip: 'O‘chirish',
                                    onPressed: () =>
                                        cart.setQuantity(line.product, 0),
                                    icon: const Icon(
                                      Icons.delete_outline,
                                      color: mimozaGold,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
            SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      children: [
                        const Text(
                          'Jami',
                          style: TextStyle(color: mimozaCream, fontSize: 16),
                        ),
                        const Spacer(),
                        Text(
                          formatUzs(cart.total),
                          style: const TextStyle(
                            color: mimozaGold,
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    FilledButton(
                      onPressed: () {
                        if (account.accessToken == null) {
                          if (!account.isRestoring && !account.isLoading) {
                            onOpenProfile();
                          }
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(
                                account.isRestoring || account.isLoading
                                    ? 'Akkaunt tekshirilmoqda.'
                                    : 'Buyurtma berish uchun akkauntga kiring.',
                              ),
                            ),
                          );
                          return;
                        }
                        Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => CheckoutScreen(
                              api: api,
                              account: account,
                              cart: cart,
                            ),
                          ),
                        );
                      },
                      child: const Text('Buyurtma berish'),
                    ),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}
