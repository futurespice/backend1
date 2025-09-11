from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal


class Store(models.Model):
    """Модель магазина"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
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

    # Связи
    region = models.ForeignKey(
        'regions.Region',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stores',
        verbose_name='Регион'
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='partner_stores',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнёр'
    )

    # Статус
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'stores'
        verbose_name = 'Магазин'
        verbose_name_plural = 'Магазины'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.store_name} ({self.user.get_full_name()})"

    @property
    def total_debt(self):
        """Общий долг магазина"""
        try:
            from apps.debts.models import Debt
            total = Debt.objects.filter(
                store=self,
                is_paid=False
            ).aggregate(
                total=models.Sum('amount')
            )['total']
            return total or Decimal('0')
        except:
            return Decimal('0')

    @property
    def orders_count(self):
        """Количество заказов"""
        return self.orders.count()

    def get_inventory_for_product(self, product):
        """Получить остаток товара в магазине"""
        try:
            inventory = self.inventory.get(product=product)
            return inventory.available_quantity
        except StoreInventory.DoesNotExist:
            return Decimal('0')


class StoreInventory(models.Model):
    """Остатки товаров в магазинах"""

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
        max_digits=10,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество'
    )
    reserved_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Зарезервировано'
    )
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Последнее обновление')

    class Meta:
        db_table = 'store_inventory'
        verbose_name = 'Остаток товара'
        verbose_name_plural = 'Остатки товаров'
        unique_together = ['store', 'product']
        ordering = ['store', 'product']

    def __str__(self):
        return f"{self.store.store_name} - {self.product.name}: {self.available_quantity}"

    @property
    def available_quantity(self):
        """Доступное количество (общее - зарезервированное)"""
        return self.quantity - self.reserved_quantity

    def reserve_quantity(self, amount):
        """Зарезервировать количество"""
        if amount <= self.available_quantity:
            self.reserved_quantity += amount
            self.save()
            return True
        return False

    def release_reservation(self, amount):
        """Освободить резерв"""
        if amount <= self.reserved_quantity:
            self.reserved_quantity -= amount
            self.save()
            return True
        return False

    def reduce_quantity(self, amount):
        """Уменьшить количество (при отгрузке)"""
        if amount <= self.quantity:
            self.quantity -= amount
            # Также уменьшаем резерв, если он есть
            if self.reserved_quantity > 0:
                reduction_from_reserve = min(amount, self.reserved_quantity)
                self.reserved_quantity -= reduction_from_reserve
            self.save()
            return True
        return False


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
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='partner_requests',
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
        total = self.items.aggregate(
            total=models.Sum('quantity')
        )['total']
        return total or Decimal('0')

    def can_be_cancelled(self):
        """Можно ли отменить запрос"""
        return self.status in ['pending', 'approved']

    def can_be_approved(self):
        """Можно ли одобрить запрос"""
        return self.status == 'pending'


class PartnerInventory(models.Model):
    """Инвентарь партнёра (виртуальный склад)"""

    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='partner_inventory',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнёр'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='partner_inventory',
        verbose_name='Товар'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество'
    )
    reserved_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Зарезервировано'
    )
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Последнее обновление')

    class Meta:
        db_table = 'partner_inventory'
        verbose_name = 'Инвентарь партнёра'
        verbose_name_plural = 'Инвентари партнёров'
        unique_together = ['partner', 'product']
        ordering = ['partner', 'product']

    def __str__(self):
        return f"{self.partner.get_full_name()} - {self.product.name}: {self.available_quantity}"

    @property
    def available_quantity(self):
        """Доступное количество"""
        return self.quantity - self.reserved_quantity


# apps/stores/models.py - исправляем AdminInventory
class AdminInventory(models.Model):
    """Позиции в запросе товаров (переименованная модель)"""

    request = models.ForeignKey(
        StoreRequest,
        on_delete=models.CASCADE,
        related_name='items',  # оставляем как есть
        verbose_name='Запрос'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='request_items',
        verbose_name='Товар'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Количество'
    )

    # Дополнительные поля для обработки
    approved_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Одобренное количество'
    )
    delivered_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Доставленное количество'
    )

    class Meta:
        db_table = 'store_request_items'
        verbose_name = 'Позиция запроса'
        verbose_name_plural = 'Позиции запросов'
        unique_together = ['request', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def final_quantity(self):
        """Итоговое количество"""
        return self.delivered_quantity or self.approved_quantity or self.quantity


# apps/stores/models.py - добавляем новую модель для главного склада
class MainInventory(models.Model):
    """Главный склад администратора"""

    product = models.OneToOneField(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='main_inventory',
        verbose_name='Товар'
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество на главном складе'
    )
    reserved_for_partners = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Зарезервировано для партнёров'
    )
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Последнее обновление')

    class Meta:
        db_table = 'main_inventory'
        verbose_name = 'Главный склад'
        verbose_name_plural = 'Главный склад'

    def __str__(self):
        return f"Главный склад - {self.product.name}: {self.available_quantity}"

    @property
    def available_quantity(self):
        """Доступное для выдачи партнёрам"""
        return self.quantity - self.reserved_for_partners