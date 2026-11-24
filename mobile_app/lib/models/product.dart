class ProductCategory {
  const ProductCategory({required this.name, required this.slug});

  final String name;
  final String slug;

  factory ProductCategory.fromJson(Map<String, dynamic> json) {
    return ProductCategory(
      name: _requiredString(json, 'name'),
      slug: _requiredString(json, 'slug'),
    );
  }
}

class Product {
  const Product({
    required this.id,
    required this.name,
    required this.slug,
    required this.category,
    required this.description,
    required this.price,
    required this.stockQuantity,
    required this.imageUrl,
    this.oldPrice,
    this.videoUrl = '',
    this.videoIsEmbed = false,
    this.isFeatured = false,
    this.likesCount = 0,
    this.isLiked = false,
  });

  final int id;
  final String name;
  final String slug;
  final ProductCategory category;
  final String description;
  final int price;
  final int? oldPrice;
  final int stockQuantity;
  final String imageUrl;
  final String videoUrl;
  final bool videoIsEmbed;
  final bool isFeatured;
  final int likesCount;
  final bool isLiked;

  factory Product.fromJson(Map<String, dynamic> json) {
    final categoryJson = json['category'];
    if (categoryJson is! Map<String, dynamic>) {
      throw const FormatException('Mahsulot kategoriyasi noto‘g‘ri.');
    }

    return Product(
      id: _requiredInt(json, 'id'),
      name: _requiredString(json, 'name'),
      slug: _requiredString(json, 'slug'),
      category: ProductCategory.fromJson(categoryJson),
      description: _optionalString(json, 'description'),
      price: _requiredInt(json, 'price'),
      oldPrice: json['old_price'] is num
          ? (json['old_price'] as num).toInt()
          : null,
      stockQuantity: _requiredInt(json, 'stock_quantity'),
      imageUrl: _optionalString(json, 'image_url'),
      videoUrl: _optionalString(json, 'video_url'),
      videoIsEmbed: json['video_is_embed'] == true,
      isFeatured: json['is_featured'] == true,
      likesCount: json['likes_count'] == null
          ? 0
          : _requiredInt(json, 'likes_count'),
      isLiked: json['is_liked'] == true,
    );
  }
}

String _requiredString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String) {
    throw FormatException('Mahsulot ma’lumotida "$key" maydoni noto‘g‘ri.');
  }
  return value;
}

String _optionalString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value == null) return '';
  if (value is! String) {
    throw FormatException('Mahsulot ma’lumotida "$key" maydoni noto‘g‘ri.');
  }
  return value;
}

int _requiredInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! num) {
    throw FormatException('Mahsulot ma’lumotida "$key" maydoni noto‘g‘ri.');
  }
  return value.toInt();
}

class ProductCatalog {
  const ProductCatalog({
    required this.products,
    required this.categories,
    required this.count,
  });

  final List<Product> products;
  final List<ProductCategory> categories;
  final int count;

  factory ProductCatalog.fromJson(Map<String, dynamic> json) {
    final productItems = json['products'];
    final categoryItems = json['categories'];
    if (productItems is! List || categoryItems is! List) {
      throw const FormatException('Katalog ma’lumotlari noto‘g‘ri.');
    }

    return ProductCatalog(
      products: productItems
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Katalogdagi mahsulot noto‘g‘ri.');
            }
            return Product.fromJson(item);
          })
          .toList(growable: false),
      categories: categoryItems
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Katalog kategoriyasi noto‘g‘ri.');
            }
            return ProductCategory.fromJson(item);
          })
          .toList(growable: false),
      count: _requiredInt(json, 'count'),
    );
  }
}

class ReelsPage {
  const ReelsPage({required this.products, required this.hasNext});

  final List<Product> products;
  final bool hasNext;

  factory ReelsPage.fromJson(Map<String, dynamic> json) {
    final items = json['products'];
    final hasNext = json['has_next'];
    if (items is! List || hasNext is! bool) {
      throw const FormatException('Reels ma’lumotlari noto‘g‘ri.');
    }
    return ReelsPage(
      products: items
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Reels mahsuloti noto‘g‘ri.');
            }
            return Product.fromJson(item);
          })
          .toList(growable: false),
      hasNext: hasNext,
    );
  }
}
