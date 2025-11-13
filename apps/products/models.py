from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.conf import settings

# ============= EXPENSES =============

class ExpenseType(models.TextChoices):
    PHYSICAL = 'physical', 'Физические'
    OVERHEAD = 'overhead', 'Накладные'


class ExpenseStatus(models.TextChoices):
    SUZERAIN = 'suzerain', 'Сюзерен'
    VASSAL = 'vassal', 'Вассал'
    CIVILIAN = 'civilian', 'Обыватель'


class ExpenseState(models.TextChoices):
    MECHANICAL = 'mechanical', 'Механическое'
    AUTOMATIC = 'automatic', 'Автоматическое'


class ExpenseApplyType(models.TextChoices):
    REGULAR = 'regular', 'Обычный'
    UNIVERSAL = 'universal', 'Универсальный'


class ExpenseUnit(models.TextChoices):
    PIECE = 'piece', 'Штука'
    KG = 'kg', 'Килограмм'
    GRAM = 'gram', 'Грамм'


class Expense(models.Model):
    """Расходы — только ADMIN управляет"""
    name = models.CharField(max_length=255)
    expense_type = models.CharField(max_length=20, choices=ExpenseType.choices)

    # Физические
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=10, choices=ExpenseUnit.choices, null=True, blank=True)

    # Накладные (месячная сумма)
    monthly_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=20, choices=ExpenseStatus.choices, default=ExpenseStatus.CIVILIAN)
    state = models.CharField(max_length=20, choices=ExpenseState.choices, default=ExpenseState.AUTOMATIC)
    apply_type = models.CharField(max_length=20, choices=ExpenseApplyType.choices, default=ExpenseApplyType.REGULAR)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expenses'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_expense_type_display()})"

    def clean(self):
        if self.expense_type == ExpenseType.PHYSICAL:
            if not self.price_per_unit or not self.unit:
                raise ValidationError("Физические расходы требуют цену и единицу измерения")

        if self.expense_type == ExpenseType.OVERHEAD:
            if not self.monthly_amount:
                raise ValidationError("Накладные расходы требуют месячную сумму")

    def save(self, *args, **kwargs):
        # ВАЖНО: Вассал ставится только для НЕ-Сюзеренов с механическим состоянием
        if self.state == ExpenseState.MECHANICAL and self.status != ExpenseStatus.SUZERAIN:
            self.status = ExpenseStatus.VASSAL

        super().save(*args, **kwargs)


# ============= PRODUCTS =============

class ProductCategory(models.Model):
    """Категория товаров"""
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Родительская категория'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'product_categories'
        verbose_name = 'Категория товаров'
        verbose_name_plural = 'Категории товаров'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    """
    Товар
    ИСПРАВЛЕНИЕ #12: Добавлена поддержка весовых товаров
    """
    UNIT_CHOICES = [
        ('kg', 'Килограмм'),
        ('piece', 'Штука'),
        ('liter', 'Литр'),
        ('pack', 'Упаковка'),
    ]

    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='Категория'
    )
    name = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')

    # ИСПРАВЛЕНИЕ #12: Весовые товары
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

    # Цена
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за единицу'
    )

    # Цена за 100г для весовых товаров
    price_per_100g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за 100г',
        help_text='Автоматически рассчитывается для весовых товаров'
    )

    # Себестоимость
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Себестоимость'
    )

    # Запасы (общий склад админа)
    stock_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество на складе'
    )

    # Статус
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    is_available = models.BooleanField(default=True, verbose_name='Доступен для заказа')

    # Изображение
    image = models.ImageField(
        upload_to='products/',
        null=True,
        blank=True,
        verbose_name='Изображение'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'products'
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active', 'is_available']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        """
        ИСПРАВЛЕНИЕ #12: Валидация весовых товаров
        """
        if self.is_weight_based:
            # Весовые товары должны быть в кг
            if self.unit != 'kg':
                raise ValidationError('Весовые товары должны иметь единицу измерения "Килограмм"')

            # Автоматический расчёт цены за 100г
            if self.price > 0:
                self.price_per_100g = self.price / Decimal('10')  # 1кг = 10 * 100г

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_unit_display_short(self):
        """Короткое отображение единицы"""
        return {
            'kg': 'кг',
            'piece': 'шт',
            'liter': 'л',
            'pack': 'уп',
        }.get(self.unit, self.unit)

    def validate_quantity(self, quantity: Decimal) -> bool:
        """
        ИСПРАВЛЕНИЕ #12: Валидация количества для весовых товаров
        """
        if self.is_weight_based:
            # Минимум 1кг
            if quantity < Decimal('1.0'):
                raise ValidationError(f'Минимальное количество для {self.name}: 1кг')

            # Шаг 0.1кг (100г)
            remainder = quantity % Decimal('0.1')
            if remainder != Decimal('0'):
                raise ValidationError(f'Количество должно быть кратно 0.1кг (100г)')

        return True

class ProductImage(models.Model):
    """Дополнительные изображения товара"""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name='Товар'
    )
    image = models.ImageField(upload_to='products/', verbose_name='Изображение')
    position = models.IntegerField(default=0, verbose_name='Порядок')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'product_images'
        ordering = ['position']
        verbose_name = 'Изображение товара'
        verbose_name_plural = 'Изображения товаров'

    def __str__(self):
        return f"Изображение {self.position} для {self.product.name}"


class ProductExpenseRelation(models.Model):
    """Связь товара с расходами (пропорции)"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='expense_relations')
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='product_relations')

    # Пропорция на единицу товара (в граммах/штуках)
    proportion = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_expense_relations'
        unique_together = [['product', 'expense']]

    def __str__(self):
        return f"{self.product.name} - {self.expense.name}: {self.proportion}"


# ============= PRODUCTION DATA =============

class ProductionRecord(models.Model):
    """Ежедневные данные производства (таблица из ТЗ)"""
    partner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='production_records')
    date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'production_records'
        unique_together = [['partner', 'date']]
        ordering = ['-date']

    def __str__(self):
        return f"Production {self.partner.username} - {self.date}"


class ProductionItem(models.Model):
    """Строка в таблице производства"""
    record = models.ForeignKey(ProductionRecord, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    # Ввод
    quantity_produced = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Количество товара
    suzerain_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Или объём Сюзерена

    # Расчёт
    ingredient_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Стоимость ингредиентов
    overhead_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Локальные расходы
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Общие расходы
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Себестоимость
    revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Доход
    net_profit = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Чистая прибыль

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'production_items'
        unique_together = [['record', 'product']]

    def __str__(self):
        return f"{self.product.name} - {self.record.date}"


class MechanicalExpenseEntry(models.Model):
    """Механический учёт расходов (ежедневный)"""
    record = models.ForeignKey(ProductionRecord, on_delete=models.CASCADE, related_name='mechanical_expenses')
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, limit_choices_to={'state': ExpenseState.MECHANICAL})

    amount_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Обед/Солярка

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mechanical_expense_entries'
        unique_together = [['record', 'expense']]

    def __str__(self):
        return f"{self.expense.name} - {self.record.date}: {self.amount_spent}"


# ============= BONUSES =============

class StoreProductCounter(models.Model):
    """
    ИСПРАВЛЕНИЕ #12: Счётчик товаров магазина для бонусов
    Каждый 21-й товар ВСЕГО (не по отдельности для каждого товара)
    """
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='product_counters',
        verbose_name='Магазин'
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'partner'},
        related_name='store_counters',
        verbose_name='Партнёр'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='store_counters',
        verbose_name='Товар'
    )

    # Общий счётчик для бонусов (все товары вместе)
    total_count = models.IntegerField(default=0, verbose_name='Всего куплено')

    # Счётчик конкретного товара
    product_count = models.IntegerField(default=0, verbose_name='Куплено этого товара')

    last_bonus_at = models.DateTimeField(null=True, blank=True, verbose_name='Последний бонус')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'store_product_counters'
        verbose_name = 'Счётчик товаров магазина'
        verbose_name_plural = 'Счётчики товаров магазинов'
        unique_together = ['store', 'partner', 'product']
        indexes = [
            models.Index(fields=['store', 'partner']),
        ]

    def __str__(self):
        return f"{self.store.name} - {self.product.name}: {self.total_count}/{self.product_count}"

    def check_bonus(self) -> bool:
        """
        ИСПРАВЛЕНИЕ #12: Проверка бонуса
        Каждый 21-й товар ВСЕГО бесплатно
        """
        # Весовые товары НЕ участвуют в бонусах
        if self.product.is_weight_based:
            return False

        # Каждый 21-й (21, 42, 63, ...)
        return self.total_count > 0 and self.total_count % 21 == 0


class BonusHistory(models.Model):
    """История выданных бонусов"""
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='bonus_history',
        verbose_name='Магазин'
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'partner'},
        related_name='bonus_history',
        verbose_name='Партнёр'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='bonus_history',
        verbose_name='Товар'
    )

    quantity = models.IntegerField(default=1, verbose_name='Количество бонусных единиц')
    bonus_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Стоимость бонуса'
    )

    # Привязка к заказу
    order = models.ForeignKey(
        'orders.StoreOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bonuses',
        verbose_name='Заказ'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'bonus_history'
        verbose_name = 'История бонусов'
        verbose_name_plural = 'История бонусов'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'partner']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Бонус для {self.store.name} - {self.product.name} x{self.quantity}"


class DefectiveProduct(models.Model):
    """Бракованные товары"""
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'partner'},
        related_name='defective_products',
        verbose_name='Партнёр'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='defects',
        verbose_name='Товар'
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
        choices=[('reported', 'Сообщено'), ('confirmed', 'Подтверждено'), ('rejected', 'Отклонено')],
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
        indexes = [
            models.Index(fields=['partner', 'status']),
        ]

    def __str__(self):
        return f"Брак: {self.product.name} x{self.quantity} ({self.status})"