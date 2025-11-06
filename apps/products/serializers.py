from rest_framework import serializers
from decimal import Decimal
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from .models import (
    ProductCategory, Product, ProductImage, Expense, ProductExpenseRelation,
    ProductionRecord, ProductionItem, MechanicalExpenseEntry,
    BonusHistory, StoreProductCounter, DefectiveProduct
)


# ============= CATEGORY =============

class ProductCategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.name', read_only=True, allow_null=True)

    class Meta:
        model = ProductCategory
        fields = ['id', 'name', 'description', 'parent', 'parent_name', 'is_active', 'created_at']


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
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'category', 'category_name',
            'unit', 'unit_display', 'price', 'is_weight_based',
            'is_active', 'is_available', 'stock_quantity',
            'images', 'created_at'
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    expense_relations = ProductExpenseRelationSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)

    uploaded_images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'category', 'category_name',
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
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = ProductionItem
        fields = [
            'id', 'product', 'product_name',
            'quantity_produced', 'suzerain_amount',
            'ingredient_cost', 'overhead_cost', 'total_cost',
            'cost_price', 'revenue', 'net_profit'
        ]
        read_only_fields = [
            'ingredient_cost', 'overhead_cost', 'total_cost',
            'cost_price', 'revenue', 'net_profit'
        ]


class ProductionRecordSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    items = ProductionItemSerializer(many=True, read_only=True)
    mechanical_expenses = MechanicalExpenseEntrySerializer(many=True, read_only=True)

    class Meta:
        model = ProductionRecord
        fields = [
            'id', 'partner', 'partner_name', 'date',
            'items', 'mechanical_expenses',
            'created_at', 'updated_at'
        ]


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