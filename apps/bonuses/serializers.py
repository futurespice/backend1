from rest_framework import serializers
from django.db import models
from .models import BonusRule, BonusHistory, BonusBalance, BonusRuleUsage


class BonusRuleSerializer(serializers.ModelSerializer):
    """Сериализатор правил бонусов"""

    products_count = serializers.SerializerMethodField()
    stores_count = serializers.SerializerMethodField()
    usage_count = serializers.SerializerMethodField()

    class Meta:
        model = BonusRule
        fields = [
            'id', 'name', 'description', 'bonus_type', 'every_nth_free',
            'percentage_discount', 'fixed_amount', 'points_multiplier',
            'applies_to_all_products', 'products', 'categories',
            'applies_to_all_stores', 'stores', 'min_order_amount', 'max_discount_amount',
            'is_active', 'start_date', 'end_date', 'max_uses_per_store', 'max_uses_total',
            'priority', 'products_count', 'stores_count', 'usage_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']

    def get_products_count(self, obj):
        """Количество товаров в правиле"""
        if obj.applies_to_all_products:
            return "Все товары"
        return obj.products.count()

    def get_stores_count(self, obj):
        """Количество магазинов в правиле"""
        if obj.applies_to_all_stores:
            return "Все магазины"
        return obj.stores.count()

    def get_usage_count(self, obj):
        """Количество использований правила"""
        return obj.usage_stats.aggregate(
            total=models.Sum('times_used')
        )['total'] or 0


class BonusRuleCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор создания/обновления правил бонусов"""

    class Meta:
        model = BonusRule
        fields = [
            'name', 'description', 'bonus_type', 'every_nth_free',
            'percentage_discount', 'fixed_amount', 'points_multiplier',
            'applies_to_all_products', 'products', 'categories',
            'applies_to_all_stores', 'stores', 'min_order_amount', 'max_discount_amount',
            'is_active', 'start_date', 'end_date', 'max_uses_per_store', 'max_uses_total',
            'priority'
        ]

    def validate(self, attrs):
        """Валидация правила"""
        bonus_type = attrs.get('bonus_type')

        if bonus_type == 'percentage' and not attrs.get('percentage_discount'):
            raise serializers.ValidationError(
                "Для процентной скидки необходимо указать процент"
            )

        if bonus_type == 'fixed_amount' and not attrs.get('fixed_amount'):
            raise serializers.ValidationError(
                "Для фиксированной скидки необходимо указать сумму"
            )

        if bonus_type == 'nth_free' and not attrs.get('every_nth_free'):
            raise serializers.ValidationError(
                "Для правила N-го товара необходимо указать интервал"
            )

        return attrs

    def create(self, validated_data):
        """Создание правила с указанием создателя"""
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class BonusHistorySerializer(serializers.ModelSerializer):
    """Сериализатор истории бонусов"""

    store_name = serializers.CharField(source='store.store_name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    rule_name = serializers.CharField(source='rule.name', read_only=True)
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = BonusHistory
        fields = [
            'id', 'store', 'store_name', 'product', 'product_name', 'product_price',
            'order', 'order_number', 'rule', 'rule_name', 'total_items_purchased',
            'bonus_items', 'points_earned', 'points_used', 'discount_amount',
            'created_at', 'notes'
        ]

    def get_order_number(self, obj):
        """Номер заказа"""
        return f"#{obj.order.id}" if obj.order else None


class BonusBalanceSerializer(serializers.ModelSerializer):
    """Сериализатор баланса бонусов"""

    store_name = serializers.CharField(source='store.store_name', read_only=True)
    store_address = serializers.CharField(source='store.address', read_only=True)
    available_points = serializers.SerializerMethodField()
    savings_percentage = serializers.SerializerMethodField()

    class Meta:
        model = BonusBalance
        fields = [
            'id', 'store', 'store_name', 'store_address',
            'total_points_earned', 'total_points_used', 'current_points', 'available_points',
            'total_items_purchased', 'total_bonus_items_received', 'total_amount_saved',
            'savings_percentage', 'last_bonus_date', 'updated_at'
        ]

    def get_available_points(self, obj):
        """Доступные очки (то же что current_points)"""
        return obj.current_points

    def get_savings_percentage(self, obj):
        """Процент экономии"""
        if obj.total_items_purchased > 0:
            return round((obj.total_bonus_items_received / obj.total_items_purchased) * 100, 2)
        return 0


class BonusRuleUsageSerializer(serializers.ModelSerializer):
    """Сериализатор использования правил"""

    rule_name = serializers.CharField(source='rule.name', read_only=True)
    store_name = serializers.CharField(source='store.store_name', read_only=True)
    average_discount = serializers.SerializerMethodField()

    class Meta:
        model = BonusRuleUsage
        fields = [
            'id', 'rule', 'rule_name', 'store', 'store_name',
            'times_used', 'total_discount_given', 'total_bonus_items_given',
            'average_discount', 'first_used', 'last_used'
        ]

    def get_average_discount(self, obj):
        """Средняя скидка за использование"""
        if obj.times_used > 0:
            return float(obj.total_discount_given / obj.times_used)
        return 0


class BonusCalculationRequestSerializer(serializers.Serializer):
    """Сериализатор запроса расчёта бонусов"""

    items = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField()
        ),
        help_text="Список товаров для расчёта: [{'product_id': 1, 'quantity': 5}]"
    )

    def validate_items(self, value):
        """Валидация товаров"""
        if not value:
            raise serializers.ValidationError("Список товаров не может быть пустым")

        for item in value:
            if 'product_id' not in item or 'quantity' not in item:
                raise serializers.ValidationError(
                    "Каждый товар должен содержать product_id и quantity"
                )

            try:
                int(item['product_id'])
                float(item['quantity'])
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    "product_id должен быть числом, quantity - числом"
                )

        return value


class BonusCalculationResponseSerializer(serializers.Serializer):
    """Сериализатор ответа расчёта бонусов"""

    items = serializers.ListField(
        child=serializers.DictField()
    )
    total_bonus_discount = serializers.FloatField()


class BonusAnalyticsRequestSerializer(serializers.Serializer):
    """Сериализатор запроса аналитики бонусов"""

    store_id = serializers.IntegerField(required=False)
    product_id = serializers.IntegerField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        """Валидация периода"""
        date_from = attrs.get('date_from')
        date_to = attrs.get('date_to')

        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                "Дата начала не может быть больше даты окончания"
            )

        return attrs


class BonusAnalyticsResponseSerializer(serializers.Serializer):
    """Сериализатор ответа аналитики бонусов"""

    total_bonus_items = serializers.IntegerField()
    total_discount = serializers.FloatField()
    total_orders_with_bonus = serializers.IntegerField()
    total_products_with_bonus = serializers.IntegerField()
    top_products = serializers.ListField()
    top_stores = serializers.ListField()

    # Дополнительная статистика
    average_bonus_per_order = serializers.FloatField(required=False)
    bonus_penetration_rate = serializers.FloatField(required=False)  # % заказов с бонусами
    most_popular_rule = serializers.CharField(required=False)


# Импорт models в конце для избежания циклических импортов
class BonusCalculationSerializer(serializers.Serializer):
    """Сериализатор для расчёта бонусов"""
    items = serializers.ListField(
        child=serializers.DictField(),
        help_text="Список товаров: [{'product_id': 1, 'quantity': 5}]"
    )


class BonusAnalyticsSerializer(serializers.Serializer):
    """Сериализатор аналитики бонусов"""
    total_bonus_items = serializers.IntegerField()
    total_discount = serializers.FloatField()
    total_orders_with_bonus = serializers.IntegerField()
    total_products_with_bonus = serializers.IntegerField()
    top_products = serializers.ListField()
    top_stores = serializers.ListField()

