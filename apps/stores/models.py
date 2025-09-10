from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal

User = get_user_model()


class Store(models.Model):
    """Модель магазина"""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='store_profile',
        verbose_name='Пользователь'
    )
    store_name = models.CharField(max_length=200, verbose_name='Название магазина')
    address = models.TextField(verbose_name='Адрес')

    # GPS координаты
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Широта'
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Долгота'
    )

    # Регион
    region = models.ForeignKey(
        'regions.Region',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stores',
        verbose_name='Регион'
    )

    # Партнёр, который обслуживает магазин
    partner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='partner_stores',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнёр'
    )

    # Статусы и метаданные
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'stores'
        verbose_name = 'Магазин'
        verbose_name_plural = 'Магазины'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.store_name} - {self.user.get_full_name()}"

    @property
    def total_debt(self):
        """Общий долг магазина"""
        from apps.debts.models import Debt
        return Debt.objects.filter(
            store=self,
            is_paid=False
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')

    @property
    def orders_count(self):
        """Количество заказов"""
        return self.orders.count()

    def get_coordinates(self):
        """Получить координаты"""
        if self.latitude and self.longitude:
            return {
                'latitude': float(self.latitude),
                'longitude': float(self.longitude)
            }
        return None


class StoreInventory(models.Model):
    """Остатки товаров в магазине (виртуальный склад)"""

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='inventory',
        verbose_name='Магазин'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='store_inventory',
        verbose_name='Товар'
    )
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество'
    )
    reserved_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Зарезервировано'
    )

    # Метаданные
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Последнее обновление')

    class Meta:
        db_table = 'store_inventory'
        verbose_name = 'Остаток в магазине'
        verbose_name_plural = 'Остатки в магазинах'
        unique_together = ['store', 'product']
        ordering = ['store', 'product__name']

    def __str__(self):
        return f"{self.store.store_name} - {self.product.name}: {self.quantity}"

    @property
    def available_quantity(self):
        """Доступное количество (общее - зарезервированное)"""
        return self.quantity - self.reserved_quantity

    def update_quantity(self, amount, operation='add'):
        """Обновление количества товара"""
        if operation == 'add':
            self.quantity += Decimal(str(amount))
        elif operation == 'subtract':
            if self.quantity >= Decimal(str(amount)):
                self.quantity -= Decimal(str(amount))
            else:
                raise ValueError("Недостаточно товара на складе")
        elif operation == 'set':
            self.quantity = Decimal(str(amount))

        self.save()

    def reserve_quantity(self, amount):
        """Резервирование товара"""
        if self.available_quantity >= Decimal(str(amount)):
            self.reserved_quantity += Decimal(str(amount))
            self.save()
        else:
            raise ValueError("Недостаточно товара для резервирования")

    def release_reservation(self, amount):
        """Освобождение резерва"""
        if self.reserved_quantity >= Decimal(str(amount)):
            self.reserved_quantity -= Decimal(str(amount))
            self.save()


class StoreRequest(models.Model):
    """Запросы товаров от магазинов"""

    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонён'),
        ('delivered', 'Доставлен'),
        ('cancelled', 'Отменён'),
    ]

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='requests',
        verbose_name='Магазин'
    )
    partner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='store_requests',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнёр'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )

    # Даты
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата запроса')
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата обработки')
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата доставки')

    # Комментарии
    store_notes = models.TextField(blank=True, verbose_name='Комментарий магазина')
    partner_notes = models.TextField(blank=True, verbose_name='Комментарий партнёра')

    class Meta:
        db_table = 'store_requests'
        verbose_name = 'Запрос товаров'
        verbose_name_plural = 'Запросы товаров'
        ordering = ['-requested_at']

    def __str__(self):
        return f"Запрос #{self.id} от {self.store.store_name}"

    @property
    def total_items(self):
        """Общее количество позиций"""
        return self.items.count()

    @property
    def total_quantity(self):
        """Общее количество товаров"""
        return self.items.aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

    def approve(self, partner_user):
        """Одобрить запрос"""
        from django.utils import timezone

        self.status = 'approved'
        self.processed_at = timezone.now()
        self.save()

        # Перемещаем товары на виртуальный склад магазина
        for item in self.items.all():
            inventory, created = StoreInventory.objects.get_or_create(
                store=self.store,
                product=item.product,
                defaults={'quantity': Decimal('0')}
            )
            inventory.update_quantity(item.quantity, 'add')

    def reject(self, partner_user, reason=""):
        """Отклонить запрос"""
        from django.utils import timezone

        self.status = 'rejected'
        self.processed_at = timezone.now()
        if reason:
            self.partner_notes = reason
        self.save()


class StoreRequestItem(models.Model):
    """Позиция в запросе товаров"""

    request = models.ForeignKey(
        StoreRequest,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Запрос'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name='Товар'
    )
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Количество'
    )

    class Meta:
        db_table = 'store_request_items'
        verbose_name = 'Позиция запроса'
        verbose_name_plural = 'Позиции запросов'
        unique_together = ['request', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"