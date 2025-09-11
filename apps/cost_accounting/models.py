from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class Expense(models.Model):
    """Расходы для себестоимости"""

    EXPENSE_TYPES = [
        ('raw_material', 'Сырье'),
        ('labor', 'Оплата труда'),
        ('overhead', 'Накладные расходы'),
        ('packaging', 'Упаковка'),
        ('delivery', 'Доставка'),
        ('utilities', 'Коммунальные услуги'),
        ('rent', 'Аренда'),
        ('taxes', 'Налоги'),
        ('fuel', 'Топливо'),
        ('equipment', 'Оборудование'),
    ]

    PERIOD_TYPES = [
        ('daily', 'Ежедневно'),
        ('monthly', 'Ежемесячно'),
        ('per_unit', 'За единицу'),
        ('per_batch', 'За партию'),
    ]

    name = models.CharField(max_length=200, verbose_name='Название расхода')
    expense_type = models.CharField(
        max_length=20,
        choices=EXPENSE_TYPES,
        verbose_name='Тип расхода'
    )

    # Единица измерения с учетом специфики бизнеса
    UNIT_CHOICES = [
        ('kg', 'кг'),
        ('g', 'г'),
        ('l', 'л'),
        ('pcs', 'шт'),
        ('bag', 'мешок'),
        ('pack', 'пачка'),
        ('batch', 'партия'),
        ('person', 'человек'),
        ('machine', 'машина'),
        ('daily', 'в день'),
        ('monthly', 'в месяц'),
        ('hour', 'час'),
    ]

    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        verbose_name='Единица измерения'
    )

    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Цена за единицу'
    )

    # Периодичность расхода
    period_type = models.CharField(
        max_length=20,
        choices=PERIOD_TYPES,
        default='per_unit',
        verbose_name='Периодичность'
    )

    # Для месячных расходов - количество дней в месяце
    days_per_month = models.PositiveIntegerField(
        default=30,
        verbose_name='Дней в месяце'
    )

    is_active = models.BooleanField(default=True, verbose_name='Активен')
    notes = models.TextField(blank=True, verbose_name='Примечания')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'expenses'
        verbose_name = 'Расход'
        verbose_name_plural = 'Расходы'
        ordering = ['expense_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.price_per_unit} сом/{self.unit})"

    def get_daily_cost(self, quantity=1):
        """Получить ежедневную стоимость расхода"""
        base_cost = self.price_per_unit * Decimal(str(quantity))

        if self.period_type == 'daily':
            return base_cost
        elif self.period_type == 'monthly':
            return base_cost / self.days_per_month
        else:
            return base_cost


class ProductExpense(models.Model):
    """
    Связь товар ↔ расход с пропорцией.
    Для физических: сколько единиц расхода на 1 единицу товара
    Для накладных: коэффициент распределения
    """
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name="cost_expenses"
    )
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name="product_links"
    )

    # Пропорция: единиц расхода на 1 единицу товара
    ratio_per_product_unit = models.DecimalField(
        max_digits=14, decimal_places=6,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Единиц расхода на 1 ед. товара"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_expenses'
        unique_together = ("product", "expense")
        verbose_name = 'Расход товара'
        verbose_name_plural = 'Расходы товаров'

    def __str__(self):
        return f"{self.product} ← {self.expense} ({self.ratio_per_product_unit})"


class BillOfMaterial(models.Model):
    """
    Спецификация товара - многоуровневая BOM система.
    Товар может состоять из других товаров (полуфабрикатов) И расходов.
    """
    product = models.OneToOneField(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='bom_specification',
        verbose_name='Продукт'
    )
    version = models.PositiveIntegerField(default=1, verbose_name='Версия')
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    notes = models.TextField(blank=True, verbose_name='Примечания')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bill_of_materials'
        verbose_name = 'Спецификация (BOM)'
        verbose_name_plural = 'Спецификации (BOM)'

    def __str__(self):
        return f"BOM: {self.product.name} v{self.version}"


class BOMLine(models.Model):
    """
    Строка спецификации - может быть:
    1. Сырьевой расход (мука, соль, фарш)
    2. Компонент-продукт (готовое тесто для пельменей)
    """

    class Unit(models.TextChoices):
        KG = 'kg', 'кг'
        PCS = 'pcs', 'шт'

    bom = models.ForeignKey(
        BillOfMaterial,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Спецификация'
    )

    # Либо расход, либо компонент-продукт (взаимоисключающие)
    expense = models.ForeignKey(
        Expense,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='used_in_bom_lines',
        verbose_name='Расход (ингредиент)'
    )
    component_product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='used_as_component_lines',
        verbose_name='Компонент-продукт'
    )

    # Количество на 1 единицу целевого продукта
    quantity = models.DecimalField(
        max_digits=12, decimal_places=6,
        validators=[MinValueValidator(Decimal('0.000001'))],
        verbose_name='Количество на 1 ед. продукта'
    )
    unit = models.CharField(
        max_length=8,
        choices=Unit.choices,
        verbose_name='Единица измерения'
    )

    # Особая роль - "Сюзерен" (главный ингредиент для расчетов)
    is_primary = models.BooleanField(
        default=False,
        verbose_name='Сюзерен (главный для расчетов)'
    )

    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    notes = models.TextField(blank=True, verbose_name='Примечания')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bom_lines'
        verbose_name = 'Строка спецификации'
        verbose_name_plural = 'Строки спецификаций'
        ordering = ['order', 'id']
        constraints = [
            # Ровно одно из двух полей должно быть заполнено
            models.CheckConstraint(
                name='bomline_one_of_component',
                check=(
                        models.Q(expense__isnull=False, component_product__isnull=True) |
                        models.Q(expense__isnull=True, component_product__isnull=False)
                )
            ),
            # Только один "Сюзерен" на BOM
            models.UniqueConstraint(
                fields=['bom'],
                condition=models.Q(is_primary=True),
                name='bomline_single_primary_per_bom'
            )
        ]

    def clean(self):
        errors = {}

        # Проверка: ровно одно из полей expense/component_product
        has_expense = bool(self.expense_id)
        has_component = bool(self.component_product_id)
        if has_expense == has_component:
            errors['expense'] = 'Укажите либо расход, либо компонент-продукт'
            errors['component_product'] = 'Укажите либо расход, либо компонент-продукт'

        # Проверка количества
        if self.quantity is None or self.quantity <= 0:
            errors['quantity'] = 'Количество должно быть больше 0'

        # Запрет циклических ссылок
        if (self.component_product_id and self.bom_id and
                self.bom.product_id == self.component_product_id):
            errors['component_product'] = 'Товар не может быть компонентом самого себя'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.expense:
            component = f"Расход: {self.expense.name}"
        else:
            component = f"Продукт: {self.component_product.name}"

        primary_mark = " [Сюзерен]" if self.is_primary else ""
        return f"{component} x {self.quantity} {self.unit}{primary_mark}"


class DailyExpenseLog(models.Model):
    """
    Дневной лог расходов - для механического учета и динамических цен.

    Физические: количество + цена (может меняться каждый день)
    Накладные: сумма за день
    """
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name="daily_logs"
    )
    date = models.DateField(db_index=True, default=timezone.localdate)

    # Для физических расходов
    quantity_used = models.DecimalField(
        max_digits=12, decimal_places=3,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Фактически использовано (кг/шт)"
    )
    actual_price_per_unit = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Актуальная цена на день"
    )

    # Для накладных расходов
    daily_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Сумма накладного расхода за день"
    )

    # Авто-рассчитанная общая стоимость
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0"),
        help_text="Итоговая стоимость расхода за день"
    )

    notes = models.TextField(blank=True, help_text="Комментарии")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'daily_expense_logs'
        unique_together = ('expense', 'date')
        verbose_name = 'Дневной расход'
        verbose_name_plural = 'Дневные расходы'
        ordering = ['-date', 'expense__name']

    def clean(self):
        if self.expense.type == Expense.ExpenseType.PHYSICAL:
            if self.quantity_used is None:
                raise ValidationError({"quantity_used": "Для физического расхода нужно количество"})
            if self.actual_price_per_unit is None:
                raise ValidationError({"actual_price_per_unit": "Для физического расхода нужна цена"})
            if self.daily_amount is not None:
                raise ValidationError({"daily_amount": "Для физического расхода не нужна daily_amount"})
        else:  # OVERHEAD
            if self.daily_amount is None:
                raise ValidationError({"daily_amount": "Для накладного расхода нужна сумма"})
            if self.quantity_used is not None or self.actual_price_per_unit is not None:
                raise ValidationError("Для накладного расхода не нужны quantity/price")

    def save(self, *args, **kwargs):
        self.clean()

        # Автоматический расчет total_cost
        if self.expense.type == Expense.ExpenseType.PHYSICAL:
            if self.quantity_used and self.actual_price_per_unit:
                self.total_cost = self.quantity_used * self.actual_price_per_unit
        else:
            if self.daily_amount:
                self.total_cost = self.daily_amount

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.expense.name} - {self.date} ({self.total_cost} сом)"


class ProductionBatch(models.Model):
    """
    Производственная смена - данные по выпуску товаров за день.
    Основа для расчета себестоимости и распределения накладных.
    """
    date = models.DateField(db_index=True, default=timezone.localdate)
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='production_batches'
    )

    # Объемы производства
    produced_quantity = models.DecimalField(
        max_digits=12, decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Произведено единиц товара"
    )

    # Ввод через Сюзерена (альтернативный способ)
    suzerain_input_amount = models.DecimalField(
        max_digits=12, decimal_places=3,
        null=True, blank=True,
        help_text="Объем главного ингредиента (Сюзерен)"
    )

    # Расчетные данные
    physical_cost = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0")
    )
    overhead_cost = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0")
    )
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0")
    )
    cost_per_unit = models.DecimalField(
        max_digits=12, decimal_places=4,
        default=Decimal("0")
    )

    # Продажи и прибыль
    revenue = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0"),
        help_text="Выручка от продаж"
    )
    net_profit = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0"),
        help_text="Чистая прибыль"
    )

    # Детализация расходов (JSON)
    cost_breakdown = models.JSONField(
        default=dict,
        blank=True,
        help_text="Детальная разбивка расходов и бонусов"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'production_batches'
        unique_together = ('date', 'product')
        verbose_name = 'Производственная смена'
        verbose_name_plural = 'Производственные смены'
        ordering = ['-date', 'product__name']

    def __str__(self):
        return f"{self.product.name} - {self.date} ({self.produced_quantity})"


class MonthlyOverheadBudget(models.Model):
    """
    Месячный бюджет накладных расходов.
    Пример: аренда 35000, свет 25000, налоги 45000 и т.д.
    """
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()  # 1-12
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name='monthly_budgets',
        limit_choices_to={'type': Expense.expense_type}
    )

    planned_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Планируемая сумма на месяц"
    )

    actual_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0"),
        help_text="Фактическая сумма (сумма daily_amount за месяц)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'monthly_overhead_budgets'
        unique_together = ('year', 'month', 'expense')
        verbose_name = 'Месячный бюджет накладных'
        verbose_name_plural = 'Месячные бюджеты накладных'
        ordering = ['-year', '-month', 'expense__name']

    def clean(self):
        if self.expense and self.expense.type != Expense.ExpenseType.OVERHEAD:
            raise ValidationError({"expense": "Только накладные расходы"})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.expense.name} - {self.month}/{self.year} ({self.planned_amount})"