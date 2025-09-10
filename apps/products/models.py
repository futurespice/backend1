from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Category(models.Model):
    """Категория товаров"""

    name = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
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
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'product_categories'
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['name']

    def __str__(self):
        return self.name


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
    ]

    name = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name='products',
        verbose_name='Категория'
    )
    sku = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        verbose_name='Артикул'
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Цена'
    )
    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default='pcs',
        verbose_name='Единица измерения'
    )
    min_order_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Минимальное количество для заказа'
    )

    # Складские данные
    stock_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Количество на складе'
    )
    low_stock_threshold = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=Decimal('10'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Минимальный остаток'
    )

    # Статусы
    is_available = models.BooleanField(default=True, verbose_name='Доступен для заказа')
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'products'
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Автогенерация SKU если не указан
        if not self.sku:
            last_product = Product.objects.all().order_by('id').last()
            if last_product:
                self.sku = f'PRD{last_product.id + 1:06d}'
            else:
                self.sku = 'PRD000001'
        super().save(*args, **kwargs)

    @property
    def is_low_stock(self):
        """Проверка на низкий остаток"""
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def is_in_stock(self):
        """Проверка наличия на складе"""
        return self.stock_quantity > 0

    def update_stock(self, quantity, operation='add'):
        """Обновление остатков на складе"""
        if operation == 'add':
            self.stock_quantity += Decimal(str(quantity))
        elif operation == 'subtract':
            if self.stock_quantity >= Decimal(str(quantity)):
                self.stock_quantity -= Decimal(str(quantity))
            else:
                raise ValueError("Недостаточно товара на складе")
        elif operation == 'set':
            self.stock_quantity = Decimal(str(quantity))

        self.save()


class ProductImage(models.Model):
    """Изображения товаров"""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name='Товар'
    )
    image = models.ImageField(
        upload_to='products/',
        verbose_name='Изображение'
    )
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Альтернативный текст'
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name='Основное изображение'
    )

    class Meta:
        db_table = 'product_images'
        verbose_name = 'Изображение товара'
        verbose_name_plural = 'Изображения товаров'
        ordering = ['-is_primary', 'id']

    def __str__(self):
        return f"{self.product.name} - изображение {self.id}"

    def save(self, *args, **kwargs):
        # Если это основное изображение, убираем флаг у других
        if self.is_primary:
            ProductImage.objects.filter(
                product=self.product,
                is_primary=True
            ).exclude(id=self.id).update(is_primary=False)
        super().save(*args, **kwargs)