from django.db import models
from django.conf import settings
from decimal import Decimal
from bonuses.models import BonusTransaction

class IncomeRecord(models.Model):
    """Запись о доходах"""
    SOURCE_CHOICES = [
        ('sale', 'Продажа'),
        ('debt_payment', 'Погашение долга'),
        ('return', 'Возврат товара'),
        ('adjustment', 'Корректировка'),
    ]

    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='income_records',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, null=True, blank=True, verbose_name='Магазин')
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, null=True, blank=True, verbose_name='Заказ')

    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Сумма')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, verbose_name='Источник дохода')
    description = models.TextField(verbose_name='Описание')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')

    class Meta:
        db_table = 'income_records'
        verbose_name = 'Запись о доходе'
        verbose_name_plural = 'Записи о доходах'
        ordering = ['-created_at']

    def __str__(self):
        return f"Доход {self.amount} сом - {self.get_source_display()}"


class ExpenseRecord(models.Model):
    """Запись о расходах"""
    EXPENSE_TYPES = [
        ('operational', 'Операционный'),
        ('material', 'Материальный'),
        ('logistics', 'Логистический'),
        ('administrative', 'Административный'),
        ('other', 'Прочее'),
    ]

    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='expense_records',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Сумма')
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPES, verbose_name='Тип расхода')
    description = models.TextField(verbose_name='Описание')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')

    class Meta:
        db_table = 'expense_records'
        verbose_name = 'Запись о расходе'
        verbose_name_plural = 'Записи о расходах'
        ordering = ['-created_at']

    def __str__(self):
        return f"Расход {self.amount} сом - {self.get_expense_type_display()}"


class DefectRecord(models.Model):
    """Запись о браке"""
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='defect_records',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, verbose_name='Товар')

    quantity = models.DecimalField(max_digits=8, decimal_places=3, verbose_name='Количество брака')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Сумма убытка')

    description = models.TextField(verbose_name='Описание брака')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата фиксации')

    class Meta:
        db_table = 'defect_records'
        verbose_name = 'Запись о браке'
        verbose_name_plural = 'Записи о браке'
        ordering = ['-created_at']

    def __str__(self):
        return f"Брак {self.product.name}: {self.quantity} на {self.amount} сом"


class FinancialSummary(models.Model):
    """Финансовая сводка"""
    SUMMARY_TYPES = [
        ('daily', 'Дневная'),
        ('weekly', 'Недельная'),
        ('monthly', 'Месячная'),
        ('yearly', 'Годовая'),
    ]

    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='financial_summaries',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )

    summary_type = models.CharField(max_length=10, choices=SUMMARY_TYPES, verbose_name='Тип сводки')

    # Период
    period_start = models.DateTimeField(verbose_name='Начало периода')
    period_end = models.DateTimeField(verbose_name='Конец периода')

    # Доходы
    total_income = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Общий доход')
    sales_income = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Доход с продаж')
    debt_payments_income = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                               verbose_name='Доход с погашений')

    # Расходы
    total_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Общие расходы')
    operational_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                               verbose_name='Операционные расходы')
    material_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                            verbose_name='Материальные расходы')

    # Убытки
    defect_losses = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Убытки от брака')
    bonus_losses = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Убытки от бонусов')

    # Долги
    total_debt = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Общий долг')
    unpaid_debt = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Непогашенный долг')

    # Итоги
    net_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Чистая прибыль')
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Общий баланс')

    # Количества
    total_orders = models.PositiveIntegerField(default=0, verbose_name='Количество заказов')
    total_items_sold = models.PositiveIntegerField(default=0, verbose_name='Продано товаров')
    bonus_items_given = models.PositiveIntegerField(default=0, verbose_name='Дано бонусных товаров')

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'financial_summaries'
        verbose_name = 'Финансовая сводка'
        verbose_name_plural = 'Финансовые сводки'
        unique_together = ['partner', 'summary_type', 'period_start', 'period_end']
        ordering = ['-period_start']

    def __str__(self):
        return f"Сводка {self.partner.full_name} ({self.get_summary_type_display()})"

    def calculate_summary(self):
        """Пересчитать сводку на основе данных"""
        # Доходы
        income_records = IncomeRecord.objects.filter(
            partner=self.partner,
            created_at__range=[self.period_start, self.period_end]
        )

        self.total_income = income_records.aggregate(total=models.Sum('amount'))['total'] or 0
        self.sales_income = income_records.filter(source='sale').aggregate(total=models.Sum('amount'))['total'] or 0
        self.debt_payments_income = income_records.filter(source='debt_payment').aggregate(total=models.Sum('amount'))[
                                        'total'] or 0

        # Расходы
        expense_records = ExpenseRecord.objects.filter(
            partner=self.partner,
            created_at__range=[self.period_start, self.period_end]
        )

        self.total_expenses = expense_records.aggregate(total=models.Sum('amount'))['total'] or 0
        self.operational_expenses = \
        expense_records.filter(expense_type='operational').aggregate(total=models.Sum('amount'))['total'] or 0
        self.material_expenses = expense_records.filter(expense_type='material').aggregate(total=models.Sum('amount'))[
                                     'total'] or 0

        # Убытки
        defect_records = DefectRecord.objects.filter(
            partner=self.partner,
            created_at__range=[self.period_start, self.period_end]
        )

        self.defect_losses = defect_records.aggregate(total=models.Sum('amount'))['total'] or 0

        # Бонусы

        bonus_transactions = BonusTransaction.objects.filter(
            store__owner=self.partner,
            transaction_type='used',
            created_at__range=[self.period_start, self.period_end]
        )

        self.bonus_losses = bonus_transactions.aggregate(total=models.Sum('amount_saved'))['total'] or 0
        self.bonus_items_given = bonus_transactions.aggregate(total=models.Sum('quantity'))['total'] or 0

        # Долги
        from debts.models import Debt
        debts = Debt.objects.filter(
            store__owner=self.partner,
            created_at__range=[self.period_start, self.period_end]
        )

        self.total_debt = debts.aggregate(total=models.Sum('amount'))['total'] or 0
        self.unpaid_debt = debts.filter(is_paid=False).aggregate(total=models.Sum('amount'))['total'] or 0

        # Заказы
        from orders.models import Order
        orders = Order.objects.filter(
            partner=self.partner,
            order_date__range=[self.period_start, self.period_end]
        )

        self.total_orders = orders.count()
        self.total_items_sold = orders.aggregate(
            total=models.Sum('items__quantity')
        )['total'] or 0

        # Итоговые расчеты
        self.net_profit = self.total_income - self.total_expenses - self.defect_losses - self.bonus_losses
        self.balance = self.net_profit - self.unpaid_debt

        self.save()