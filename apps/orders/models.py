from django.db import models
from django.conf import settings
from decimal import Decimal
from django.core.validators import MinValueValidator
from stores.models import Store
from products.models import Product
import uuid


class Order(models.Model):
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='orders',
        verbose_name='Магазин'
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Общая сумма'
    )
    debt_increase = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Увеличение долга'
    )
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Ожидает'), ('confirmed', 'Подтвержден'), ('rejected', 'Отклонен'), ('cancelled', 'Отменен')],
        default='pending',
        verbose_name='Статус'
    )
    note = models.TextField(blank=True, verbose_name='Примечание')
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, verbose_name='Ключ идемпотентности')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'orders'
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        return f"Заказ {self.id} для {self.store.name}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Заказ'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name='Товар'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.1'))],
        verbose_name='Количество'
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за единицу'
    )

    class Meta:
        db_table = 'order_items'
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказов'

    def __str__(self):
        return f"{self.product.name}: {self.quantity} ({self.order.id})"

    @property
    def total(self):
        return self.quantity * self.price


class OrderHistory(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='history',
        verbose_name='Заказ'
    )
    type = models.CharField(
        max_length=20,
        choices=[('general', 'Общий'), ('bonus', 'Бонус'), ('defect', 'Брак'), ('sold', 'Проданный'), ('returned', 'Возвращенный')],
        verbose_name='Тип'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Сумма'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Количество'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Товар'
    )
    note = models.TextField(blank=True, verbose_name='Примечание')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'order_history'
        verbose_name = 'История заказа'
        verbose_name_plural = 'История заказов'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()} для заказа {self.order.id}"


class OrderReturn(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='returns',
        verbose_name='Заказ'
    )
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Ожидает'), ('approved', 'Подтвержден'), ('rejected', 'Отклонен')],
        default='pending',
        verbose_name='Статус'
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Общая сумма возврата'
    )
    reason = models.TextField(blank=True, verbose_name='Причина')
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, verbose_name='Ключ идемпотентности')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'order_returns'
        verbose_name = 'Возврат заказа'
        verbose_name_plural = 'Возвраты заказов'
        ordering = ['-created_at']

    def __str__(self):
        return f"Возврат для заказа {self.order.id}"


class OrderReturnItem(models.Model):
    return_order = models.ForeignKey(
        OrderReturn,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Возврат'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name='Товар'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.1'))],
        verbose_name='Количество'
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за единицу'
    )

    class Meta:
        db_table = 'order_return_items'
        verbose_name = 'Позиция возврата'
        verbose_name_plural = 'Позиции возвратов'

    def __str__(self):
        return f"{self.product.name}: {self.quantity} ({self.return_order.id})"

    @property
    def total(self):
        return self.quantity * self.price