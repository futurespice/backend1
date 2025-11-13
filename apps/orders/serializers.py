# apps/orders/serializers.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, OpenApiTypes

from .models import (
    PartnerOrder, PartnerOrderItem,
    StoreOrder, StoreOrderItem,
    OrderHistory, OrderReturn, OrderReturnItem
)
from products.models import Product
from stores.models import Store, StoreRequest


# =============================================================================
#  HELPER FUNCTIONS
# =============================================================================

def safe_decimal(value: Any) -> Decimal:
    """Безопасное преобразование в Decimal, fallback → 0"""
    try:
        return Decimal(value) if value is not None else Decimal('0')
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


# =============================================================================
#  PARTNER ORDER (партнёр → админ)
# =============================================================================

class PartnerOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = PartnerOrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'total']
        read_only_fields = ['total']

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total(self, obj: PartnerOrderItem) -> Decimal:
        """Безопасный расчёт итога позиции"""
        if not obj.pk:
            return Decimal('0')
        return obj.total  # @property из модели


class PartnerOrderSerializer(serializers.ModelSerializer):
    partner_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = PartnerOrderItemSerializer(many=True, read_only=True)
    total_amount_display = serializers.SerializerMethodField()

    class Meta:
        model = PartnerOrder
        fields = [
            'id', 'partner', 'partner_name', 'status', 'status_display',
            'total_amount', 'total_amount_display', 'note', 'items',
            'idempotency_key', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'partner', 'total_amount', 'total_amount_display',
            'idempotency_key', 'created_at', 'updated_at'
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_partner_name(self, obj: PartnerOrder) -> str:
        return obj.partner.get_full_name() or obj.partner.email

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total_amount_display(self, obj: PartnerOrder) -> Decimal:
        return obj.total_amount


class CreatePartnerOrderSerializer(serializers.Serializer):
    """Создание заказа партнёра с полной валидацией и пересчётом"""
    note = serializers.CharField(max_length=500, allow_blank=True, required=False, default='')
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        error_messages={'min_length': 'Укажите хотя бы одну позицию'}
    )
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_items(self, items: List[Dict]) -> List[Dict]:
        if not items:
            raise serializers.ValidationError("Список позиций не может быть пустым")

        validated = []
        product_ids = set()

        for idx, item in enumerate(items):
            product_id = item.get('product')
            quantity = item.get('quantity')
            price = item.get('price')

            if not product_id or not isinstance(product_id, int):
                raise serializers.ValidationError(f"Позиция {idx + 1}: укажите корректный product ID")
            if product_id in product_ids:
                raise serializers.ValidationError(f"Позиция {idx + 1}: дублирование товара")
            product_ids.add(product_id)

            if not quantity or not isinstance(quantity, (int, float, Decimal, str)):
                raise serializers.ValidationError(f"Позиция {idx + 1}: quantity обязателен")
            try:
                qty = Decimal(str(quantity))
                if qty <= 0:
                    raise serializers.ValidationError("quantity должен быть > 0")
            except InvalidOperation:
                raise serializers.ValidationError(f"Позиция {idx + 1}: некорректное значение quantity")

            if price is not None:
                try:
                    prc = Decimal(str(price))
                    if prc < 0:
                        raise serializers.ValidationError("price не может быть отрицательным")
                except InvalidOperation:
                    raise serializers.ValidationError(f"Позиция {idx + 1}: некорректное значение price")
            else:
                prc = None

            validated.append({
                'product_id': product_id,
                'quantity': qty,
                'price': prc
            })

        return validated

    @transaction.atomic
    def create(self, validated_data: Dict) -> PartnerOrder:
        items_data = validated_data.pop('items')
        idempotency_key = validated_data.pop('idempotency_key', None)

        # Идемпотентность
        if idempotency_key:
            existing = PartnerOrder.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        order = PartnerOrder.objects.create(
            partner=self.context['request'].user,
            **validated_data
        )

        if idempotency_key:
            order.idempotency_key = idempotency_key
            order.save(update_fields=['idempotency_key'])

        total = Decimal('0')
        order_items = []

        for item in items_data:
            product = get_object_or_404(Product, id=item['product_id'])
            price = item['price'] if item['price'] is not None else product.price

            order_item = PartnerOrderItem(
                order=order,
                product=product,
                quantity=item['quantity'],
                price=price
            )
            order_item.save()
            order_items.append(order_item)
            total += order_item.total

        order.total_amount = total
        order.save(update_fields=['total_amount'])

        return order


# =============================================================================
#  STORE ORDER (магазин → партнёр)
# =============================================================================

class StoreOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = StoreOrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'is_bonus', 'total']
        read_only_fields = ['total']

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total(self, obj: StoreOrderItem) -> Decimal:
        return Decimal('0') if obj.is_bonus else obj.total


class StoreOrderSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    partner_name = serializers.SerializerMethodField()
    items = StoreOrderItemSerializer(many=True, read_only=True)
    total_amount_display = serializers.SerializerMethodField()
    bonus_applied_display = serializers.SerializerMethodField()

    class Meta:
        model = StoreOrder
        fields = [
            'id', 'store', 'store_name', 'partner', 'partner_name',
            'store_request', 'is_fulfilled', 'total_amount', 'total_amount_display',
            'bonus_applied', 'bonus_applied_display', 'note', 'items',
            'idempotency_key', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'store', 'partner', 'store_request', 'total_amount', 'total_amount_display',
            'bonus_applied', 'bonus_applied_display', 'idempotency_key', 'created_at', 'updated_at'
        ]

    def get_partner_name(self, obj: StoreOrder) -> str:
        return obj.partner.get_full_name() or obj.partner.email if obj.partner else "—"

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total_amount_display(self, obj: StoreOrder) -> Decimal:
        return obj.total_amount

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_bonus_applied_display(self, obj: StoreOrder) -> Decimal:
        return obj.bonus_applied


class CreateStoreOrderSerializer(serializers.Serializer):
    """Создание заказа магазина из подтверждённого StoreRequest"""
    store_request_id = serializers.IntegerField()
    note = serializers.CharField(max_length=500, allow_blank=True, required=False, default='')
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_store_request_id(self, value: int) -> StoreRequest:
        try:
            request = StoreRequest.objects.select_related('store').get(id=value, status='confirmed')
        except StoreRequest.DoesNotExist:
            raise serializers.ValidationError("Запрос не найден или не подтверждён")
        return request

    @transaction.atomic
    def create(self, validated_data: Dict) -> StoreOrder:
        store_request = validated_data.pop('store_request_id')
        idempotency_key = validated_data.pop('idempotency_key', None)

        if idempotency_key:
            existing = StoreOrder.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        order = StoreOrder.objects.create(
            store=store_request.store,
            partner=self.context['request'].user,
            store_request=store_request,
            **validated_data
        )

        if idempotency_key:
            order.idempotency_key = idempotency_key
            order.save(update_fields=['idempotency_key'])

        # Копируем позиции из запроса
        total = Decimal('0')
        bonus = Decimal('0')
        for item in store_request.items.select_related('product').all():
            price = item.price or item.product.price
            order_item = StoreOrderItem(
                order=order,
                product=item.product,
                quantity=item.quantity,
                price=price,
                is_bonus=item.is_bonus
            )
            order_item.save()
            if item.is_bonus:
                bonus += price * item.quantity
            else:
                total += price * item.quantity

        order.total_amount = total
        order.bonus_applied = bonus
        order.save(update_fields=['total_amount', 'bonus_applied'])

        return order


# =============================================================================
#  ORDER HISTORY
# =============================================================================

class OrderHistorySerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    product_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderHistory
        fields = [
            'id', 'order_type', 'order_id', 'type', 'type_display',
            'product', 'product_name', 'amount', 'quantity', 'note', 'created_at'
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_product_name(self, obj: OrderHistory) -> Optional[str]:
        return obj.product.name if obj.product else None


# =============================================================================
#  ORDER RETURNS
# =============================================================================

class OrderReturnItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = OrderReturnItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'total']
        read_only_fields = ['total']

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total(self, obj: OrderReturnItem) -> Decimal:
        return obj.total if obj.pk else Decimal('0')


class OrderReturnSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    store_name = serializers.CharField(source='order.store.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = OrderReturnItemSerializer(many=True, read_only=True)
    total_amount_display = serializers.SerializerMethodField()

    class Meta:
        model = OrderReturn
        fields = [
            'id', 'order', 'order_id', 'store_name', 'status', 'status_display',
            'total_amount', 'total_amount_display', 'reason', 'items',
            'idempotency_key', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'total_amount', 'total_amount_display', 'idempotency_key', 'created_at', 'updated_at'
        ]

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total_amount_display(self, obj: OrderReturn) -> Decimal:
        return obj.total_amount


class CreateOrderReturnSerializer(serializers.Serializer):
    """Создание возврата с полной валидацией"""
    order_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1
    )
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_order_id(self, value: int) -> StoreOrder:
        try:
            order = StoreOrder.objects.select_related('store').get(id=value, is_fulfilled=True)
        except StoreOrder.DoesNotExist:
            raise serializers.ValidationError("Заказ не найден или не выполнен")
        return order

    def validate_items(self, items: List[Dict]) -> List[Dict]:
        if not items:
            raise serializers.ValidationError("Укажите хотя бы одну позицию")

        validated = []
        product_ids = set()

        for idx, item in enumerate(items):
            product_id = item.get('product')
            quantity = item.get('quantity')

            if not product_id or not isinstance(product_id, int):
                raise serializers.ValidationError(f"Позиция {idx + 1}: укажите product ID")
            if product_id in product_ids:
                raise serializers.ValidationError(f"Позиция {idx + 1}: дублирование")
            product_ids.add(product_id)

            try:
                qty = Decimal(str(quantity))
                if qty <= 0:
                    raise serializers.ValidationError("quantity > 0")
            except (InvalidOperation, TypeError):
                raise serializers.ValidationError(f"Позиция {idx + 1}: некорректное quantity")

            validated.append({'product_id': product_id, 'quantity': qty})

        return validated

    @transaction.atomic
    def create(self, validated_data: Dict) -> OrderReturn:
        order = validated_data.pop('order_id')
        items_data = validated_data.pop('items')
        idempotency_key = validated_data.pop('idempotency_key', None)

        if idempotency_key:
            existing = OrderReturn.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        return_request = OrderReturn.objects.create(
            order=order,
            **validated_data
        )

        if idempotency_key:
            return_request.idempotency_key = idempotency_key
            return_request.save(update_fields=['idempotency_key'])

        total = Decimal('0')
        for item in items_data:
            product = get_object_or_404(Product, id=item['product_id'])
            order_item = order.items.filter(product=product).first()
            if not order_item:
                raise serializers.ValidationError(f"Товар {product.name} не найден в заказе")

            max_qty = order_item.quantity
            if item['quantity'] > max_qty:
                raise serializers.ValidationError(f"Возврат {product.name}: превышено ({item['quantity']} > {max_qty})")

            return_item = OrderReturnItem(
                return_request=return_request,
                product=product,
                quantity=item['quantity'],
                price=order_item.price
            )
            return_item.save()
            total += return_item.total

        return_request.total_amount = total
        return_request.save(update_fields=['total_amount'])

        return return_request