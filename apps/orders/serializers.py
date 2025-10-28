from rest_framework import serializers
from .models import Order, OrderItem, OrderHistory, OrderReturn, OrderReturnItem
from stores.serializers import StoreSerializer
from decimal import Decimal,ROUND_HALF_UP

from stores.models import Store


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_unit', 'quantity', 'price', 'total']
        read_only_fields = ['price', 'total']

    def validate(self, attrs):
        product = attrs.get('product')
        quantity = attrs.get('quantity')
        if not product or quantity is None:
            return attrs

        if product.category == "weight":
            scaled = (quantity * Decimal("10")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            if scaled / Decimal("10") != quantity:
                raise serializers.ValidationError(
                    {"quantity": "Количество для весовых товаров должно быть кратно 0.1 кг"})
            if quantity < Decimal("0.1"):
                raise serializers.ValidationError({"quantity": "Минимальное количество для весовых товаров: 0.1 кг"})
        else:
            if quantity != quantity.to_integral_value(rounding=ROUND_HALF_UP):
                raise serializers.ValidationError(
                    {"quantity": "Количество для штучных товаров должно быть целым числом"})
        return attrs


class CreateOrderSerializer(serializers.Serializer):
    store = serializers.PrimaryKeyRelatedField(queryset=Store.objects.all())
    note = serializers.CharField(max_length=500, allow_blank=True)
    items = OrderItemSerializer(many=True)
    idempotency_key = serializers.UUIDField()

    def validate(self, attrs):
        items = attrs.get('items')
        if not items:
            raise serializers.ValidationError("Необходимо указать хотя бы одну позицию")
        return attrs


class OrderSerializer(serializers.ModelSerializer):
    store = StoreSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    partner_name = serializers.CharField(source='partner.name', read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'store', 'partner', 'partner_name', 'total_amount', 'debt_increase', 'status', 'note', 'items', 'idempotency_key', 'created_at', 'updated_at']
        read_only_fields = ['partner', 'total_amount', 'debt_increase', 'idempotency_key', 'created_at', 'updated_at']


class OrderHistorySerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True, allow_null=True)

    class Meta:
        model = OrderHistory
        fields = ['id', 'order_id', 'type', 'amount', 'quantity', 'product', 'product_name', 'note', 'created_at']


class OrderReturnItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)

    class Meta:
        model = OrderReturnItem
        fields = ['id', 'product', 'product_name', 'product_unit', 'quantity', 'price', 'total']
        read_only_fields = ['price', 'total']

    def validate(self, attrs):
        product = attrs.get('product')
        quantity = attrs.get('quantity')
        if not product or quantity is None:
            return attrs

        if product.category == "weight":
            scaled = (quantity * Decimal("10")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            if scaled / Decimal("10") != quantity:
                raise serializers.ValidationError(
                    {"quantity": "Количество для весовых товаров должно быть кратно 0.1 кг"})
            if quantity < Decimal("0.1"):
                raise serializers.ValidationError({"quantity": "Минимальное количество для весовых товаров: 0.1 кг"})
        else:
            if quantity != quantity.to_integral_value(rounding=ROUND_HALF_UP):
                raise serializers.ValidationError(
                    {"quantity": "Количество для штучных товаров должно быть целым числом"})
        return attrs


class CreateOrderReturnSerializer(serializers.Serializer):
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    reason = serializers.CharField(max_length=500, allow_blank=True)
    items = OrderReturnItemSerializer(many=True)
    idempotency_key = serializers.UUIDField()


class OrderReturnSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    items = OrderReturnItemSerializer(many=True, read_only=True)

    class Meta:
        model = OrderReturn
        fields = ['id', 'order_id', 'status', 'total_amount', 'reason', 'items', 'idempotency_key', 'created_at']
        read_only_fields = ['total_amount', 'idempotency_key', 'created_at']