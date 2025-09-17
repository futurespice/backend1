from __future__ import annotations
from datetime import date, timedelta
from typing import Optional, Dict, Any, Iterable
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum

from .models import (
    Report,)
from .waste_models import WasteLog, WasteReport


def _daterange(d1: date, d2: date) -> Iterable[date]:
    cur = d1
    while cur <= d2:
        yield cur
        cur += timedelta(days=1)


def _apply_filters(qs, partner_id: Optional[int], store_id: Optional[int], product_id: Optional[int]):
    if partner_id:
        qs = qs.filter(partner_id=partner_id)
    if store_id:
        qs = qs.filter(store_id=store_id)
    if product_id:
        qs = qs.filter(product_id=product_id)
    return qs


# ---------------- WASTE ----------------

@transaction.atomic
def rebuild_waste_daily(
    date_on: date,
    partner_id: Optional[int] = None,
    store_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> int:
    qs = WasteLog.objects.filter(date=date_on)
    qs = _apply_filters(qs, partner_id, store_id, product_id)

    grouped = (
        qs.values("date", "partner_id", "store_id", "product_id")
          .annotate(waste_quantity=Sum("quantity"), waste_amount=Sum("amount"))
    )

    updated = 0
    for row in grouped:
        WasteReport.objects.update_or_create(
            date=row["date"],
            partner_id=row["partner_id"],
            store_id=row["store_id"],
            product_id=row["product_id"],
            defaults=dict(
                waste_quantity=row["waste_quantity"] or Decimal("0"),
                waste_amount=row["waste_amount"] or Decimal("0"),
            ),
        )
        updated += 1
    return updated


def rebuild_waste_range(
    date_from: date,
    date_to: date,
    partner_id: Optional[int] = None,
    store_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> int:
    total = 0
    for d in _daterange(date_from, date_to):
        total += rebuild_waste_daily(d, partner_id, store_id, product_id)
    return total


def _to_str(d: Decimal | None, places: str) -> str:
    d = Decimal(d or 0)
    return str(d.quantize(Decimal(places), rounding=ROUND_HALF_UP))


from decimal import Decimal, ROUND_HALF_UP

def _to_str(d: Decimal | None, places: str) -> str:
    d = Decimal(d or 0)
    return str(d.quantize(Decimal(places), rounding=ROUND_HALF_UP))

def collect_waste_period_totals(
    date_from: date,
    date_to: date,
    partner_id: Optional[int] = None,
    store_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> Dict[str, Any]:
    qs = WasteReport.objects.filter(date__range=(date_from, date_to))
    qs = _apply_filters(qs, partner_id, store_id, product_id)

    agg = qs.aggregate(
        total_waste_quantity=Sum("waste_quantity"),
        total_waste_amount=Sum("waste_amount"),
    )
    qty = agg["total_waste_quantity"]
    amt = agg["total_waste_amount"]
    return {
        "total_waste_quantity": _to_str(qty, "0.001"),  # строка, 3 знака
        "total_waste_amount": _to_str(amt, "0.01"),     # строка, 2 знака
    }



# ---------------- SALES ----------------

@transaction.atomic
def rebuild_sales_daily(
    day: date,
    partner_id: Optional[int] = None,
    store_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> int:
    return 0


# ---------------- INVENTORY ----------------

@transaction.atomic
def rebuild_inventory_daily(
    day: date,
    partner_id: Optional[int] = None,
    store_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> int:
    return 0


# ---------------- DEBTS ----------------

@transaction.atomic
def rebuild_debts_daily(
    day: date,
    partner_id: Optional[int] = None,
    store_id: Optional[int] = None,
) -> int:
    return 0


# ---------------- BONUS ----------------

@transaction.atomic
def rebuild_bonus_daily(
    day: date,
    partner_id: Optional[int] = None,
    store_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> int:
    return 0


@transaction.atomic
def rebuild_bonus_monthly(
    year: int,
    month: int,
    partner_id: Optional[int] = None,
    store_id: Optional[int] = None
) -> int:
    return 0


# ---------------- COST ----------------

@transaction.atomic
def rebuild_cost_on_date(
    day: date,
    product_id: int,
    production_batch_id: Optional[int] = None,
) -> int:
    return 0


# ---------------- ENTRY POINT ----------------

def _build_report_data(
    report_type: str,
    date_from: date,
    date_to: date,
    partner_id: Optional[int] = None,
    store_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> Dict[str, Any]:
    base_meta = {
        "report_type": report_type,
        "period": {"date_from": str(date_from), "date_to": str(date_to)},
        "filters": {"partner_id": partner_id, "store_id": store_id, "product_id": product_id},
    }

    if report_type == "waste":
        rebuilt = rebuild_waste_range(date_from, date_to, partner_id, store_id, product_id)
        totals = collect_waste_period_totals(date_from, date_to, partner_id, store_id, product_id)
        return {**base_meta, "rebuilt_rows": rebuilt, "totals": totals}

    if report_type == "sales":
        return {**base_meta, "status": "sales_not_implemented"}

    if report_type == "inventory":
        return {**base_meta, "status": "inventory_not_implemented"}

    if report_type == "debts":
        return {**base_meta, "status": "debts_not_implemented"}

    if report_type == "bonuses":
        return {**base_meta, "status": "bonuses_not_implemented"}

    if report_type == "costs":
        return {**base_meta, "status": "costs_not_implemented"}

    if report_type == "profit":
        return {**base_meta, "status": "profit_not_implemented"}

    if report_type == "partner_performance":
        return {**base_meta, "status": "partner_perf_not_implemented"}

    if report_type == "store_performance":
        return {**base_meta, "status": "store_perf_not_implemented"}

    return {**base_meta, "status": "unknown_report_type"}


@transaction.atomic
def generate_and_save_report(
    *,
    name: str,
    report_type: str,
    period: str,
    date_from: date,
    date_to: date,
    created_by_id: int,
    partner_id: Optional[int] = None,
    store_id: Optional[int] = None,
    product_id: Optional[int] = None,
    is_automated: bool = False,
) -> Report:
    data = _build_report_data(
        report_type=report_type,
        date_from=date_from,
        date_to=date_to,
        partner_id=partner_id,
        store_id=store_id,
        product_id=product_id,
    )

    report = Report.objects.create(
        name=name,
        report_type=report_type,
        period=period,
        date_from=date_from,
        date_to=date_to,
        store_id=store_id,
        partner_id=partner_id,
        product_id=product_id,
        data=data,
        created_by_id=created_by_id,
        is_automated=is_automated,
    )
    return report
