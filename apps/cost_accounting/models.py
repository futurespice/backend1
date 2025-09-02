from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone

from products.models import Product


class Expense(models.Model):
    """Расход из ТЗ 4.1: физический (ингредиент/упаковка) или накладной (аренда, ЗП и т.д.).
    - type: ветка расходов
    - status: Сюзерен / Вассал / Обыватель
    - state: Механическое (ручной учёт) / Автоматическое (распределяется алгоритмом)
    - unit/price_per_unit только для физ. расходов
    - is_universal: «универсальный» тип — применяется ко всем товарам
    """

    class ExpenseType(models.TextChoices):
        PHYSICAL = "physical", "Физический"   # ингредиент/упаковка
        OVERHEAD = "overhead", "Накладной"   # аренда/ЗП/электроэнергия и т.п.

    class ExpenseStatus(models.TextChoices):
        SUZERAIN = "suzerain", "Сюзерен"
        VASSAL = "vassal", "Вассал"
        COMMONER = "commoner", "Обыватель"

    class ExpenseState(models.TextChoices):
        MECHANICAL = "mechanical", "Механическое"
        AUTOMATIC = "automatic", "Автоматическое"

    class Unit(models.TextChoices):
        KG = "kg", "Кг"
        PCS = "pcs", "Шт"

    type = models.CharField(max_length=20, choices=ExpenseType.choices)
    name = models.CharField(max_length=120, db_index=True)

    # Только для физ. расходов
    unit = models.CharField(
        max_length=8, choices=Unit.choices, null=True, blank=True,
        help_text="Ед. изм. для физического расхода (кг/шт). Для накладных пусто."
    )
    price_per_unit = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Цена за единицу (кг/шт) для физического расхода."
    )

    # Поведенческие поля из ТЗ
    status = models.CharField(max_length=16, choices=ExpenseStatus.choices, default=ExpenseStatus.COMMONER)
    state = models.CharField(max_length=16, choices=ExpenseState.choices, default=ExpenseState.AUTOMATIC)

    # Применение
    is_universal = models.BooleanField(
        default=False,
        help_text="Если включено — расход применяется ко всем товарам (тип 'универсальный' из ТЗ)."
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Бизнес-валидация по ТЗ
    def clean(self):
        from django.core.exceptions import ValidationError

        if self.type == self.ExpenseType.PHYSICAL:
            if not self.unit:
                raise ValidationError({"unit": "Для физического расхода требуется единица измерения (кг/шт)."})
            if self.price_per_unit is None:
                raise ValidationError({"price_per_unit": "Для физического расхода требуется цена за единицу."})
        else:  # OVERHEAD
            if self.unit or self.price_per_unit:
                raise ValidationError("Для накладных расходов не задаются unit/price_per_unit.")

        # Автоматический переход статуса при выборе 'механического' учёта (по ТЗ)
        if self.state == self.ExpenseState.MECHANICAL and self.status == self.ExpenseStatus.COMMONER:
            self.status = self.ExpenseStatus.VASSAL

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class ProductExpense(models.Model):
    """Связь товар ↔ расход с пропорцией.
    - Для физ. расходов: сколько ЕД. расхода требуется на 1 ЕД. товара.
      Пример: 0.12 кг фарша на 1 кг пельменей или 0.06 кг на 1 шт — зависит от твоей товарной модели.
    - Для накладных: коэффициент распределения (обычно автопересчёт по объёмам производства).
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cost_expenses"
    )
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name="product_links"
    )

    # Сколько единиц расхода на 1 «единицу товара» (шт или кг товара).
    # Для накладных это может быть коэффициент (будет масштабироваться авто-алгоритмом).
    ratio_per_product_unit = models.DecimalField(
        max_digits=14, decimal_places=6,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Единиц расхода на 1 ед. товара (шт/кг). Для накладных — коэффициент."
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("product", "expense")

    def __str__(self):
        return f"{self.product} ← {self.expense} ({self.ratio_per_product_unit})"


class MechanicalExpenseLog(models.Model):
    """Лог ручного ('механического') учёта расходов по датам.
    Используется для: накладные/физические с state=mechanical — вводится фактическая сумма/объём.
    - Для физ. расхода логгируем количество в ЕД. (кг/шт), а сумму можно вычислить.
    - Для накладного — сразу сумму.
    """
    expense = models.ForeignKey(
        Expense, on_delete=models.CASCADE, related_name="mechanical_logs"
    )
    date = models.DateField(db_index=True, default=timezone.localdate)

    # Кол-во единиц расхода (для физического: кг/шт). Для накладного оставляем 0 и используем amount.
    quantity = models.DecimalField(
        max_digits=14, decimal_places=6, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))]
    )
    # Денежная сумма (для накладного обязательно, для физического может быть пусто — посчитаем * price_per_unit)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))]
    )

    note = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("expense", "date")

    def __str__(self):
        return f"{self.expense.name} @ {self.date}"


class CostSnapshot(models.Model):
    """Дневной снапшот себестоимости по каждому товару (не конфликтует с 'CostRegister').
    Сохраняется по кнопке «Сохранить» (перезаписывает только текущую дату, историю не трогаем).
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cost_accounting_snapshots",  # уникальный реверс
        related_query_name="cost_accounting_snapshot",  # и для ORM-запросов
    )
    date = models.DateField(db_index=True, default=timezone.localdate)

    # Сценарии ввода из ТЗ:
    produced_qty = models.DecimalField(  # введено количество произведённого товара (шт/кг)
        max_digits=14, decimal_places=6,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Количество произведённого товара (шт/кг)."
    )
    suzerain_input_amount = models.DecimalField(  # или введён объём «Сюзерена» (кг/шт)
        max_digits=14, decimal_places=6, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Введённый объём Сюзерена (если выбран такой сценарий)."
    )

    # Итоги (пересчитываются сервисом/калькулятором)
    physical_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    overhead_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))  # physical+overhead
    cost_per_unit = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal("0"))

    # Для интеграции с продажами/доходами (можно заполнять из другого модуля)
    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    net_profit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # Детальная разбивка: {expense_id: {"consumed_qty": .., "amount": ..}, "overhead_allocation": {...}}
    breakdown = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("product", "date")
        indexes = [
            models.Index(fields=["date", "product"]),
        ]

    def __str__(self):
        return f"{self.product} — {self.date}"





# ────────────────────────────────────────────────────────────────────────────────
# BOM: многоуровневый состав продукта
# ────────────────────────────────────────────────────────────────────────────────

class BillOfMaterial(models.Model):
    """
    Заголовок спецификации для продукта (1 активный BOM на продукт).
    Если планируются версии, можно хранить несколько версий и переключать is_active.
    """
    product = models.OneToOneField(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='bom',
        verbose_name='Продукт',
    )
    version = models.PositiveIntegerField(default=1, verbose_name='Версия')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Спецификация (BOM)'
        verbose_name_plural = 'Спецификации (BOM)'

    def __str__(self):
        status = 'активен' if self.is_active else 'неактивен'
        return f'BOM[{self.product_id}] {self.product} v{self.version} ({status})'

    def get_lines(self):
        """Утилита для префетча строк BOM."""
        return (self.lines
                .select_related('expense', 'component_product')
                .all())


class BOMLine(models.Model):
    """
    Строка состава: либо сырьевой расход (Expense), либо полуфабрикат (другой Product).
    Кол-во указывается на 1 единицу целевого продукта (bom.product).
    """
    class Unit(models.TextChoices):
        KG = 'kg', 'кг'
        PCS = 'pcs', 'шт'

    bom = models.ForeignKey(
        BillOfMaterial,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='BOM',
    )

    # Ровно одно из двух:
    expense = models.ForeignKey(
        'cost_accounting.Expense',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='used_in_bom_lines',
        verbose_name='Расход (ингредиент/упаковка)',
    )
    component_product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='used_as_component_lines',
        verbose_name='Компонент-продукт (полуфабрикат)',
    )

    quantity = models.DecimalField(
        max_digits=10, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Кол-во на 1 ед. целевого продукта',
        help_text='Например: 0.150 кг или 2.000 шт на 1 ед. bom.product',
    )
    unit = models.CharField(
        max_length=8,
        choices=Unit.choices,
        verbose_name='Ед. изм.',
    )

    # «Сюзерен» (ровно один на BOM). Нужен по ТЗ для сценариев пересчёта.
    is_primary = models.BooleanField(default=False, verbose_name='Сюзерен')

    # служебные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        verbose_name = 'Строка BOM'
        verbose_name_plural = 'Строки BOM'
        ordering = ('id',)
        constraints = [
            # one-of: либо expense, либо component_product
            models.CheckConstraint(
                name='bomline_one_of_component',
                check=(
                    models.Q(expense__isnull=False, component_product__isnull=True) |
                    models.Q(expense__isnull=True, component_product__isnull=False)
                ),
            ),
            # единственный «сюзерен» на BOM
            models.UniqueConstraint(
                fields=['bom'],
                condition=models.Q(is_primary=True),
                name='bomline_single_primary_per_bom',
            ),
        ]
        indexes = [
            models.Index(fields=['bom'], name='idx_bomline_bom'),
            models.Index(fields=['expense'], name='idx_bomline_expense'),
            models.Index(fields=['component_product'], name='idx_bomline_component_product'),
        ]

    def __str__(self):
        if self.expense_id:
            who = f'Expense#{self.expense_id}'
        else:
            who = f'Product#{self.component_product_id}'
        return f'BOMLine[{self.id}] {who} x {self.quantity} {self.get_unit_display()}'

    # Дополнительные бизнес-валидации
    def clean(self):
        errors = {}

        # 1) Ровно один тип компонента
        has_exp = bool(self.expense_id)
        has_prod = bool(self.component_product_id)
        if has_exp == has_prod:
            errors['expense'] = 'Укажите либо expense, либо component_product (ровно одно).'
            errors['component_product'] = 'Укажите либо expense, либо component_product (ровно одно).'

        # 2) Количество > 0 (дополнительно к валидатору — на случай нулей после округления)
        if self.quantity is None or self.quantity <= 0:
            errors['quantity'] = 'Количество должно быть > 0.'

        # 3) Запрет прямого самоссылания: component_product не может быть тем же, что bom.product
        if self.component_product_id and self.bom_id and self.bom.product_id == self.component_product_id:
            errors['component_product'] = 'Компонент-продукт не может быть тем же, что и целевой продукт BOM.'

        # 4) Простая проверка соответствия единиц (можно расширить при наличии типов продуктов/расходов)
        if self.unit not in dict(self.Unit.choices):
            errors['unit'] = 'Недопустимая единица измерения.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Нормализуем количество к 3-м знакам, чтобы не плодить 0.100000 и т.п.
        if self.quantity is not None:
            self.quantity = (Decimal(self.quantity)
                             .quantize(Decimal('0.001')))  # количество — до тысячных
        super().save(*args, **kwargs)

