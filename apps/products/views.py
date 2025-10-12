from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from datetime import date

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
    DefectiveProductSerializer
)
from .services import CostCalculator, BonusService
from .permissions import IsAdminOnly, IsPartnerOrAdmin


class ExpenseViewSet(viewsets.ModelViewSet):
    """Расходы — только ADMIN"""
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated, IsAdminOnly]
    queryset = Expense.objects.all()

    @action(detail=False, methods=['get'])
    def physical(self, request):
        """Только физические расходы"""
        expenses = self.queryset.filter(expense_type='physical')
        serializer = self.get_serializer(expenses, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def overhead(self, request):
        """Только накладные расходы"""
        expenses = self.queryset.filter(expense_type='overhead')
        serializer = self.get_serializer(expenses, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Деактивация расхода"""
        expense = self.get_object()
        expense.is_active = False
        expense.save()
        return Response({'status': 'deactivated'})


class ProductViewSet(viewsets.ModelViewSet):
    """Товары — ADMIN создаёт, все видят"""
    queryset = Product.objects.all().prefetch_related('images')

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductDetailSerializer

    def get_permissions(self):
        # Создание/редактирование только ADMIN
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'reorder']:
            return [IsAuthenticated(), IsAdminOnly()]
        return [IsAuthenticated()]

    def perform_destroy(self, instance):
        """Удаление товара (полное из БД)"""
        instance.delete()

    @action(detail=True, methods=['post'])
    def reorder(self, request, pk=None):
        """Изменить позицию товара"""
        product = self.get_object()
        new_position = request.data.get('position')

        if new_position is not None:
            product.position = new_position
            product.save()

        return Response({'position': product.position})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdminOnly])
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
    permission_classes = [IsAuthenticated, IsAdminOnly]
    queryset = ProductionRecord.objects.all()

    def create(self, request, *args, **kwargs):
        """Создание записи на дату"""
        date_str = request.data.get('date', date.today())

        record, created = ProductionRecord.objects.get_or_create(date=date_str)

        serializer = self.get_serializer(record)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_item(self, request, pk=None):
        """Добавить товар в таблицу"""
        record = self.get_object()
        product_id = request.data.get('product_id')
        quantity_produced = request.data.get('quantity_produced', 0)
        suzerain_amount = request.data.get('suzerain_amount', 0)

        product = get_object_or_404(Product, id=product_id)

        item, created = ProductionItem.objects.update_or_create(
            record=record,
            product=product,
            defaults={
                'quantity_produced': quantity_produced,
                'suzerain_amount': suzerain_amount
            }
        )

        # Расчёт
        CostCalculator.calculate_production_item(item)

        serializer = ProductionItemSerializer(item)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_mechanical_expense(self, request, pk=None):
        """Добавить механический расход (солярка, обеды)"""
        record = self.get_object()
        expense_id = request.data.get('expense_id')
        amount_spent = request.data.get('amount_spent', 0)

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
    def save_data(self, request, pk=None):
        """Сохранить данные за день (перезапись)"""
        record = self.get_object()

        # Пересчитываем всё
        CostCalculator.recalculate_all_items(record)

        serializer = self.get_serializer(record)
        return Response(serializer.data)


class BonusViewSet(viewsets.ReadOnlyModelViewSet):
    """История бонусов"""
    serializer_class = BonusHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == 'ADMIN':
            return BonusHistory.objects.all()

        if user.role == 'PARTNER':
            return BonusHistory.objects.filter(partner=user)

        return BonusHistory.objects.filter(store=user)

    @action(detail=False, methods=['get'])
    def progress(self, request):
        """Прогресс до бонуса для STORE"""
        if request.user.role != 'STORE':
            return Response({'error': 'Only for stores'}, status=status.HTTP_403_FORBIDDEN)

        counters = StoreProductCounter.objects.filter(
            store=request.user
        ).select_related('product', 'partner')

        data = [
            {
                'product_id': c.product.id,
                'product_name': c.product.name,
                'partner_name': c.partner.username,
                'progress': c.bonus_eligible_count,
                'total_count': c.total_count
            }
            for c in counters
        ]

        return Response(data)


class DefectiveProductViewSet(viewsets.ModelViewSet):
    """Бракованные товары (партнёр фиксирует свой брак)"""
    serializer_class = DefectiveProductSerializer
    permission_classes = [IsAuthenticated, IsPartnerOrAdmin]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'ADMIN':
            return DefectiveProduct.objects.all()
        return DefectiveProduct.objects.filter(partner=user)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Статистика брака"""
        queryset = self.get_queryset()

        from django.db.models import Sum
        total_defects = queryset.count()
        total_amount = queryset.aggregate(Sum('amount'))['amount__sum'] or 0

        return Response({
            'total_defects': total_defects,
            'total_amount': total_amount
        })