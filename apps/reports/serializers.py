from rest_framework import serializers
from .models import Report, SalesReport, InventoryReport
from datetime import date, datetime


class ReportSerializer(serializers.ModelSerializer):
    """Сериализатор отчетов"""

    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    store_name = serializers.CharField(source='store.store_name', read_only=True)
    partner_name = serializers.CharField(source='partner.get_full_name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = Report
        fields = [
            'id', 'name', 'report_type', 'period',
            'date_from', 'date_to', 'store', 'store_name',
            'partner', 'partner_name', 'product', 'product_name',
            'data', 'created_by', 'created_by_name',
            'created_at', 'is_automated'
        ]
        read_only_fields = ['created_at', 'created_by']


class SalesReportSerializer(serializers.ModelSerializer):
    """Сериализатор отчетов по продажам"""

    store_name = serializers.CharField(source='store.store_name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    profit_margin = serializers.SerializerMethodField()

    class Meta:
        model = SalesReport
        fields = [
            'id', 'date', 'store', 'store_name', 'product', 'product_name',
            'orders_count', 'total_quantity', 'total_revenue',
            'total_bonus_discount', 'total_cost', 'profit', 'profit_margin',
            'updated_at'
        ]

    def get_profit_margin(self, obj):
        """Рассчитать маржу прибыли в процентах"""
        if obj.total_revenue > 0:
            return round((obj.profit / obj.total_revenue) * 100, 2)
        return 0


class InventoryReportSerializer(serializers.ModelSerializer):
    """Сериализатор отчетов по остаткам"""

    store_name = serializers.CharField(source='store.store_name', read_only=True)
    partner_name = serializers.CharField(source='partner.get_full_name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    turnover_ratio = serializers.SerializerMethodField()

    class Meta:
        model = InventoryReport
        fields = [
            'id', 'date', 'store', 'store_name', 'partner', 'partner_name',
            'product', 'product_name', 'opening_balance', 'received_quantity',
            'sold_quantity', 'closing_balance', 'opening_value',
            'closing_value', 'turnover_ratio'
        ]

    def get_turnover_ratio(self, obj):
        """Коэффициент оборачиваемости"""
        avg_balance = (obj.opening_balance + obj.closing_balance) / 2
        if avg_balance > 0:
            return round(obj.sold_quantity / avg_balance, 2)
        return 0


class ReportGenerateSerializer(serializers.Serializer):
    """Сериализатор для генерации отчетов"""

    report_type = serializers.ChoiceField(choices=Report.REPORT_TYPES)
    period = serializers.ChoiceField(choices=Report.PERIODS)
    date_from = serializers.DateField()
    date_to = serializers.DateField()

    # Опциональные фильтры
    store_id = serializers.IntegerField(required=False)
    partner_id = serializers.IntegerField(required=False)
    product_id = serializers.IntegerField(required=False)

    def validate(self, data):
        """Валидация дат"""
        if data['date_from'] > data['date_to']:
            raise serializers.ValidationError("Дата начала не может быть больше даты окончания")

        # Проверяем что даты не в будущем
        if data['date_to'] > date.today():
            raise serializers.ValidationError("Дата окончания не может быть в будущем")

        return data


class ReportAnalyticsSerializer(serializers.Serializer):
    """Сериализатор аналитики отчетов"""

    # Фильтры
    report_type = serializers.ChoiceField(choices=Report.REPORT_TYPES, required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    store_id = serializers.IntegerField(required=False)
    partner_id = serializers.IntegerField(required=False)


class DashboardSerializer(serializers.Serializer):
    """Сериализатор дашборда"""

    # Общая статистика
    total_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_orders = serializers.IntegerField()
    total_profit = serializers.DecimalField(max_digits=12, decimal_places=2)
    profit_margin = serializers.FloatField()

    # Динамика по дням
    daily_sales = serializers.ListField(child=serializers.DictField())

    # Топы
    top_products = serializers.ListField(child=serializers.DictField())
    top_stores = serializers.ListField(child=serializers.DictField())

    # Остатки
    low_stock_products = serializers.ListField(child=serializers.DictField())

    # Долги
    total_debt = serializers.DecimalField(max_digits=12, decimal_places=2)
    overdue_debt = serializers.DecimalField(max_digits=12, decimal_places=2)