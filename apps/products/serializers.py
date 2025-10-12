from rest_framework import serializers
from .models import (
    Product, ProductImage, Expense, ProductExpenseRelation,
    ProductionRecord, ProductionItem, MechanicalExpenseEntry,
    BonusHistory, StoreProductCounter, ProductCategory, DefectiveProduct
)


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

    # УБИРАЕМ create() — логика теперь в save() модели

class ProductExpenseRelationSerializer(serializers.ModelSerializer):
    expense_name = serializers.CharField(source='expense.name', read_only=True)
    expense_unit = serializers.CharField(source='expense.unit', read_only=True)

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
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'category', 'category_display',
            'price', 'is_bonus', 'is_active', 'position', 'images', 'created_at'
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    expense_relations = ProductExpenseRelationSerializer(many=True, read_only=True)
    suzerain_expense_name = serializers.CharField(source='suzerain_expense.name', read_only=True)

    uploaded_images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'category', 'price',
            'is_bonus', 'is_active', 'position',
            'suzerain_expense', 'suzerain_expense_name',
            'images', 'uploaded_images', 'expense_relations',
            'created_at', 'updated_at'
        ]

    def validate_uploaded_images(self, value):
        if len(value) > 3:
            raise serializers.ValidationError("Максимум 3 изображения")
        return value

    def validate(self, data):
        if data.get('category') == ProductCategory.WEIGHT and data.get('is_bonus'):
            raise serializers.ValidationError("Весовой товар не может быть бонусным")

        if self.instance and self.instance.category == ProductCategory.WEIGHT:
            if data.get('category') == ProductCategory.PIECE:
                raise serializers.ValidationError("Нельзя менять весовой товар на штучный")

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
    items = ProductionItemSerializer(many=True, read_only=True)
    mechanical_expenses = MechanicalExpenseEntrySerializer(many=True, read_only=True)

    class Meta:
        model = ProductionRecord
        fields = ['id', 'date', 'items', 'mechanical_expenses', 'created_at', 'updated_at']


# ============= BONUS SERIALIZERS =============

class BonusHistorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    store_name = serializers.CharField(source='store.username', read_only=True)

    class Meta:
        model = BonusHistory
        fields = ['id', 'store', 'store_name', 'product', 'product_name', 'bonus_count', 'date']


# ============= DEFECTIVE SERIALIZERS =============

class DefectiveProductSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_category = serializers.CharField(source='product.category', read_only=True)

    class Meta:
        model = DefectiveProduct
        fields = ['id', 'product', 'product_name', 'product_category', 'quantity', 'amount', 'reason', 'date',
                  'created_at']
        read_only_fields = ['partner', 'amount']

    def validate(self, data):
        product = data.get('product')
        quantity = data.get('quantity')

        # Для весовых — автоматический расчёт суммы
        if product.category == 'weight':
            data['amount'] = product.get_price_for_weight(quantity)
        else:
            # Для штучных
            data['amount'] = product.price * quantity

        return data

    def create(self, validated_data):
        validated_data['partner'] = self.context['request'].user
        return super().create(validated_data)