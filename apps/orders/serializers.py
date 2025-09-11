from rest_framework import serializers
from .models import Order, OrderItem, ProductRequest, ProductRequestItem


class OrderItemSerializer(serializers.ModelSerializer):
    """Сериализатор позиции заказа"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    unit = serializers.CharField(source='product.unit', read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_name', 'quantity', 'unit',
            'unit_price', 'total_price', 'bonus_quantity', 'bonus_discount'
        ]
        read_only_fields = ['unit_price', 'total_price', 'bonus_quantity', 'bonus_discount']


class OrderSerializer(serializers.ModelSerializer):
    """Сериализатор заказа"""

    store_name = serializers.CharField(source='store.store_name', read_only=True)
    partner_name = serializers.CharField(source='partner.get_full_name', read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'store', 'store_name', 'partner', 'partner_name',
            'status', 'order_date', 'confirmed_date', 'completed_date',
            'subtotal', 'bonus_discount', 'total_amount',
            'payment_amount', 'debt_amount', 'bonus_items_count',
            'items', 'items_count', 'notes'
        ]
        read_only_fields = [
            'order_date', 'confirmed_date', 'completed_date',
            'subtotal', 'bonus_discount', 'total_amount', 'debt_amount'
        ]

    def get_items_count(self, obj):
        return obj.items.count()


class OrderCreateSerializer(serializers.ModelSerializer):
    """Сериализатор создания заказа"""

    items = OrderItemSerializer(many=True, write_only=True)

    class Meta:
        model = Order
        fields = ['partner', 'payment_amount', 'notes', 'items']

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Список товаров не может быть пустым")

        # Проверяем уникальность товаров
        product_ids = [item['product'].id for item in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("Товары в заказе должны быть уникальными")

        return value

    def create(self, validated_data):
        items_data = validated_data.pop('items')

        # Получаем магазин из текущего пользователя
        store = self.context['request'].user.store_profile
        validated_data['store'] = store

        # Создаём заказ
        order = Order.objects.create(**validated_data)

        # Создаём позиции и рассчитываем бонусы
        for item_data in items_data:
            item = OrderItem.objects.create(order=order, **item_data)
            item.calculate_bonus_discount()

        # Пересчитываем итоги заказа
        order.calculate_totals()

        return order


class ProductRequestItemSerializer(serializers.ModelSerializer):
    """Сериализатор позиции запроса товаров"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    unit = serializers.CharField(source='product.unit', read_only=True)

    class Meta:
        model = ProductRequestItem
        fields = ['id', 'product', 'product_name', 'requested_quantity', 'unit']


class ProductRequestSerializer(serializers.ModelSerializer):
    """Сериализатор запроса товаров"""

    partner_name = serializers.CharField(source='partner.get_full_name', read_only=True)
    items = ProductRequestItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = ProductRequest
        fields = [
            'id', 'partner', 'partner_name', 'status',
            'requested_at', 'processed_at',
            'partner_notes', 'admin_notes',
            'items', 'items_count'
        ]
        read_only_fields = ['requested_at', 'processed_at']

    def get_items_count(self, obj):
        return obj.items.count()


class ProductRequestCreateSerializer(serializers.ModelSerializer):
    """Сериализатор создания запроса товаров"""

    items = ProductRequestItemSerializer(many=True, write_only=True)

    class Meta:
        model = ProductRequest
        fields = ['partner_notes', 'items']

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Список товаров не может быть пустым")

        # Проверяем уникальность товаров
        product_ids = [item['product'].id for item in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("Товары в запросе должны быть уникальными")

        return value

    def create(self, validated_data):
        items_data = validated_data.pop('items')

        # Получаем партнёра из текущего пользователя
        partner = self.context['request'].user
        validated_data['partner'] = partner

        # Создаём запрос
        request = ProductRequest.objects.create(**validated_data)

        # Создаём позиции
        for item_data in items_data:
            ProductRequestItem.objects.create(request=request, **item_data)

        return request