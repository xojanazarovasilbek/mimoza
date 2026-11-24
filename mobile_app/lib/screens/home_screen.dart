import 'package:flutter/material.dart';

import '../widgets/product_image.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({required this.onOpenCatalog, super.key});

  final VoidCallback onOpenCatalog;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 18),
          Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: mimozaGold.withValues(alpha: .6)),
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
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 2,
                    ),
                  ),
                  SizedBox(height: 4),
                  Text(
                    'Toshkent',
                    style: TextStyle(color: mimozaCream, fontSize: 12),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 30),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(22),
            decoration: BoxDecoration(
              color: const Color(0xFF4A1722),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: mimozaGold.withValues(alpha: .4)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'GULLAR BILAN QUVONCH ULASHING',
                  style: TextStyle(
                    color: mimozaGold,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.6,
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Har bir buket — o‘ziga xos bir hikoya.',
                  style: TextStyle(
                    color: mimozaCream,
                    fontSize: 25,
                    fontWeight: FontWeight.w600,
                    height: 1.2,
                  ),
                ),
                const SizedBox(height: 10),
                const Text(
                  'Yaqinlaringizga mehringizni eng go‘zal gullar bilan bildiring.',
                  style: TextStyle(color: Color(0xFFE0D1C9), height: 1.5),
                ),
                const SizedBox(height: 20),
                FilledButton.icon(
                  onPressed: onOpenCatalog,
                  icon: const Icon(Icons.local_florist_outlined),
                  label: const Text('Katalogni ko‘rish'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const Text(
            'Mimoza Floral',
            style: TextStyle(
              color: mimozaCream,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            'Sevimli buketingizni tanlang, mahsulotlar bilan tanishing va '
            'yoqtirganlaringizni savatga qo‘shing.',
            style: TextStyle(color: Color(0xFFD7C7BF), height: 1.5),
          ),
        ],
      ),
    );
  }
}
