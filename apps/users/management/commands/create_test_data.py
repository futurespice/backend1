# apps/users/management/commands/create_test_data.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from decimal import Decimal
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Создание тестовых данных для B2B системы'

    def handle(self, *args, **options):
        self.stdout.write('Создание тестовых данных...')

        # Создаём регионы
        from apps.regions.models import Region

        # Страна
        kyrgyzstan = Region.objects.create(
            name='Кыргызстан',
            code='KG',
            region_type='country'
        )

        # Области
        bishkek_city = Region.objects.create(
            name='г. Бишкек',
            code='01',
            region_type='city',
            parent=kyrgyzstan,
            latitude=Decimal('42.874621'),
            longitude=Decimal('74.569762')
        )

        chui_oblast = Region.objects.create(
            name='Чуйская область',
            code='02',
            region_type='oblast',
            parent=kyrgyzstan
        )

        # Города
        tokmok = Region.objects.create(
            name='Токмок',
            code='0201',
            region_type='city',
            parent=chui_oblast
        )

        # Создаём категории товаров
        from apps.products.models import Category, Product

        meat_category = Category.objects.create(
            name='Мясные изделия',
            description='Полуфабрикаты и мясные продукты'
        )

        frozen_category = Category.objects.create(
            name='Замороженные продукты',
            description='Пельмени, хинкали и другие замороженные изделия',
            parent=meat_category
        )

        # Создаём товары
        chicken = Product.objects.create(
            name='Курица сырая',
            description='Охлаждённая курица',
            category=meat_category,
            price=Decimal('450.00'),
            unit='kg',
            stock_quantity=Decimal('100.000')
        )

        pelmeni_red = Product.objects.create(
            name='Пельмени Красные',
            description='Пельмени с мясной начинкой',
            category=frozen_category,
            price=Decimal('450.00'),
            unit='pcs',
            min_order_quantity=Decimal('5'),
            stock_quantity=Decimal('545.000')
        )

        pelmeni_green = Product.objects.create(
            name='Зеленые Красные',
            description='Пельмени с зеленой начинкой',
            category=frozen_category,
            price=Decimal('450.00'),
            unit='pcs',
            min_order_quantity=Decimal('5'),
            stock_quantity=Decimal('545.000')
        )

        # Создаём пользователей

        # Админ
        admin = User.objects.create_user(
            email='admin@test.com',
            password='admin123',
            name='Администратор',
            second_name='Системы',
            phone='+996555000001',
            role='admin',
            is_approved=True
        )

        # Партнёры
        partner1 = User.objects.create_user(
            email='partner1@test.com',
            password='P@rtner2024!partner123',  # Пароль с маркером
            name='Бакиров',
            second_name='Эмир',
            phone='+996999888777',
            role='partner',
            is_approved=True
        )

        partner2 = User.objects.create_user(
            email='partner2@test.com',
            password='P@rtner2024!partner456',
            name='Иванов',
            second_name='Петр',
            phone='+996555123456',
            role='partner',
            is_approved=True
        )

        # Магазины (пользователи)
        store_user1 = User.objects.create_user(
            email='store1@test.com',
            password='St0re2024!store123',  # Пароль с маркером
            name='Сыдыков',
            second_name='Тариэл',
            phone='+996777111222',
            role='store',
            is_approved=True
        )

        store_user2 = User.objects.create_user(
            email='store2@test.com',
            password='St0re2024!store456',
            name='Ахметов',
            second_name='Бакыт',
            phone='+996555987654',
            role='store',
            is_approved=True
        )

        # Создаём магазины
        from apps.stores.models import Store, StoreInventory

        store1 = Store.objects.create(
            user=store_user1,
            store_name='БайЭл',
            address='ул. Манаса 125, Бишкек',
            region=bishkek_city,
            partner=partner1,
            latitude=Decimal('42.876046'),
            longitude=Decimal('74.588204')
        )

        store2 = Store.objects.create(
            user=store_user2,
            store_name='2 Ак терек',
            address='ул. Советская 45, Токмок',
            region=tokmok,
            partner=partner1
        )

        # Создаём остатки товаров в магазинах
        StoreInventory.objects.create(
            store=store1,
            product=chicken,
            quantity=Decimal('1.000')
        )

        StoreInventory.objects.create(
            store=store1,
            product=pelmeni_red,
            quantity=Decimal('545.000')
        )

        StoreInventory.objects.create(
            store=store2,
            product=pelmeni_green,
            quantity=Decimal('545.000')
        )

        # Создаём правила бонусов
        from apps.bonuses.models import BonusRule

        BonusRule.objects.create(
            name='Каждый 21-й товар бесплатно',
            description='Стандартное правило - каждый 21-й товар получается бесплатно',
            every_nth_free=21,
            applies_to_all_products=True,
            is_active=True
        )

        # Создаём тестовые заказы
        from apps.orders.models import Order, OrderItem

        order1 = Order.objects.create(
            store=store1,
            partner=partner1,
            payment_amount=Decimal('300.00'),
            notes='Тестовый заказ'
        )

        # Позиции заказа
        OrderItem.objects.create(
            order=order1,
            product=chicken,
            quantity=Decimal('2.000'),
            unit_price=chicken.price
        )

        OrderItem.objects.create(
            order=order1,
            product=pelmeni_red,
            quantity=Decimal('10.000'),
            unit_price=pelmeni_red.price
        )

        # Рассчитываем итоги заказа
        order1.calculate_totals()

        # Создаём долг
        from apps.debts.models import Debt
        from django.utils import timezone
        from datetime import timedelta

        if order1.debt_amount > 0:
            Debt.objects.create(
                store=store1,
                order=order1,
                amount=order1.debt_amount,
                description=f'Долг по заказу #{order1.id}',
                due_date=timezone.now().date() + timedelta(days=30)
            )

        # Создаём расширенную структуру расходов на основе требований заказчика
        from apps.cost_accounting.models import Expense, BillOfMaterial, BOMLine

        # Месячные расходы (фиксированные)
        monthly_expenses = [
            ('Аренда помещения', 35000, 'overhead'),
            ('Электричество', 25000, 'overhead'),
            ('Налоги', 45000, 'overhead'),
            ('Уборщица', 12000, 'labor'),
            ('Админ', 5000, 'labor'),
            ('Холодильник (обслуживание)', 5000, 'overhead'),
            ('Упаковка', 36000, 'packaging'),
            ('Фарш (перемешивание)', 6000, 'labor'),
            ('Лук (очистка)', 25000, 'labor'),
        ]

        for name, price, exp_type in monthly_expenses:
            expense, created = Expense.objects.get_or_create(
                name=name,
                defaults={
                    'expense_type': exp_type,
                    'unit': 'monthly',
                    'price_per_unit': Decimal(str(price))
                }
            )

        # Ежедневные расходы сырья
        daily_raw_materials = [
            ('Мука (3 мешка)', 5700, 'kg', 'raw_material'),
            ('Соль (3 пачки)', 90, 'pcs', 'raw_material'),
            ('Яйца', 400, 'pcs', 'raw_material'),
            ('Мука (обработка)', 1500, 'daily', 'labor'),
            ('Фарш говяжий', 270, 'kg', 'raw_material'),  # 105кг * 270сом
            ('Лук репчатый', 4200, 'kg', 'raw_material'),
            ('Зарплата упаковщиц', 12000, 'daily', 'labor'),
            ('Пакеты для упаковки', 4.5, 'pcs', 'packaging'),
            ('Приправы', 5, 'pcs', 'raw_material'),
            ('Зарплата водителей (6 чел)', 1700, 'person', 'labor'),
            ('Солярка (3 машины)', 2000, 'machine', 'overhead'),
            ('Обед водителям', 600, 'machine', 'overhead'),
        ]

        for name, price, unit, exp_type in daily_raw_materials:
            expense, created = Expense.objects.get_or_create(
                name=name,
                defaults={
                    'expense_type': exp_type,
                    'unit': unit,
                    'price_per_unit': Decimal(str(price))
                }
            )

        # Расходы для теста отдельно
        dough_expenses = [
            ('Мука для теста (4 мешка)', 2500, 'bag', 'raw_material'),
            ('Работа тестомеса', 2000, 'daily', 'labor'),
            ('Масло растительное', 8000, 'l', 'raw_material'),
            ('Упаковочная бумага', 5, 'pcs', 'packaging'),
            ('Упаковка теста', 1000, 'daily', 'labor'),
        ]

        for name, price, unit, exp_type in dough_expenses:
            expense, created = Expense.objects.get_or_create(
                name=name,
                defaults={
                    'expense_type': exp_type,
                    'unit': unit,
                    'price_per_unit': Decimal(str(price))
                }
            )

        # Расходы для пельменей "апарат"
        aparaт_expenses = [
            ('Фарш для апарат (4 пакета)', 6480, 'batch', 'raw_material'),
            ('Соль и яйца (апарат)', 500, 'batch', 'raw_material'),
            ('Работа (апарат)', 1200, 'batch', 'labor'),
            ('Мука (апарат)', 2500, 'batch', 'raw_material'),
            ('Пакеты (апарат)', 4, 'pcs', 'packaging'),
            ('Картофель', 600, 'kg', 'raw_material'),
            ('Лук (апарат)', 1400, 'kg', 'raw_material'),
        ]

        for name, price, unit, exp_type in aparaт_expenses:
            expense, created = Expense.objects.get_or_create(
                name=name,
                defaults={
                    'expense_type': exp_type,
                    'unit': unit,
                    'price_per_unit': Decimal(str(price))
                }
            )

        # Создаём BOM для пельменей
        pelmeni_bom = BillOfMaterial.objects.create(
            product=pelmeni_red,
            version=1,
            notes='Рецепт красных пельменей'
        )

        # Строки BOM
        BOMLine.objects.create(
            bom=pelmeni_bom,
            expense=flour_expense,
            quantity=Decimal('0.500'),  # 500г муки на 1 порцию
            unit='kg',
            is_primary=True  # Мука - основной ингредиент
        )

        BOMLine.objects.create(
            bom=pelmeni_bom,
            expense=meat_expense,
            quantity=Decimal('0.300'),  # 300г фарша на 1 порцию
            unit='kg'
        )

        BOMLine.objects.create(
            bom=pelmeni_bom,
            expense=salt_expense,
            quantity=Decimal('0.010'),  # 10г соли на 1 порцию
            unit='kg'
        )

        self.stdout.write(
            self.style.SUCCESS('Тестовые данные успешно созданы!')
        )

        # Выводим информацию о созданных данных
        self.stdout.write('\nСозданные пользователи:')
        self.stdout.write(f'  Админ: admin@test.com / admin123')
        self.stdout.write(f'  Партнёр 1: partner1@test.com / P@rtner2024!partner123')
        self.stdout.write(f'  Партнёр 2: partner2@test.com / P@rtner2024!partner456')
        self.stdout.write(f'  Магазин 1: store1@test.com / St0re2024!store123')
        self.stdout.write(f'  Магазин 2: store2@test.com / St0re2024!store456')

        self.stdout.write('\nСозданные магазины:')
        self.stdout.write(f'  {store1.store_name} - {store1.address}')
        self.stdout.write(f'  {store2.store_name} - {store2.address}')

        self.stdout.write('\nСозданные товары:')
        self.stdout.write(f'  {chicken.name} - {chicken.price} сом/{chicken.unit}')
        self.stdout.write(f'  {pelmeni_red.name} - {pelmeni_red.price} сом/{pelmeni_red.unit}')
        self.stdout.write(f'  {pelmeni_green.name} - {pelmeni_green.price} сом/{pelmeni_green.unit}')

        self.stdout.write(f'\nСоздан тестовый заказ #{order1.id} на сумму {order1.total_amount} сом')
        if order1.debt_amount > 0:
            self.stdout.write(f'Создан долг на сумму {order1.debt_amount} сом')

        self.stdout.write('\nAPI доступно по адресу: http://localhost:8000/api/')
        self.stdout.write('Документация API: http://localhost:8000/api/docs/')