from decimal import Decimal
from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Product, ProductCategory, ProductImage, ProductBOM


class ProductCategorySerializer(serializers.ModelSerializer):
    """Сериализатор категорий товаров"""

    products_count = serializers.SerializerMethodField()
    category_type_display = serializers.CharField(source='get_category_type_display', read_only=True)

    class Meta:
        model = ProductCategory
        fields = [
            'id', 'name', 'category_type', 'description', 'is_active',
            'category_type_display', 'products_count', 'created_at'
        ]
        read_only_fields = ['created_at']

    def get_products_count(self, obj):
        """Количество активных товаров в категории"""
        return obj.products.filter(is_active=True).count()


class ProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений товаров"""

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = [
            'id', 'product', 'image', 'image_url', 'is_primary',
            'order', 'created_at'
        ]
        read_only_fields = ['created_at']

    def get_image_url(self, obj):
        """Полный URL изображения"""
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class ProductListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка товаров (облегченный)"""

    category_name = serializers.CharField(source='category.name', read_only=True)
    category_type_display = serializers.CharField(source='get_category_type_display', read_only=True)
    primary_image = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category_name', 'category_type', 'category_type_display',
            'price', 'stock_quantity', 'in_stock', 'primary_image',
            'is_bonus_eligible', 'bonus_every_n', 'is_active', 'is_available'
        ]

    def get_primary_image(self, obj):
        """Основное изображение товара"""
        primary_img = obj.images.filter(is_primary=True).first()
        if primary_img:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(primary_img.image.url)
            return primary_img.image.url
        return None

    def get_in_stock(self, obj):
        """Есть ли товар в наличии"""
        return obj.stock_quantity > 0


class ProductDetailSerializer(serializers.ModelSerializer):
    """Детальный сериализатор товара"""

    category_name = serializers.CharField(source='category.name', read_only=True)
    category_type_display = serializers.CharField(source='get_category_type_display', read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    # Вычисляемые поля
    is_weight = serializers.BooleanField(read_only=True)
    is_piece = serializers.BooleanField(read_only=True)
    in_stock = serializers.SerializerMethodField()
    min_order_info = serializers.SerializerMethodField()

    # Интеграция с системой себестоимости
    has_cost_setup = serializers.SerializerMethodField()
    suzerain_expense = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'category', 'category_name',
            'category_type', 'category_type_display', 'price', 'stock_quantity',
            'min_order_quantity', 'is_bonus_eligible', 'bonus_every_n',
            'is_active', 'is_available', 'images',
            'is_weight', 'is_piece', 'in_stock', 'min_order_info',
            'has_cost_setup', 'suzerain_expense',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_in_stock(self, obj):
        """Статус наличия"""
        return {
            'available': obj.stock_quantity > 0,
            'quantity': float(obj.stock_quantity),
            'low_stock': obj.stock_quantity < 10  # порог низкого остатка
        }

    def get_min_order_info(self, obj):
        """Информация о минимальном заказе"""
        if obj.is_weight:
            # Для весовых товаров минимум зависит от остатка
            actual_min = obj._calculate_min_order_quantity()
            return {
                'quantity': float(actual_min),
                'unit': 'кг',
                'step': 0.1,
                'rule': '1 кг если в наличии ≥1кг, иначе 0.1 кг'
            }
        else:
            return {
                'quantity': 1,
                'unit': 'шт',
                'step': 1,
                'rule': 'Только целые числа'
            }

    def get_has_cost_setup(self, obj):
        """Настроена ли себестоимость товара"""
        try:
            from cost_accounting.models import ProductExpense
            return ProductExpense.objects.filter(product=obj, is_active=True).exists()
        except ImportError:
            return False

    def get_suzerain_expense(self, obj):
        """Информация о расходе-Сюзерене"""
        try:
            from cost_accounting.models import ProductExpense, Expense
            suzerain = ProductExpense.objects.filter(
                product=obj,
                expense__status=Expense.ExpenseStatus.SUZERAIN,
                is_active=True
            ).select_related('expense').first()

            if suzerain:
                return {
                    'id': suzerain.expense.id,
                    'name': suzerain.expense.name,
                    'unit': suzerain.expense.unit,
                    'ratio_per_unit': float(suzerain.ratio_per_product_unit)
                }
        except ImportError:
            pass
        return None


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания/редактирования товаров"""

    class Meta:
        model = Product
        fields = [
            'name', 'description', 'category', 'category_type', 'price',
            'stock_quantity', 'min_order_quantity', 'is_bonus_eligible',
            'bonus_every_n', 'is_active', 'is_available'
        ]

    def validate(self, attrs):
        # Дополнительная валидация на уровне сериализатора
        category_type = attrs.get('category_type', getattr(self.instance, 'category_type', None))
        is_bonus_eligible = attrs.get('is_bonus_eligible', getattr(self.instance, 'is_bonus_eligible', False))
        min_order_quantity = attrs.get('min_order_quantity', getattr(self.instance, 'min_order_quantity', None))

        # Весовые товары не могут быть бонусными
        if category_type == Product.CategoryType.WEIGHT and is_bonus_eligible:
            raise serializers.ValidationError({
                'is_bonus_eligible': 'Весовые товары не могут участвовать в бонусной программе'
            })

        # Для весовых проверяем шаг минимального заказа
        if category_type == Product.CategoryType.WEIGHT and min_order_quantity:
            if min_order_quantity % Decimal('0.1') != 0:
                raise serializers.ValidationError({
                    'min_order_quantity': 'Для весовых товаров шаг должен быть 0.1 кг'
                })

        return attrs

    def create(self, validated_data):
        try:
            return Product.objects.create(**validated_data)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict or str(e))

    def update(self, instance, validated_data):
        # Проверяем смену типа категории
        old_type = instance.category_type
        new_type = validated_data.get('category_type', old_type)

        if old_type == Product.CategoryType.WEIGHT and new_type == Product.CategoryType.PIECE:
            raise serializers.ValidationError({
                'category_type': 'Нельзя сменить категорию с "Весовой" на "Штучный"'
            })

        for field, value in validated_data.items():
            setattr(instance, field, value)

        try:
            instance.save()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict or str(e))

        return instance


class ProductStockUpdateSerializer(serializers.Serializer):
    """Обновление остатков товара"""

    OPERATION_CHOICES = [
        ('add', 'Приход'),
        ('subtract', 'Расход')
    ]

    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3,
        min_value=Decimal('0.001')
    )
    operation = serializers.ChoiceField(choices=OPERATION_CHOICES)

    def validate(self, attrs):
        # Получаем товар из контекста view
        product = self.context.get('product')
        if not product:
            raise serializers.ValidationError("Товар не найден в контексте")

        quantity = attrs['quantity']
        operation = attrs['operation']

        # Для весовых проверяем шаг 0.1
        if product.is_weight and quantity % Decimal('0.1') != 0:
            raise serializers.ValidationError({
                'quantity': 'Для весовых товаров шаг 0.1 кг'
            })

        # Для штучных проверяем целые числа
        if not product.is_weight and quantity % 1 != 0:
            raise serializers.ValidationError({
                'quantity': 'Для штучных товаров только целые числа'
            })

        # При списании проверяем остаток
        if operation == 'subtract' and not product.is_in_stock(quantity):
            raise serializers.ValidationError({
                'quantity': f'Недостаточно остатка. Доступно: {product.stock_quantity}'
            })

        return attrs


class ProductRequestSerializer(serializers.Serializer):
    """Запрос товаров партнером/магазином"""

    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3,
        min_value=Decimal('0.001')
    )

    def validate(self, attrs):
        product_id = attrs['product_id']
        quantity = attrs['quantity']

        # Проверка существования товара
        try:
            product = Product.objects.get(
                id=product_id,
                is_active=True,
                is_available=True
            )
        except Product.DoesNotExist:
            raise serializers.ValidationError({
                'product_id': 'Товар не найден или недоступен'
            })

        # Валидация количества в зависимости от типа товара
        if product.is_weight:
            # Весовые: проверяем минимум и шаг
            if quantity < product.min_order_quantity:
                raise serializers.ValidationError({
                    'quantity': f'Минимальный заказ: {product.min_order_quantity} кг'
                })
            if quantity % Decimal('0.1') != 0:
                raise serializers.ValidationError({
                    'quantity': 'Шаг для весовых товаров: 0.1 кг'
                })
        else:
            # Штучные: только целые числа, минимум 1
            if quantity < 1 or quantity % 1 != 0:
                raise serializers.ValidationError({
                    'quantity': 'Минимальный заказ: 1 шт, только целые числа'
                })

        # Проверка наличия на складе
        if not product.is_in_stock(quantity):
            raise serializers.ValidationError({
                'quantity': f'Недостаточно на складе. Доступно: {product.stock_quantity}'
            })

        # Сохраняем товар в контекст для использования в view
        attrs['product'] = product
        return attrs


class ProductBOMSerializer(serializers.ModelSerializer):
    """
    DEPRECATED: Старая система состава товаров.
    Сохранена для совместимости, новые данные через cost_accounting.
    """

    product_name = serializers.CharField(source='product.name', read_only=True)
    ingredient_name = serializers.CharField(source='ingredient.name', read_only=True)

    class Meta:
        model = ProductBOM
        fields = [
            'id', 'product', 'ingredient', 'qty_per_unit',
            'product_name', 'ingredient_name'
        ]

    def validate(self, attrs):
        product = attrs.get('product')
        ingredient = attrs.get('ingredient')

        if product and ingredient and product.id == ingredient.id:
            raise serializers.ValidationError({
                'ingredient': 'Товар не может быть ингредиентом самого себя'
            })
        return attrs


class ProductPriceCalculationSerializer(serializers.Serializer):
    """Расчет цены товара"""

    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3,
        min_value=Decimal('0.001')
    )
    include_bonus = serializers.BooleanField(default=True)

    def validate(self, attrs):
        product_id = attrs['product_id']
        quantity = attrs['quantity']

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError({
                'product_id': 'Товар не найден'
            })

        # Валидация количества
        if product.is_weight:
            if quantity % Decimal('0.1') != 0:
                raise serializers.ValidationError({
                    'quantity': 'Для весовых товаров шаг 0.1 кг'
                })
        else:
            if quantity % 1 != 0:
                raise serializers.ValidationError({
                    'quantity': 'Для штучных товаров только целые числа'
                })

        attrs['product'] = product
        return attrs


class ProductCostSetupSerializer(serializers.Serializer):
    """
    Быстрая настройка себестоимости товара.
    Создает связи с расходами через cost_accounting.
    """

    product_id = serializers.IntegerField()
    suzerain_expense_id = serializers.IntegerField(required=False)
    physical_expenses = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="[{'expense_id': 1, 'ratio': 0.15}, ...]"
    )
    overhead_expenses = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="[{'expense_id': 5, 'ratio': 1.0}, ...]"
    )

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value, is_active=True)
            return value
        except Product.DoesNotExist:
            raise serializers.ValidationError("Товар не найден")

    def validate_physical_expenses(self, value):
        if not value:
            return value

        for item in value:
            if 'expense_id' not in item or 'ratio' not in item:
                raise serializers.ValidationError(
                    "Каждый элемент должен содержать expense_id и ratio"
                )

            try:
                ratio = Decimal(str(item['ratio']))
                if ratio <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    f"Некорректный ratio для expense_id {item['expense_id']}"
                )

        return value

    def validate_overhead_expenses(self, value):
        # Аналогичная валидация для накладных
        return self.validate_physical_expenses(value)


class ProductSearchSerializer(serializers.Serializer):
    """Расширенный поиск товаров"""

    query = serializers.CharField(required=False, allow_blank=True)
    category_id = serializers.IntegerField(required=False)
    category_type = serializers.ChoiceField(
        choices=Product.CategoryType.choices,
        required=False
    )
    price_min = serializers.DecimalField(
        max_digits=12, decimal_places=2,
        required=False, min_value=0
    )
    price_max = serializers.DecimalField(
        max_digits=12, decimal_places=2,
        required=False, min_value=0
    )
    in_stock_only = serializers.BooleanField(default=True)
    bonus_eligible_only = serializers.BooleanField(default=False)

    def validate(self, attrs):
        price_min = attrs.get('price_min')
        price_max = attrs.get('price_max')

        if price_min and price_max and price_min > price_max:
            raise serializers.ValidationError({
                'price_min': 'Минимальная цена не может быть больше максимальной'
            })

        return attrs


class ProductStatisticsSerializer(serializers.Serializer):
    """Статистика по товарам"""

    total_products = serializers.IntegerField()
    active_products = serializers.IntegerField()
    available_products = serializers.IntegerField()
    out_of_stock = serializers.IntegerField()
    low_stock = serializers.IntegerField()

    by_category = serializers.DictField()
    by_type = serializers.DictField()

    # Ценовая статистика
    price_stats = serializers.DictField()

    # Топ товары
    top_expensive = serializers.ListField()
    top_cheap = serializers.ListField()


# Вспомогательные сериализаторы для интеграции

class ProductBriefSerializer(serializers.ModelSerializer):
    """Краткая информация о товаре для использования в других модулях"""

    category_type_display = serializers.CharField(source='get_category_type_display', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category_type', 'category_type_display',
            'price', 'stock_quantity'
        ]


class ProductForCostCalculationSerializer(serializers.ModelSerializer):
    """Товар в контексте расчета себестоимости"""

    has_suzerain = serializers.SerializerMethodField()
    physical_expenses_count = serializers.SerializerMethodField()
    overhead_expenses_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category_type', 'price',
            'has_suzerain', 'physical_expenses_count', 'overhead_expenses_count'
        ]

    def get_has_suzerain(self, obj):
        """Есть ли у товара расход-Сюзерен"""
        try:
            from cost_accounting.models import ProductExpense, Expense
            return ProductExpense.objects.filter(
                product=obj,
                expense__status=Expense.ExpenseStatus.SUZERAIN,
                is_active=True
            ).exists()
        except ImportError:
            return False

    def get_physical_expenses_count(self, obj):
        """Количество физических расходов"""
        try:
            from cost_accounting.models import ProductExpense, Expense
            return ProductExpense.objects.filter(
                product=obj,
                expense__type=Expense.ExpenseType.PHYSICAL,
                is_active=True
            ).count()
        except ImportError:
            return 0

    def get_overhead_expenses_count(self, obj):
        """Количество накладных расходов"""
        try:
            from cost_accounting.models import ProductExpense, Expense
            return ProductExpense.objects.filter(
                product=obj,
                expense__type=Expense.ExpenseType.OVERHEAD,
                is_active=True
            ).count()
        except ImportError:
            return 0