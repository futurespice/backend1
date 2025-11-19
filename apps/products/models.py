# apps/products/models.py - ВРЕМЕННАЯ ВЕРСИЯ для создания миграций

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.conf import settings
from django.db.models.functions import Coalesce
from django.db.models import Sum
from django.utils import timezone



class Expense(models.Model):
    """Расходы (физические и накладные)"""
    EXPENSE_TYPE_CHOICES = [
        ('physical', 'Физические'),
        ('overhead', 'Накладные'),
    ]

    STATUS_CHOICES = [
        ('suzerain', 'Сюзерен'),
        ('vassal', 'Вассал'),
        ('civilian', 'Обыватель'),
    ]

    STATE_CHOICES = [
        ('mechanical', 'Механическое'),
        ('automatic', 'Автоматическое'),
    ]

    APPLY_TYPE_CHOICES = [
        ('regular', 'Обычный'),
        ('universal', 'Универсальный'),
    ]

    name = models.CharField(max_length=255)
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPE_CHOICES)

    # Для физических расходов
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=10, choices=[
        ('piece', 'Штука'),
        ('kg', 'Килограмм'),
        ('gram', 'Грамм'),
    ], null=True, blank=True)

    # Для накладных расходов
    monthly_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='civilian')
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default='automatic')
    apply_type = models.CharField(max_length=20, choices=APPLY_TYPE_CHOICES, default='regular')

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expenses'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Product(models.Model):
    """Товары"""
    UNIT_CHOICES = [
        ('kg', 'Килограмм'),
        ('piece', 'Штука'),
        ('liter', 'Литр'),
        ('pack', 'Упаковка'),
    ]

    name = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')

    is_weight_based = models.BooleanField(
        default=False,
        verbose_name='Весовой товар',
        help_text='Продаётся на вес с шагом 0.1кг (минимум 1кг)'
    )
    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default='piece',
        verbose_name='Единица измерения'
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за единицу'
    )
    price_per_100g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за 100г',
        help_text='Автоматически рассчитывается для весовых товаров'
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Себестоимость'
    )

    stock_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество на складе'
    )

    is_active = models.BooleanField(default=True, verbose_name='Активен')
    is_available = models.BooleanField(default=True, verbose_name='Доступен для заказа')

    image = models.ImageField(upload_to='products/', null=True, blank=True, verbose_name='Изображение')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    popularity_weight = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal('1.000000'),
        validators=[MinValueValidator(Decimal('0.0001'))],
        verbose_name='Коэффициент популярности',
        help_text='Чем выше — тем больше накладных расходов несёт товар (по продажам за 90 дней)'
    )

    class Meta:
        db_table = 'products'
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    def update_popularity_weight(self) -> None:
        """
        Автоматическое обновление коэффициента популярности.
        Вызывать ежедневно (Celery beat / management command).
        """
        from orders.models import StoreOrderItem  # Импорт здесь, чтобы избежать циклического импорта

        ninety_days_ago = timezone.now() - timezone.timedelta(days=90)

        sales_qty: Decimal = (
            StoreOrderItem.objects
            .filter(
                product=self,
                order__status='completed',
                order__created_at__gte=ninety_days_ago,
                is_bonus=False
            )
            .aggregate(total=Coalesce(Sum('quantity'), Decimal('0')))['total']
        )

        # Формула: 1.0 + (продано за 90 дней / 1000)
        # Можно менять под бизнес-логику
        weight = Decimal('1.0') + (sales_qty / Decimal('1000'))
        weight = min(weight, Decimal('10.0'))  # Ограничение сверху

        self.popularity_weight = weight.quantize(Decimal('0.000001'))
        self.save(update_fields=['popularity_weight'])


class ProductImage(models.Model):
    """Дополнительные изображения товара"""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name='Товар',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    image = models.ImageField(upload_to='products/', verbose_name='Изображение')
    position = models.IntegerField(default=0, verbose_name='Порядок')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'product_images'
        verbose_name = 'Изображение товара'
        verbose_name_plural = 'Изображения товаров'
        ordering = ['position']

    def __str__(self):
        return f"Image {self.position} for {self.product.name if self.product else 'Unknown'}"


class ProductExpenseRelation(models.Model):
    """Связь товара с расходами"""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='expense_relations',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name='product_relations',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    proportion = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_expense_relations'
        unique_together = [['product', 'expense']]

    def __str__(self):
        return f"{self.product} - {self.expense}"


class ProductionRecord(models.Model):
    """Учётная запись производства за день"""
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='production_records',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'production_records'
        ordering = ['-date']
        unique_together = [['partner', 'date']]

    def __str__(self):
        return f"Production {self.date}"


class ProductionItem(models.Model):
    """Позиция в производственной записи"""
    record = models.ForeignKey(
        ProductionRecord,
        on_delete=models.CASCADE,
        related_name='items',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )

    quantity_produced = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    suzerain_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    ingredient_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    overhead_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_profit = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'production_items'
        unique_together = [['record', 'product']]


class MechanicalExpenseEntry(models.Model):
    """Механический учёт расходов"""
    record = models.ForeignKey(
        ProductionRecord,
        on_delete=models.CASCADE,
        related_name='mechanical_expenses',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        limit_choices_to={'state': 'mechanical'},
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    amount_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mechanical_expense_entries'
        unique_together = [['record', 'expense']]


class BonusHistory(models.Model):
    """История начисления бонусов"""
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='bonus_history',
        verbose_name='Магазин',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bonus_history',
        verbose_name='Партнёр',
        limit_choices_to={'role': 'partner'},
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='bonus_history',
        verbose_name='Товар',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    order = models.ForeignKey(
        'orders.StoreOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bonuses',
        verbose_name='Заказ'
    )
    quantity = models.IntegerField(default=1, verbose_name='Количество бонусных единиц')
    bonus_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Стоимость бонуса'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'bonus_history'
        verbose_name = 'История бонусов'
        verbose_name_plural = 'История бонусов'
        ordering = ['-created_at']


class StoreProductCounter(models.Model):
    """Счётчик товаров для бонусной системы"""
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='product_counters',
        verbose_name='Магазин',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='store_counters',
        verbose_name='Партнёр',
        limit_choices_to={'role': 'partner'},
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='store_counters',
        verbose_name='Товар',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )

    total_count = models.IntegerField(default=0, verbose_name='Всего куплено')
    product_count = models.IntegerField(default=0, verbose_name='Куплено этого товара')
    last_bonus_at = models.DateTimeField(null=True, blank=True, verbose_name='Последний бонус')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'store_product_counters'
        verbose_name = 'Счётчик товаров магазина'
        verbose_name_plural = 'Счётчики товаров магазинов'
        unique_together = [['store', 'partner', 'product']]

    def check_bonus(self):
        """Проверка доступности бонуса"""
        return self.total_count > 0 and self.total_count % 21 == 0


class DefectiveProduct(models.Model):
    """Бракованные товары"""
    STATUS_CHOICES = [
        ('reported', 'Сообщено'),
        ('confirmed', 'Подтверждено'),
        ('rejected', 'Отклонено'),
    ]

    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='defective_products',
        verbose_name='Партнёр',
        limit_choices_to={'role': 'partner'},
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='defects',
        verbose_name='Товар',
        null=True,  # ВРЕМЕННО для миграции
        blank=True
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.1'))],
        verbose_name='Количество'
    )
    reason = models.TextField(verbose_name='Причина брака')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='reported',
        verbose_name='Статус'
    )
    reported_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата сообщения')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата решения')

    class Meta:
        db_table = 'defective_products'
        verbose_name = 'Бракованный товар'
        verbose_name_plural = 'Бракованные товары'
        ordering = ['-reported_at']

    def __str__(self):
        return f"Defect: {self.product} - {self.quantity}"