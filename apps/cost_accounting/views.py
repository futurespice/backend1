from datetime import date, timedelta
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Sum, Avg
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    Expense, ProductExpense, DailyExpenseLog,
    ProductionBatch, MonthlyOverheadBudget
)
from .serializers import (
    ExpenseSerializer, ProductExpenseSerializer, DailyExpenseLogSerializer,
    ProductionBatchSerializer, MonthlyOverheadBudgetSerializer,
    CostCalculationRequestSerializer, CostBreakdownSerializer,
    BulkDailyExpenseSerializer, MonthlyOverheadBulkSerializer,
    DailyCostSummarySerializer, ExpensePriceUpdateSerializer,
    SuzerainProductSetupSerializer
)
from .services import CostCalculationService, ExpenseManagementService
from users.permissions import IsAdminUser, IsPartnerUser


class ExpenseViewSet(viewsets.ModelViewSet):
    """
    CRUD операции с расходами.
    Админ: полный доступ
    Партнер: только просмотр
    """
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'status', 'state', 'is_universal', 'is_active']
    search_fields = ['name']
    ordering_fields = ['name', 'type', 'status', 'created_at']
    ordering = ['name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """Группировка расходов по типам"""
        physical = self.get_queryset().filter(type=Expense.ExpenseType.PHYSICAL)
        overhead = self.get_queryset().filter(type=Expense.ExpenseType.OVERHEAD)

        return Response({
            'physical': ExpenseSerializer(physical, many=True).data,
            'overhead': ExpenseSerializer(overhead, many=True).data
        })

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def update_price(self, request):
        """Обновление цены физического расхода"""
        serializer = ExpensePriceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        expense_id = serializer.validated_data['expense_id']
        new_price = serializer.validated_data['new_price']
        effective_date = serializer.validated_data['effective_date']

        expense = Expense.objects.get(id=expense_id)

        # Обновляем базовую цену
        expense.price_per_unit = new_price
        expense.save()

        # Создаем дневной лог с новой ценой
        service = ExpenseManagementService()
        service.update_daily_expense(
            expense_id=expense_id,
            calculation_date=effective_date,
            actual_price_per_unit=new_price
        )

        return Response({
            'message': f'Цена расхода "{expense.name}" обновлена на {new_price}',
            'effective_date': effective_date
        })


class ProductExpenseViewSet(viewsets.ModelViewSet):
    """Управление связями товар-расход"""
    queryset = ProductExpense.objects.select_related('product', 'expense')
    serializer_class = ProductExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'expense', 'expense__type', 'expense__status', 'is_active']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def setup_suzerain(self, request):
        """Настройка товара с расходом-Сюзереном"""
        serializer = SuzerainProductSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = serializer.validated_data['product']
        expense = serializer.validated_data['expense']
        ratio = serializer.validated_data['ratio_per_unit']

        # Создаем/обновляем связь
        link, created = ProductExpense.objects.update_or_create(
            product=product,
            expense=expense,
            defaults={
                'ratio_per_product_unit': ratio,
                'is_active': True
            }
        )

        return Response({
            'message': f'Сюзерен "{expense.name}" настроен для товара "{product.name}"',
            'ratio_per_unit': float(ratio),
            'created': created
        })

    @action(detail=False, methods=['get'])
    def by_product(self, request):
        """Расходы по конкретному товару"""
        product_id = request.query_params.get('product_id')
        if not product_id:
            return Response({'error': 'Нужен параметр product_id'}, status=400)

        expenses = self.get_queryset().filter(product_id=product_id, is_active=True)

        # Группируем по типам
        physical = expenses.filter(expense__type=Expense.ExpenseType.PHYSICAL)
        overhead = expenses.filter(expense__type=Expense.ExpenseType.OVERHEAD)

        return Response({
            'product_id': int(product_id),
            'physical_expenses': ProductExpenseSerializer(physical, many=True).data,
            'overhead_expenses': ProductExpenseSerializer(overhead, many=True).data
        })


class DailyExpenseLogViewSet(viewsets.ModelViewSet):
    """Управление дневными расходами"""
    queryset = DailyExpenseLog.objects.select_related('expense')
    serializer_class = DailyExpenseLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date', 'expense', 'expense__type']
    ordering = ['-date', 'expense__name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'bulk_update']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def bulk_update(self, request):
        """Массовое обновление дневных расходов"""
        serializer = BulkDailyExpenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        calc_date = serializer.validated_data['date']
        expenses_data = serializer.validated_data['expenses']

        service = ExpenseManagementService()
        created_logs = []

        with transaction.atomic():
            for expense_data in expenses_data:
                expense_id = expense_data.pop('expense_id')

                log = service.update_daily_expense(
                    expense_id=expense_id,
                    calculation_date=calc_date,
                    **expense_data
                )
                created_logs.append(log)

        return Response({
            'message': f'Обновлено {len(created_logs)} расходов на {calc_date}',
            'date': calc_date,
            'updated_count': len(created_logs)
        })

    @action(detail=False, methods=['get'])
    def for_date(self, request):
        """Все расходы за конкретный день"""
        target_date = request.query_params.get('date')
        if not target_date:
            target_date = date.today().isoformat()

        logs = self.get_queryset().filter(date=target_date)

        # Группируем по типам
        physical_logs = logs.filter(expense__type=Expense.ExpenseType.PHYSICAL)
        overhead_logs = logs.filter(expense__type=Expense.ExpenseType.OVERHEAD)

        physical_total = physical_logs.aggregate(total=Sum('total_cost'))['total'] or 0
        overhead_total = overhead_logs.aggregate(total=Sum('total_cost'))['total'] or 0

        return Response({
            'date': target_date,
            'physical_expenses': DailyExpenseLogSerializer(physical_logs, many=True).data,
            'overhead_expenses': DailyExpenseLogSerializer(overhead_logs, many=True).data,
            'totals': {
                'physical': float(physical_total),
                'overhead': float(overhead_total),
                'grand_total': float(physical_total + overhead_total)
            }
        })


class ProductionBatchViewSet(viewsets.ModelViewSet):
    """Производственные смены и расчет себестоимости"""
    queryset = ProductionBatch.objects.select_related('product')
    serializer_class = ProductionBatchSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date', 'product']
    ordering = ['-date', 'product__name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'calculate_costs']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def calculate_costs(self, request):
        """
        Расчет себестоимости по производственным данным.

        Пример запроса из реального кейса заказчика:
        {
            "date": "2025-09-03",
            "production_data": {
                "1": {"quantity": 1100},              # пельмени
                "2": {"quantity": 440},               # тесто
                "3": {"suzerain_input": 105}          # через фарш
            }
        }
        """
        serializer = CostCalculationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        calc_date = serializer.validated_data['date']
        production_data = serializer.validated_data['production_data']

        # Конвертируем ключи в int для сервиса
        production_data_int = {
            int(k): v for k, v in production_data.items()
        }

        service = CostCalculationService()

        try:
            # Рассчитываем себестоимость
            breakdowns = service.calculate_daily_costs(
                production_data=production_data_int,
                calculation_date=calc_date
            )

            # Сохраняем результаты
            saved_batches = []
            for breakdown in breakdowns:
                batch = service.save_production_batch(breakdown)
                saved_batches.append(batch)

            # Формируем ответ
            results = []
            for breakdown in breakdowns:
                from products.models import Product
                product = Product.objects.get(id=breakdown.product_id)

                results.append({
                    'product_id': breakdown.product_id,
                    'product_name': product.name,
                    'date': breakdown.date,
                    'produced_quantity': float(breakdown.produced_quantity),
                    'physical_costs': [
                        {
                            'name': item.name,
                            'unit': item.unit,
                            'consumed_quantity': float(item.consumed_quantity),
                            'unit_price': float(item.unit_price),
                            'total_cost': float(item.total_cost)
                        }
                        for item in breakdown.physical_costs
                    ],
                    'overhead_costs': [
                        {
                            'name': item.name,
                            'daily_budget': float(item.daily_budget),
                            'product_share': float(item.product_share),
                            'allocated_cost': float(item.allocated_cost)
                        }
                        for item in breakdown.overhead_costs
                    ],
                    'totals': {
                        'physical': float(breakdown.total_physical),
                        'overhead': float(breakdown.total_overhead),
                        'total': float(breakdown.total_cost),
                        'cost_per_unit': float(breakdown.cost_per_unit)
                    }
                })

            return Response({
                'date': calc_date,
                'calculated_products': len(results),
                'results': results
            })

        except Exception as e:
            return Response(
                {'error': f'Ошибка расчета: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['patch'], permission_classes=[IsAdminUser])
    def update_revenue(self, request, pk=None):
        """Обновление выручки и прибыли смены С УЧЕТОМ БОНУСОВ"""
        batch = self.get_object()
        revenue = request.data.get('revenue')
        sold_quantity = request.data.get('sold_quantity')  # НОВЫЙ параметр для бонусов

        if revenue is None:
            return Response({'error': 'Нужен параметр revenue'}, status=400)

        try:
            revenue = Decimal(str(revenue))

            # Если указано sold_quantity, применяем бонусную систему
            if sold_quantity is not None:
                from .bonus_service import BonusIntegrationService

                sold_qty = int(sold_quantity)

                # Интегрируем бонусы
                updated_batch = BonusIntegrationService.integrate_bonus_with_cost_calculation(
                    batch.id, {batch.product.id: sold_qty}
                )

                if updated_batch:
                    bonus_info = updated_batch.cost_breakdown.get('bonus_info', {})
                    return Response({
                        'message': 'Выручка обновлена с учетом бонусов',
                        'revenue': float(updated_batch.revenue),
                        'net_profit': float(updated_batch.net_profit),
                        'profit_margin': float(
                            updated_batch.net_profit / updated_batch.revenue * 100) if updated_batch.revenue > 0 else 0,
                        'bonus_info': {
                            'sold_quantity': bonus_info.get('sold_quantity', 0),
                            'payable_quantity': bonus_info.get('payable_quantity', 0),
                            'bonus_quantity': bonus_info.get('bonus_quantity', 0),
                            'bonus_discount': bonus_info.get('bonus_discount', 0),
                            'net_revenue': bonus_info.get('net_revenue', 0)
                        }
                    })
            else:
                # Стандартное обновление без бонусов
                service = CostCalculationService()
                updated_batch = service.update_batch_revenue(batch.id, revenue)

                return Response({
                    'message': 'Выручка обновлена',
                    'revenue': float(updated_batch.revenue),
                    'net_profit': float(updated_batch.net_profit),
                    'profit_margin': float(
                        updated_batch.net_profit / updated_batch.revenue * 100) if updated_batch.revenue > 0 else 0
                })

        except (ValueError, TypeError):
            return Response({'error': 'Некорректные значения'}, status=400)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def apply_mass_bonuses(self, request):
        """
        Массовое применение бонусов ко всем продажам за день.

        Пример запроса:
        {
            "date": "2025-09-03",
            "sales_data": {
                "1": 1100,  // product_id: sold_quantity
                "2": 440,
                "3": 280
            }
        }
        """
        calc_date_str = request.data.get('date')
        sales_data = request.data.get('sales_data', {})

        if not calc_date_str or not sales_data:
            return Response({
                'error': 'Нужны параметры date и sales_data'
            }, status=400)

        try:
            calc_date = date.fromisoformat(calc_date_str)
            # Конвертируем ключи в int
            sales_by_product = {int(k): int(v) for k, v in sales_data.items()}
        except (ValueError, TypeError):
            return Response({
                'error': 'Некорректный формат данных'
            }, status=400)

        from .bonus_service import BonusIntegrationService

        result = BonusIntegrationService.apply_mass_bonus_calculation(
            calc_date, sales_by_product
        )

        return Response(result)

    @action(detail=False, methods=['get'])
    def daily_summary(self, request):
        """Сводка по всем товарам за день"""
        target_date = request.query_params.get('date')
        if not target_date:
            target_date = date.today().isoformat()

        try:
            calc_date = date.fromisoformat(target_date)
        except ValueError:
            return Response({'error': 'Некорректный формат даты'}, status=400)

        service = CostCalculationService()
        summary = service.get_cost_summary_for_date(calc_date)

        return Response(summary)


class MonthlyOverheadBudgetViewSet(viewsets.ModelViewSet):
    """Месячные бюджеты накладных расходов"""
    queryset = MonthlyOverheadBudget.objects.select_related('expense')
    serializer_class = MonthlyOverheadBudgetSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['year', 'month', 'expense']
    ordering = ['-year', '-month', 'expense__name']

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Массовое создание месячного бюджета.

        Пример из реального кейса:
        {
            "year": 2025,
            "month": 9,
            "overheads": {
                "1": 35000,  # аренда
                "2": 25000,  # свет
                "3": 45000,  # налоги
                "4": 12000,  # уборщица
                "5": 5000    # админ
            }
        }
        """
        serializer = MonthlyOverheadBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        year = serializer.validated_data['year']
        month = serializer.validated_data['month']
        overheads_data = serializer.validated_data['overheads']

        # Конвертируем ключи в int
        overheads_int = {int(k): v for k, v in overheads_data.items()}

        service = ExpenseManagementService()
        service.bulk_update_monthly_overheads(year, month, overheads_int)

        # Возвращаем созданные/обновленные бюджеты
        budgets = self.get_queryset().filter(year=year, month=month)

        return Response({
            'message': f'Бюджеты на {month}/{year} обновлены',
            'count': budgets.count(),
            'total_planned': float(sum(b.planned_amount for b in budgets)),
            'budgets': MonthlyOverheadBudgetSerializer(budgets, many=True).data
        })

    @action(detail=False, methods=['get'])
    def current_month(self, request):
        """Бюджеты текущего месяца"""
        today = date.today()
        budgets = self.get_queryset().filter(year=today.year, month=today.month)

        total_planned = budgets.aggregate(total=Sum('planned_amount'))['total'] or 0
        total_actual = budgets.aggregate(total=Sum('actual_amount'))['total'] or 0

        return Response({
            'year': today.year,
            'month': today.month,
            'budgets': MonthlyOverheadBudgetSerializer(budgets, many=True).data,
            'totals': {
                'planned': float(total_planned),
                'actual': float(total_actual),
                'execution_percent': float(total_actual / total_planned * 100) if total_planned > 0 else 0,
                'daily_average_planned': float(total_planned / 30)
            }
        })


# ---------- Дополнительные ViewSets для аналитики ----------

class CostAnalyticsViewSet(viewsets.ViewSet):
    """Аналитика по себестоимости"""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def product_cost_trend(self, request):
        """Динамика себестоимости товара за период"""
        product_id = request.query_params.get('product_id')
        days = int(request.query_params.get('days', 30))

        if not product_id:
            return Response({'error': 'Нужен параметр product_id'}, status=400)

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        batches = ProductionBatch.objects.filter(
            product_id=product_id,
            date__range=[start_date, end_date]
        ).order_by('date')

        trend_data = [
            {
                'date': batch.date,
                'cost_per_unit': float(batch.cost_per_unit),
                'physical_cost': float(batch.physical_cost),
                'overhead_cost': float(batch.overhead_cost),
                'produced_quantity': float(batch.produced_quantity),
                'profit_margin': float(batch.net_profit / batch.revenue * 100) if batch.revenue > 0 else 0
            }
            for batch in batches
        ]

        # Средние показатели
        if batches:
            avg_stats = batches.aggregate(
                avg_cost_per_unit=Avg('cost_per_unit'),
                avg_physical=Avg('physical_cost'),
                avg_overhead=Avg('overhead_cost')
            )
        else:
            avg_stats = {}

        return Response({
            'product_id': int(product_id),
            'period': {'start': start_date, 'end': end_date},
            'trend_data': trend_data,
            'averages': avg_stats
        })

    @action(detail=False, methods=['get'])
    def expense_impact_analysis(self, request):
        """Анализ влияния расходов на себестоимость"""
        target_date = request.query_params.get('date', date.today().isoformat())

        try:
            calc_date = date.fromisoformat(target_date)
        except ValueError:
            return Response({'error': 'Некорректный формат даты'}, status=400)

        # Получаем все смены за день
        batches = ProductionBatch.objects.filter(date=calc_date).select_related('product')

        if not batches:
            return Response({
                'message': f'Нет данных производства за {calc_date}',
                'date': calc_date
            })

        # Анализируем влияние каждого расхода
        expense_impact = {}

        for batch in batches:
            breakdown = batch.cost_breakdown

            # Физические расходы
            for item in breakdown.get('physical_costs', []):
                expense_id = item['expense_id']
                if expense_id not in expense_impact:
                    expense_impact[expense_id] = {
                        'name': item['name'],
                        'type': 'physical',
                        'total_cost': 0,
                        'affected_products': []
                    }

                expense_impact[expense_id]['total_cost'] += item['total_cost']
                expense_impact[expense_id]['affected_products'].append({
                    'product_id': batch.product.id,
                    'product_name': batch.product.name,
                    'cost_contribution': item['total_cost']
                })

            # Накладные расходы
            for item in breakdown.get('overhead_costs', []):
                expense_id = item['expense_id']
                if expense_id not in expense_impact:
                    expense_impact[expense_id] = {
                        'name': item['name'],
                        'type': 'overhead',
                        'total_cost': 0,
                        'affected_products': []
                    }

                expense_impact[expense_id]['total_cost'] += item['allocated_cost']
                expense_impact[expense_id]['affected_products'].append({
                    'product_id': batch.product.id,
                    'product_name': batch.product.name,
                    'cost_contribution': item['allocated_cost']
                })

        # Сортируем по влиянию (общей стоимости)
        sorted_impact = sorted(
            expense_impact.values(),
            key=lambda x: x['total_cost'],
            reverse=True
        )

        return Response({
            'date': calc_date,
            'total_expenses': len(expense_impact),
            'expense_impact_ranking': sorted_impact
        })