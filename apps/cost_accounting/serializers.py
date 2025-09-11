from rest_framework import serializers
from .models import (
    Expense, ProductExpense, DailyExpenseLog, ProductionBatch,
    MonthlyOverheadBudget, BillOfMaterial, BOMLine
)


class ExpenseSerializer(serializers.ModelSerializer):
    """Сериализатор расходов"""

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class ProductExpenseSerializer(serializers.ModelSerializer):
    """Сериализатор расходов на продукт"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    expense_name = serializers.CharField(source='expense.name', read_only=True)

    class Meta:
        model = ProductExpense
        fields = '__all__'


class DailyExpenseLogSerializer(serializers.ModelSerializer):
    """Сериализатор ежедневных логов расходов"""

    expense_name = serializers.CharField(source='expense.name', read_only=True)

    class Meta:
        model = DailyExpenseLog
        fields = '__all__'


class ProductionBatchSerializer(serializers.ModelSerializer):
    """Сериализатор производственных партий"""

    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = ProductionBatch
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class MonthlyOverheadBudgetSerializer(serializers.ModelSerializer):
    """Сериализатор месячных бюджетов накладных расходов"""

    class Meta:
        model = MonthlyOverheadBudget
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class BOMLineSerializer(serializers.ModelSerializer):
    """Сериализатор строк рецептуры"""

    expense_name = serializers.CharField(source='expense.name', read_only=True)
    expense_unit = serializers.CharField(source='expense.unit', read_only=True)
    expense_price = serializers.DecimalField(source='expense.price_per_unit', max_digits=10, decimal_places=2,
                                             read_only=True)
    line_total_cost = serializers.SerializerMethodField()

    class Meta:
        model = BOMLine
        fields = ['id', 'expense', 'expense_name', 'expense_unit', 'expense_price',
                  'quantity', 'line_total_cost', 'notes']

    def get_line_total_cost(self, obj):
        """Расчёт стоимости строки"""
        return float(obj.quantity * obj.expense.price_per_unit)


class BOMSerializer(serializers.ModelSerializer):
    """Сериализатор рецептур (Bill of Materials)"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    lines = BOMLineSerializer(many=True, read_only=True)
    total_cost = serializers.SerializerMethodField()
    cost_per_unit = serializers.SerializerMethodField()

    class Meta:
        model = BillOfMaterial
        fields = ['id', 'name', 'description', 'product', 'product_name',
                  'output_quantity', 'output_unit', 'is_active', 'lines',
                  'total_cost', 'cost_per_unit', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_total_cost(self, obj):
        """Общая стоимость рецептуры"""
        return float(sum(line.quantity * line.expense.price_per_unit for line in obj.lines.all()))

    def get_cost_per_unit(self, obj):
        """Себестоимость единицы продукции"""
        total_cost = self.get_total_cost(obj)
        if obj.output_quantity > 0:
            return float(total_cost / obj.output_quantity)
        return 0


class CostAnalyticsSerializer(serializers.Serializer):
    """Сериализатор аналитики себестоимости"""

    total_expenses = serializers.IntegerField()
    total_products_with_cost = serializers.IntegerField()
    total_batches = serializers.IntegerField()
    expenses_by_type = serializers.ListField()
    avg_production_cost = serializers.FloatField()
    top_expenses = serializers.ListField()


class BatchCostCalculationSerializer(serializers.Serializer):
    """Сериализатор расчёта себестоимости партии"""

    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)
    production_date = serializers.DateField()
    notes = serializers.CharField(max_length=500, required=False)

    def validate_product_id(self, value):
        """Проверяем существование товара"""
        from apps.products.models import Product
        try:
            Product.objects.get(id=value)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Товар не найден")
        return value


class BonusAnalysisSerializer(serializers.Serializer):
    """Сериализатор анализа влияния бонусов на себестоимость"""

    total_bonus_cost = serializers.FloatField()
    bonus_percentage_of_revenue = serializers.FloatField()
    products_affected = serializers.IntegerField()
    average_bonus_per_order = serializers.FloatField()
    recommendations = serializers.ListField(child=serializers.CharField())


class QuickSetupSerializer(serializers.Serializer):
    """Сериализатор быстрой настройки"""

    create_default_expenses = serializers.BooleanField(default=True)
    create_sample_bom = serializers.BooleanField(default=False)
    setup_monthly_budgets = serializers.BooleanField(default=False)