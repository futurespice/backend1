from rest_framework import serializers
from .models import ProductCategory, Product, ProductImage
from decimal import Decimal


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'is_primary', 'order']


class ProductCategorySerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = ['id', 'name', 'category_type', 'description', 'is_active', 'products_count', 'created_at']

    def get_products_count(self, obj):
        return obj.products.filter(is_active=True).count()


class ProductListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка товаров"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    primary_image = serializers.SerializerMethodField()
    price_per_100g = serializers.ReadOnlyField()
    is_in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category_type', 'category_name', 'price', 'price_per_100g',
            'stock_quantity', 'min_order_quantity', 'is_bonus_eligible',
            'is_active', 'is_available', 'is_in_stock', 'primary_image', 'created_at'
        ]

    def get_primary_image(self, obj):
        primary_image = obj.images.filter(is_primary=True).first()
        if primary_image:
            return primary_image.image.url
        return None

    def get_is_in_stock(self, obj):
        return obj.is_in_stock()


class ProductDetailSerializer(serializers.ModelSerializer):
    """Подробная информация о товаре"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    price_per_100g = serializers.ReadOnlyField()
    is_in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'category', 'category_name', 'category_type',
            'price', 'price_per_100g', 'stock_quantity', 'min_order_quantity',
            'is_bonus_eligible', 'is_active', 'is_available', 'is_in_stock',
            'images', 'created_at', 'updated_at'
        ]

    def get_is_in_stock(self, obj):
        return obj.is_in_stock()


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Создание и обновление товара"""

    class Meta:
        model = Product
        fields = [
            'name', 'description', 'category', 'category_type', 'price',
            'stock_quantity', 'min_order_quantity', 'is_bonus_eligible',
            'is_active', 'is_available'
        ]

    def validate(self, attrs):
        # Весовые товары не могут быть бонусными
        if attrs.get('category_type') == 'weight' and attrs.get('is_bonus_eligible'):
            raise serializers.ValidationError("Весовые товары не могут участвовать в бонусной программе")

        return attrs

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Цена должна быть больше 0")
        return value

    def validate_stock_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Количество не может быть отрицательным")
        return value


class ProductPriceCalculationSerializer(serializers.Serializer):
    """Расчет цены для указанного количества"""
    quantity = serializers.DecimalField(max_digits=8, decimal_places=3, min_value=Decimal('0.001'))

    def validate_quantity(self, value):
        product = self.context['product']

        # Проверяем минимальное количество для заказа
        if value < product.min_order_quantity:
            raise serializers.ValidationError(
                f"Минимальное количество для заказа: {product.min_order_quantity}"
            )

        return value


class ProductStockUpdateSerializer(serializers.Serializer):
    """Обновление остатков товара"""
    quantity = serializers.DecimalField(max_digits=8, decimal_places=3)
    operation = serializers.ChoiceField(choices=['add', 'subtract', 'set'])
    reason = serializers.CharField(max_length=200, required=False)

    def validate_quantity(self, value):
        if self.initial_data.get('operation') in ['add', 'set'] and value < 0:
            raise serializers.ValidationError("Количество не может быть отрицательным")
        return value


class ProductRequestSerializer(serializers.Serializer):
    """Запрос товара партнером"""
    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=8, decimal_places=3, min_value=Decimal('0.001'))

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value, is_active=True, is_available=True)
            return value
        except Product.DoesNotExist:
            raise serializers.ValidationError("Товар не найден или недоступен")

    def validate(self, attrs):
        product = Product.objects.get(id=attrs['product_id'])
        quantity = attrs['quantity']

        # Проверяем минимальное количество
        if quantity < product.min_order_quantity:
            raise serializers.ValidationError(
                f"Минимальное количество для товара '{product.name}': {product.min_order_quantity}"
            )

        # Проверяем наличие на складе
        if not product.is_in_stock(quantity):
            raise serializers.ValidationError(
                f"Недостаточно товара '{product.name}' на складе. Доступно: {product.stock_quantity}"
            )

        return attrs