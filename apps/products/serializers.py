from rest_framework import serializers
from .models import Category, Product, ProductImage, ProductCharacteristic, ProductPriceHistory


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор категорий"""

    children = serializers.SerializerMethodField()
    products_count = serializers.ReadOnlyField(source='get_products_count')
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'description', 'slug', 'parent', 'full_name',
            'image', 'is_active', 'sort_order', 'children', 'products_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at']

    def get_children(self, obj):
        """Получить дочерние категории"""
        children = obj.children.filter(is_active=True)
        return CategorySerializer(children, many=True, context=self.context).data


class ProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений товара"""

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'title', 'sort_order']


class ProductCharacteristicSerializer(serializers.ModelSerializer):
    """Сериализатор характеристик товара"""

    class Meta:
        model = ProductCharacteristic
        fields = ['id', 'name', 'value', 'unit', 'sort_order']


class ProductListSerializer(serializers.ModelSerializer):
    """Сериализатор списка товаров (краткая информация)"""

    category_name = serializers.CharField(source='category.name', read_only=True)
    is_in_stock = serializers.ReadOnlyField()
    is_low_stock = serializers.ReadOnlyField()
    profit_margin = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'article', 'slug', 'category', 'category_name',
            'price', 'unit', 'stock_quantity', 'main_image',
            'is_active', 'is_available', 'is_in_stock', 'is_low_stock',
            'is_bonus_eligible', 'profit_margin', 'created_at'
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    """Детальный сериализатор товара"""

    category_name = serializers.CharField(source='category.name', read_only=True)
    category_full_name = serializers.CharField(source='category.full_name', read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    characteristics = ProductCharacteristicSerializer(many=True, read_only=True)

    # Computed fields
    is_in_stock = serializers.ReadOnlyField()
    is_low_stock = serializers.ReadOnlyField()
    profit_margin = serializers.ReadOnlyField()
    profit_amount = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'article', 'slug',
            'category', 'category_name', 'category_full_name',
            'price', 'cost_price', 'unit', 'stock_quantity', 'low_stock_threshold',
            'is_bonus_eligible', 'bonus_points', 'main_image', 'images',
            'weight', 'volume', 'characteristics',
            'is_active', 'is_available', 'is_in_stock', 'is_low_stock',
            'production_time_days', 'shelf_life_days',
            'profit_margin', 'profit_amount',
            'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at', 'created_by']


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор создания/обновления товара"""

    characteristics = ProductCharacteristicSerializer(many=True, required=False)

    class Meta:
        model = Product
        fields = [
            'name', 'description', 'category', 'price', 'cost_price', 'unit',
            'stock_quantity', 'low_stock_threshold', 'is_bonus_eligible', 'bonus_points',
            'main_image', 'weight', 'volume', 'is_active', 'is_available',
            'production_time_days', 'shelf_life_days', 'characteristics'
        ]

    def create(self, validated_data):
        """Создание товара с характеристиками"""
        characteristics_data = validated_data.pop('characteristics', [])

        # Устанавливаем создателя
        validated_data['created_by'] = self.context['request'].user

        product = Product.objects.create(**validated_data)

        # Создаем характеристики
        for char_data in characteristics_data:
            ProductCharacteristic.objects.create(product=product, **char_data)

        return product

    def update(self, instance, validated_data):
        """Обновление товара"""
        characteristics_data = validated_data.pop('characteristics', [])

        # Сохраняем старую цену для истории
        old_price = instance.price
        new_price = validated_data.get('price', old_price)

        # Обновляем товар
        product = super().update(instance, validated_data)

        # Записываем историю изменения цены
        if old_price != new_price:
            ProductPriceHistory.objects.create(
                product=product,
                old_price=old_price,
                new_price=new_price,
                changed_by=self.context['request'].user,
                reason='Обновление через API'
            )

        # Обновляем характеристики
        if characteristics_data:
            # Удаляем старые характеристики
            product.characteristics.all().delete()

            # Создаем новые
            for char_data in characteristics_data:
                ProductCharacteristic.objects.create(product=product, **char_data)

        return product


class ProductPriceHistorySerializer(serializers.ModelSerializer):
    """Сериализатор истории цен"""

    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)

    class Meta:
        model = ProductPriceHistory
        fields = [
            'id', 'old_price', 'new_price', 'changed_by', 'changed_by_name',
            'reason', 'created_at'
        ]


class ProductCatalogSerializer(serializers.ModelSerializer):
    """Сериализатор каталога товаров для магазинов"""

    category_name = serializers.CharField(source='category.name', read_only=True)
    available_quantity = serializers.SerializerMethodField()
    in_cart = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'unit', 'category_name',
            'main_image', 'is_bonus_eligible', 'available_quantity', 'in_cart'
        ]

    def get_available_quantity(self, obj):
        """Доступное количество на складе партнёра"""
        # TODO: Реализовать логику получения остатков у партнёра
        return float(obj.stock_quantity)

    def get_in_cart(self, obj):
        """Проверить, есть ли товар в корзине"""
        # TODO: Реализовать логику корзины
        return False


class ProductStockUpdateSerializer(serializers.Serializer):
    """Сериализатор обновления остатков"""

    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)
    operation = serializers.ChoiceField(choices=['add', 'subtract', 'set'])
    reason = serializers.CharField(max_length=200, required=False)

    def validate_product_id(self, value):
        """Проверяем существование товара"""
        try:
            Product.objects.get(id=value)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Товар не найден")
        return value

    def validate_quantity(self, value):
        """Проверяем количество"""
        if value < 0:
            raise serializers.ValidationError("Количество не может быть отрицательным")
        return value


class ProductAnalyticsSerializer(serializers.Serializer):
    """Сериализатор аналитики по товарам"""

    total_products = serializers.IntegerField()
    active_products = serializers.IntegerField()
    low_stock_products = serializers.IntegerField()
    out_of_stock_products = serializers.IntegerField()
    average_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_stock_value = serializers.DecimalField(max_digits=15, decimal_places=2)
    top_categories = serializers.ListField()
    price_ranges = serializers.DictField()