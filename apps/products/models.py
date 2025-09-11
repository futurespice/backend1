from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils.text import slugify


class Category(models.Model):
    """Категория товаров"""

    name = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    slug = models.SlugField(max_length=200, unique=True, blank=True, verbose_name='Слаг')
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Родительская категория'
    )
    image = models.ImageField(
        upload_to='categories/',
        blank=True,
        null=True,
        verbose_name='Изображение'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Порядок сортировки')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'product_categories'
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        """Полное имя категории с иерархией"""
        parts = []
        current = self
        while current:
            parts.append(current.name)
            current = current.parent
        return " > ".join(reversed(parts))

    def get_all_children(self):
        """Получить всех потомков рекурсивно"""
        children = []
        for child in self.children.all():
            children.append(child)
            children.extend(child.get_all_children())
        return children

    def get_products_count(self):
        """Количество товаров в категории и подкатегориях"""
        children_ids = [child.id for child in self.get_all_children()]
        children_ids.append(self.id)
        return Product.objects.filter(category_id__in=children_ids, is_active=True).count()


class Product(models.Model):
    """Модель товара"""

    UNIT_CHOICES = [
        ('kg', 'кг'),
        ('g', 'г'),
        ('l', 'л'),
        ('ml', 'мл'),
        ('pcs', 'шт'),
        ('pack', 'упак'),
        ('box', 'коробка'),
        ('bag', 'мешок'),
    ]

    # Основная информация
    name = models.CharField(max_length=200, verbose_name='Название товара')
    description = models.TextField(blank=True, verbose_name='Описание')
    article = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Артикул')
    slug = models.SlugField(max_length=200, unique=True, blank=True, verbose_name='Слаг')

    # Категория
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name='Категория'
    )

    # Цена и единицы измерения
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Цена'
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        default=0,
        verbose_name='Себестоимость'
    )
    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default='pcs',
        verbose_name='Единица измерения'
    )

    # Остатки и наличие
    stock_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Остаток на складе'
    )
    low_stock_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=10,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Минимальный остаток'
    )

    # Бонусная система
    is_bonus_eligible = models.BooleanField(
        default=True,
        verbose_name='Участвует в бонусной программе'
    )
    bonus_points = models.PositiveIntegerField(
        default=1,
        verbose_name='Бонусные очки за товар'
    )

    # Изображения
    main_image = models.ImageField(
        upload_to='products/main/',
        blank=True,
        null=True,
        verbose_name='Главное изображение'
    )

    # Характеристики
    weight = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name='Вес (кг)'
    )
    volume = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name='Объём (л)'
    )

    # Статусы
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    is_available = models.BooleanField(default=True, verbose_name='Доступен для заказа')

    # Производство
    production_time_days = models.PositiveIntegerField(
        default=1,
        verbose_name='Время производства (дни)'
    )
    shelf_life_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Срок годности (дни)'
    )

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Создал'
    )

    class Meta:
        db_table = 'products'
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['article']),
            models.Index(fields=['category']),
            models.Index(fields=['is_active', 'is_available']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        if not self.article:
            # Генерируем артикул автоматически
            self.article = f"ART-{self.category.id}-{self.id or '000'}"
        super().save(*args, **kwargs)

    @property
    def is_in_stock(self):
        """Есть ли товар в наличии"""
        return self.stock_quantity > 0

    @property
    def is_low_stock(self):
        """Мало товара на складе"""
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def profit_margin(self):
        """Процент прибыли"""
        if self.cost_price > 0:
            return ((self.price - self.cost_price) / self.cost_price) * 100
        return 0

    @property
    def profit_amount(self):
        """Сумма прибыли с единицы"""
        return self.price - self.cost_price

    def can_fulfill_quantity(self, quantity):
        """Можно ли выполнить заказ на указанное количество"""
        return self.stock_quantity >= quantity

    def reserve_quantity(self, quantity):
        """Резервирование товара"""
        if self.can_fulfill_quantity(quantity):
            self.stock_quantity -= quantity
            self.save(update_fields=['stock_quantity'])
            return True
        return False

    def release_quantity(self, quantity):
        """Освобождение зарезервированного товара"""
        self.stock_quantity += quantity
        self.save(update_fields=['stock_quantity'])


class ProductImage(models.Model):
    """Дополнительные изображения товара"""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name='Товар'
    )
    image = models.ImageField(
        upload_to='products/gallery/',
        verbose_name='Изображение'
    )
    title = models.CharField(max_length=200, blank=True, verbose_name='Название')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Добавлено')

    class Meta:
        db_table = 'product_images'
        verbose_name = 'Изображение товара'
        verbose_name_plural = 'Изображения товаров'
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return f"{self.product.name} - {self.title or 'Изображение'}"


class ProductCharacteristic(models.Model):
    """Характеристики товара"""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='characteristics',
        verbose_name='Товар'
    )
    name = models.CharField(max_length=100, verbose_name='Название характеристики')
    value = models.CharField(max_length=200, verbose_name='Значение')
    unit = models.CharField(max_length=20, blank=True, verbose_name='Единица измерения')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        db_table = 'product_characteristics'
        verbose_name = 'Характеристика товара'
        verbose_name_plural = 'Характеристики товаров'
        ordering = ['sort_order', 'name']
        unique_together = ['product', 'name']

    def __str__(self):
        return f"{self.product.name} - {self.name}: {self.value}"


class ProductPriceHistory(models.Model):
    """История изменения цен"""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='price_history',
        verbose_name='Товар'
    )
    old_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Старая цена'
    )
    new_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Новая цена'
    )
    changed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Изменил'
    )
    reason = models.CharField(max_length=200, blank=True, verbose_name='Причина изменения')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата изменения')

    class Meta:
        db_table = 'product_price_history'
        verbose_name = 'История цен'
        verbose_name_plural = 'История цен'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.name} - {self.old_price} → {self.new_price}"