from django.db import models
from django.conf import settings
from decimal import Decimal
from django.core.validators import MinValueValidator
from datetime import datetime, date


class Report(models.Model):
    """Отчеты системы"""

    REPORT_TYPES = [
        ('sales', 'Отчет по продажам'),
        ('inventory', 'Отчет по остаткам'),
        ('debts', 'Отчет по долгам'),
        ('bonuses', 'Отчет по бонусам'),
        ('costs', 'Отчет по себестоимости'),
        ('profit', 'Отчет по прибыли'),
        ('partner_performance', 'Отчет по партнерам'),
        ('store_performance', 'Отчет по магазинам'),
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
    report_type = models.CharField(
        max_length=20,
        choices=REPORT_TYPES,
        verbose_name='Тип отчета'
    )
    period = models.CharField(
        max_length=20,
        choices=PERIODS,
        verbose_name='Период'
    )

    # Даты для отчета
    date_from = models.DateField(verbose_name='Дата начала')
    date_to = models.DateField(verbose_name='Дата окончания')

    # Фильтры
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Магазин'
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Товар'
    )

    # Данные отчета (JSON)
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

    class Meta:
        db_table = 'reports'
        verbose_name = 'Отчет'
        verbose_name_plural = 'Отчеты'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.date_from} - {self.date_to})"


class SalesReport(models.Model):
    """Агрегированная статистика продаж"""

    # Период
    date = models.DateField(verbose_name='Дата')
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Магазин'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Товар'
    )

    # Метрики
    orders_count = models.PositiveIntegerField(default=0, verbose_name='Количество заказов')
    total_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        verbose_name='Общее количество'
    )
    total_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Выручка'
    )
    total_bonus_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Бонусные скидки'
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Себестоимость'
    )
    profit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Прибыль'
    )

    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'sales_reports'
        verbose_name = 'Отчет по продажам'
        verbose_name_plural = 'Отчеты по продажам'
        unique_together = ['date', 'store', 'product']
        ordering = ['-date']

    def __str__(self):
        parts = [str(self.date)]
        if self.store:
            parts.append(self.store.store_name)
        if self.product:
            parts.append(self.product.name)
        return f"Продажи {' - '.join(parts)}"


class InventoryReport(models.Model):
    """Отчет по остаткам"""

    date = models.DateField(verbose_name='Дата')
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Магазин'
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name='Товар'
    )

    # Остатки
    opening_balance = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        verbose_name='Остаток на начало'
    )
    received_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        verbose_name='Поступило'
    )
    sold_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        verbose_name='Продано'
    )
    closing_balance = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        verbose_name='Остаток на конец'
    )

    # Стоимостные показатели
    opening_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Стоимость на начало'
    )
    closing_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Стоимость на конец'
    )

    class Meta:
        db_table = 'inventory_reports'
        verbose_name = 'Отчет по остаткам'
        verbose_name_plural = 'Отчеты по остаткам'
        unique_together = ['date', 'store', 'partner', 'product']

    def __str__(self):
        location = self.store.store_name if self.store else f"Партнер {self.partner.get_full_name()}"
        return f"Остатки {location} - {self.product.name} ({self.date})"