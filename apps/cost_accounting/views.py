
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsOwnerOrAdmin  # type: ignore


from .models import Expense, ProductExpense, MechanicalExpenseLog, CostSnapshot, BillOfMaterial, BOMLine
from .serializers import (
    ExpenseSerializer,
    ExpenseShortSerializer,
    ProductExpenseSerializer,
    MechanicalExpenseLogSerializer,
    CostSnapshotSerializer,
    RecalculateRequestSerializer, BomCostPreviewRequestSerializer, BillOfMaterialSerializer,
)
from .calculators import build_and_save_snapshot, BOMNotFound, BOMPriceResolveError, BOMCycleError, BomCostCalculator


# =========================
# CRUD: Expenses
# =========================
class ExpenseViewSet(viewsets.ModelViewSet):
    """
    /api/cost/expenses/
      - GET (list): ?type=physical|overhead&active=true|false&search=<name substr>
      - POST/PUT/PATCH/DELETE
    """
    queryset = Expense.objects.all().order_by("-id")
    serializer_class = ExpenseSerializer
    permission_classes = [IsOwnerOrAdmin]

    def get_serializer_class(self):
        if self.action == "list":
            return ExpenseShortSerializer
        return ExpenseSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        t = self.request.query_params.get("type")
        if t in (Expense.ExpenseType.PHYSICAL, Expense.ExpenseType.OVERHEAD):
            qs = qs.filter(type=t)

        active = self.request.query_params.get("active")
        if active in ("true", "false"):
            qs = qs.filter(is_active=(active == "true"))

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)

        return qs


# =========================
# CRUD: ProductExpense (BOM)
# =========================
class ProductExpenseViewSet(viewsets.ModelViewSet):
    """
    /api/cost/product-expenses/
      - GET (list): ?product=<id>&expense=<id>&active=true|false
    """
    queryset = ProductExpense.objects.select_related("product", "expense").all().order_by("-id")
    serializer_class = ProductExpenseSerializer
    permission_classes = [IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        product_id = self.request.query_params.get("product")
        expense_id = self.request.query_params.get("expense")
        active = self.request.query_params.get("active")

        if product_id:
            qs = qs.filter(product_id=product_id)
        if expense_id:
            qs = qs.filter(expense_id=expense_id)
        if active in ("true", "false"):
            qs = qs.filter(is_active=(active == "true"))
        return qs


# =========================
# CRUD: Mechanical logs
# =========================
class MechanicalExpenseLogViewSet(viewsets.ModelViewSet):
    """
    /api/cost/mechanical-logs/
      - GET (list): ?date=YYYY-MM-DD&expense=<id>&type=overhead|physical
    """
    queryset = MechanicalExpenseLog.objects.select_related("expense").all().order_by("-date", "-id")
    serializer_class = MechanicalExpenseLogSerializer
    permission_classes = [IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        date = self.request.query_params.get("date")
        expense_id = self.request.query_params.get("expense")
        t = self.request.query_params.get("type")

        if date:
            qs = qs.filter(date=date)
        if expense_id:
            qs = qs.filter(expense_id=expense_id)
        if t in (Expense.ExpenseType.PHYSICAL, Expense.ExpenseType.OVERHEAD):
            qs = qs.filter(expense__type=t)

        return qs


# =========================
# READONLY: Cost snapshots
# =========================
class CostSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/cost/snapshots/
      - GET (list): ?date=YYYY-MM-DD | ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
                    &product=<id>
    """
    queryset = CostSnapshot.objects.select_related("product").all().order_by("-date", "-id")
    serializer_class = CostSnapshotSerializer
    permission_classes = [IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        date = self.request.query_params.get("date")
        product_id = self.request.query_params.get("product")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if date:
            qs = qs.filter(date=date)
        else:
            if date_from and date_to:
                qs = qs.filter(date__range=[date_from, date_to])
            elif date_from:
                qs = qs.filter(date__gte=date_from)
            elif date_to:
                qs = qs.filter(date__lte=date_to)

        if product_id:
            qs = qs.filter(product_id=product_id)

        return qs


# =========================
# ACTION: Recalculate & Save snapshot
# =========================
class RecalculateAPIView(APIView):
    """
    POST /api/cost/recalculate/
      payload:
        {
          "product_id": 1,
          "date": "2025-09-02",
          "produced_qty": "200.0",           # либо
          "suzerain_input_amount": null,     # либо объём сюзерена
          "revenue": "0.00",
          "production_totals_by_product": {"1": "200.0", "2": "80.0"}
        }
    """
    permission_classes = [IsOwnerOrAdmin]

    def post(self, request, *args, **kwargs):
        s = RecalculateRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        product = data["product"]
        date = data.get("date") or timezone.localdate()
        produced_qty = data.get("produced_qty")
        suzerain_amount = data.get("suzerain_input_amount")
        revenue = data.get("revenue") or Decimal("0.00")
        totals_map: Optional[Dict[int, Decimal]] = data.get("production_totals_by_product")

        snap = build_and_save_snapshot(
            product=product,
            date=date,
            produced_qty=produced_qty,
            suzerain_input_amount=suzerain_amount,
            production_totals_by_product=totals_map,
            revenue=revenue,
        )

        return Response(CostSnapshotSerializer(snap).data, status=status.HTTP_200_OK)


class BillOfMaterialViewSet(viewsets.ModelViewSet):
    """
    CRUD для BOM (с вложенными строками).
    Поддерживает фильтр по product_id: /api/bom/?product_id=123
    """
    permission_classes = [IsOwnerOrAdmin]
    serializer_class = BillOfMaterialSerializer

    def get_queryset(self):
        qs = (
            BillOfMaterial.objects
            .select_related("product")
            .prefetch_related(
                Prefetch("lines", queryset=BOMLine.objects.select_related("expense", "component_product"))
            )
        )
        product_id = self.request.query_params.get("product_id")
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs.order_by("-is_active", "product_id", "-version")

    def create(self, request, *args, **kwargs):
        # product_id обязателен при создании
        serializer = self.get_serializer(data=request.data, context={})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save()

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial, context={})
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)


class BomCostPreviewView(APIView):
    """
    POST /api/bom/preview-cost/
    Тело: { "product_id": <id>, "date": "YYYY-MM-DD" (опционально) }
    Возвращает: base_cost, overheads_addon, final_cost
    """
    permission_classes = [IsOwnerOrAdmin]

    def post(self, request, *args, **kwargs):
        req = BomCostPreviewRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        product = req.validated_data["product"]
        as_of = req.validated_data["date"]

        # Собираем калькулятор. По умолчанию мягко относимся к отсутствию BOM.
        calc = BomCostCalculator(as_of=as_of)

        try:
            res = calc.compute(product)
        except BOMCycleError as e:
            return Response(
                {"detail": "Обнаружен цикл в BOM.", "chain": e.chain},
                status=status.HTTP_409_CONFLICT,
            )
        except BOMPriceResolveError as e:
            return Response(
                {"detail": f"Ошибка определения цены: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except BOMNotFound as e:
            # Если решишь включить strict_on_missing_bom=True
            return Response(
                {"detail": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "product_id": res.product_id,
                "as_of": str(res.as_of),
                "base_cost": str(res.base_cost),
                "overheads_addon": str(res.overheads_addon),
                "final_cost": str(res.final_cost),
            },
            status=status.HTTP_200_OK,
        )