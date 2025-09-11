from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from decimal import Decimal


# --- Запросы товаров от партнёров ---

class ProductRequest(models.Model):
    """Запрос товаров от партнёра (заявка на поставку)"""

    STATUS_CHOICES = [
        ('pending', 'Ожидает рассмотрения'),
        ('approved', 'Одобрен'),
        ('partially_approved', 'Частично одобрен'),
        ('rejected', 'Отклонён'),
        ('cancelled', 'Отменён'),
    ]

    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_requests',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнёр'
    )

    # Статус и даты
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата запроса')
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата рассмотрения')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_requests',
        verbose_name='Рассмотрел'
    )

    # Суммы
    total_requested_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Общая сумма запроса'
    )
    total_approved_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Одобренная сумма'
    )

    # Комментарии
    partner_notes = models.TextField(blank=True, verbose_name='Комментарий партнёра')
    admin_notes = models.TextField(blank=True, verbose_name='Комментарий администратора')

    class Meta:
        db_table = 'product_requests'
        verbose_name = 'Запрос товаров'
        verbose_name_plural = 'Запросы товаров'
        ordering = ['-requested_at']

    def __str__(self):
        return f"Запрос #{self.id} от {self.partner.get_full_name()}"

    def calculate_totals(self):
        """Пересчёт итоговых сумм"""
        items = self.items.all()

        self.total_requested_amount = sum(
            item.requested_quantity * item.unit_price for item in items
        )
        self.total_approved_amount = sum(
            item.get_approved_quantity() * item.unit_price for item in items
        )

        self.save(update_fields=['total_requested_amount', 'total_approved_amount'])

    def approve(self, reviewed_by, admin_notes=''):
        """Одобрить запрос"""
        self.status = 'approved'
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.admin_notes = admin_notes
        self.save()

        # Создаём поставки товаров
        self._create_supply_orders()

    def reject(self, reviewed_by, admin_notes=''):
        """Отклонить запрос"""
        self.status = 'rejected'
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.admin_notes = admin_notes
        self.save()

    def _create_supply_orders(self):
        """Создание заказов поставки товаров"""
        for item in self.items.filter(approved_quantity__gt=0):
            # Здесь будет логика создания заказов поставки
            pass


class ProductRequestItem(models.Model):
    """Позиция в запросе товаров"""

    request = models.ForeignKey(
        ProductRequest,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Запрос'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name='Товар'
    )

    # Количества
    requested_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Запрошенное количество'
    )
    approved_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Одобренное количество'
    )

    # Цена на момент запроса
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Цена за единицу'
    )

    # Комментарии
    notes = models.TextField(blank=True, verbose_name='Примечания')

    class Meta:
        db_table = 'product_request_items'
        verbose_name = 'Позиция запроса товаров'
        verbose_name_plural = 'Позиции запросов товаров'
        unique_together = ['request', 'product']

    def __str__(self):
        return f"{self.product.name} - {self.requested_quantity} {self.product.unit}"

    @property
    def total_requested_amount(self):
        """Общая сумма запрошенного товара"""
        return self.requested_quantity * self.unit_price

    @property
    def total_approved_amount(self):
        """Общая сумма одобренного товара"""
        approved_qty = self.approved_quantity or Decimal('0')
        return approved_qty * self.unit_price

    def get_approved_quantity(self):
        """Получить одобренное количество (если не указано, то запрошенное)"""
        return self.approved_quantity if self.approved_quantity is not None else self.requested_quantity


# --- Заказы клиентов в магазинах ---

class Order(models.Model):
    """Заказ клиента в магазине (продажа)"""

    STATUS_CHOICES = [
        ('pending', 'Ожидает подтверждения'),
        ('confirmed', 'Подтвержден'),
        ('completed', 'Выполнен'),
        ('cancelled', 'Отменен'),
    ]

    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='customer_orders',
        verbose_name='Магазин'
    )

    # Клиент (опционально)
    customer_name = models.CharField(max_length=200, blank=True, verbose_name='Имя клиента')
    customer_phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон клиента')
    customer_address = models.TextField(blank=True, verbose_name='Адрес клиента')

    # Статус и даты
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    order_date = models.DateTimeField(auto_now_add=True, verbose_name='Дата заказа')
    confirmed_date = models.DateTimeField(null=True, blank=True, verbose_name='Дата подтверждения')
    completed_date = models.DateTimeField(null=True, blank=True, verbose_name='Дата выполнения')
    delivery_date = models.DateTimeField(null=True, blank=True, verbose_name='Дата доставки')

    # Суммы
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Подытог'
    )
    bonus_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Скидка по бонусам'
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Итоговая сумма'
    )

    # Оплата
    payment_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Сумма оплаты'
    )
    debt_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Сумма долга'
    )

    # Бонусная информация
    bonus_items_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Количество бонусных товаров'
    )
    bonus_points_earned = models.PositiveIntegerField(
        default=0,
        verbose_name='Заработано бонусных очков'
    )
    bonus_points_used = models.PositiveIntegerField(
        default=0,
        verbose_name='Использовано бонусных очков'
    )

    # Доставка
    delivery_required = models.BooleanField(default=False, verbose_name='Требуется доставка')
    delivery_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        verbose_name='Стоимость доставки'
    )

    # Комментарии
    notes = models.TextField(blank=True, verbose_name='Комментарии к заказу')
    internal_notes = models.TextField(blank=True, verbose_name='Внутренние комментарии')

    # Метаданные
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Создал заказ'
    )

    class Meta:
        db_table = 'customer_orders'
        verbose_name = 'Заказ клиента'
        verbose_name_plural = 'Заказы клиентов'
        ordering = ['-order_date']
        indexes = [
            models.Index(fields=['store', 'status']),
            models.Index(fields=['order_date']),
            models.Index(fields=['customer_phone']),
        ]

    def __str__(self):
        return f"Заказ #{self.id} в {self.store.store_name}"

    def calculate_totals(self):
        """Пересчёт итоговых сумм заказа на основе его позиций"""
        items = self.items.all()

        self.subtotal = sum(item.total_price for item in items)
        self.bonus_discount = sum(item.bonus_discount for item in items)
        self.bonus_items_count = sum(item.bonus_quantity for item in items)
        self.bonus_points_earned = sum(item.bonus_points_earned for item in items)

        # Учитываем стоимость доставки
        self.total_amount = self.subtotal - self.bonus_discount + self.delivery_cost
        self.debt_amount = max(self.total_amount - self.payment_amount, Decimal('0'))

        self.save()

    def confirm(self):
        """Подтвердить заказ"""
        if self.status == 'pending':
            self.status = 'confirmed'
            self.confirmed_date = timezone.now()
            self.save()

    def complete(self):
        """Завершить заказ, списать товары и создать долг"""
        if self.status in ['pending', 'confirmed']:
            self.status = 'completed'
            self.completed_date = timezone.now()
            self.save()

            # Списываем товары со склада магазина
            for item in self.items.all():
                try:
                    inventory = self.store.inventory.get(product=item.product)
                    if inventory.quantity >= item.quantity:
                        inventory.quantity -= item.quantity
                        inventory.save()
                except ObjectDoesNotExist:
                    # Товара нет в инвентаре магазина
                    pass

            # Создаём долг, если оплачено не всё
            if self.debt_amount > 0:
                from apps.debts.models import Debt
                Debt.objects.create(
                    store=self.store,
                    amount=self.debt_amount,
                    order=self,
                    description=f'Долг по заказу #{self.id}',
                    due_date=timezone.now().date() + timezone.timedelta(days=30)
                )

            # Обновляем бонусную историю
            self._update_bonus_history()

    def cancel(self):
        """Отменить заказ"""
        if self.status in ['pending', 'confirmed']:
            self.status = 'cancelled'
            self.save()

            # Возвращаем зарезервированные товары
            for item in self.items.all():
                item.product.release_quantity(item.quantity)

    def _update_bonus_history(self):
        """Обновление истории бонусов"""
        from apps.bonuses.models import BonusHistory

        for item in self.items.all():
            if item.bonus_quantity > 0:
                BonusHistory.objects.create(
                    store=self.store,
                    product=item.product,
                    order=self,
                    bonus_items=item.bonus_quantity,
                    total_items_purchased=item.quantity + item.bonus_quantity
                )


class OrderItem(models.Model):
    """Позиция в заказе клиента"""

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

    # Количества
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Количество'
    )
    bonus_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Бонусное количество'
    )

    # Цены на момент заказа
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Цена за единицу'
    )
    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Общая стоимость'
    )
    bonus_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Скидка за бонусные товары'
    )

    # Бонусы
    bonus_points_earned = models.PositiveIntegerField(
        default=0,
        verbose_name='Заработано бонусных очков'
    )

    # Себестоимость (для расчёта прибыли)
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Себестоимость за единицу'
    )

    class Meta:
        db_table = 'order_items'
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказов'
        unique_together = ['order', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def save(self, *args, **kwargs):
        """Автоматический расчёт полей при сохранении"""
        # Рассчитываем общую стоимость
        self.total_price = self.quantity * self.unit_price

        # Рассчитываем скидку за бонусные товары
        self.bonus_discount = self.bonus_quantity * self.unit_price

        # Рассчитываем бонусные очки
        if self.product.is_bonus_eligible:
            self.bonus_points_earned = int(self.quantity) * self.product.bonus_points

        # Берём текущую себестоимость товара
        if not self.cost_price:
            self.cost_price = self.product.cost_price

        super().save(*args, **kwargs)

    @property
    def profit_amount(self):
        """Прибыль с позиции"""
        return (self.unit_price - self.cost_price) * self.quantity

    @property
    def total_quantity(self):
        """Общее количество (купленное + бонусное)"""
        return self.quantity + self.bonus_quantity


# --- Корзина (временное хранение) ---

class Cart(models.Model):
    """Корзина магазина"""

    store = models.OneToOneField(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='cart',
        verbose_name='Магазин'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        db_table = 'carts'
        verbose_name = 'Корзина'
        verbose_name_plural = 'Корзины'

    def __str__(self):
        return f"Корзина {self.store.store_name}"

    @property
    def total_amount(self):
        """Общая сумма корзины"""
        return sum(item.total_price for item in self.items.all())

    @property
    def items_count(self):
        """Количество позиций в корзине"""
        return self.items.count()

    def clear(self):
        """Очистить корзину"""
        self.items.all().delete()


class CartItem(models.Model):
    """Позиция в корзине"""

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Корзина'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name='Товар'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Количество'
    )
    added_at = models.DateTimeField(auto_now_add=True, verbose_name='Добавлен')

    class Meta:
        db_table = 'cart_items'
        verbose_name = 'Позиция корзины'
        verbose_name_plural = 'Позиции корзины'
        unique_together = ['cart', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def total_price(self):
        """Общая стоимость позиции"""
        return self.quantity * self.product.price