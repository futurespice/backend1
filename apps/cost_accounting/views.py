# ИСПРАВЛЕНИЕ: Удаляем несуществующий импорт ExpenseManagementService

from datetime import date, timedelta
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Sum, Avg
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from .models import (
    Expense, ProductExpense, DailyExpenseLog,
    ProductionBatch, MonthlyOverheadBudget, BillOfMaterial, BOMLine
)
from .serializers import (
    ExpenseSerializer, ProductExpenseSerializer, DailyExpenseLogSerializer,
    ProductionBatchSerializer, MonthlyOverheadBudgetSerializer,
    CostCalculationRequestSerializer, CostBreakdownSerializer,
    BulkDailyExpenseSerializer, MonthlyOverheadBulkSerializer,
    DailyCostSummarySerializer, ExpensePriceUpdateSerializer,
    SuzerainProductSetupSerializer, BOMSerializer
)
# ИСПРАВЛЕНО: Импортируем только существующий сервис
from .services import CostCalculationService
from users.permissions import IsAdminUser, IsPartnerUser


class ExpenseViewSet(viewsets.ModelViewSet):
    """CRUD операции с расходами"""
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'status', 'is_active', 'is_universal']
    search_fields = ['name', 'description']
    ordering = ['type', 'name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['post'])
    def bulk_price_update(self, request):
        """Массовое обновление цен расходов"""
        serializer = ExpensePriceUpdateSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        updated_count = 0
        for item in serializer.validated_data:
            try:
                expense = Expense.objects.get(id=item['expense_id'])
                expense.price_per_unit = item['new_price']
                expense.save()
                updated_count += 1
            except Expense.DoesNotExist:
                continue

        return Response({
            'message': f'Обновлено цен: {updated_count}',
            'updated_count': updated_count
        })


class ProductExpenseViewSet(viewsets.ModelViewSet):
    """Связи продуктов с расходами"""
    queryset = ProductExpense.objects.select_related('product', 'expense')
    serializer_class = ProductExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'expense', 'expense__type', 'is_active']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]


class BOMViewSet(viewsets.ModelViewSet):
    """Спецификации состава товаров (Bill of Materials)"""
    queryset = BillOfMaterial.objects.select_related('product').prefetch_related('lines')
    serializer_class = BOMSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['product', 'is_active']
    search_fields = ['product__name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def duplicate_bom(self, request, pk=None):
        """Дублирование BOM спецификации"""
        original_bom = self.get_object()

        with transaction.atomic():
            # Создаем новую BOM
            new_bom = BillOfMaterial.objects.create(
                product=original_bom.product,
                version=f"{original_bom.version}_copy",
                is_active=False  # Создаем неактивной
            )

            # Копируем все линии
            for line in original_bom.lines.all():
                BOMLine.objects.create(
                    bom=new_bom,
                    expense=line.expense,
                    component_product=line.component_product,
                    quantity=line.quantity,
                    unit=line.unit,
                    is_primary=line.is_primary,
                    order=line.order
                )

        return Response({
            'message': 'BOM скопирована успешно',
            'new_bom_id': new_bom.id
        })

    @action(detail=False, methods=['post'])
    def create_from_template(self, request):
        """Создание BOM из шаблона"""
        from .serializers import ProductRecipeTemplateSerializer

        serializer = ProductRecipeTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from .services import ProductRecipeManager
        from products.models import Product

        product = Product.objects.get(id=serializer.validated_data['product_id'])
        template_data = {
            'components': serializer.validated_data['components']
        }

        recipe_manager = ProductRecipeManager()

        try:
            bom = recipe_manager.create_recipe_from_template(product, template_data)
            return Response({
                'message': f'BOM создана для продукта {product.name}',
                'bom_id': bom.id,
                'components_count': len(template_data['components'])
            })
        except Exception as e:
            return Response({
                'error': f'Ошибка создания BOM: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)


class DailyExpenseLogViewSet(viewsets.ModelViewSet):
    """Дневные логи расходов"""
    queryset = DailyExpenseLog.objects.select_related('expense')
    serializer_class = DailyExpenseLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date', 'expense', 'expense__type']
    ordering = ['-date', 'expense__name']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Массовое создание дневных логов"""
        serializer = BulkDailyExpenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        log_date = serializer.validated_data['date']
        expenses_data = serializer.validated_data['expenses']

        created_logs = []
        for expense_data in expenses_data:
            expense = Expense.objects.get(id=expense_data['expense_id'])

            # Рассчитываем total_cost
            quantity = Decimal(str(expense_data['quantity_used']))
            price = Decimal(str(expense_data.get('actual_price', expense.price_per_unit)))
            total_cost = quantity * price

            log, created = DailyExpenseLog.objects.update_or_create(
                expense=expense,
                date=log_date,
                defaults={
                    'quantity_used': quantity,
                    'actual_price_per_unit': price,
                    'total_cost': total_cost
                }
            )

            if created:
                created_logs.append(log)

        return Response({
            'message': f'Создано {len(created_logs)} записей расходов за {log_date}',
            'date': log_date,
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

        Пример запроса:
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

        # Конвертируем ключи в int
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
                    'component_costs': [  # ДОБАВЛЕНО: Компоненты-продукты
                        {
                            'name': item.name,
                            'unit': item.unit,
                            'consumed_quantity': float(item.consumed_quantity),
                            'unit_price': float(item.unit_price),
                            'total_cost': float(item.total_cost)
                        }
                        for item in breakdown.component_costs
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
                        'components': float(breakdown.total_components),  # ДОБАВЛЕНО
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
            return Response({
                'error': f'Ошибка расчета: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)


class MonthlyOverheadBudgetViewSet(viewsets.ModelViewSet):
    """Месячные бюджеты накладных расходов"""
    queryset = MonthlyOverheadBudget.objects.select_related('expense')
    serializer_class = MonthlyOverheadBudgetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['year', 'month', 'expense']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Массовое создание месячных бюджетов"""
        serializer = MonthlyOverheadBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        year = serializer.validated_data['year']
        month = serializer.validated_data['month']
        budgets_data = serializer.validated_data['budgets']

        created_budgets = []
        for budget_data in budgets_data:
            expense = Expense.objects.get(id=budget_data['expense_id'])

            budget, created = MonthlyOverheadBudget.objects.update_or_create(
                expense=expense,
                year=year,
                month=month,
                defaults={
                    'planned_amount': Decimal(str(budget_data['planned_amount']))
                }
            )

            if created:
                created_budgets.append(budget)

        return Response({
            'message': f'Создано бюджетов: {len(created_budgets)} за {month}/{year}',
            'year': year,
            'month': month,
            'created_count': len(created_budgets)
        })

    @action(detail=False, methods=['get'])
    def current_month(self, request):
        """Бюджет текущего месяца"""
        today = date.today()

        budgets = self.get_queryset().filter(
            year=today.year,
            month=today.month
        )

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

        return Response({
            'product_id': int(product_id),
            'period': {'start': start_date, 'end': end_date},
            'trend_data': trend_data
        })

    @action(detail=False, methods=['get'])
    def daily_summary(self, request):
        """Дневная сводка расходов и производства"""
        target_date = request.query_params.get('date', date.today().isoformat())

        try:
            summary_date = date.fromisoformat(target_date)
        except ValueError:
            return Response({'error': 'Неверный формат даты'}, status=400)

        # Расходы за день
        daily_logs = DailyExpenseLog.objects.filter(date=summary_date)
        physical_expenses = daily_logs.filter(expense__type=Expense.ExpenseType.PHYSICAL).aggregate(
            total=Sum('total_cost')
        )['total'] or 0
        overhead_expenses = daily_logs.filter(expense__type=Expense.ExpenseType.OVERHEAD).aggregate(
            total=Sum('total_cost')
        )['total'] or 0

        # Производство за день
        production_batches = ProductionBatch.objects.filter(date=summary_date)
        total_produced = production_batches.aggregate(total=Sum('produced_quantity'))['total'] or 0
        total_costs = production_batches.aggregate(total=Sum('total_cost'))['total'] or 0
        total_revenue = production_batches.aggregate(total=Sum('revenue'))['total'] or 0

        return Response({
            'date': summary_date,
            'expenses': {
                'physical': float(physical_expenses),
                'overhead': float(overhead_expenses),
                'total': float(physical_expenses + overhead_expenses)
            },
            'production': {
                'total_quantity': float(total_produced),
                'total_costs': float(total_costs),
                'total_revenue': float(total_revenue),
                'profit': float(total_revenue - total_costs),
                'products_count': production_batches.count()
            }
        })


# ---------- Специальные API Views ----------

class QuickSetupView(APIView):
    """Быстрая настройка системы расходов"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        """
        Создает базовые расходы для старта системы

        Пример из ТЗ:
        - Аренда: 35000 (накладной)
        - Фарш: 270 сом/кг (физический, Сюзерен)
        - Мука: 630 сом/мешок (физический)
        """

        basic_expenses = [
            # Накладные расходы (месячные)
            {'name': 'Аренда', 'type': 'overhead', 'price': 35000, 'unit': 'мес'},
            {'name': 'Электричество', 'type': 'overhead', 'price': 25000, 'unit': 'мес'},
            {'name': 'Налоги', 'type': 'overhead', 'price': 45000, 'unit': 'мес'},
            {'name': 'Зарплата уборщицы', 'type': 'overhead', 'price': 12000, 'unit': 'мес'},
            {'name': 'Админ расходы', 'type': 'overhead', 'price': 5000, 'unit': 'мес'},
            {'name': 'Холодильник', 'type': 'overhead', 'price': 5000, 'unit': 'мес'},
            {'name': 'Упаковка общая', 'type': 'overhead', 'price': 36000, 'unit': 'мес'},

            # Физические расходы
            {'name': 'Фарш говяжий', 'type': 'physical', 'price': 270, 'unit': 'кг', 'status': 'suzerain'},
            {'name': 'Мука высший сорт', 'type': 'physical', 'price': 630, 'unit': 'кг'},
            {'name': 'Соль пищевая', 'type': 'physical', 'price': 30, 'unit': 'кг'},
            {'name': 'Яйца куриные', 'type': 'physical', 'price': 400, 'unit': 'шт'},
            {'name': 'Лук репчатый', 'type': 'physical', 'price': 50, 'unit': 'кг'},
            {'name': 'Пакеты упаковочные', 'type': 'physical', 'price': 4.5, 'unit': 'шт'},
            {'name': 'Приправы', 'type': 'physical', 'price': 5, 'unit': 'кг'},
            {'name': 'Солярка', 'type': 'physical', 'price': 50, 'unit': 'л'},
        ]

        created_expenses = []

        for expense_data in basic_expenses:
            expense, created = Expense.objects.get_or_create(
                name=expense_data['name'],
                defaults={
                    'type': expense_data['type'],
                    'status': expense_data.get('status', 'regular'),
                    'price_per_unit': expense_data['price'],
                    'unit': expense_data['unit'],
                    'is_active': True,
                    'is_universal': True
                }
            )

            if created:
                created_expenses.append(expense.name)

        return Response({
            'message': 'Базовые расходы созданы',
            'created_expenses': created_expenses,
            'total_created': len(created_expenses)
        })


class BatchCostCalculationView(APIView):
    """Упрощенный расчет себестоимости для одного продукта"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        """
        Расчет себестоимости для одного продукта

        {
            "product_id": 1,
            "quantity": 1100,
            "date": "2025-09-03"
        }
        """
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity')
        calc_date = request.data.get('date', date.today().isoformat())

        if not product_id or not quantity:
            return Response({
                'error': 'Требуются product_id и quantity'
            }, status=400)

        try:
            calc_date = date.fromisoformat(str(calc_date))
        except ValueError:
            return Response({'error': 'Неверный формат даты'}, status=400)

        service = CostCalculationService()

        # Формируем данные в нужном формате
        production_data = {
            int(product_id): {'quantity': float(quantity)}
        }

        try:
            breakdowns = service.calculate_daily_costs(
                production_data=production_data,
                calculation_date=calc_date
            )

            if not breakdowns:
                return Response({
                    'error': 'Не удалось рассчитать себестоимость'
                }, status=400)

            breakdown = breakdowns[0]

            return Response({
                'product_id': breakdown.product_id,
                'quantity': float(breakdown.produced_quantity),
                'date': breakdown.date,
                'cost_per_unit': float(breakdown.cost_per_unit),
                'total_cost': float(breakdown.total_cost),
                'breakdown': {
                    'physical': float(breakdown.total_physical),
                    'components': float(breakdown.total_components),
                    'overhead': float(breakdown.total_overhead)
                }
            })

        except Exception as e:
            return Response({
                'error': f'Ошибка расчета: {str(e)}'
            }, status=400)


class BonusCalculationView(APIView):
    """Расчет бонусов (заготовка)"""
    permission_classes = [IsPartnerUser]
    serializer_class = CostBreakdownSerializer  # Для документации

    def post(self, request):
        return Response({
            'message': 'Система бонусов в разработке'
        })


class BonusAnalysisView(APIView):
    """Анализ бонусов (заготовка)"""
    permission_classes = [IsPartnerUser]
    serializer_class = CostBreakdownSerializer  # Для документации

    def get(self, request):
        return Response({
            'message': 'Анализ бонусов в разработке'
        })