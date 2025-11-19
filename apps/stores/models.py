# apps/stores/models.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction


class Region(models.Model):
    """Регион/Область"""
    # ИСПРАВЛЕНИЕ #1: Убрано ненужное поле code
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')

    class Meta:
        db_table = 'regions'
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'
        ordering = ['name']

    def __str__(self):
        return self.name


class City(models.Model):
    """Город"""
    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name='cities',
        verbose_name='Регион'
    )
    name = models.CharField(max_length=100, verbose_name='Название')

    class Meta:
        db_table = 'cities'
        verbose_name = 'Город'
        verbose_name_plural = 'Города'
        ordering = ['region', 'name']
        unique_together = ['region', 'name']

    def __str__(self):
        return f"{self.name} ({self.region.name})"


class Store(models.Model):
    """
    Магазин - общая сущность.
    Любой пользователь с ролью STORE может выбрать магазин и работать от его имени.
    """
    # ИСПРАВЛЕНИЕ #13: ИНН валидация 12-14 цифр
    inn_regex = RegexValidator(
        regex=r'^\d{12,14}$',
        message='ИНН должен быть 12-14 цифр'
    )

    phone_regex = RegexValidator(
        regex=r'^\+996\d{9}$',
        message="Формат: +996XXXXXXXXX"
    )

    # Основная информация
    name = models.CharField(max_length=200, verbose_name='Название магазина')
    inn = models.CharField(
        max_length=14,
        validators=[inn_regex],
        unique=True,
        verbose_name='ИНН'
    )
    owner_name = models.CharField(max_length=200, verbose_name='ФИО владельца')
    phone = models.CharField(
        max_length=13,
        validators=[phone_regex],
        verbose_name='Телефон'
    )

    # Местоположение
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        verbose_name='Регион'
    )
    city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        verbose_name='Город'
    )
    address = models.CharField(max_length=250, verbose_name='Адрес')
    latitude = models.FloatField(null=True, blank=True, verbose_name='Широта')
    longitude = models.FloatField(null=True, blank=True, verbose_name='Долгота')

    # Финансы
    debt = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Долг'
    )

    # Статус
    approval_status = models.CharField(
        max_length=20,
        choices=[('pending', 'Ожидает'), ('approved', 'Принят'), ('rejected', 'Отклонен')],
        default='pending',
        verbose_name='Статус одобрения'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    # Системная информация
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Создал'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'stores'
        verbose_name = 'Магазин'
        verbose_name_plural = 'Магазины'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['inn', 'phone'])]

    def clean(self):
        if self.city and self.region and self.city.region != self.region:
            raise ValidationError({'city': 'Город должен принадлежать выбранному региону'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class StoreSelection(models.Model):
    """Выбор магазина пользователем (роль STORE)"""
    user = models.ForeignKey(  # Изменил с OneToOne на ForeignKey
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'store'},
        related_name='store_selections',  # Для multiple
        verbose_name='Пользователь'
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='selections',
        verbose_name='Магазин'
    )
    selected_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата выбора')

    class Meta:
        db_table = 'store_selections'
        unique_together = []
        verbose_name = 'Выбор магазина'
        verbose_name_plural = 'Выборы магазинов'

    def __str__(self):
        return f"{self.user.name} → {self.store.name} ({self.selected_at})"


class StoreProductRequest(models.Model):
    """
    Запрос магазина на товар (временный список "корзины")
    НЕ влияет на инвентарь, пока не подтверждён партнёром
    """
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='product_requests',
        verbose_name='Магазин'
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
        verbose_name='Запрошенное количество'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'store_product_requests'
        verbose_name = 'Запрос товара'
        verbose_name_plural = 'Запросы товаров'
        unique_together = ['store', 'product']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.store.name} → {self.product.name}: {self.quantity}"


class StoreRequest(models.Model):
    """
    История запросов магазина.
    Создается из StoreProductRequest (wishlist).
    Без статусов — просто snapshot wishlist'а.
    """
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='requests',
        verbose_name='Магазин'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Создал'
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

    # ИСПРАВЛЕНИЕ #11: Защита от race condition
    idempotency_key = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Ключ идемпотентности'
    )

    class Meta:
        db_table = 'store_requests'
        verbose_name = 'Запрос магазина'
        verbose_name_plural = 'Запросы магазинов'
        ordering = ['-created_at']
        # Убрали unique_together — multiple requests per store ок (история)

    def __str__(self):
        return f"Запрос {self.id} для {self.store.name} ({self.total_amount} сом)"


class StoreRequestItem(models.Model):
    """Позиция в запросе магазина"""
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
    is_cancelled = models.BooleanField(default=False, verbose_name='Отменено')

    class Meta:
        db_table = 'store_request_items'
        verbose_name = 'Позиция запроса'
        verbose_name_plural = 'Позиции запросов'

    def __str__(self):
        return f"{self.product.name}: {self.quantity} ({self.request.id})"

    @property
    def total(self) -> Decimal:  # ИСПРАВЛЕНИЕ #19: типизация
        """Общая стоимость позиции"""
        return self.quantity * self.price


class StoreInventory(models.Model):
    """Инвентарь магазина"""
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='inventory',
        verbose_name='Магазин'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name='Товар'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество'
    )
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Последнее обновление')

    class Meta:
        db_table = 'store_inventory'
        verbose_name = 'Инвентарь магазина'
        verbose_name_plural = 'Инвентарь магазинов'
        unique_together = ['store', 'product']

    def __str__(self):
        return f"{self.store.name} - {self.product.name}: {self.quantity} {self.product.get_unit_display()}"

    @property
    def total_price(self) -> Decimal:  # ИСПРАВЛЕНИЕ #19: типизация
        """Общая стоимость товара в инвентаре"""
        if self.product and self.product.price:
            return self.quantity * self.product.price
        return Decimal('0')

    def check_stock(self, quantity):
        """Проверка достаточности на складе"""
        if self.quantity < quantity:
            raise ValidationError(f"Недостаточно товара: {self.product.name}. Доступно: {self.quantity}")


class PartnerInventory(models.Model):
    """Инвентарь партнёра (личный склад партнёра)"""
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'partner'},
        related_name='inventory',
        verbose_name='Партнёр'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name='Товар'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество'
    )
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Последнее обновление')

    class Meta:
        db_table = 'partner_inventory'
        verbose_name = 'Инвентарь партнёра'
        verbose_name_plural = 'Инвентарь партнёров'
        unique_together = ['partner', 'product']

    def __str__(self):
        return f"{self.partner.name} - {self.product.name}: {self.quantity}"

    def check_stock(self, quantity):
        """Проверка достаточности на складе"""
        if self.quantity < quantity:
            raise ValidationError(f"Недостаточно товара: {self.product.name}. Доступно: {self.quantity}")


class ReturnRequest(models.Model):
    """Запрос на возврат товаров от партнера к админу"""
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='partner_return_requests',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='return_requests',
        verbose_name='Магазин',
        null=True,
        blank=True
    )
    order = models.ForeignKey(
        'orders.PartnerOrder',  # ИСПРАВЛЕНИЕ #5: ссылка на правильную модель заказа
        on_delete=models.CASCADE,
        related_name='return_requests',
        verbose_name='Заказ',
        null=True,
        blank=True
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
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    # ИСПРАВЛЕНИЕ #11: Защита от race condition
    idempotency_key = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Ключ идемпотентности'
    )

    class Meta:
        db_table = 'return_requests'
        verbose_name = 'Запрос на возврат'
        verbose_name_plural = 'Запросы на возврат'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['partner', 'created_at']),
            models.Index(fields=['idempotency_key']),
        ]

    def __str__(self):
        return f"Возврат {self.id} от партнера {self.partner.name}"


class ReturnRequestItem(models.Model):
    """Позиция в запросе на возврат"""
    request = models.ForeignKey(
        ReturnRequest,
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
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.1'))],
        verbose_name='Количество'
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),  # ИСПРАВЛЕНИЕ #17/#18: default для price
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Цена за единицу'
    )

    class Meta:
        db_table = 'return_request_items'
        verbose_name = 'Позиция возврата'
        verbose_name_plural = 'Позиции возвратов'

    def __str__(self):
        return f"{self.product.name}: {self.quantity} ({self.request.id})"

    @property
    def total(self) -> Decimal:  # ИСПРАВЛЕНИЕ #19: типизация
        """Общая стоимость позиции"""
        if self.price is not None:
            return self.quantity * self.price
        return Decimal('0')