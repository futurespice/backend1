from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class ProductCategory(models.Model):
    """Категория товаров"""
    CATEGORY_TYPES = [
        ('piece', 'Штучный'),
        ('weight', 'Весовой'),
    ]

    name = models.CharField(max_length=100, unique=True, verbose_name='Название категории')
    category_type = models.CharField(max_length=10, choices=CATEGORY_TYPES, default='piece',
                                     verbose_name='Тип категории')
    description = models.TextField(blank=True, verbose_name='Описание')
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_categories'
        verbose_name = 'Категория товаров'
        verbose_name_plural = 'Категории товаров'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"


class Product(models.Model):
    """Товар"""
    CATEGORY_TYPES = [
        ('piece', 'Штучный'),
        ('weight', 'Весовой'),
    ]

    # Основная информация
    name = models.CharField(max_length=200, verbose_name='Название товара')
    description = models.TextField(max_length=250, blank=True, verbose_name='Описание')
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='Категория'
    )

    # Тип товара
    category_type = models.CharField(
        max_length=10,
        choices=CATEGORY_TYPES,
        default='piece',
        verbose_name='Тип товара'
    )

    # Цена и количество
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Цена'
    )

    # Для штучных товаров - количество штук, для весовых - килограммы
    stock_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,  # Для весовых товаров с точностью до грамма
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество на складе'
    )

    # Минимальный порог для весовых товаров
    min_order_quantity = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal('0.1'),  # 100 грамм
        validators=[MinValueValidator(Decimal('0.1'))],
        verbose_name='Минимальное количество для заказа'
    )

    # Бонусная система
    is_bonus_eligible = models.BooleanField(
        default=True,
        verbose_name='Участвует в бонусной программе',
        help_text='Весовые товары не могут быть бонусными'
    )

    # Статус
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    is_available = models.BooleanField(default=True, verbose_name='Доступен для заказа')

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'products'
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.price} сом)"

    def save(self, *args, **kwargs):
        # Весовые товары не могут быть бонусными
        if self.category_type == 'weight':
            self.is_bonus_eligible = False

        # Устанавливаем минимальный порог для весовых товаров
        if self.category_type == 'weight':
            if self.stock_quantity < 1:
                self.min_order_quantity = Decimal('0.1')  # 100 грамм
            else:
                self.min_order_quantity = Decimal('1.0')  # 1 кг
        else:
            self.min_order_quantity = Decimal('1.0')  # 1 штука

        super().save(*args, **kwargs)

    @property
    def price_per_100g(self):
        """Цена за 100 грамм для весовых товаров"""
        if self.category_type == 'weight':
            return self.price / 10
        return None

    def calculate_price(self, quantity):
        """Рассчитать цену за указанное количество"""
        if self.category_type == 'weight':
            # Для весовых: цена за 100г * (вес / 0.1)
            return self.price_per_100g * (quantity / Decimal('0.1'))
        else:
            # Для штучных: цена * количество
            return self.price * quantity

    def is_in_stock(self, requested_quantity=None):
        """Проверить наличие товара на складе"""
        if requested_quantity is None:
            return self.stock_quantity > 0
        return self.stock_quantity >= requested_quantity

    def reduce_stock(self, quantity):
        """Уменьшить количество на складе"""
        if self.is_in_stock(quantity):
            self.stock_quantity -= quantity
            self.save()
            return True
        return False

    def increase_stock(self, quantity):
        """Увеличить количество на складе"""
        self.stock_quantity += quantity
        self.save()


class ProductImage(models.Model):
    """Изображения товаров"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/', verbose_name='Изображение')
    is_primary = models.BooleanField(default=False, verbose_name='Основное изображение')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_images'
        verbose_name = 'Изображение товара'
        verbose_name_plural = 'Изображения товаров'
        ordering = ['order', 'created_at']

    def save(self, *args, **kwargs):
        # Если это первое изображение товара, делаем его основным
        if not self.product.images.exists():
            self.is_primary = True
        # Если установили как основное, убираем флаг с других
        elif self.is_primary:
            self.product.images.update(is_primary=False)
        super().save(*args, **kwargs)