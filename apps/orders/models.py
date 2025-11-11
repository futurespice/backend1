# apps/orders/models.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.core.exceptions import ValidationError

from products.models import Product
from stores.models import Store, StoreRequest


class PartnerOrder(models.Model):
    """
    ИСПРАВЛЕНИЕ #5: Заказ партнёра → админу
    Это заказ партнера на пополнение своего склада у админа
    """
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'partner'},
        related_name='partner_orders',
        verbose_name='Партнёр'
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Ожидает подтверждения'),
            ('confirmed', 'Подтверждён'),
            ('processing', 'Обработка'),
            ('shipped', 'Отправлен'),
            ('delivered', 'Доставлен'),
            ('cancelled', 'Отменён'),
        ],
        default='pending',
        verbose_name='Статус'
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Общая сумма'
    )

    note = models.TextField(blank=True, verbose_name='Примечание')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    # ИСПРАВЛЕНИЕ #11: Защита от race condition
    idempotency_key = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Ключ идемпотентности'
    )

    class Meta:
        db_table = 'partner_orders'
        verbose_name = 'Заказ партнёра'
        verbose_name_plural = 'Заказы партнёров'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['partner', 'created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['idempotency_key']),
        ]

    def __str__(self):
        return f"Заказ партнёра {self.id} от {self.partner.name}"


class PartnerOrderItem(models.Model):
    """Позиция в заказе партнёра"""
    order = models.ForeignKey(
        PartnerOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Заказ'
    )
    product = models.ForeignKey(
        Product,
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
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за единицу'
    )

    class Meta:
        db_table = 'partner_order_items'
        verbose_name = 'Позиция заказа партнёра'
        verbose_name_plural = 'Позиции заказов партнёров'

    def __str__(self):
        return f"{self.product.name}: {self.quantity} ({self.order.id})"

    @property
    def total(self) -> Decimal:
        """Общая стоимость позиции"""
        return self.quantity * self.price


class StoreOrder(models.Model):
    """
    ИСПРАВЛЕНИЕ #5-6: Заказ магазина → партнёру
    Создается из StoreRequest после подтверждения партнёром
    """
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='store_orders',
        verbose_name='Магазин'
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={'role': 'partner'},
        related_name='store_orders_as_partner',
        verbose_name='Партнёр'
    )

    # Ссылка на запрос магазина
    store_request = models.ForeignKey(
        StoreRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name='Запрос магазина'
    )

    # У заказа магазина НЕТ статусов - партнёр просто принимает или отклоняет
    is_fulfilled = models.BooleanField(default=False, verbose_name='Выполнен')

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Общая сумма'
    )

    bonus_applied = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Применён бонус'
    )

    note = models.TextField(blank=True, verbose_name='Примечание')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    # ИСПРАВЛЕНИЕ #11: Защита от race condition
    idempotency_key = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Ключ идемпотентности'
    )

    class Meta:
        db_table = 'store_orders'
        verbose_name = 'Заказ магазина'
        verbose_name_plural = 'Заказы магазинов'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'created_at']),
            models.Index(fields=['partner', 'created_at']),
            models.Index(fields=['is_fulfilled']),
            models.Index(fields=['idempotency_key']),
        ]

    def __str__(self):
        return f"Заказ {self.id} для {self.store.name}"


class StoreOrderItem(models.Model):
    """Позиция в заказе магазина"""
    order = models.ForeignKey(
        StoreOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Заказ'
    )
    product = models.ForeignKey(
        Product,
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
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за единицу'
    )

    # ИСПРАВЛЕНИЕ #12: Признак бонусной позиции
    is_bonus = models.BooleanField(default=False, verbose_name='Бонусная позиция')

    class Meta:
        db_table = 'store_order_items'
        verbose_name = 'Позиция заказа магазина'
        verbose_name_plural = 'Позиции заказов магазинов'

    def __str__(self):
        return f"{self.product.name}: {self.quantity} ({self.order.id})"

    @property
    def total(self) -> Decimal:
        """Общая стоимость позиции"""
        if self.is_bonus:
            return Decimal('0')  # Бонусные позиции не учитываются в сумме
        return self.quantity * self.price


class OrderHistory(models.Model):
    """История операций по заказам"""
    # Полиморфная связь с заказами
    order_type = models.CharField(
        max_length=20,
        choices=[('partner', 'Заказ партнёра'), ('store', 'Заказ магазина')],
        verbose_name='Тип заказа'
    )
    order_id = models.PositiveIntegerField(verbose_name='ID заказа')

    type = models.CharField(
        max_length=20,
        choices=[
            ('general', 'Общий'),
            ('bonus', 'Бонус'),
            ('defect', 'Брак'),
            ('sold', 'Проданный'),
            ('returned', 'Возвращенный')
        ],
        verbose_name='Тип'
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Товар'
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Сумма')
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Количество'
    )
    note = models.TextField(blank=True, verbose_name='Примечание')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'order_history'
        verbose_name = 'История заказа'
        verbose_name_plural = 'История заказов'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_type', 'order_id']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.type} для заказа {self.order_id} ({self.created_at})"


class OrderReturn(models.Model):
    """
    ИСПРАВЛЕНИЕ #8: Возврат товаров по заказу
    (от магазина к партнёру)
    """
    order = models.ForeignKey(
        StoreOrder,  # Только заказы магазинов можно возвращать
        on_delete=models.CASCADE,
        related_name='returns',
        verbose_name='Заказ'
    )

    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Ожидает'), ('approved', 'Подтверждён'), ('rejected', 'Отклонён')],
        default='pending',
        verbose_name='Статус'
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Сумма возврата'
    )

    reason = models.TextField(verbose_name='Причина возврата')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    # ИСПРАВЛЕНИЕ #11: Защита от race condition
    idempotency_key = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Ключ идемпотентности'
    )

    class Meta:
        db_table = 'order_returns'
        verbose_name = 'Возврат товаров'
        verbose_name_plural = 'Возвраты товаров'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['idempotency_key']),
        ]

    def __str__(self):
        return f"Возврат по заказу {self.order.id}"


class OrderReturnItem(models.Model):
    """Позиция в возврате товаров"""
    return_request = models.ForeignKey(
        OrderReturn,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Возврат'
    )
    product = models.ForeignKey(
        Product,
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
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за единицу'
    )

    class Meta:
        db_table = 'order_return_items'
        verbose_name = 'Позиция возврата'
        verbose_name_plural = 'Позиции возвратов'

    def __str__(self):
        return f"{self.product.name}: {self.quantity}"

    @property
    def total(self) -> Decimal:
        """Общая стоимость возврата"""
        return self.quantity * self.price