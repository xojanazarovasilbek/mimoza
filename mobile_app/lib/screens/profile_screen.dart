import 'package:flutter/material.dart';

import '../models/account.dart';
import '../services/store_api.dart';
import '../state/account_controller.dart';
import '../widgets/product_image.dart';
import 'order_receipt_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({
    required this.accountController,
    required this.api,
    super.key,
  });

  final AccountController accountController;
  final StoreApi api;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _emailController = TextEditingController();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _passwordConfirmationController = TextEditingController();
  bool _isRegistering = false;

  @override
  void dispose() {
    _nameController.dispose();
    _phoneController.dispose();
    _emailController.dispose();
    _usernameController.dispose();
    _passwordController.dispose();
    _passwordConfirmationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.accountController,
      builder: (context, _) {
        final controller = widget.accountController;
        return ListView(
          padding: const EdgeInsets.all(20),
          children: [
            const SizedBox(height: 12),
            const Text(
              'Profil',
              style: TextStyle(
                color: mimozaCream,
                fontSize: 26,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 18),
            if (controller.isRestoring)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator(color: mimozaGold),
                ),
              )
            else if (controller.account case final account?)
              _buildAccount(account, controller)
            else
              _buildGuestForm(controller),
            if (controller.error != null) ...[
              const SizedBox(height: 12),
              _errorMessage(controller.error!),
              if (controller.account == null)
                TextButton(
                  onPressed: controller.isLoading
                      ? null
                      : () => controller.restore(force: true),
                  child: const Text('Qayta urinish'),
                ),
            ],
          ],
        );
      },
    );
  }

  Widget _buildGuestForm(AccountController controller) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const CircleAvatar(
                  radius: 25,
                  backgroundColor: mimozaMaroon,
                  child: Icon(Icons.person_outline, color: mimozaGold),
                ),
                const SizedBox(width: 14),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Mehmon',
                        style: TextStyle(
                          color: mimozaMaroon,
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      SizedBox(height: 4),
                      Text(
                        'Buyurtmalaringizni ko‘rish uchun akkauntga kiring',
                        style: TextStyle(color: Color(0xFF786B64)),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    _isRegistering ? 'Yangi akkaunt' : 'Akkauntga kirish',
                    style: const TextStyle(
                      color: mimozaMaroon,
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (_isRegistering) ...[
                    _textField(
                      controller: _nameController,
                      label: 'Ism va familiya',
                      validator: _requiredValidator,
                      textCapitalization: TextCapitalization.words,
                    ),
                    _textField(
                      controller: _phoneController,
                      label: 'Telefon raqam',
                      validator: _requiredValidator,
                      keyboardType: TextInputType.phone,
                    ),
                    _textField(
                      controller: _emailController,
                      label: 'Email (ixtiyoriy)',
                      keyboardType: TextInputType.emailAddress,
                    ),
                  ],
                  _textField(
                    controller: _usernameController,
                    label: 'Foydalanuvchi nomi',
                    validator: _requiredValidator,
                    textInputAction: TextInputAction.next,
                  ),
                  _textField(
                    controller: _passwordController,
                    label: 'Parol',
                    validator: _requiredValidator,
                    obscureText: true,
                  ),
                  if (_isRegistering)
                    _textField(
                      controller: _passwordConfirmationController,
                      label: 'Parolni tasdiqlang',
                      validator: (value) {
                        final requiredError = _requiredValidator(value);
                        if (requiredError != null) return requiredError;
                        if (value != _passwordController.text) {
                          return 'Parollar bir-biriga mos emas.';
                        }
                        return null;
                      },
                      obscureText: true,
                    ),
                  const SizedBox(height: 8),
                  FilledButton(
                    onPressed: controller.isLoading ? null : _submit,
                    child: controller.isLoading
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: mimozaMaroon,
                            ),
                          )
                        : Text(_isRegistering ? 'Ro‘yxatdan o‘tish' : 'Kirish'),
                  ),
                  TextButton(
                    onPressed: controller.isLoading
                        ? null
                        : () => setState(() {
                            _isRegistering = !_isRegistering;
                            widget.accountController.error = null;
                          }),
                    child: Text(
                      _isRegistering
                          ? 'Akkauntingiz bormi? Kirish'
                          : 'Yangi akkaunt yaratish',
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        const ListTile(
          leading: Icon(Icons.receipt_long_outlined, color: mimozaGold),
          title: Text('Buyurtmalarim', style: TextStyle(color: mimozaCream)),
          subtitle: Text(
            'Akkauntga kirgandan so‘ng buyurtmalar shu yerda chiqadi',
            style: TextStyle(color: Color(0xFFCCBFC0)),
          ),
        ),
      ],
    );
  }

  Widget _buildAccount(CustomerAccount account, AccountController controller) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const CircleAvatar(
                  radius: 25,
                  backgroundColor: mimozaMaroon,
                  child: Icon(Icons.person, color: mimozaGold),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        account.name,
                        style: const TextStyle(
                          color: mimozaMaroon,
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        account.phone.isEmpty
                            ? '@${account.username}'
                            : account.phone,
                        style: const TextStyle(color: Color(0xFF786B64)),
                      ),
                      if (account.email.isNotEmpty)
                        Text(
                          account.email,
                          style: const TextStyle(color: Color(0xFF786B64)),
                        ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Akkauntdan chiqish',
                  onPressed: controller.isLoading ? null : controller.signOut,
                  icon: const Icon(Icons.logout, color: mimozaMaroon),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 20),
        Row(
          children: [
            const Expanded(
              child: Text(
                'Buyurtmalarim',
                style: TextStyle(
                  color: mimozaCream,
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            IconButton(
              tooltip: 'Buyurtmalarni yangilash',
              onPressed: controller.isLoading
                  ? null
                  : () => controller.restore(force: true),
              icon: const Icon(Icons.refresh, color: mimozaGold),
            ),
            Text(
              '${account.orders.length}',
              style: const TextStyle(color: mimozaGold),
            ),
          ],
        ),
        const SizedBox(height: 10),
        if (account.orders.isEmpty)
          const Card(
            child: ListTile(
              leading: Icon(Icons.receipt_long_outlined, color: mimozaMaroon),
              title: Text(
                'Hozircha buyurtmalar yo‘q',
                style: TextStyle(color: mimozaMaroon),
              ),
              subtitle: Text('Buyurtmalaringiz bu yerda ko‘rinadi.'),
            ),
          )
        else
          ...account.orders.map(_orderCard),
      ],
    );
  }

  Widget _orderCard(CustomerOrder order) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: InkWell(
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => OrderReceiptScreen(
              api: widget.api,
              account: widget.accountController,
              orderId: order.id,
            ),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Buyurtma #${order.code}',
                      style: const TextStyle(
                        color: mimozaMaroon,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  Text(
                    _formatDate(order.createdAt),
                    style: const TextStyle(color: Color(0xFF786B64)),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                order.status,
                style: const TextStyle(color: Color(0xFF947333)),
              ),
              if (const {
                    'click',
                    'payme',
                    'uzum',
                  }.contains(order.paymentMethod) &&
                  order.paymentStatus != 'paid')
                const Text(
                  'Avans to‘lovi kutilmoqda',
                  style: TextStyle(color: Color(0xFF947333)),
                ),
              const Divider(height: 18),
              ...order.items.map(
                (item) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(
                    '${item.name}  × ${item.quantity}',
                    style: const TextStyle(color: mimozaMaroon),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerRight,
                child: Text(
                  '${_formatMoney(order.total)} so‘m',
                  style: const TextStyle(
                    color: mimozaMaroon,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _textField({
    required TextEditingController controller,
    required String label,
    String? Function(String?)? validator,
    TextInputType? keyboardType,
    TextCapitalization textCapitalization = TextCapitalization.none,
    TextInputAction? textInputAction,
    bool obscureText = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        key: ValueKey('profile-field-$label'),
        controller: controller,
        validator: validator,
        keyboardType: keyboardType,
        textCapitalization: textCapitalization,
        textInputAction: textInputAction,
        obscureText: obscureText,
        decoration: InputDecoration(labelText: label),
      ),
    );
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_isRegistering) {
      await widget.accountController.register(
        fullName: _nameController.text.trim(),
        phone: _phoneController.text.trim(),
        email: _emailController.text.trim(),
        username: _usernameController.text.trim(),
        password: _passwordController.text,
        passwordConfirmation: _passwordConfirmationController.text,
      );
    } else {
      await widget.accountController.signIn(
        username: _usernameController.text.trim(),
        password: _passwordController.text,
      );
    }
  }

  Widget _errorMessage(String message) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF5B2630),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(message, style: const TextStyle(color: mimozaCream)),
    );
  }

  String? _requiredValidator(String? value) {
    if (value == null || value.trim().isEmpty) return 'Bu maydonni to‘ldiring.';
    return null;
  }

  String _formatDate(DateTime date) {
    final local = date.toLocal();
    final day = local.day.toString().padLeft(2, '0');
    final month = local.month.toString().padLeft(2, '0');
    return '$day.$month.${local.year}';
  }

  String _formatMoney(int amount) {
    return amount.toString().replaceAllMapped(
      RegExp(r'\B(?=(\d{3})+(?!\d))'),
      (_) => ' ',
    );
  }
}
