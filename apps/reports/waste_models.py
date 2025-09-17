# apps/reports/waste_models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal

class WasteLog(models.Model):
    """
    Первичка по браку (списаниям) — вводится вручную с выбором товара.
    По ТЗ: списывает из остатков и идёт «в минус дохода».
    """

    date = models.DateField(verbose_name='Дата')
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнёр'
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='waste_logs',
        verbose_name='Магазин'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        verbose_name='Товар'
    )

    # Количество (шт/кг) и сумма списания
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Количество'
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Сумма списания'
    )

    reason = models.CharField(max_length=200, blank=True, verbose_name='Причина')
    notes = models.TextField(blank=True, verbose_name='Примечания')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_waste_logs',
        verbose_name='Создал'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'waste_logs'
        verbose_name = 'Брак (списание)'
        verbose_name_plural = 'Брак (списания)'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['store']),
            models.Index(fields=['partner']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        who = self.store.store_name if self.store else (f'Партнёр {self.partner_id}' if self.partner else '—')
        return f'Брак {who} — {self.product.name} ({self.date}): {self.quantity} / {self.amount} с'


class WasteReport(models.Model):
    """
    Дневная витрина по браку (агрегат из WasteLog).
    Нужна для быстрых диаграмм/сводок: «Брак» — отдельный сектор и строка.
    """

    date = models.DateField(verbose_name='Дата')
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнёр'
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        null=True, blank=True,
        verbose_name='Магазин'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name='Товар'
    )

    waste_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Кол-во брака (шт/кг)'
    )
    waste_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Сумма брака'
    )

    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'waste_reports'
        verbose_name = 'Отчёт по браку (день)'
        verbose_name_plural = 'Отчёты по браку (день)'
        unique_together = ['date', 'partner', 'store', 'product']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['partner']),
            models.Index(fields=['store']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        parts = [str(self.date)]
        if self.partner: parts.append(f'Партнёр {self.partner_id}')
        if self.store: parts.append(self.store.store_name)
        if self.product: parts.append(self.product.name)
        return 'Брак ' + ' - '.join(parts)
