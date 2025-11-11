from django.db import models
from django.conf import settings
from decimal import Decimal

class ReportType(models.TextChoices):
    SALES = 'sales', 'Продажи'
    DEBTS = 'debts', 'Долги'
    COSTS = 'costs', 'Расходы'
    BONUSES = 'bonuses', 'Бонусы'
    DEFECTS = 'brak', 'Брак'
    BALANCE = 'balance', 'Баланс'
    ORDERS = 'orders', 'Заказы'
    PRODUCTS = 'products', 'Товары'
    MARKUP = 'markup', 'Наценка'


class Report(models.Model):
    """Отчёты"""
    type = models.CharField(max_length=20, choices=ReportType.choices, verbose_name='Тип отчёта')
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Сгенерировал'
    )
    data = models.JSONField(verbose_name='Данные отчёта')  # JSON с данными (shares, labels, etc.)
    pdf_file = models.FileField(upload_to='reports/pdfs/', null=True, blank=True, verbose_name='PDF файл')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'reports'
        verbose_name = 'Отчёт'
        verbose_name_plural = 'Отчёты'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()} ({self.created_at})"