from rest_framework import viewsets, permissions, status, generics
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import Sum, Count, Avg, Q
from datetime import datetime, date, timedelta
from decimal import Decimal
from django.db import models
from .models import Report, SalesReport, InventoryReport
from .serializers import (
    ReportSerializer, SalesReportSerializer, InventoryReportSerializer,
    ReportGenerateSerializer, ReportAnalyticsSerializer, DashboardSerializer
)
from .services import ReportGeneratorService
from users.permissions import IsAdminUser, IsPartnerUser


class ReportViewSet(viewsets.ModelViewSet):
    """ViewSet для отчетов"""

    queryset = Report.objects.select_related('created_by', 'store', 'partner', 'product')
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['report_type', 'period', 'store', 'partner', 'is_automated']
    search_fields = ['name']
    ordering_fields = ['created_at', 'date_from']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'store':
            # Магазин видит только отчеты по себе
            qs = qs.filter(store__user=user)
        elif user.role == 'partner':
            # Партнёр видит отчеты по своим магазинам
            qs = qs.filter(Q(partner=user) | Q(store__partner=user))

        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class SalesReportViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для отчетов по продажам"""

    queryset = SalesReport.objects.select_related('store', 'product')
    serializer_class = SalesReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date', 'store', 'product']
    ordering_fields = ['date', 'total_revenue', 'profit']
    ordering = ['-date']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'store':
            qs = qs.filter(store__user=user)
        elif user.role == 'partner':
            qs = qs.filter(store__partner=user)

        return qs

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Сводка по продажам"""
        qs = self.get_queryset()

        # Фильтры
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        summary = qs.aggregate(
            total_revenue=Sum('total_revenue'),
            total_orders=Sum('orders_count'),
            total_quantity=Sum('total_quantity'),
            total_profit=Sum('profit'),
            avg_order_value=Avg('total_revenue')
        )

        return Response(summary)


class InventoryReportViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для отчетов по остаткам"""

    queryset = InventoryReport.objects.select_related('store', 'partner', 'product')
    serializer_class = InventoryReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date', 'store', 'partner', 'product']
    ordering_fields = ['date', 'closing_balance']
    ordering = ['-date']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.role == 'store':
            qs = qs.filter(store__user=user)
        elif user.role == 'partner':
            qs = qs.filter(Q(partner=user) | Q(store__partner=user))

        return qs


class GenerateReportView(generics.CreateAPIView):
    """Генерация отчетов"""

    serializer_class = ReportGenerateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Генерируем отчет
        generator = ReportGeneratorService()
        report = generator.generate_report(
            report_type=serializer.validated_data['report_type'],
            period=serializer.validated_data['period'],
            date_from=serializer.validated_data['date_from'],
            date_to=serializer.validated_data['date_to'],
            created_by=request.user,
            filters=serializer.validated_data
        )

        response_serializer = ReportSerializer(report)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ReportAnalyticsView(generics.GenericAPIView):
    """Аналитика отчетов"""

    serializer_class = ReportAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        filters = serializer.validated_data
        user = request.user

        # Базовые QuerySet'ы с учетом прав доступа
        sales_qs = SalesReport.objects.all()
        inventory_qs = InventoryReport.objects.all()

        if user.role == 'store':
            sales_qs = sales_qs.filter(store__user=user)
            inventory_qs = inventory_qs.filter(store__user=user)
        elif user.role == 'partner':
            sales_qs = sales_qs.filter(store__partner=user)
            inventory_qs = inventory_qs.filter(Q(partner=user) | Q(store__partner=user))

        # Применяем фильтры
        if filters.get('date_from'):
            sales_qs = sales_qs.filter(date__gte=filters['date_from'])
            inventory_qs = inventory_qs.filter(date__gte=filters['date_from'])

        if filters.get('date_to'):
            sales_qs = sales_qs.filter(date__lte=filters['date_to'])
            inventory_qs = inventory_qs.filter(date__lte=filters['date_to'])

        if filters.get('store_id'):
            sales_qs = sales_qs.filter(store_id=filters['store_id'])
            inventory_qs = inventory_qs.filter(store_id=filters['store_id'])

        # Аналитика продаж
        sales_analytics = sales_qs.aggregate(
            total_revenue=Sum('total_revenue'),
            total_orders=Sum('orders_count'),
            total_profit=Sum('profit'),
            avg_order_value=Avg('total_revenue')
        )

        # Топ товары
        top_products = sales_qs.values(
            'product__name', 'product_id'
        ).annotate(
            revenue=Sum('total_revenue'),
            quantity=Sum('total_quantity')
        ).order_by('-revenue')[:10]

        # Топ магазины (для админов и партнёров)
        top_stores = []
        if user.role in ['admin', 'partner']:
            top_stores = sales_qs.values(
                'store__store_name', 'store_id'
            ).annotate(
                revenue=Sum('total_revenue'),
                orders=Sum('orders_count')
            ).order_by('-revenue')[:10]

        # Динамика по дням (последние 30 дней)
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        daily_sales = sales_qs.filter(
            date__gte=start_date,
            date__lte=end_date
        ).values('date').annotate(
            revenue=Sum('total_revenue'),
            orders=Sum('orders_count')
        ).order_by('date')

        return Response({
            'sales_analytics': sales_analytics,
            'top_products': list(top_products),
            'top_stores': list(top_stores),
            'daily_sales': list(daily_sales),
            'period': {
                'from': filters.get('date_from'),
                'to': filters.get('date_to')
            }
        })


class DashboardView(generics.GenericAPIView):
    """Дашборд с основными метриками"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # Период - последние 30 дней
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        # Базовые QuerySet'ы
        from apps.orders.models import Order
        from apps.debts.models import Debt
        from apps.stores.models import StoreInventory

        orders_qs = Order.objects.filter(
            order_date__date__gte=start_date,
            status='completed'
        )

        if user.role == 'store':
            orders_qs = orders_qs.filter(store__user=user)
        elif user.role == 'partner':
            orders_qs = orders_qs.filter(store__partner=user)

        # Общая статистика
        total_stats = orders_qs.aggregate(
            total_sales=Sum('total_amount'),
            total_orders=Count('id'),
            avg_order_value=Avg('total_amount')
        )

        # Динамика по дням
        daily_sales = orders_qs.extra(
            select={'day': 'date(order_date)'}
        ).values('day').annotate(
            revenue=Sum('total_amount'),
            orders=Count('id')
        ).order_by('day')

        # Топ товары
        from apps.orders.models import OrderItem
        top_products = OrderItem.objects.filter(
            order__in=orders_qs
        ).values(
            'product__name', 'product_id'
        ).annotate(
            revenue=Sum('total_price'),
            quantity=Sum('quantity')
        ).order_by('-revenue')[:5]

        # Низкие остатки
        inventory_qs = StoreInventory.objects.select_related('product')
        if user.role == 'store':
            inventory_qs = inventory_qs.filter(store__user=user)
        elif user.role == 'partner':
            inventory_qs = inventory_qs.filter(store__partner=user)

        low_stock = inventory_qs.filter(
            quantity__lte=models.F('product__low_stock_threshold')
        ).values(
            'product__name', 'quantity', 'product__low_stock_threshold'
        )[:10]

        # Долги
        debt_qs = Debt.objects.filter(is_paid=False)
        if user.role == 'store':
            debt_qs = debt_qs.filter(store__user=user)
        elif user.role == 'partner':
            debt_qs = debt_qs.filter(store__partner=user)

        debt_stats = debt_qs.aggregate(
            total_debt=Sum('amount') - Sum('paid_amount'),
            overdue_debt=Sum('amount', filter=Q(due_date__lt=date.today())) - Sum('paid_amount',
                                                                                  filter=Q(due_date__lt=date.today()))
        )

        dashboard_data = {
            'total_sales': total_stats['total_sales'] or 0,
            'total_orders': total_stats['total_orders'] or 0,
            'total_profit': 0,  # Будет рассчитано позже
            'profit_margin': 0,
            'daily_sales': list(daily_sales),
            'top_products': list(top_products),
            'top_stores': [],
            'low_stock_products': list(low_stock),
            'total_debt': debt_stats['total_debt'] or 0,
            'overdue_debt': debt_stats['overdue_debt'] or 0
        }

        serializer = DashboardSerializer(dashboard_data)
        return Response(serializer.data)