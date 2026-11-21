from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Customer, ImportantDate


User = get_user_model()


class CustomerAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Foydalanuvchi nomi yoki parol noto‘g‘ri.',
        'inactive': 'Bu akkaunt faol emas.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Foydalanuvchi nomi'
        self.fields['username'].error_messages['required'] = 'Foydalanuvchi nomini kiriting.'
        self.fields['username'].widget.attrs.update({'placeholder': 'Foydalanuvchi nomini kiriting'})
        self.fields['password'].label = 'Parol'
        self.fields['password'].error_messages['required'] = 'Parolni kiriting.'
        self.fields['password'].widget.attrs.update({'placeholder': 'Parolingizni kiriting'})


class CustomerRegistrationForm(UserCreationForm):
    error_messages = {
        **UserCreationForm.error_messages,
        'password_mismatch': 'Kiritilgan parollar bir-biriga mos emas.',
    }

    full_name = forms.CharField(label='Ism va familiya', max_length=150)
    phone = forms.CharField(label='Telefon raqam', max_length=30)
    email = forms.EmailField(label='Elektron pochta', required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(('full_name', 'phone', 'email', 'username', 'password1', 'password2'))
        self.fields['username'].label = 'Foydalanuvchi nomi'
        self.fields['username'].help_text = 'Faqat harf, raqam va @/./+/-/_ belgilaridan foydalaning.'
        self.fields['username'].error_messages['unique'] = 'Bu foydalanuvchi nomi band.'
        self.fields['username'].error_messages['invalid'] = 'Foydalanuvchi nomida ruxsat etilmagan belgi bor.'
        self.fields['full_name'].widget.attrs.update({'placeholder': 'Ism va familiyangiz'})
        self.fields['phone'].widget.attrs.update({'placeholder': '+998'})
        self.fields['email'].widget.attrs.update({'placeholder': 'email@example.com'})
        for field in self.fields.values():
            field.error_messages['required'] = 'Bu maydonni to‘ldirish shart.'
        self.fields['email'].error_messages['invalid'] = 'Elektron pochta manzilini to‘g‘ri kiriting.'
        self.fields['password1'].label = 'Parol'
        self.fields['password1'].help_text = 'Kamida 8 ta belgi kiriting; keng tarqalgan parollardan foydalanmang.'
        self.fields['password2'].label = 'Parolni tasdiqlang'
        self.fields['password2'].help_text = 'Tasdiqlash uchun parolni qayta kiriting.'

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError(self.error_messages['password_mismatch'], code='password_mismatch')
        if password2:
            try:
                validate_password(password2, self.instance)
            except ValidationError as error:
                translations = {
                    'password_too_short': 'Parol juda qisqa; kamida 8 ta belgi kiriting.',
                    'password_too_common': 'Bu parol juda keng tarqalgan. Boshqa parol tanlang.',
                    'password_entirely_numeric': 'Parol faqat raqamlardan iborat bo‘lmasligi kerak.',
                    'password_too_similar': 'Parol foydalanuvchi ma’lumotlariga juda o‘xshash.',
                }
                raise ValidationError([
                    ValidationError(translations.get(item.code, 'Parol xavfsizlik talablariga mos emas.'),
                                    code=item.code)
                    for item in error.error_list
                ])
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data['full_name'].strip()
        first_name, _, last_name = full_name.partition(' ')
        user.first_name = first_name
        user.last_name = last_name
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            Customer.objects.create(
                user=user,
                name=full_name,
                phone=self.cleaned_data['phone'].strip(),
                email=user.email,
            )
        return user


class ImportantDateForm(forms.ModelForm):
    class Meta:
        model = ImportantDate
        fields = ('label', 'date', 'reminder_enabled')
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }
