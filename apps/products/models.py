from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


class ProductCategory(models.Model):
    """Категории товаров с типом (штучный/весовой)"""

    class CategoryType(models.TextChoices):
        PIECE = "piece", "Штучный"
        WEIGHT = "weight", "Весовой"

    name = models.CharField(max_length=100, unique=True, verbose_name="Название")
    category_type = models.CharField(
        max_length=10,
        choices=CategoryType.choices,
        default=CategoryType.PIECE,
        verbose_name="Тип категории"
    )
    description = models.TextField(blank=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_categories"
        ordering = ["name"]
        verbose_name = "Категория товаров"
        verbose_name_plural = "Категории товаров"

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"


class Product(models.Model):
    """
    Товар - базовая модель продукта.
    Может быть штучным или весовым, с разной логикой расчета цены.
    Может состоять из других продуктов через BOM систему.
    """

    class CategoryType(models.TextChoices):
        PIECE = "piece", "Штучный"
        WEIGHT = "weight", "Весовой"

    # Основные поля
    name = models.CharField(max_length=200, unique=True, verbose_name="Название")
    description = models.TextField(max_length=500, blank=True, verbose_name="Описание")
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="products",
        verbose_name="Категория"
    )

    # Тип товара (наследуется от категории, но можно переопределить)
    category_type = models.CharField(
        max_length=10,
        choices=CategoryType.choices,
        default=CategoryType.PIECE,
        verbose_name="Тип товара"
    )

    # Цена: для штучных — за штуку, для весовых — за кг
    price = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Цена (шт/кг)"
    )

    # Остаток на складе
    stock_quantity = models.DecimalField(
        max_digits=12, decimal_places=3,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Остаток"
    )

    # Минимальный заказ (динамический для весовых)
    min_order_quantity = models.DecimalField(
        max_digits=6, decimal_places=3,
        default=Decimal("1.000"),
        validators=[MinValueValidator(Decimal("0.1"))],
        verbose_name="Минимум к заказу"
    )

    # Бонусная система (только для штучных)
    is_bonus_eligible = models.BooleanField(
        default=True,
        verbose_name="Участвует в бонусах"
    )
    bonus_every_n = models.PositiveIntegerField(
        default=21,
        verbose_name="Каждый N-й бесплатно"
    )

    # Производственные характеристики
    is_manufactured = models.BooleanField(
        default=False,
        verbose_name="Производимый товар",
        help_text="Товар производится из других товаров/расходов"
    )
    manufacturing_time_minutes = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Время производства (мин)"
    )

    # Статусы
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    is_available = models.BooleanField(default=True, verbose_name="Доступен")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"
        ordering = ["-created_at"]
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

    @property
    def is_weight(self):
        """Является ли товар весовым"""
        return self.category_type == self.CategoryType.WEIGHT

    @property
    def is_piece(self):
        """Является ли товар штучным"""
        return self.category_type == self.CategoryType.PIECE

    @property
    def has_bom_specification(self):
        """Есть ли у товара спецификация состава"""
        return hasattr(self, 'bom_specification') and self.bom_specification.is_active

    @property
    def can_be_component(self):
        """Может ли товар быть компонентом в других товарах"""
        return self.is_active and (self.is_manufactured or self.stock_quantity > 0)

    def clean(self):
        """Валидация бизнес-правил"""
        errors = {}

        # Весовые товары не могут быть бонусными
        if self.is_weight and self.is_bonus_eligible:
            errors['is_bonus_eligible'] = 'Весовые товары не могут участвовать в бонусной программе'

        # Минимальный заказ для весовых должен быть кратен 0.1
        if self.is_weight:
            if self.min_order_quantity % Decimal('0.1') != 0:
                errors['min_order_quantity'] = 'Для весовых товаров шаг должен быть 0.1 кг'

        # Наследование типа от категории
        if self.category and self.category.category_type != self.category_type:
            # Можно сделать предупреждение, но не критическую ошибку
            pass

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()

        # Автоматическое определение минимального заказа для весовых
        if self.is_weight:
            self.min_order_quantity = self._calculate_min_order_quantity()
            # Весовые не могут быть бонусными
            self.is_bonus_eligible = False

        super().save(*args, **kwargs)

    def _calculate_min_order_quantity(self):
        """Расчет минимального заказа для весовых товаров по ТЗ"""
        if self.stock_quantity >= Decimal('1.0'):
            return Decimal('1.0')  # Если товара >= 1 кг, минимум 1 кг
        else:
            return Decimal('0.1')  # Если < 1 кг, минимум 100 грамм

    def is_in_stock(self, quantity):
        """Проверка наличия на складе"""
        return self.stock_quantity >= quantity

    def calculate_price(self, quantity):
        """
        Расчет цены по ТЗ:
        - Штучные: цена * количество
        - Весовые: (цена_за_кг / 10) * (вес / 0.1)
        """
        if not self.is_weight:
            # Штучные товары
            return (self.price * quantity).quantize(Decimal("0.01"))

        # Весовые товары - специальная логика из ТЗ
        # Цена за 100г = цена_за_кг / 10
        # Итог = цена_за_100г * (вес / 0.1)
        price_per_100g = self.price / Decimal('10')
        steps = quantity / Decimal('0.1')
        return (price_per_100g * steps).quantize(Decimal("0.01"))

    def split_bonus(self, quantity):
        """
        Разделение количества на платное/бонусное (только для штучных).
        Возвращает (платное_кол-во, бонусное_кол-во)
        """
        if self.is_weight or not self.is_bonus_eligible or self.bonus_every_n < 2:
            return int(quantity), 0

        bonus_qty = int(quantity) // self.bonus_every_n
        payable_qty = int(quantity) - bonus_qty
        return payable_qty, bonus_qty

    def update_stock(self, quantity, operation='subtract'):
        """Обновление остатков на складе"""
        if operation == 'add':
            self.stock_quantity += quantity
        elif operation == 'subtract':
            if not self.is_in_stock(quantity):
                raise ValueError(f"Недостаточно остатка. Доступно: {self.stock_quantity}")
            self.stock_quantity -= quantity
        else:
            raise ValueError("operation должен быть 'add' или 'subtract'")

        self.save(update_fields=['stock_quantity', 'updated_at'])

    def get_bom_components(self):
        """Получить все компоненты товара (расходы + продукты)"""
        if not self.has_bom_specification:
            return {'expenses': [], 'products': [], 'primary_component': None}

        bom = self.bom_specification
        lines = bom.lines.select_related('expense', 'component_product').all()

        expenses = []
        products = []
        primary_component = None

        for line in lines:
            component_data = {
                'quantity': line.quantity,
                'unit': line.unit,
                'is_primary': line.is_primary,
                'notes': line.notes
            }

            if line.expense:
                component_data.update({
                    'type': 'expense',
                    'id': line.expense.id,
                    'name': line.expense.name,
                    'expense_type': line.expense.type,
                    'current_price': line.expense.price_per_unit
                })
                expenses.append(component_data)
            else:
                component_data.update({
                    'type': 'product',
                    'id': line.component_product.id,
                    'name': line.component_product.name,
                    'product_type': line.component_product.category_type,
                    'current_price': line.component_product.price,
                    'in_stock': line.component_product.stock_quantity
                })
                products.append(component_data)

            if line.is_primary:
                primary_component = component_data

        return {
            'expenses': expenses,
            'products': products,
            'primary_component': primary_component,
            'total_components': len(expenses) + len(products)
        }

    def calculate_production_cost(self, quantity=1):
        """
        Расчет стоимости производства товара на основе BOM.
        Учитывает как расходы, так и компоненты-продукты.
        """
        if not self.has_bom_specification:
            return None

        components = self.get_bom_components()
        total_cost = Decimal('0')
        cost_breakdown = {
            'expenses': [],
            'products': [],
            'total_expense_cost': Decimal('0'),
            'total_product_cost': Decimal('0')
        }

        # Расходы (сырье)
        for expense_comp in components['expenses']:
            needed_qty = expense_comp['quantity'] * quantity
            unit_price = expense_comp['current_price'] or Decimal('0')
            line_cost = needed_qty * unit_price

            cost_breakdown['expenses'].append({
                'name': expense_comp['name'],
                'needed_quantity': needed_qty,
                'unit_price': unit_price,
                'total_cost': line_cost
            })
            cost_breakdown['total_expense_cost'] += line_cost
            total_cost += line_cost

        # Компоненты-продукты
        for product_comp in components['products']:
            needed_qty = product_comp['quantity'] * quantity
            unit_price = product_comp['current_price']
            line_cost = needed_qty * unit_price

            cost_breakdown['products'].append({
                'name': product_comp['name'],
                'needed_quantity': needed_qty,
                'unit_price': unit_price,
                'total_cost': line_cost,
                'available_stock': product_comp['in_stock']
            })
            cost_breakdown['total_product_cost'] += line_cost
            total_cost += line_cost

        cost_breakdown['total_cost'] = total_cost
        cost_breakdown['cost_per_unit'] = total_cost / quantity if quantity > 0 else Decimal('0')

        return cost_breakdown

    def can_produce_quantity(self, quantity):
        """
        Проверяет, можно ли произвести указанное количество товара
        на основе доступных компонентов.
        """
        if not self.has_bom_specification:
            return True, "Товар не имеет спецификации производства"

        components = self.get_bom_components()
        constraints = []

        # Проверяем компоненты-продукты на наличие
        for product_comp in components['products']:
            needed_qty = product_comp['quantity'] * quantity
            available = product_comp['in_stock']

            if available < needed_qty:
                max_possible = available / product_comp['quantity']
                constraints.append({
                    'component': product_comp['name'],
                    'needed': needed_qty,
                    'available': available,
                    'max_possible_production': int(max_possible)
                })

        if constraints:
            return False, {
                'message': 'Недостаточно компонентов для производства',
                'constraints': constraints
            }

        return True, "Производство возможно"

    def __str__(self):
        type_icon = "⚖️" if self.is_weight else "📦"
        manufactured_icon = " 🏭" if self.is_manufactured else ""
        return f"{type_icon} {self.name}{manufactured_icon} ({self.get_category_type_display()})"


class ProductImage(models.Model):
    """Изображения товаров с поддержкой множественных фото и сортировки"""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images"
    )
    image = models.ImageField(upload_to="products/", verbose_name="Изображение")
    is_primary = models.BooleanField(default=False, verbose_name="Основное")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_images"
        ordering = ["order", "created_at"]
        verbose_name = "Изображение товара"
        verbose_name_plural = "Изображения товаров"

    def save(self, *args, **kwargs):
        # Первое изображение автоматически становится основным
        if not self.product.images.exists():
            self.is_primary = True
        # При назначении основного - убираем флаг у остальных
        elif self.is_primary:
            self.product.images.update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Фото {self.product.name} ({'основное' if self.is_primary else 'доп.'})"


class ProductBOM(models.Model):
    """
    DEPRECATED: Старая система состава товаров.
    Теперь используется cost_accounting.BillOfMaterial + BOMLine.
    Оставлено для совместимости с существующими данными.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="old_bom_items",
        verbose_name="Продукт"
    )
    ingredient = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="old_used_in",
        verbose_name="Ингредиент"
    )
    qty_per_unit = models.DecimalField(
        max_digits=12, decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
        verbose_name="Количество на единицу"
    )

    class Meta:
        db_table = "product_bom"
        unique_together = [("product", "ingredient")]
        verbose_name = "Ингредиент продукта (устар.)"
        verbose_name_plural = "Ингредиенты продуктов (устар.)"

    def clean(self):
        if self.product_id == self.ingredient_id:
            raise ValidationError("Продукт не может быть ингредиентом самого себя")

    def __str__(self):
        return f"{self.product} ← {self.ingredient} ({self.qty_per_unit})"


class ProductionTemplate(models.Model):
    """
    Шаблон производства - предустановки для производственных смен.
    Помогает быстро создавать типовые производственные задания.
    """
    name = models.CharField(max_length=200, verbose_name="Название шаблона")
    description = models.TextField(blank=True, verbose_name="Описание")

    # Можно привязать к конкретному товару или сделать универсальным
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='production_templates',
        verbose_name="Товар"
    )

    # Типовые объемы производства
    default_quantity = models.DecimalField(
        max_digits=12, decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Количество по умолчанию"
    )

    # Настройки расчета
    use_suzerain_input = models.BooleanField(
        default=False,
        verbose_name="Использовать ввод через Сюзерена"
    )
    default_suzerain_amount = models.DecimalField(
        max_digits=12, decimal_places=3,
        null=True, blank=True,
        verbose_name="Количество Сюзерена по умолчанию"
    )

    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'production_templates'
        verbose_name = 'Шаблон производства'
        verbose_name_plural = 'Шаблоны производства'
        ordering = ['name']

    def __str__(self):
        product_info = f" ({self.product.name})" if self.product else " (универсальный)"
        return f"{self.name}{product_info}"

    def create_production_data(self):
        """Создает данные для производственного расчета на основе шаблона"""
        if self.use_suzerain_input and self.default_suzerain_amount:
            return {
                'suzerain_input': float(self.default_suzerain_amount)
            }
        else:
            return {
                'quantity': float(self.default_quantity)
            }