# from django.db import models
# from django.conf import settings
# from decimal import Decimal
# from django.core.validators import MinValueValidator
# from django.utils import timezone
#
#
# class Debt(models.Model):
#     """Долг магазина"""
#
#     store = models.ForeignKey(
#         'stores.Store',
#         on_delete=models.CASCADE,
#         related_name='debts',
#         verbose_name='Магазин'
#     )
#     order = models.ForeignKey(
#         'orders.Order',
#         on_delete=models.CASCADE,
#         null=True,
#         blank=True,
#         related_name='debt_records',
#         verbose_name='Заказ'
#     )
#
#     # Сумма долга
#     amount = models.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         validators=[MinValueValidator(Decimal('0.01'))],
#         verbose_name='Сумма долга'
#     )
#
#     # Статус погашения
#     is_paid = models.BooleanField(default=False, verbose_name='Погашен')
#     paid_amount = models.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         default=0,
#         validators=[MinValueValidator(Decimal('0'))],
#         verbose_name='Погашенная сумма'
#     )
#
#     # Даты
#     created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
#     due_date = models.DateField(null=True, blank=True, verbose_name='Дата погашения')
#     paid_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата погашения')
#
#     # Описание
#     description = models.TextField(verbose_name='Описание долга')
#     notes = models.TextField(blank=True, verbose_name='Примечания')
#
#     class Meta:
#         db_table = 'debts'
#         verbose_name = 'Долг'
#         verbose_name_plural = 'Долги'
#         ordering = ['-created_at']
#
#     def __str__(self):
#         status = "Погашен" if self.is_paid else "Активен"
#         return f"Долг {self.store.store_name}: {self.remaining_amount} сом ({status})"
#
#     @property
#     def remaining_amount(self):
#         """Оставшаяся сумма долга"""
#         return self.amount - self.paid_amount
#
#     @property
#     def is_overdue(self):
#         """Просрочен ли долг"""
#         if self.is_paid or not self.due_date:
#             return False
#         return timezone.now().date() > self.due_date
#
#     def make_payment(self, amount, payment_method='cash', notes=''):
#         """Внести платёж по долгу"""
#         amount = Decimal(str(amount))
#
#         if amount <= 0:
#             raise ValueError("Сумма платежа должна быть положительной")
#
#         if amount > self.remaining_amount:
#             amount = self.remaining_amount
#
#         # Создаём запись о платеже
#         payment = DebtPayment.objects.create(
#             debt=self,
#             amount=amount,
#             payment_method=payment_method,
#             notes=notes
#         )
#
#         # Обновляем долг
#         self.paid_amount += amount
#
#         if self.remaining_amount <= Decimal('0.01'):  # Учитываем копейки
#             self.is_paid = True
#             self.paid_at = timezone.now()
#
#         self.save()
#         return payment
#
#
# class DebtPayment(models.Model):
#     """Платёж по долгу"""
#
#     PAYMENT_METHODS = [
#         ('cash', 'Наличные'),
#         ('card', 'Банковская карта'),
#         ('transfer', 'Банковский перевод'),
#         ('mobile', 'Мобильный платёж'),
#         ('other', 'Другое'),
#     ]
#
#     debt = models.ForeignKey(
#         Debt,
#         on_delete=models.CASCADE,
#         related_name='payments',
#         verbose_name='Долг'
#     )
#
#     amount = models.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         validators=[MinValueValidator(Decimal('0.01'))],
#         verbose_name='Сумма платежа'
#     )
#
#     payment_method = models.CharField(
#         max_length=20,
#         choices=PAYMENT_METHODS,
#         default='cash',
#         verbose_name='Способ оплаты'
#     )
#
#     # Метаданные платежа
#     created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата платежа')
#     processed_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True,
#         verbose_name='Обработал'
#     )
#
#     notes = models.TextField(blank=True, verbose_name='Примечания')
#     transaction_id = models.CharField(
#         max_length=100,
#         blank=True,
#         verbose_name='ID транзакции'
#     )
#
#     class Meta:
#         db_table = 'debt_payments'
#         verbose_name = 'Платёж по долгу'
#         verbose_name_plural = 'Платежи по долгам'
#         ordering = ['-created_at']
#
#     def __str__(self):
#         return f"Платёж {self.amount} сом по долгу #{self.debt.id}"
#
#
# class DebtSummary(models.Model):
#     """Сводка по долгам магазина (для оптимизации запросов)"""
#
#     store = models.OneToOneField(
#         'stores.Store',
#         on_delete=models.CASCADE,
#         related_name='debt_summary',
#         verbose_name='Магазин'
#     )
#
#     # Суммы
#     total_debt = models.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         default=0,
#         verbose_name='Общий долг'
#     )
#     overdue_debt = models.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         default=0,
#         verbose_name='Просроченный долг'
#     )
#
#     # Счётчики
#     active_debts_count = models.PositiveIntegerField(
#         default=0,
#         verbose_name='Количество активных долгов'
#     )
#     overdue_debts_count = models.PositiveIntegerField(
#         default=0,
#         verbose_name='Количество просроченных долгов'
#     )
#
#     # Даты
#     last_payment_date = models.DateTimeField(
#         null=True,
#         blank=True,
#         verbose_name='Дата последнего платежа'
#     )
#     updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')
#
#     class Meta:
#         db_table = 'debt_summaries'
#         verbose_name = 'Сводка долгов'
#         verbose_name_plural = 'Сводки долгов'
#
#     def __str__(self):
#         return f"Долги {self.store.store_name}: {self.total_debt} сом"
#
#     def recalculate(self):
#         """Пересчёт сводки"""
#         from django.db.models import Sum, Count
#
#         # Активные долги
#         active_debts = self.store.debts.filter(is_paid=False)
#
#         self.total_debt = active_debts.aggregate(
#             total=Sum('amount') - Sum('paid_amount')
#         )['total'] or Decimal('0')
#
#         self.active_debts_count = active_debts.count()
#
#         # Просроченные долги
#         overdue_debts = active_debts.filter(
#             due_date__lt=timezone.now().date()
#         )
#
#         self.overdue_debt = overdue_debts.aggregate(
#             total=Sum('amount') - Sum('paid_amount')
#         )['total'] or Decimal('0')
#
#         self.overdue_debts_count = overdue_debts.count()
#
#         # Последний платёж
#         last_payment = DebtPayment.objects.filter(
#             debt__store=self.store
#         ).order_by('-created_at').first()
#
#         if last_payment:
#             self.last_payment_date = last_payment.created_at
#
#         self.save()
#
#
# # Сигналы для автоматического обновления сводки
# from django.db.models.signals import post_save, post_delete
# from django.dispatch import receiver
#
#
# @receiver([post_save, post_delete], sender=Debt)
# @receiver([post_save, post_delete], sender=DebtPayment)
# def update_debt_summary(sender, instance, **kwargs):
#     """Обновление сводки при изменении долгов"""
#     if sender == Debt:
#         store = instance.store
#     else:  # DebtPayment
#         store = instance.debt.store
#
#     summary, created = DebtSummary.objects.get_or_create(store=store)
#     summary.recalculate()