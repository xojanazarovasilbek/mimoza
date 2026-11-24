import 'package:flutter/material.dart';

const mimozaMaroon = Color(0xFF31010D);
const mimozaGold = Color(0xFFD9B95B);
const mimozaCream = Color(0xFFFAF7F2);

class ProductImage extends StatelessWidget {
  const ProductImage({required this.url, this.fit = BoxFit.cover, super.key});

  final String url;
  final BoxFit fit;

  @override
  Widget build(BuildContext context) {
    if (url.isEmpty) return const _ImagePlaceholder();
    return Image.network(
      url,
      fit: fit,
      errorBuilder: (context, error, stackTrace) => const _ImagePlaceholder(),
      loadingBuilder: (context, child, progress) {
        if (progress == null) return child;
        return const ColoredBox(
          color: Color(0xFFEEE5DC),
          child: Center(
            child: CircularProgressIndicator(color: mimozaGold, strokeWidth: 2),
          ),
        );
      },
    );
  }
}

class _ImagePlaceholder extends StatelessWidget {
  const _ImagePlaceholder();

  @override
  Widget build(BuildContext context) {
    return const ColoredBox(
      color: Color(0xFFEEE5DC),
      child: Center(
        child: Icon(Icons.local_florist, color: mimozaMaroon, size: 38),
      ),
    );
  }
}
