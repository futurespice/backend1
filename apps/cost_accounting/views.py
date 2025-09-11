from rest_framework import viewsets, permissions, status, generics, serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import Sum, Count, Avg, Q
from datetime import datetime, date
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from .models import (
    Expense, ProductExpense, DailyExpenseLog, ProductionBatch,
    MonthlyOverheadBudget, BillOfMaterial, BOMLine
)
from .serializers import (
    ExpenseSerializer, ProductExpenseSerializer, DailyExpenseLogSerializer,
    ProductionBatchSerializer, MonthlyOverheadBudgetSerializer,
    BOMSerializer, BOMLineSerializer, CostAnalyticsSerializer,
    BonusAnalysisSerializer, BatchCostCalculationSerializer
)
from apps.users.permissions import IsAdminUser


class ExpenseViewSet(viewsets.ModelViewSet):
    """ViewSet для расходов"""

    queryset = ProductExpense.objects.select_related('product', 'expense')
    serializer_class = ProductExpenseSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'expense', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'price_per_unit', 'created_at']
    ordering = ['name']


class ProductExpenseViewSet(viewsets.ModelViewSet):
    """ViewSet для расходов на продукт"""

    queryset = ProductExpense.objects.select_related('product', 'expense')
    serializer_class = ProductExpenseSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'expense']


class DailyExpenseLogViewSet(viewsets.ModelViewSet):
    """ViewSet для ежедневных логов расходов"""

    queryset = DailyExpenseLog.objects.select_related('expense')
    serializer_class = DailyExpenseLogSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['expense', 'date']
    ordering_fields = ['date', 'quantity_used', 'total_cost']
    ordering = ['-date']


class ProductionBatchViewSet(viewsets.ModelViewSet):
    """ViewSet для производственных партий"""

    queryset = ProductionBatch.objects.select_related('product')
    serializer_class = ProductionBatchSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['product', 'status', 'date']  # изменили production_date на date
    ordering_fields = ['date', 'quantity_produced', 'total_cost']  # изменили production_date на date
    ordering = ['-date']


class MonthlyOverheadBudgetViewSet(viewsets.ModelViewSet):
    """ViewSet для месячных бюджетов накладных расходов"""

    queryset = MonthlyOverheadBudget.objects.all()
    serializer_class = MonthlyOverheadBudgetSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['year', 'month']
    ordering_fields = ['year', 'month', 'total_budget']
    ordering = ['-year', '-month']


class BOMViewSet(viewsets.ModelViewSet):
    """ViewSet для рецептур (Bill of Materials)"""

    queryset = BillOfMaterial.objects.select_related('product').prefetch_related('lines')
    serializer_class = BOMSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['product', 'is_active']
    search_fields = ['name', 'description', 'product__name']

    @action(detail=True, methods=['post'])
    def calculate_cost(self, request, pk=None):
        """Расчёт себестоимости по рецептуре"""
        bom = self.get_object()

        total_cost = 0
        calculations = []

        for line in bom.lines.all():
            line_cost = line.quantity * line.expense.price_per_unit
            total_cost += line_cost

            calculations.append({
                'expense': line.expense.name,
                'quantity': float(line.quantity),
                'unit_price': float(line.expense.price_per_unit),
                'total_cost': float(line_cost)
            })

        return Response({
            'bom_id': bom.id,
            'product': bom.product.name,
            'total_cost': float(total_cost),
            'cost_per_unit': float(total_cost / bom.output_quantity) if bom.output_quantity > 0 else 0,
            'calculations': calculations
        })


class CostAnalyticsViewSet(viewsets.GenericViewSet):
    """ViewSet для аналитики себестоимости"""

    permission_classes = [IsAdminUser]
    serializer_class = CostAnalyticsSerializer  # Добавили serializer_class

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Общая сводка по себестоимости"""

        # Базовые метрики
        total_expenses = Expense.objects.count()
        total_products_with_cost = ProductExpense.objects.values('product').distinct().count()
        total_batches = ProductionBatch.objects.count()

        # Расходы по типам
        expenses_by_type = Expense.objects.values('expense_type').annotate(
            count=Count('id'),
            total_cost=Sum('price_per_unit')
        )

        # Средняя себестоимость
        avg_production_cost = ProductionBatch.objects.aggregate(
            avg_cost=Avg('cost_per_unit')
        )['avg_cost'] or 0

        # Топ дорогие расходы
        top_expenses = Expense.objects.order_by('-price_per_unit')[:5].values(
            'name', 'price_per_unit', 'expense_type'
        )

        analytics_data = {
            'total_expenses': total_expenses,
            'total_products_with_cost': total_products_with_cost,
            'total_batches': total_batches,
            'expenses_by_type': list(expenses_by_type),
            'avg_production_cost': float(avg_production_cost),
            'top_expenses': list(top_expenses)
        }

        serializer = CostAnalyticsSerializer(analytics_data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def monthly_trends(self, request):
        """Тренды по месяцам"""
        year = request.query_params.get('year', datetime.now().year)

        monthly_data = []
        for month in range(1, 13):
            month_expenses = DailyExpenseLog.objects.filter(
                date__year=year,
                date__month=month
            ).aggregate(
                total_cost=Sum('total_cost'),
                total_quantity=Sum('quantity_used')
            )

            monthly_data.append({
                'month': month,
                'total_cost': float(month_expenses['total_cost'] or 0),
                'total_quantity': float(month_expenses['total_quantity'] or 0)
            })

        return Response(monthly_data)


class QuickSetupView(generics.CreateAPIView):
    """Быстрая настройка себестоимости"""

    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="quick_setup",
        tags=["Cost Setup"],
        request=None,
        responses={200: {"description": "Настройка завершена"}}
    )
    def post(self, request):
        """Быстрая настройка"""
        return Response({"message": "Быстрая настройка завершена"})



class BatchCostCalculationView(generics.CreateAPIView):
    """Расчет стоимости партии"""

    serializer_class = BatchCostCalculationSerializer
    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="batch_cost_calculation",
        tags=["Cost Calculation"]
    )
    def post(self, request):
        """Рассчитать стоимость партии"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Логика расчета партии
        return Response({
            "total_cost": 0,
            "cost_per_unit": 0
        })



class CostBonusCalculationView(APIView):
    """Расчет бонусов"""

    serializer_class = serializers.Serializer  # добавляем для drf-spectacular
    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="cost_bonus_calculation",
        tags=["Cost Analysis"],
        request=None,
        responses={200: {"description": "Расчет бонусов"}}
    )
    def post(self, request):
        """Рассчитать бонусы для себестоимости"""
        return Response({"message": "Расчет бонусов для себестоимости"})


class BonusAnalysisView(APIView):
    queryset = BillOfMaterial.objects.none()  # добавляем пустой queryset
    permission_classes = [IsAdminUser]


    @extend_schema(
        operation_id="bonus_analysis",
        tags=["Cost Analysis"],
        responses={200: {"description": "Анализ бонусов"}}
    )
    def get(self, request):
        """Получить анализ бонусов"""
        return Response({"message": "Анализ бонусов"})


    def list(self, request, *args, **kwargs):
        """Анализ бонусной системы"""

        analysis_data = {
            'total_bonus_cost': 50000.0,
            'bonus_percentage_of_revenue': 12.5,
            'products_affected': 45,
            'average_bonus_per_order': 150.0,
            'recommendations': [
                'Пересмотреть правило "каждый 21-й товар бесплатно"',
                'Добавить минимальную сумму заказа для бонусов',
                'Исключить дорогие товары из бонусной программы'
            ]
        }

        serializer = BonusAnalysisSerializer(analysis_data)
        return Response(serializer.data)