from rest_framework import serializers
from .models import BonusRule, BonusHistory


class BonusRuleSerializer(serializers.ModelSerializer):
    """Сериализатор правил бонусов"""

    products_count = serializers.SerializerMethodField()

    class Meta:
        model = BonusRule
        fields = [
            'id', 'name', 'description', 'every_nth_free',
            'applies_to_all_products', 'products', 'products_count',
            'is_active', 'start_date', 'end_date',
            'created_at', 'updated_at'
        ]

    def get_products_count(self, obj):
        if obj.applies_to_all_products:
            return "Все товары"
        return f"{obj.products.count()} товаров"


class BonusHistorySerializer(serializers.ModelSerializer):
    """Сериализатор истории бонусов"""

    store_name = serializers.CharField(source='store.store_name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    order_id = serializers.IntegerField(source='order.id', read_only=True)

    class Meta:
        model = BonusHistory
        fields = [
            'id', 'store', 'store_name', 'product', 'product_name',
            'order', 'order_id', 'order_item',
            'purchased_quantity', 'bonus_quantity', 'cumulative_quantity',
            'unit_price', 'bonus_discount', 'created_at'
        ]
        read_only_fields = ['created_at']


class BonusCalculationSerializer(serializers.Serializer):
    """Сериализатор для расчёта бонусов"""

    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=8, decimal_places=3, min_value=0.001)

    def validate_product_id(self, value):
        from apps.products.models import Product
        try:
            Product.objects.get(id=value)
            return value
        except Product.DoesNotExist:
            raise serializers.ValidationError("Товар не найден")


class BonusAnalyticsSerializer(serializers.Serializer):
    """Сериализатор аналитики бонусов"""

    store_id = serializers.IntegerField(required=False)
    product_id = serializers.IntegerField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)