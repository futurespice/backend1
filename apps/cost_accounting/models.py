from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils import timezone


class Expense(models.Model):
    """Расходы для расчёта себестоимости"""

    EXPENSE_TYPES = [
        ('raw_material', 'Сырьё'),
        ('labor', 'Труд'),
        ('overhead', 'Накладные расходы'),
        ('packaging', 'Упаковка'),
        ('transport', 'Транспорт'),
    ]

    UNITS = [
        ('kg', 'кг'),
        ('pcs', 'шт'),
        ('monthly', 'в месяц'),
        ('daily', 'в день'),
        ('hourly', 'в час'),
    ]

    name = models.CharField(max_length=200, verbose_name='Название')
    expense_type = models.CharField(
        max_length=20,
        choices=EXPENSE_TYPES,
        default='raw_material',
        verbose_name='Тип расхода'
    )
    unit = models.CharField(
        max_length=20,
        choices=UNITS,
        default='kg',
        verbose_name='Единица измерения'
    )
    price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за единицу'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    notes = models.TextField(blank=True, verbose_name='Примечания')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        db_table = 'expenses'
        verbose_name = 'Расход'
        verbose_name_plural = 'Расходы'
        ordering = ['expense_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.price_per_unit} сом/{self.unit})"


# Остальные модели оставляем как есть, но упрощенные
class ProductExpense(models.Model):
    """Связь товар-расход"""

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='cost_expenses'
    )
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name='product_links'
    )
    quantity_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество на единицу товара'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'product_expenses'
        unique_together = ['product', 'expense']
        verbose_name = 'Расход товара'
        verbose_name_plural = 'Расходы товаров'

    def __str__(self):
        return f"{self.product.name} - {self.expense.name}"


class DailyExpenseLog(models.Model):
    """Ежедневные логи расходов"""

    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name='daily_logs'
    )
    date = models.DateField(default=timezone.now)
    quantity_used = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))]
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0')
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'daily_expense_logs'
        unique_together = ['expense', 'date']
        verbose_name = 'Дневной лог расходов'
        verbose_name_plural = 'Дневные логи расходов'


class ProductionBatch(models.Model):
    """Производственная партия"""

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='production_batches'
    )
    date = models.DateField(default=timezone.now)
    quantity_produced = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))]
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0')
    )
    cost_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0')
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('planned', 'Запланирована'),
            ('in_progress', 'В производстве'),
            ('completed', 'Завершена'),
        ],
        default='planned'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'production_batches'
        unique_together = ['product', 'date']
        verbose_name = 'Производственная партия'
        verbose_name_plural = 'Производственные партии'


class MonthlyOverheadBudget(models.Model):
    """Месячный бюджет накладных расходов"""

    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE
    )
    planned_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    actual_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0')
    )

    class Meta:
        db_table = 'monthly_overhead_budgets'
        unique_together = ['year', 'month', 'expense']


class BillOfMaterial(models.Model):
    """Спецификация (рецептура) товара"""

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='bom_specs'
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    output_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('1')
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bill_of_materials'
        verbose_name = 'Спецификация'
        verbose_name_plural = 'Спецификации'


class BOMLine(models.Model):
    """Строка спецификации"""

    bom = models.ForeignKey(
        BillOfMaterial,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))]
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'bom_lines'
        verbose_name = 'Строка спецификации'
        verbose_name_plural = 'Строки спецификаций'