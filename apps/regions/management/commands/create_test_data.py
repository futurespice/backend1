# apps/regions/management/commands/create_test_data.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from regions.models import Region, City
from stores.models import Store

User = get_user_model()


class Command(BaseCommand):
    help = 'Создать тестовые данные для системы'

    def handle(self, *args, **options):
        self.stdout.write('Создание тестовых данных...')

        # 1. Создаем регионы
        regions_data = [
            'Чуйская область',
            'Ошская область',
            'Иссык-Кульская область',
            'Нарынская область',
            'Таласская область',
            'Джалал-Абадская область',
            'Баткенская область'
        ]

        regions = {}
        for region_name in regions_data:
            region, created = Region.objects.get_or_create(name=region_name)
            regions[region_name] = region
            if created:
                self.stdout.write(f'✅ Создан регион: {region_name}')

        # 2. Создаем города
        cities_data = {
            'Чуйская область': ['Бишкек', 'Токмок', 'Кант', 'Сокулук'],
            'Ошская область': ['Ош', 'Узген', 'Кара-Суу'],
            'Иссык-Кульская область': ['Каракол', 'Балыкчы', 'Чолпон-Ата'],
            'Нарынская область': ['Нарын', 'Кочкор'],
            'Таласская область': ['Талас'],
            'Джалал-Абадская область': ['Джалал-Абад', 'Токтогул'],
            'Баткенская область': ['Баткен', 'Сулюкта']
        }

        for region_name, city_names in cities_data.items():
            region = regions[region_name]
            for city_name in city_names:
                city, created = City.objects.get_or_create(
                    name=city_name,
                    region=region
                )
                if created:
                    self.stdout.write(f'✅ Создан город: {city_name} ({region_name})')

        # 3. Создаем тестовых пользователей
        # Партнер
        if not User.objects.filter(email='partner@test.com').exists():
            partner = User.objects.create_user(
                email='partner@test.com',
                phone='+996555123456',
                name='Айбек',
                second_name='Партнеров',
                password='test123p!8Rt',  # С маркером партнера
                role='partner',
                is_approved=True
            )
            self.stdout.write('✅ Создан тестовый партнер: partner@test.com')

        # Пользователь-магазин
        if not User.objects.filter(email='store@test.com').exists():
            store_user = User.objects.create_user(
                email='store@test.com',
                phone='+996555123457',
                name='Бакыт',
                second_name='Магазинов',
                password='test123456',
                role='store',
                is_approved=True
            )
            self.stdout.write('✅ Создан тестовый пользователь магазина: store@test.com')

        # 4. Создаем тестовый магазин
        if not Store.objects.filter(inn='1234567890123').exists():
            partner = User.objects.get(email='partner@test.com')
            store_user = User.objects.get(email='store@test.com')
            bishkek_city = City.objects.get(name='Бишкек')

            store = Store.objects.create(
                owner=partner,
                user=store_user,
                name='Тестовый продуктовый магазин',
                inn='1234567890123',
                phone='+996312555777',
                region=bishkek_city.region,
                city=bishkek_city,
                address='ул. Чуй, 123',
                contact_name='Бакыт Магазинов',
                is_active=True
            )
            self.stdout.write('✅ Создан тестовый магазин: Тестовый продуктовый магазин')

        self.stdout.write(
            self.style.SUCCESS('\n🎉 Тестовые данные успешно созданы!')
        )
        self.stdout.write('\n📝 Данные для входа:')
        self.stdout.write('👨‍💼 Админ: admin@example.com / admin123')
        self.stdout.write('🤝 Партнер: partner@test.com / test123p!8Rt')
        self.stdout.write('🏪 Магазин: store@test.com / test123456')