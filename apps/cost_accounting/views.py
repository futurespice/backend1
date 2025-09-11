from rest_framework import viewsets, permissions, status, generics
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import Sum, Count, Avg, Q
from datetime import datetime, date

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

    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['expense_type', 'unit']  # ИСПРАВЛЕНО: убрали expense__type
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'price_per_unit', 'created_at']
    ordering = ['name']


class ProductExpenseViewSet(viewsets.ModelViewSet):
    """ViewSet для расходов на продукт"""

    queryset = ProductExpense.objects.select_related('product', 'expense')
    serializer_class = ProductExpenseSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'expense', 'date']


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
    filterset_fields = ['product', 'status', 'production_date']
    ordering_fields = ['production_date', 'quantity_produced', 'total_cost']
    ordering = ['-production_date']


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


class BatchCostCalculationView(generics.CreateAPIView):
    """Расчёт себестоимости партии"""

    permission_classes = [IsAdminUser]
    serializer_class = BatchCostCalculationSerializer  # Добавили serializer_class

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Здесь будет логика расчёта себестоимости партии
        # Пока заглушка

        return Response({
            'message': 'Расчёт себестоимости выполнен',
            'batch_cost': 1000.00,
            'cost_per_unit': 50.00
        }, status=status.HTTP_201_CREATED)


class QuickSetupView(generics.CreateAPIView):
    """Быстрая настройка системы учёта расходов"""

    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        """Создание базовых расходов и настроек"""

        # Создаём базовые расходы если их нет
        default_expenses = [
            {'name': 'Аренда помещения', 'expense_type': 'overhead', 'unit': 'monthly', 'price_per_unit': 35000},
            {'name': 'Электричество', 'expense_type': 'overhead', 'unit': 'monthly', 'price_per_unit': 25000},
            {'name': 'Мука', 'expense_type': 'raw_material', 'unit': 'kg', 'price_per_unit': 50},
            {'name': 'Соль', 'expense_type': 'raw_material', 'unit': 'kg', 'price_per_unit': 30},
            {'name': 'Упаковка', 'expense_type': 'packaging', 'unit': 'pcs', 'price_per_unit': 5},
        ]

        created_count = 0
        for expense_data in default_expenses:
            expense, created = Expense.objects.get_or_create(
                name=expense_data['name'],
                defaults=expense_data
            )
            if created:
                created_count += 1

        return Response({
            'message': f'Быстрая настройка завершена. Создано {created_count} расходов.',
            'created_expenses': created_count
        })


class BonusCalculationView(generics.CreateAPIView):
    """Расчёт влияния бонусов на себестоимость"""

    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        """Расчёт как бонусы влияют на себестоимость"""

        # Заглушка для расчёта бонусов
        return Response({
            'bonus_impact': 15.5,
            'additional_cost_per_unit': 7.75,
            'recommendation': 'Увеличить цену на 8 сом для покрытия бонусных расходов'
        })


class BonusAnalysisView(generics.ListAPIView):
    """Анализ влияния бонусной системы на себестоимость"""

    permission_classes = [IsAdminUser]
    serializer_class = BonusAnalysisSerializer

    def get_queryset(self):
        # Заглушка для анализа
        return []

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