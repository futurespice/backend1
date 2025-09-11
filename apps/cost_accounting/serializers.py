from rest_framework import serializers
from .models import (
    Expense, ProductExpense, DailyExpenseLog, ProductionBatch,
    MonthlyOverheadBudget, BillOfMaterial, BOMLine
)
from drf_spectacular.utils import extend_schema_field
from typing import Optional, Dict, Any

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

    @extend_schema_field({"type": "number", "format": "float"})
    def get_line_total_cost(self, obj) -> float:
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
        fields = [
            'id', 'product', 'product_name', 'name', 'description',
            'output_quantity', 'is_active', 'lines', 'total_cost', 'cost_per_unit',
            'created_at'
        ]
        read_only_fields = ['created_at']

    @extend_schema_field({"type": "number", "format": "float"})
    def get_total_cost(self, obj) -> float:
        """Общая стоимость рецептуры"""
        return float(sum(line.quantity * line.expense.price_per_unit for line in obj.lines.all()))

    @extend_schema_field({"type": "number", "format": "float"})
    def get_cost_per_unit(self, obj) -> float:
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


class BonusAnalysisSerializer(serializers.Serializer):
    """Сериализатор анализа бонусов"""

    message = serializers.CharField()


class BatchCostCalculationSerializer(serializers.Serializer):
    """Сериализатор расчета стоимости партии"""

    product_id = serializers.IntegerField(write_only=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, write_only=True)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    cost_per_unit = serializers.DecimalField(max_digits=10, decimal_places=4, read_only=True)

class QuickSetupSerializer(serializers.Serializer):
    """Сериализатор быстрой настройки"""

    create_default_expenses = serializers.BooleanField(default=True)
    create_sample_bom = serializers.BooleanField(default=False)
    setup_monthly_budgets = serializers.BooleanField(default=False)


