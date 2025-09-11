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
        """Проверка низкого остатка"""
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def primary_image(self):
        """Получить основное изображение"""
        return self.images.filter(is_primary=True).first()

    def calculate_cost_price(self):
        """Расчёт себестоимости через BOM"""
        try:
            bom = self.bom_specification
            if not bom.is_active:
                return None

            total_cost = Decimal('0')

            for line in bom.lines.all():
                if line.expense:
                    # Стоимость расходного материала
                    cost = line.expense.price_per_unit * line.quantity
                    total_cost += cost
                elif line.component_product:
                    # Рекурсивный расчёт стоимости компонента
                    component_cost = line.component_product.calculate_cost_price()
                    if component_cost:
                        cost = component_cost * line.quantity
                        total_cost += cost

            return total_cost

        except:
            return None


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
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        db_table = 'product_images'
        verbose_name = 'Изображение товара'
        verbose_name_plural = 'Изображения товаров'
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"Изображение для {self.product.name}"

    def save(self, *args, **kwargs):
        # Если это первое изображение или устанавливается как основное
        if self.is_primary:
            # Снимаем флаг основного с других изображений
            ProductImage.objects.filter(
                product=self.product,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)

        # Если нет основного изображения, делаем это основным
        elif not ProductImage.objects.filter(product=self.product, is_primary=True).exists():
            self.is_primary = True

        super().save(*args, **kwargs)