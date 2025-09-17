from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal, InvalidOperation


class Report(models.Model):
    """Журнал сформированных отчётов (параметры, период, итоговый JSON)."""

    REPORT_TYPES = [
        ('sales', 'Отчет по продажам'),
        ('inventory', 'Отчет по остаткам'),
        ('debts', 'Отчет по долгам'),
        ('bonuses', 'Отчет по бонусам'),
        ('costs', 'Отчет по себестоимости'),
        ('profit', 'Отчет по прибыли'),
        ('partner_performance', 'Отчет по партнерам'),
        ('store_performance', 'Отчет по магазинам'),
        ('waste', 'Отчет по браку'),
    ]

    PERIODS = [
        ('daily', 'За день'),
        ('weekly', 'За неделю'),
        ('monthly', 'За месяц'),
        ('quarterly', 'За квартал'),
        ('yearly', 'За год'),
        ('custom', 'Произвольный период'),
    ]

    name = models.CharField(max_length=200, verbose_name='Название отчета')
    report_type = models.CharField(max_length=32, choices=REPORT_TYPES, verbose_name='Тип отчета')
    period = models.CharField(max_length=20, choices=PERIODS, verbose_name='Период')

    # Период отчёта
    date_from = models.DateField(verbose_name='Дата начала')
    date_to = models.DateField(verbose_name='Дата окончания')

    # Фильтры
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Магазин',
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name='Товар',
    )

    # Итоговые данные отчёта (кеш результата рендеринга/экспорта)
    data = models.JSONField(default=dict, verbose_name='Данные отчета')

    # Метаданные
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_reports',
        verbose_name='Создал'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    is_automated = models.BooleanField(default=False, verbose_name='Автоматический')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError('Дата начала не может быть позже даты окончания.')
        if self.period == 'custom' and (not self.date_from or not self.date_to):
            raise ValidationError('Для произвольного периода нужно указать обе даты.')

    class Meta:
        db_table = 'reports'
        verbose_name = 'Отчет'
        verbose_name_plural = 'Отчеты'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['report_type', 'date_from', 'date_to']),
            models.Index(fields=['store']),
            models.Index(fields=['partner']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        return f"{self.name} ({self.date_from} - {self.date_to})"


class SalesReport(models.Model):
    """
    Агрегированная статистика продаж.
    Источник для расчёта: orders.Order / orders.OrderItem (+ бонусы, себестоимость).
    """

    date = models.DateField(verbose_name='Дата')
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Магазин'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name='Товар'
    )

    # Метрики
    orders_count = models.PositiveIntegerField(default=0, verbose_name='Количество заказов')
    total_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0'),
        verbose_name='Общее количество'
    )
    total_revenue = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        verbose_name='Выручка'
    )
    total_bonus_discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        verbose_name='Бонусные скидки'
    )
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        verbose_name='Себестоимость'
    )
    profit = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        verbose_name='Прибыль'
    )

    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'sales_reports'
        verbose_name = 'Отчет по продажам'
        verbose_name_plural = 'Отчеты по продажам'
        unique_together = ['date', 'partner', 'store', 'product']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['partner']),
            models.Index(fields=['store']),
            models.Index(fields=['product']),
            models.Index(fields=['date', 'store']),
            models.Index(fields=['date', 'partner']),
        ]

    def __str__(self):
        parts = [str(self.date)]
        if self.partner:
            parts.append(f"Партнер {self.partner_id}")
        if self.store:
            parts.append(self.store.store_name)
        if self.product:
            parts.append(self.product.name)
        return f"Продажи {' - '.join(parts)}"


class InventoryReport(models.Model):
    """
    Отчет по остаткам (на дату).
    Данные сверяются/подкрепляются снапшотом себестоимости.
    """

    date = models.DateField(verbose_name='Дата')
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Магазин'
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name='Товар'
    )

    # Остатки (в штуках или кг; для кг используем точность .3 по ТЗ)
    opening_balance = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0'),
        verbose_name='Остаток на начало'
    )
    received_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0'),
        verbose_name='Поступило'
    )
    sold_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0'),
        verbose_name='Продано'
    )
    closing_balance = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0'),
        verbose_name='Остаток на конец'
    )

    # Стоимостные показатели
    opening_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        verbose_name='Стоимость на начало'
    )
    closing_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        verbose_name='Стоимость на конец'
    )

    production_batch = models.ForeignKey(
        'cost_accounting.ProductionBatch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Производственная партия (для расчёта себестоимости)'
    )

    def clean(self):
        from django.core.exceptions import ValidationError
        try:
            opening = Decimal(self.opening_balance or 0)
            received = Decimal(self.received_quantity or 0)
            sold = Decimal(self.sold_quantity or 0)
            closing = Decimal(self.closing_balance or 0)
        except InvalidOperation:
            raise ValidationError('Некорректные числовые значения остатков.')

        if (opening + received - sold) != closing:
            raise ValidationError('Инвариант баланса нарушен: opening + received - sold != closing.')

    class Meta:
        db_table = 'inventory_reports'
        verbose_name = 'Отчет по остаткам'
        verbose_name_plural = 'Отчеты по остаткам'
        unique_together = ['date', 'store', 'partner', 'product']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['store']),
            models.Index(fields=['partner']),
            models.Index(fields=['product']),
            models.Index(fields=['production_batch']),
        ]

    def __str__(self):
        who = self.store.store_name if self.store else (f"Партнер {self.partner_id}" if self.partner else "—")
        return f"Остатки {who} - {self.product.name} ({self.date})"


class DebtReport(models.Model):
    """
    Отчет по долгам (на дату): открытие, новое начисление, погашение, закрытие.
    Источник: debts.Debt (+ платежи).
    """

    date = models.DateField(verbose_name='Дата')
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Магазин'
    )

    opening_debt = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        verbose_name='Долг на начало'
    )
    new_debt = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        verbose_name='Начислено за период'
    )
    paid_debt = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Погашено за период'
    )
    closing_debt = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        verbose_name='Долг на конец'
    )

    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'debt_reports'
        verbose_name = 'Отчет по долгам'
        verbose_name_plural = 'Отчеты по долгам'
        unique_together = ['date', 'partner', 'store']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['partner']),
            models.Index(fields=['store']),
        ]

    def __str__(self):
        who = self.store.store_name if self.store else (f"Партнер {self.partner_id}" if self.partner else "—")
        return f"Долги {who} ({self.date})"


class BonusReport(models.Model):
    """
    Суточный отчёт по бонусам на уровне товара/локации.
    bonus_quantity — всегда в штуках, т.к. весовые товары по ТЗ бонусами быть не могут.
    """

    date = models.DateField(verbose_name='Дата')
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Магазин'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name='Товар'
    )

    sold_quantity = models.PositiveIntegerField(default=0, verbose_name='Продано (ед.)')
    bonus_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name='Бесплатно выдано (ед.)'
    )
    bonus_discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Сумма бонусной скидки'
    )
    net_revenue = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Выручка с учётом бонусов'
    )
    bonus_rule_n = models.PositiveIntegerField(null=True, blank=True, verbose_name='Правило бонусов (каждый N-й)')

    production_batch = models.ForeignKey(
        'cost_accounting.ProductionBatch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Производственная партия'
    )

    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'bonus_reports'
        verbose_name = 'Отчет по бонусам (день)'
        verbose_name_plural = 'Отчеты по бонусам (день)'
        unique_together = ['date', 'partner', 'store', 'product']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['partner']),
            models.Index(fields=['store']),
            models.Index(fields=['product']),
            models.Index(fields=['production_batch']),
        ]

    def clean(self):
        """
        Валидация: весовые товары не могут быть бонусными.
        """
        from django.core.exceptions import ValidationError
        if self.product:
            weight_units = {'kg', 'g', 'l', 'ml'}
            if self.product.unit in weight_units and self.bonus_quantity > 0:
                raise ValidationError("Весовые товары не могут иметь бонусное количество.")

    def __str__(self):
        who = self.store.store_name if self.store else (f"Партнер {self.partner_id}" if self.partner else "—")
        return f"Бонусы {who} — {self.product.name} ({self.date})"


class BonusReportMonthly(models.Model):
    """
    Месячная сводка по бонусам (кеш агрегатов).
    Заполняется либо из BonusReport (агрегация за месяц), либо напрямую из сервисов bonus_service.py.
    """

    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()

    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Магазин'
    )

    total_bonus_discount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Сумма бонусных скидок за месяц'
    )
    total_bonus_items = models.PositiveIntegerField(
        default=0, verbose_name='Всего бесплатных единиц'
    )
    days_with_bonuses = models.PositiveIntegerField(
        default=0, verbose_name='Дней с бонусами'
    )
    avg_daily_bonus_discount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Средняя бонусная скидка в день'
    )
    avg_daily_bonus_items = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Среднее бесплатных единиц в день'
    )

    # Детализация (по желанию: кусочки monthly summary, дневная разбивка и т.д.)
    meta = models.JSONField(default=dict, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bonus_reports_monthly'
        verbose_name = 'Отчет по бонусам (месяц)'
        verbose_name_plural = 'Отчеты по бонусам (месяц)'
        unique_together = ['year', 'month', 'partner', 'store']
        indexes = [
            models.Index(fields=['year', 'month']),
            models.Index(fields=['partner']),
            models.Index(fields=['store']),
        ]

    def __str__(self):
        who = self.store.store_name if self.store else (f"Партнер {self.partner_id}" if self.partner else "—")
        return f"Бонусы (месяц) {who} — {self.year}-{self.month:02d}"



class CostReport(models.Model):
    """
    Отчет по себестоимости на дату (связь со снапшотом).
    Суммы разложены по материалам и накладным согласно ТЗ (4.1).
    """

    date = models.DateField(verbose_name='Дата')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, verbose_name='Товар')

    # Опциональная привязка к снимку расчёта себестоимости
    production_batch = models.ForeignKey(
        'cost_accounting.ProductionBatch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Производственная партия'
    )

    # Детализация
    materials_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Материалы (ингредиенты/упаковка)'
    )
    overhead_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Накладные расходы'
    )
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Себестоимость итого'
    )
    produced_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Произведено (шт/кг)'
    )

    meta = models.JSONField(default=dict, verbose_name='Метаданные (алгоритм, доли и пр.)', blank=True)

    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    def clean(self):
        from django.core.exceptions import ValidationError
        if (self.materials_cost + self.overhead_cost) != self.total_cost:
            raise ValidationError('Сумма материалов и накладных должна равняться себестоимости.')

    class Meta:
        db_table = 'cost_reports'
        verbose_name = 'Отчет по себестоимости'
        verbose_name_plural = 'Отчеты по себестоимости'
        unique_together = ['date', 'product']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['product']),
            models.Index(fields=['production_batch']),
        ]

    def __str__(self):
        return f"Себестоимость {self.product.name} ({self.date})"
