import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../models/admin_management.dart';
import '../services/store_api.dart';
import '../widgets/product_card.dart';

class AdminProductsScreen extends StatefulWidget {
  const AdminProductsScreen({
    required this.api,
    required this.token,
    super.key,
  });
  final StoreApi api;
  final String token;
  @override
  State<AdminProductsScreen> createState() => _AdminProductsScreenState();
}

class _AdminProductsScreenState extends State<AdminProductsScreen> {
  final _query = TextEditingController();
  AdminProductsPage? _data;
  int _page = 1;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _data = null;
    });
    try {
      final result = await widget.api.fetchAdminProducts(
        widget.token,
        page: _page,
        query: _query.text.trim(),
      );
      if (mounted) setState(() => _data = result);
    } on StoreApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _edit(
    AdminProduct? product,
    List<AdminCategory> categories,
  ) async {
    if (categories.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Avval saytda kategoriya qo‘shing.')),
      );
      return;
    }
    await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => _ProductEditor(
          api: widget.api,
          token: widget.token,
          product: product,
          categories: categories,
        ),
      ),
    );
    if (mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    return Scaffold(
      appBar: AppBar(title: const Text('Mahsulotlar va ombor')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _query,
            enabled: !_loading,
            decoration: const InputDecoration(
              labelText: 'Mahsulot yoki kategoriya',
            ),
            onSubmitted: (_) {
              _page = 1;
              _load();
            },
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _loading
                      ? null
                      : () {
                          _page = 1;
                          _load();
                        },
                  child: const Text('Qidirish'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: FilledButton(
                  onPressed: _loading || data == null
                      ? null
                      : () => _edit(null, data.categories),
                  child: const Text('Qo‘shish'),
                ),
              ),
            ],
          ),
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) ...[
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
            TextButton(
              onPressed: _loading ? null : _load,
              child: const Text('Qayta urinish'),
            ),
          ],
          if (data != null) ...[
            if (data.products.isEmpty)
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text('Mahsulot topilmadi.'),
              ),
            ...data.products.map(
              (product) => Card(
                margin: const EdgeInsets.only(top: 8),
                child: ListTile(
                  title: Text(
                    product.name,
                    style: const TextStyle(color: Color(0xFF3B111A)),
                  ),
                  subtitle: Text(
                    '${product.category} · ${formatUzs(product.price)}\nOmbor: ${product.quantity} ta · ${product.inStock ? 'Sotuvda' : 'Sotuvda emas'}',
                    style: const TextStyle(color: Color(0xFF786B64)),
                  ),
                  isThreeLine: true,
                  trailing: const Icon(Icons.edit, color: Color(0xFF3B111A)),
                  onTap: _loading
                      ? null
                      : () => _edit(product, data.categories),
                ),
              ),
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                TextButton(
                  onPressed: _loading || _page == 1
                      ? null
                      : () {
                          _page--;
                          _load();
                        },
                  child: const Text('Oldingi'),
                ),
                Text('$_page'),
                TextButton(
                  onPressed: _loading || !data.hasNext
                      ? null
                      : () {
                          _page++;
                          _load();
                        },
                  child: const Text('Keyingi'),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _ProductEditor extends StatefulWidget {
  const _ProductEditor({
    required this.api,
    required this.token,
    required this.product,
    required this.categories,
  });
  final StoreApi api;
  final String token;
  final AdminProduct? product;
  final List<AdminCategory> categories;
  @override
  State<_ProductEditor> createState() => _ProductEditorState();
}

class _ProductEditorState extends State<_ProductEditor> {
  final _form = GlobalKey<FormState>();
  late final Map<String, TextEditingController> _fields;
  late int _category;
  late bool _inStock, _featured;
  bool _clearImage = false, _clearVideo = false, _saving = false;
  XFile? _image, _video;
  String? _error;

  @override
  void initState() {
    super.initState();
    final p = widget.product;
    _category = p?.categoryId ?? widget.categories.first.id;
    _inStock = p?.inStock ?? true;
    _featured = p?.featured ?? false;
    _fields = {
      'name': TextEditingController(text: p?.name),
      'slug': TextEditingController(text: p?.slug),
      'description': TextEditingController(text: p?.description),
      'price': TextEditingController(text: p == null ? '' : '${p.price}'),
      'old_price': TextEditingController(text: p?.oldPrice?.toString() ?? ''),
      'stock_quantity': TextEditingController(
        text: p == null ? '0' : '${p.quantity}',
      ),
      'image_url': TextEditingController(text: p?.imageUrl),
      'video_url': TextEditingController(text: p?.videoUrl),
    };
  }

  @override
  void dispose() {
    for (final controller in _fields.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _pick(bool video) async {
    try {
      final picker = ImagePicker();
      final file = video
          ? await picker.pickVideo(source: ImageSource.gallery)
          : await picker.pickImage(source: ImageSource.gallery);
      if (file != null && mounted) {
        setState(() {
          if (video) {
            _video = file;
            _clearVideo = false;
          } else {
            _image = file;
            _clearImage = false;
          }
        });
      }
    } on PlatformException {
      if (mounted) setState(() => _error = 'Faylni tanlab bo‘lmadi.');
    }
  }

  Future<void> _save() async {
    if (_saving || !_form.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final fields = <String, String>{
      for (final entry in _fields.entries) entry.key: entry.value.text.trim(),
      'category': '$_category',
      if (widget.product != null) 'version': widget.product!.version,
      if (_inStock) 'in_stock': 'on',
      if (_featured) 'is_featured': 'on',
      if (_clearImage) 'image-clear': 'on',
      if (_clearVideo) 'video-clear': 'on',
    };
    try {
      await widget.api.saveAdminProduct(
        widget.token,
        id: widget.product?.id,
        fields: fields,
        imagePath: _image?.path,
        videoPath: _video?.path,
      );
      if (mounted) Navigator.pop(context, true);
    } on StoreApiException catch (exception) {
      if (mounted) setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _field(
    String key,
    String label, {
    bool required = false,
    bool number = false,
    int lines = 1,
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: TextFormField(
      controller: _fields[key],
      enabled: !_saving,
      maxLines: lines,
      keyboardType: number ? TextInputType.number : TextInputType.text,
      decoration: InputDecoration(labelText: label),
      validator: (value) {
        final text = value?.trim() ?? '';
        if (required && text.isEmpty) return 'Bu maydonni to‘ldiring.';
        if (number &&
            text.isNotEmpty &&
            (int.tryParse(text) == null || int.parse(text) < 0)) {
          return 'Musbat yoki nol son kiriting.';
        }
        return null;
      },
    ),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        widget.product == null ? 'Mahsulot qo‘shish' : 'Mahsulotni tahrirlash',
      ),
    ),
    body: Form(
      key: _form,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _field('name', 'Nomi', required: true),
          _field('slug', 'Slug (lotin harflari va tire)', required: true),
          DropdownButtonFormField<int>(
            initialValue: _category,
            decoration: const InputDecoration(labelText: 'Kategoriya'),
            items: widget.categories
                .map(
                  (category) => DropdownMenuItem(
                    value: category.id,
                    child: Text(category.name),
                  ),
                )
                .toList(),
            onChanged: _saving
                ? null
                : (value) => setState(() => _category = value ?? _category),
          ),
          const SizedBox(height: 12),
          _field('description', 'Tavsif', lines: 3),
          _field('price', 'Narx', required: true, number: true),
          _field('old_price', 'Eski narx', number: true),
          _field(
            'stock_quantity',
            'Ombor miqdori',
            required: true,
            number: true,
          ),
          _field('image_url', 'Rasm havolasi'),
          _field('video_url', 'Video havolasi'),
          OutlinedButton.icon(
            onPressed: _saving ? null : () => _pick(false),
            icon: const Icon(Icons.image),
            label: Text(
              _image == null ? 'Rasm tanlash' : 'Rasm: ${_image!.name}',
            ),
          ),
          if (widget.product?.hasImage == true)
            CheckboxListTile(
              value: _clearImage,
              title: const Text('Yuklangan rasmni o‘chirish'),
              onChanged: _saving
                  ? null
                  : (value) => setState(() {
                      _clearImage = value ?? false;
                      if (_clearImage) _image = null;
                    }),
            ),
          OutlinedButton.icon(
            onPressed: _saving ? null : () => _pick(true),
            icon: const Icon(Icons.videocam),
            label: Text(
              _video == null ? 'Video tanlash' : 'Video: ${_video!.name}',
            ),
          ),
          if (widget.product?.hasVideo == true)
            CheckboxListTile(
              value: _clearVideo,
              title: const Text('Yuklangan videoni o‘chirish'),
              onChanged: _saving
                  ? null
                  : (value) => setState(() {
                      _clearVideo = value ?? false;
                      if (_clearVideo) _video = null;
                    }),
            ),
          const Text('Yuklangan rasm yoki video havoladan ustun turadi.'),
          SwitchListTile(
            value: _inStock,
            title: const Text('Sotuvda'),
            onChanged: _saving
                ? null
                : (value) => setState(() => _inStock = value),
          ),
          SwitchListTile(
            value: _featured,
            title: const Text('Tavsiya etilgan'),
            onChanged: _saving
                ? null
                : (value) => setState(() => _featured = value),
          ),
          if (_error != null)
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Saqlanmoqda...' : 'Saqlash'),
          ),
        ],
      ),
    ),
  );
}
