from django.core.management.base import BaseCommand

from mimoza.models import Category, Product


class Command(BaseCommand):
    help = 'Mimoza demo categoriyalari va mahsulotlarini qo‘shadi'

    def handle(self, *args, **options):
        categories = [
            ('Romantika', 'romantika'),
            ('Tug‘ilgan kun', 'tugilgan-kun'),
            ('To‘ylar', 'to-ylar'),
            ('VIP to‘plamlar', 'vip'),
        ]
        category_objects = {}
        for name, slug in categories:
            category_objects[slug], _ = Category.objects.get_or_create(
                slug=slug,
                defaults={'name': name},
            )

        products = [
            ('101 qizil atirgul', '101-qizil-atirgul', 'romantika', 850000, 'https://images.unsplash.com/photo-1518895949257-7621c3c786d7?auto=format&fit=crop&w=900&q=85'),
            ('Pushti peoniyalar', 'pushti-peoniyalar', 'romantika', 690000, 'https://images.unsplash.com/photo-1490750967868-88aa4486c946?auto=format&fit=crop&w=900&q=85'),
            ('Oq atirgullar buketi', 'oq-atirgullar-buketi', 'vip', 1200000, 'https://images.unsplash.com/photo-1487530811176-3780de880c2d?auto=format&fit=crop&w=900&q=85'),
            ('Bayramga hashamatli buket', 'bayramga-hashamatli-buket', 'tugilgan-kun', 540000, 'https://images.unsplash.com/photo-1526047932273-341f2a7631f9?auto=format&fit=crop&w=900&q=85'),
            ('To‘y kolleksiyasi', 'toy-kolleksiyasi', 'to-ylar', 2100000, 'https://images.unsplash.com/photo-1520763185298-1b434c919102?auto=format&fit=crop&w=900&q=85'),
            ('Pastel aralash buket', 'pastel-aralash-buket', 'vip', 780000, 'https://images.unsplash.com/photo-1494972308805-463bc619d34e?auto=format&fit=crop&w=900&q=85'),
        ]
        for index, (name, slug, category_slug, price, image_url) in enumerate(products):
            Product.objects.update_or_create(
                slug=slug,
                defaults={
                    'name': name,
                    'category': category_objects[category_slug],
                    'description': 'Yangi mavsum gullaridan tayyorlangan nafis buket.',
                    'price': price,
                    'image_url': image_url,
                    'video': '',
                    'video_url': '',
                    'in_stock': True,
                    'stock_quantity': 20,
                    'is_featured': index < 4,
                },
            )
        self.stdout.write(self.style.SUCCESS('Demo katalog muvaffaqiyatli qo‘shildi'))
