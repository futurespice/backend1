from __future__ import annotations
from typing import Optional

from django.db.models import QuerySet
from django.utils.dateparse import parse_date
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from django.db.models import Q
from .models import (
    Report,
    SalesReport, InventoryReport, DebtReport,
    BonusReport, BonusReportMonthly, CostReport
)
from .waste_models import WasteLog, WasteReport
from .serializers import (
    ReportSerializer, GenerateReportSerializer,
    SalesReportSerializer, InventoryReportSerializer, DebtReportSerializer,
    BonusReportSerializer, BonusReportMonthlySerializer, CostReportSerializer,
    WasteLogSerializer, WasteReportSerializer,
)


# --------- helpers ---------
def _int_or_none(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value not in (None, "", "null") else None
    except ValueError:
        return None

def _str_or_none(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip()
    return v if v and v.lower() != "null" else None


def _apply_common_filters(qs: QuerySet, request: Request, *, date_field: Optional[str] = None) -> QuerySet:
    """
    Общие фильтры:
      - partner, store, product (ID)
      - date_from/date_to (если передан date_field)
      - ДОП: inn, store_name, partner_query, region / region_code / region_name
    """
    partner = _int_or_none(request.query_params.get("partner"))
    store = _int_or_none(request.query_params.get("store"))
    product = _int_or_none(request.query_params.get("product"))

    if partner is not None:
        qs = qs.filter(partner_id=partner)
    if store is not None:
        qs = qs.filter(store_id=store)
    if product is not None and hasattr(qs.model, "product_id"):
        qs = qs.filter(product_id=product)

    # даты по одному полю
    if date_field:
        d_from = parse_date(request.query_params.get("date_from") or "")
        d_to = parse_date(request.query_params.get("date_to") or "")
        if d_from and d_to:
            qs = qs.filter(**{f"{date_field}__range": (d_from, d_to)})
        elif d_from:
            qs = qs.filter(**{f"{date_field}__gte": d_from})
        elif d_to:
            qs = qs.filter(**{f"{date_field}__lte": d_to})

    # ---- доп. фильтры
    inn = _str_or_none(request.query_params.get("inn"))
    store_name = _str_or_none(request.query_params.get("store_name") or request.query_params.get("store_title"))
    partner_query = _str_or_none(request.query_params.get("partner_name") or request.query_params.get("partner_query"))

    region_id = _int_or_none(request.query_params.get("region"))
    region_code = _str_or_none(request.query_params.get("region_code"))
    region_name = _str_or_none(request.query_params.get("region_name"))

    if inn:
        qs = qs.filter(store__inn=inn) if inn.isdigit() and 12 <= len(inn) <= 14 else qs.filter(store__inn__icontains=inn)

    if store_name:
        qs = qs.filter(Q(store__name__icontains=store_name) | Q(store__store_name__icontains=store_name))

    if partner_query:
        qs = qs.filter(
            Q(partner__name__icontains=partner_query) |
            Q(partner__second_name__icontains=partner_query) |
            Q(partner__email__icontains=partner_query) |
            Q(partner__phone__icontains=partner_query)
        )

    if region_id is not None:
        qs = qs.filter(store__region_id=region_id)
    if region_code:
        qs = qs.filter(store__region__code__iexact=region_code)
    if region_name:
        qs = qs.filter(store__region__name__icontains=region_name)

    return qs


# --------- Report journal ---------
class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Журнал сформированных отчётов (витрина Report).

    Эндпоинты:
      • GET /api/reports/ — список отчётов с фильтрами.
      • GET /api/reports/{id}/ — подробности конкретного отчёта (включая сохранённый JSON в поле data).
      • POST /api/reports/generate/ — сгенерировать и сохранить новый отчёт в журнале.

    Фильтры списка:
      • report_type — тип отчёта (sales, inventory, debts, bonuses, costs, profit, partner_performance, store_performance, waste)
      • period — период (daily, weekly, monthly, quarterly, yearly, custom)
      • date_from, date_to — ограничение по датам отчёта
      • partner, store, product — фильтры по объектам

    Примеры:
      • /api/reports/?report_type=waste&date_from=2025-09-01&date_to=2025-09-15
      • /api/reports/?period=monthly&partner=7
    """
    permission_classes = [IsAuthenticated]
    queryset = Report.objects.all().select_related("store", "partner", "product", "created_by")
    serializer_class = ReportSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        # --- базовые фильтры ---
        rtype = self.request.query_params.get("report_type")
        period = self.request.query_params.get("period")
        if rtype:
            qs = qs.filter(report_type=rtype)
        if period:
            qs = qs.filter(period=period)

        # даты по паре полей (date_from / date_to)
        d_from = parse_date(self.request.query_params.get("date_from") or "")
        d_to = parse_date(self.request.query_params.get("date_to") or "")
        if d_from and d_to:
            qs = qs.filter(date_from__gte=d_from, date_to__lte=d_to)
        elif d_from:
            qs = qs.filter(date_to__gte=d_from)
        elif d_to:
            qs = qs.filter(date_from__lte=d_to)

        # partner / store / product (ID)
        partner = _int_or_none(self.request.query_params.get("partner"))
        store = _int_or_none(self.request.query_params.get("store"))
        product = _int_or_none(self.request.query_params.get("product"))
        if partner is not None:
            qs = qs.filter(partner_id=partner)
        if store is not None:
            qs = qs.filter(store_id=store)
        if product is not None:
            qs = qs.filter(product_id=product)

        # --- дополнительные фильтры ---
        inn = _str_or_none(self.request.query_params.get("inn"))
        store_name = _str_or_none(
            self.request.query_params.get("store_name")
            or self.request.query_params.get("store_title")
        )
        partner_query = _str_or_none(
            self.request.query_params.get("partner_name")
            or self.request.query_params.get("partner_query")
        )
        region_id = _int_or_none(self.request.query_params.get("region"))
        region_code = _str_or_none(self.request.query_params.get("region_code"))
        region_name = _str_or_none(self.request.query_params.get("region_name"))

        if inn:
            qs = qs.filter(store__inn=inn) if inn.isdigit() and 12 <= len(inn) <= 14 \
                else qs.filter(store__inn__icontains=inn)

        if store_name:
            qs = qs.filter(Q(store__name__icontains=store_name) |
                           Q(store__store_name__icontains=store_name))

        if partner_query:
            qs = qs.filter(
                Q(partner__name__icontains=partner_query) |
                Q(partner__second_name__icontains=partner_query) |
                Q(partner__email__icontains=partner_query) |
                Q(partner__phone__icontains=partner_query)
            )

        if region_id is not None:
            qs = qs.filter(store__region_id=region_id)
        if region_code:
            qs = qs.filter(store__region__code__iexact=region_code)
        if region_name:
            qs = qs.filter(store__region__name__icontains=region_name)

        return qs

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request: Request) -> Response:
        """
        Сгенерировать отчёт и сохранить его в журнал.

        Тело запроса (JSON):
          - name (str) — название отчёта
          - report_type (str) — тип (см. Report.REPORT_TYPES)
          - period (str) — период (см. Report.PERIODS)
          - date_from (date), date_to (date)
          - partner (id, опц.), store (id, опц.), product (id, опц.)
          - is_automated (bool, опц.)

        Ответ: объект Report (включая поле data с рассчитанными агрегатами).
        """
        ser = GenerateReportSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        report = ser.save()
        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)


# --------- Waste (лог + дневная витрина) ---------
class WasteLogViewSet(mixins.CreateModelMixin,
                      mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """
    Логи брака (первичка списаний).

    Эндпоинты:
      • GET  /api/reports/waste-logs/         — список инцидентов брака с фильтрами.
      • POST /api/reports/waste-logs/         — создать запись о браке (кол-во, сумма, причина).
      • GET  /api/reports/waste-logs/{id}/    — подробности инцидента.

    Фильтры списка:
      • date_from, date_to — даты инцидентов
      • partner, store, product — по объектам

    Пример:
      • /api/reports/waste-logs/?store=3&date_from=2025-09-01&date_to=2025-09-10
    """
    permission_classes = [IsAuthenticated]
    queryset = WasteLog.objects.all().select_related("store", "partner", "product", "created_by")
    serializer_class = WasteLogSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        return _apply_common_filters(qs, self.request, date_field="date")


class WasteReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Дневные агрегированные отчёты по браку (витрина по дням).

    Эндпоинты:
      • GET /api/reports/waste/           — список дневных агрегатов по браку.
      • GET /api/reports/waste/{id}/      — детали конкретной записи.

    Фильтры списка:
      • date_from, date_to — диапазон дат
      • partner, store, product — по объектам

    Пример:
      • /api/reports/waste/?partner=12&date_from=2025-09-01&date_to=2025-09-15
    """
    permission_classes = [IsAuthenticated]
    queryset = WasteReport.objects.all().select_related("store", "partner", "product")
    serializer_class = WasteReportSerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        return _apply_common_filters(qs, self.request, date_field="date")


# --------- Sales ---------
class SalesReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Отчёты по продажам за день (количество заказов, объём продаж, выручка, бонусы, себестоимость, прибыль).

    Эндпоинты:
      • GET /api/reports/sales/           — список дневных отчётов по продажам.
      • GET /api/reports/sales/{id}/      — детали записи.

    Фильтры списка:
      • date_from, date_to — диапазон дат
      • partner, store, product — по объектам

    Пример:
      • /api/reports/sales/?store=5&date_from=2025-09-01&date_to=2025-09-07
    """
    permission_classes = [IsAuthenticated]
    queryset = SalesReport.objects.all().select_related("store", "partner", "product")
    serializer_class = SalesReportSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        return _apply_common_filters(qs, self.request, date_field="date")


# --------- Inventory ---------
class InventoryReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Отчёты по остаткам (на дату): начальный остаток, поступления, продажи, конечный остаток и их стоимость.

    Эндпоинты:
      • GET /api/reports/inventory/           — список отчётов по остаткам.
      • GET /api/reports/inventory/{id}/      — детали записи.

    Фильтры списка:
      • date_from, date_to — диапазон дат
      • partner, store, product — по объектам

    Пример:
      • /api/reports/inventory/?product=101&date_from=2025-09-01&date_to=2025-09-30
    """
    permission_classes = [IsAuthenticated]
    queryset = InventoryReport.objects.all().select_related("store", "partner", "product", "production_batch")
    serializer_class = InventoryReportSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        return _apply_common_filters(qs, self.request, date_field="date")


# --------- Debts ---------
class DebtReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Отчёты по долгам партнёров/магазинов на дату: открытый долг, начислено, погашено, долг на конец.

    Эндпоинты:
      • GET /api/reports/debts/           — список отчётов по долгам.
      • GET /api/reports/debts/{id}/      — детали записи.

    Фильтры списка:
      • date_from, date_to — диапазон дат
      • partner, store — по объектам

    Пример:
      • /api/reports/debts/?partner=7&date_from=2025-09-01&date_to=2025-09-15
    """
    permission_classes = [IsAuthenticated]
    queryset = DebtReport.objects.all().select_related("store", "partner")
    serializer_class = DebtReportSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        return _apply_common_filters(qs, self.request, date_field="date")


# --------- Bonuses (daily) ---------
class BonusReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Ежедневные отчёты по бонусам (штучные товары): бесплатные единицы, сумма бонусной скидки, net-выручка.

    Эндпоинты:
      • GET /api/reports/bonuses/           — список дневных бонусных отчётов.
      • GET /api/reports/bonuses/{id}/      — детали записи.

    Фильтры списка:
      • date_from, date_to — диапазон дат
      • partner, store, product — по объектам

    Пример:
      • /api/reports/bonuses/?store=2&date_from=2025-09-01&date_to=2025-09-30
    """
    permission_classes = [IsAuthenticated]
    queryset = BonusReport.objects.all().select_related("store", "partner", "product", "production_batch")
    serializer_class = BonusReportSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        return _apply_common_filters(qs, self.request, date_field="date")


# --------- Bonuses (monthly) ---------
class BonusReportMonthlyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Месячная сводка по бонусам (агрегат на основе дневных отчётов).

    Эндпоинты:
      • GET /api/reports/bonuses-monthly/           — список месячных сводок.
      • GET /api/reports/bonuses-monthly/{id}/      — детали записи.

    Фильтры списка:
      • year, month — период (например, ?year=2025&month=9)
      • partner, store — по объектам (опционально)

    Пример:
      • /api/reports/bonuses-monthly/?year=2025&month=9&partner=7
    """
    permission_classes = [IsAuthenticated]
    queryset = BonusReportMonthly.objects.all().select_related("store", "partner")
    serializer_class = BonusReportMonthlySerializer

    def get_queryset(self):
        qs = super().get_queryset()

        year = _int_or_none(self.request.query_params.get("year"))
        month = _int_or_none(self.request.query_params.get("month"))
        if year is not None:
            qs = qs.filter(year=year)
        if month is not None:
            qs = qs.filter(month=month)

        partner = _int_or_none(self.request.query_params.get("partner"))
        store = _int_or_none(self.request.query_params.get("store"))
        if partner is not None:
            qs = qs.filter(partner_id=partner)
        if store is not None:
            qs = qs.filter(store_id=store)

        return qs


# --------- Cost ---------
class CostReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Отчёты по себестоимости продукции (на дату): материалы, накладные, итоговая себестоимость, объём выпуска.

    Эндпоинты:
      • GET /api/reports/costs/           — список отчётов по себестоимости.
      • GET /api/reports/costs/{id}/      — детали записи (включая привязку к производственной партии).

    Фильтры списка:
      • date_from, date_to — диапазон дат
      • partner, store, product — по объектам (partner/store используются в связке с товарами/складами)

    Пример:
      • /api/reports/costs/?product=42&date_from=2025-09-01&date_to=2025-09-10
    """
    permission_classes = [IsAuthenticated]
    queryset = CostReport.objects.all().select_related("product", "production_batch")
    serializer_class = CostReportSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        return _apply_common_filters(qs, self.request, date_field="date")
