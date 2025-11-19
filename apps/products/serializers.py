from rest_framework import serializers
from decimal import Decimal
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from .models import (
    Product, ProductImage, Expense, ProductExpenseRelation,
    ProductionRecord, ProductionItem, MechanicalExpenseEntry,
    BonusHistory, StoreProductCounter, DefectiveProduct
)
from typing import Any
from .models import ProductionRecord, ProductionItem, MechanicalExpenseEntry
from .services import CostCalculator
# ============= CATEGORY =============




# ============= EXPENSE SERIALIZERS =============

class ExpenseSerializer(serializers.ModelSerializer):
    expense_type_display = serializers.CharField(source='get_expense_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    state_display = serializers.CharField(source='get_state_display', read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id', 'name', 'expense_type', 'expense_type_display',
            'price_per_unit', 'unit', 'monthly_amount',
            'status', 'status_display', 'state', 'state_display',
            'apply_type', 'is_active', 'created_at', 'updated_at'
        ]

    def validate(self, data):
        expense_type = data.get('expense_type')

        if expense_type == 'physical':
            if not data.get('price_per_unit') or not data.get('unit'):
                raise serializers.ValidationError("Физические расходы требуют цену и единицу")

        if expense_type == 'overhead':
            if not data.get('monthly_amount'):
                raise serializers.ValidationError("Накладные расходы требуют месячную сумму")

        return data


class ProductExpenseRelationSerializer(serializers.ModelSerializer):
    expense_name = serializers.CharField(source='expense.name', read_only=True)
    expense_unit = serializers.CharField(source='expense.unit', read_only=True, allow_null=True)

    class Meta:
        model = ProductExpenseRelation
        fields = ['id', 'expense', 'expense_name', 'expense_unit', 'proportion']


# ============= PRODUCT SERIALIZERS =============

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'position']


class ProductListSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description',
            'unit', 'unit_display', 'price', 'is_weight_based',
            'is_active', 'is_available', 'stock_quantity',
            'images', 'created_at'
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    expense_relations = ProductExpenseRelationSerializer(many=True, read_only=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)

    uploaded_images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description',
            'unit', 'unit_display', 'price', 'price_per_100g', 'cost_price',
            'is_weight_based', 'is_active', 'is_available',
            'stock_quantity', 'image', 'images', 'uploaded_images',
            'expense_relations', 'created_at', 'updated_at'
        ]

    def validate_uploaded_images(self, value):
        if len(value) > 3:
            raise serializers.ValidationError("Максимум 3 изображения")
        return value

    def validate(self, data):
        # Весовые товары НЕ могут быть бонусными
        if data.get('is_weight_based'):
            if self.instance and hasattr(self.instance, 'unit'):
                if data.get('unit', self.instance.unit) != 'kg':
                    raise serializers.ValidationError(
                        "Весовые товары должны иметь единицу измерения 'кг'"
                    )

        return data

    def create(self, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])
        product = super().create(validated_data)

        for idx, image in enumerate(uploaded_images):
            ProductImage.objects.create(product=product, image=image, position=idx)

        return product

    def update(self, instance, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', None)
        product = super().update(instance, validated_data)

        if uploaded_images is not None:
            product.images.all().delete()
            for idx, image in enumerate(uploaded_images):
                ProductImage.objects.create(product=product, image=image, position=idx)

        return product


# ============= PRODUCTION SERIALIZERS =============

class MechanicalExpenseEntrySerializer(serializers.ModelSerializer):
    expense_name = serializers.CharField(source='expense.name', read_only=True)

    class Meta:
        model = MechanicalExpenseEntry
        fields = ['id', 'expense', 'expense_name', 'amount_spent']



class ProductionItemSerializer(serializers.ModelSerializer):
    """Сериализатор позиции производства — с расчётом себестоимости"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(
        source='product.price', max_digits=14, decimal_places=2, read_only=True
    )

    # Расчётные поля — только для чтения
    ingredient_cost = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    overhead_cost = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_cost = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    cost_price = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    net_profit = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = ProductionItem
        fields = [
            'id',
            'product', 'product_name', 'product_price',
            'quantity_produced', 'suzerain_amount',
            'ingredient_cost', 'overhead_cost', 'total_cost',
            'cost_price', 'revenue', 'net_profit',
        ]
        read_only_fields = [
            'ingredient_cost', 'overhead_cost', 'total_cost',
            'cost_price', 'revenue', 'net_profit',
            'product_name', 'product_price',
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Валидация: либо quantity_produced, либо suzerain_amount"""
        quantity = attrs.get('quantity_produced')
        suzerain_amount = attrs.get('suzerain_amount')

        if not quantity and not suzerain_amount:
            raise serializers.ValidationError(
                "Укажите либо quantity_produced, либо suzerain_amount"
            )
        if quantity and suzerain_amount:
            raise serializers.ValidationError(
                "Нельзя указывать и quantity_produced, и suzerain_amount одновременно"
            )

        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError("quantity_produced должен быть > 0")

        if suzerain_amount is not None and suzerain_amount <= 0:
            raise serializers.ValidationError("suzerain_amount должен быть > 0")

        return attrs

    def create(self, validated_data: dict[str, Any]) -> ProductionItem:
        item = super().create(validated_data)
        CostCalculator.calculate_production_item(item)
        return item

    def update(self, instance: ProductionItem, validated_data: dict[str, Any]) -> ProductionItem:
        item = super().update(instance, validated_data)
        CostCalculator.calculate_production_item(item)
        return item


class ProductionRecordSerializer(serializers.ModelSerializer):
    """Сериализатор производственной записи — с вложенными данными"""
    partner_name = serializers.CharField(source='partner.get_full_name', read_only=True)
    partner_phone = serializers.CharField(source='partner.phone', read_only=True)

    items = ProductionItemSerializer(many=True, read_only=True)
    mechanical_expenses = serializers.SerializerMethodField()

    # Итоговые показатели за день
    total_produced = serializers.DecimalField(max_digits=18, decimal_places=3, read_only=True)
    total_revenue = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_cost = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    net_profit = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = ProductionRecord
        fields = [
            'id', 'partner', 'partner_name', 'partner_phone',
            'date', 'created_at', 'updated_at',
            'items', 'mechanical_expenses',
            'total_produced', 'total_revenue', 'total_cost', 'net_profit',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_mechanical_expenses(self, obj: ProductionRecord) -> list[dict[str, Any]]:
        """Вложенные механические расходы"""
        qs = obj.mechanical_entries.select_related('expense').all()
        return [
            {
                'expense_name': entry.expense.name,
                'amount_spent': str(entry.amount_spent),
                'comment': entry.comment or '',
            }
            for entry in qs
        ]

    def to_representation(self, instance: ProductionRecord) -> dict[str, Any]:
        """Добавляем итоги по записи"""
        data = super().to_representation(instance)

        # Итоги по всем позициям
        items = instance.items.all()
        total_produced = sum(item.quantity_produced for item in items if item.quantity_produced)
        total_revenue = sum(item.revenue for item in items if item.revenue)
        total_cost = sum(item.total_cost for item in items if item.total_cost)
        net_profit = total_revenue - total_cost

        data.update({
            'total_produced': str(total_produced.quantize(Decimal('0.001')) if total_produced else Decimal('0')),
            'total_revenue': str(total_revenue.quantize(Decimal('0.01'))),
            'total_cost': str(total_cost.quantize(Decimal('0.01'))),
            'net_profit': str(net_profit.quantize(Decimal('0.01'))),
        })

        return data

# ============= BONUS SERIALIZERS =============

class BonusHistorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True)
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    order_id = serializers.IntegerField(source='order.id', read_only=True, allow_null=True)

    class Meta:
        model = BonusHistory
        fields = [
            'id', 'store', 'store_name', 'partner', 'partner_name',
            'product', 'product_name', 'quantity', 'bonus_value',
            'order_id', 'created_at'
        ]


# ============= DEFECTIVE SERIALIZERS =============

class DefectiveProductSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = DefectiveProduct
        fields = [
            'id', 'product', 'product_name', 'partner', 'partner_name',
            'quantity', 'reason', 'status', 'status_display',
            'reported_at', 'resolved_at'
        ]
        read_only_fields = ['partner', 'reported_at', 'resolved_at']


class ProductionFinanceSummarySerializer(serializers.Serializer):
    """
    Агрегированный фин.результат по ProductionRecord.
    """

    record_id = serializers.IntegerField()
    date = serializers.DateField()

    total_quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    ingredient_cost = serializers.DecimalField(max_digits=14, decimal_places=2)
    overhead_cost = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_cost = serializers.DecimalField(max_digits=14, decimal_places=2)
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2)
    net_profit = serializers.DecimalField(max_digits=14, decimal_places=2)

    fixed_daily_overhead = serializers.DecimalField(max_digits=14, decimal_places=2)
    mechanical_daily_overhead = serializers.DecimalField(
        max_digits=14, decimal_places=2
    )

    cost_per_unit = serializers.DecimalField(max_digits=14, decimal_places=4)
    profit_per_unit = serializers.DecimalField(max_digits=14, decimal_places=4)