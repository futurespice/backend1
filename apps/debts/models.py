from django.db import models
from django.conf import settings
from decimal import Decimal
from django.core.validators import MinValueValidator


class Debt(models.Model):
    """Долг магазина"""
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='debts', verbose_name='Магазин')
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='debts',
        verbose_name='Заказ'
    )

    # Сумма долга
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Сумма долга'
    )

    # Статус
    is_paid = models.BooleanField(default=False, verbose_name='Погашен')

    # Описание
    description = models.TextField(verbose_name='Описание долга')

    # Даты
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    due_date = models.DateTimeField(null=True, blank=True, verbose_name='Срок погашения')
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата погашения')

    class Meta:
        db_table = 'debts'
        verbose_name = 'Долг'
        verbose_name_plural = 'Долги'
        ordering = ['-created_at']

    def __str__(self):
        status = "Погашен" if self.is_paid else "Активен"
        return f"Долг {self.store.name}: {self.amount} сом ({status})"

    @property
    def is_overdue(self):
        """Проверить, просрочен ли долг"""
        if self.due_date and not self.is_paid:
            from django.utils import timezone
            return timezone.now() > self.due_date
        return False

    def mark_as_paid(self, payment_amount=None):
        """Отметить долг как погашенный"""
        from django.utils import timezone

        if payment_amount is None:
            payment_amount = self.amount

        # Создаем запись о платеже
        payment = DebtPayment.objects.create(
            debt=self,
            amount=payment_amount,
            payment_date=timezone.now()
        )

        # Если оплачен полностью
        if payment_amount >= self.amount:
            self.is_paid = True
            self.paid_at = timezone.now()
            self.save()

            # Добавляем в доход партнера
            from reports.models import IncomeRecord
            IncomeRecord.objects.create(
                partner=self.store.owner,
                store=self.store,
                amount=payment_amount,
                source='debt_payment',
                description=f'Погашение долга {self.id}'
            )

        return payment


class DebtPayment(models.Model):
    """Платеж по долгу"""
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name='payments', verbose_name='Долг')
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Сумма платежа'
    )
    payment_date = models.DateTimeField(verbose_name='Дата платежа')
    notes = models.TextField(blank=True, verbose_name='Комментарии')

    # Кто обработал платеж
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role__in': ['admin', 'partner']},
        verbose_name='Обработал'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'debt_payments'
        verbose_name = 'Платеж по долгу'
        verbose_name_plural = 'Платежи по долгам'
        ordering = ['-payment_date']

    def __str__(self):
        return f"Платеж {self.amount} сом по долгу {self.debt.id}"


class DebtSummary(models.Model):
    """Сводка по долгам для отчетности"""
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, verbose_name='Магазин')
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )

    # Суммы
    total_debt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Общий долг')
    paid_debt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Погашенный долг')
    unpaid_debt = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Непогашенный долг')

    # Период
    period_start = models.DateTimeField(verbose_name='Начало периода')
    period_end = models.DateTimeField(verbose_name='Конец периода')

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'debt_summaries'
        verbose_name = 'Сводка по долгам'
        verbose_name_plural = 'Сводки по долгам'
        unique_together = ['store', 'partner', 'period_start', 'period_end']
        ordering = ['-created_at']

    def __str__(self):
        return f"Сводка {self.store.name}: {self.unpaid_debt} сом"

    def update_summary(self):
        """Обновить сводку по долгам"""
        debts = Debt.objects.filter(
            store=self.store,
            created_at__range=[self.period_start, self.period_end]
        )

        self.total_debt = debts.aggregate(total=models.Sum('amount'))['total'] or 0
        self.paid_debt = debts.filter(is_paid=True).aggregate(total=models.Sum('amount'))['total'] or 0
        self.unpaid_debt = self.total_debt - self.paid_debt

        self.save()