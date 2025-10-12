from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


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

class ProductCategory(models.TextChoices):
    PIECE = 'piece', 'Штучный'
    WEIGHT = 'weight', 'Весовой'


class Product(models.Model):
    # Убираем partner — товары создаёт только ADMIN
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=250, blank=True)

    category = models.CharField(max_length=10, choices=ProductCategory.choices, default=ProductCategory.PIECE)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    stock_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    is_bonus = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    suzerain_expense = models.ForeignKey(
        Expense,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='suzerain_products',
        limit_choices_to={'status': ExpenseStatus.SUZERAIN}
    )

    position = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        ordering = ['position', '-created_at']
        unique_together = [['name']]  # Убираем partner

    def __str__(self):
        return self.name

    def clean(self):
        if self.category == ProductCategory.WEIGHT and self.is_bonus:
            raise ValidationError("Весовой товар не может быть бонусным")

    def get_price_for_weight(self, weight_kg):
        if self.category != ProductCategory.WEIGHT:
            return self.price
        return (self.price / Decimal('10')) * (weight_kg / Decimal('0.1'))


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_images'
        ordering = ['position']

    def __str__(self):
        return f"Image {self.position} for {self.product.name}"


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

class BonusHistory(models.Model):
    """История бонусов партнёра-магазина"""
    partner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='bonus_given')
    store = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='bonus_received')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    bonus_count = models.IntegerField(default=0)  # Сколько бонусов дано
    date = models.DateField(auto_now_add=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bonus_history'
        ordering = ['-created_at']

    def __str__(self):
        return f"Bonus: {self.product.name} x{self.bonus_count} to {self.store.username}"


class StoreProductCounter(models.Model):
    """Счётчик товаров магазина (для бонусов каждый 21-й)"""
    store = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='product_counters')
    partner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='store_counters')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    total_count = models.IntegerField(default=0)  # Всего куплено
    bonus_eligible_count = models.IntegerField(default=0)  # Счётчик до бонуса (0-20)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_product_counters'
        unique_together = [['store', 'partner', 'product']]

    def __str__(self):
        return f"{self.store.username} - {self.product.name}: {self.bonus_eligible_count}/21"


# Добавить в конец models.py

# В products/models.py — обновляем DefectiveProduct

class DefectiveProduct(models.Model):
    """Брак товара (партнёр фиксирует)"""
    partner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='defective_products')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='defects')

    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    reason = models.TextField(blank=True)
    date = models.DateField(auto_now_add=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'defective_products'
        ordering = ['-created_at']

    def __str__(self):
        return f"Брак: {self.product.name} - {self.quantity} ({self.amount} сом)"

    def save(self, *args, **kwargs):
        if self.amount == 0 and self.product.category == 'weight':
            self.amount = self.product.get_price_for_weight(self.quantity)

        super().save(*args, **kwargs)

        if self.product.stock_quantity >= self.quantity:
            self.product.stock_quantity -= self.quantity
            self.product.save()