from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import date
from decimal import Decimal

from rest_framework.views import APIView

from .models import (
    Product, Expense, ProductionRecord, ProductionItem,
    MechanicalExpenseEntry, BonusHistory, StoreProductCounter,
    ProductExpenseRelation, DefectiveProduct
)
from .serializers import (
    ProductListSerializer, ProductDetailSerializer,
    ExpenseSerializer, ProductionRecordSerializer,
    ProductionItemSerializer, MechanicalExpenseEntrySerializer,
    BonusHistorySerializer, ProductExpenseRelationSerializer,
    DefectiveProductSerializer, ProductionFinanceSummarySerializer
)
from .services import CostCalculator, BonusService
from users.permissions import IsAdminUser, IsPartnerUser
from .finance import ProductionFinanceService


class ExpenseViewSet(viewsets.ModelViewSet):
    """Расходы — только ADMIN"""
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = Expense.objects.all().order_by('-created_at')

    @action(detail=False, methods=['get'])
    def physical(self, request):
        """Только физические расходы"""
        expenses = self.queryset.filter(expense_type='physical', is_active=True)
        serializer = self.get_serializer(expenses, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def overhead(self, request):
        """Только накладные расходы"""
        expenses = self.queryset.filter(expense_type='overhead', is_active=True)
        serializer = self.get_serializer(expenses, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def deactivate(self, request, pk=None):
        """Деактивация расхода"""
        expense = self.get_object()
        expense.is_active = False
        expense.save()
        return Response({'status': 'deactivated'})


class ProductViewSet(viewsets.ModelViewSet):
    """
    Товары — ADMIN создаёт, все видят
    N+1 защита: prefetch_related('images', 'expense_relations')
    """
    queryset = Product.objects.prefetch_related(
        'images', 'expense_relations__expense'
    ).order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductDetailSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    @transaction.atomic
    def perform_destroy(self, instance):
        """Удаление товара"""
        instance.delete()

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    @transaction.atomic
    def add_expense_relation(self, request, pk=None):
        """Добавить связь с расходом (пропорция)"""
        product = self.get_object()
        expense_id = request.data.get('expense_id')
        proportion = request.data.get('proportion', 0)

        expense = get_object_or_404(Expense, id=expense_id)

        relation, created = ProductExpenseRelation.objects.update_or_create(
            product=product,
            expense=expense,
            defaults={'proportion': proportion}
        )

        serializer = ProductExpenseRelationSerializer(relation)
        return Response(serializer.data)


class ProductionViewSet(viewsets.ModelViewSet):
    """Учёт данных (таблица производства) — только ADMIN"""
    serializer_class = ProductionRecordSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = ProductionRecord.objects.select_related('partner').prefetch_related(
        'items__product', 'mechanical_expenses__expense'
    ).order_by('-date')

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Создание или получение записи на дату"""
        date_str = request.data.get('date', str(date.today()))
        partner = request.user

        record, created = ProductionRecord.objects.get_or_create(
            partner=partner,
            date=date_str
        )

        serializer = self.get_serializer(record)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def add_item(self, request, pk=None):
        """Добавить товар в таблицу"""
        record = self.get_object()
        product_id = request.data.get('product_id')
        quantity_produced = Decimal(request.data.get('quantity_produced', 0))
        suzerain_amount = Decimal(request.data.get('suzerain_amount', 0))

        product = get_object_or_404(Product, id=product_id)

        item, created = ProductionItem.objects.update_or_create(
            record=record,
            product=product,
            defaults={
                'quantity_produced': quantity_produced,
                'suzerain_amount': suzerain_amount
            }
        )

        # Расчёт себестоимости
        CostCalculator.calculate_production_item(item)

        serializer = ProductionItemSerializer(item)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def add_mechanical_expense(self, request, pk=None):
        """Добавить механический расход (солярка, обеды)"""
        record = self.get_object()
        expense_id = request.data.get('expense_id')
        amount_spent = Decimal(request.data.get('amount_spent', 0))

        expense = get_object_or_404(Expense, id=expense_id, state='mechanical')

        entry, created = MechanicalExpenseEntry.objects.update_or_create(
            record=record,
            expense=expense,
            defaults={'amount_spent': amount_spent}
        )

        # Пересчитываем все строки
        CostCalculator.recalculate_all_items(record)

        serializer = MechanicalExpenseEntrySerializer(entry)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def save_data(self, request, pk=None):
        """Сохранить/пересчитать данные за день"""
        record = self.get_object()
        CostCalculator.recalculate_all_items(record)
        serializer = self.get_serializer(record)
        return Response(serializer.data)


class BonusViewSet(viewsets.ReadOnlyModelViewSet):
    """История бонусов (только чтение)"""
    serializer_class = BonusHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = BonusHistory.objects.select_related(
            'store', 'partner', 'product', 'order'
        )

        if user.role == 'admin':
            return queryset
        elif user.role == 'partner':
            return queryset.filter(partner=user)
        elif user.role == 'store':
            return queryset.filter(store__selections__user=user)

        return queryset.none()


class DefectiveProductViewSet(viewsets.ModelViewSet):
    """Бракованные товары"""
    serializer_class = DefectiveProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = DefectiveProduct.objects.select_related('partner', 'product')

        if user.role == 'admin':
            return queryset
        elif user.role == 'partner':
            return queryset.filter(partner=user)

        return queryset.none()

    def get_permissions(self):
        if self.action in ['create']:
            return [IsAuthenticated(), IsPartnerUser()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save(partner=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    @transaction.atomic
    def confirm(self, request, pk=None):
        """Подтвердить брак"""
        defect = self.get_object()
        defect.status = 'confirmed'
        defect.resolved_at = date.today()
        defect.save()
        return Response({'status': 'confirmed'})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    @transaction.atomic
    def reject(self, request, pk=None):
        """Отклонить брак"""
        defect = self.get_object()
        defect.status = 'rejected'
        defect.resolved_at = date.today()
        defect.save()
        return Response({'status': 'rejected'})


class ProductionFinanceView(APIView):
    """
    GET /api/products/production-finance/?record_id=XXX

    Возвращает:
    - себестоимость, выручку, чистую прибыль за день
    - фиксированные/механические накладные
    - себестоимость и прибыль с 1 единицы.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        record_id = request.query_params.get("record_id")
        if not record_id:
            return Response(
                {"detail": "record_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        record = get_object_or_404(ProductionRecord, pk=record_id)

        summary = ProductionFinanceService.calculate_for_record(record)
        serializer = ProductionFinanceSummarySerializer(summary)

        return Response(serializer.data)

class ProductionRecordViewSet(viewsets.ModelViewSet):
    """
    Производственные записи (день производства)
    - Партнёр создаёт и редактирует
    - Админ видит всё
    """
    queryset = ProductionRecord.objects.all().select_related('partner').prefetch_related('items__product')
    serializer_class = ProductionRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if user.role == 'admin' or user.is_superuser:
            return qs
        if user.role == 'partner':
            return qs.filter(partner=user)

        return qs.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsPartnerUser()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(partner=self.request.user)

    @action(detail=True, methods=['post'], url_path='from-suzerain')
    @transaction.atomic
    def from_suzerain(self, request, pk=None):
        """
        POST /api/products/production-records/{id}/from-suzerain/

        {
            "product_id": 42,
            "suzerain_amount": "3.75"   // например, 3.75 кг фарша → сколько пельменей
        }

        Делает:
        - Рассчитывает количество по Сюзерену
        - Создаёт/обновляет ProductionItem
        - Пересчитывает полную себестоимость (ингредиенты + умная наценка по популярности)
        """
        record: ProductionRecord = self.get_object()

        product_id = request.data.get('product_id')
        suzerain_amount_raw = request.data.get('suzerain_amount')

        if not product_id or suzerain_amount_raw is None:
            return Response(
                {'error': 'product_id и suzerain_amount обязательны'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            suzerain_amount = Decimal(str(suzerain_amount_raw))
            if suzerain_amount <= 0:
                raise ValueError
        except (ValueError, Decimal.InvalidOperation):
            return Response(
                {'error': 'suzerain_amount должен быть положительным числом'},
                status=status.HTTP_400_BAD_REQUEST
            )

        product: Product = get_object_or_404(Product, id=product_id)

        # Расчёт количества по Сюзерену
        quantity_produced = CostCalculator._calculate_quantity_from_suzerain(
            product=product,
            suzerain_amount=suzerain_amount
        )

        if quantity_produced <= 0:
            return Response(
                {'error': 'Не удалось рассчитать количество: нет связи с Сюзереном или proportion = 0'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Создаём или обновляем позицию
        item, created = ProductionItem.objects.update_or_create(
            record=record,
            product=product,
            defaults={
                'suzerain_amount': suzerain_amount,
                'quantity_produced': quantity_produced,
            }
        )

        # Пересчитываем себестоимость (с умной наценкой!)
        CostCalculator.calculate_production_item(item)

        serializer = ProductionItemSerializer(item)

        return Response(
            {
                'message': 'Расчёт от Сюзерена выполнен',
                'created': created,
                'item': serializer.data,
                'quantity_produced': str(quantity_produced),
                'cost_price_per_unit': str(item.cost_price),
                'total_cost': str(item.total_cost),
                'net_profit': str(item.net_profit),
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )