
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Callable, Iterable, Tuple

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from .models import (
    Expense,
    ProductExpense,
    MechanicalExpenseLog,
    CostSnapshot,
    BillOfMaterial,
    BOMLine,
)
from products.models import Product


# ────────────────────────────────────────────────────────────────────────────────
# Округление / числовые помощники (единый стиль)
# ────────────────────────────────────────────────────────────────────────────────

MONEY_PLACES = Decimal("0.01")    # деньги до копеек
QTY_PLACES   = Decimal("0.001")   # количества до тысячных
QZERO        = Decimal("0")

def q2(x: Decimal) -> Decimal:
    return Decimal(x).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)

def q3(x: Decimal) -> Decimal:
    return Decimal(x).quantize(QTY_PLACES, rounding=ROUND_HALF_UP)

def _to_dec(x: Decimal | int | float | str | None) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if x is None:
        return QZERO
    try:
        return Decimal(str(x))
    except Exception:
        return QZERO


# ────────────────────────────────────────────────────────────────────────────────
# DTO (физические/накладные) и итог расчёта (блок 4.1)
# ────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PhysicalLine:
    expense_id: int
    name: str
    unit: Optional[str]
    consumed_qty: Decimal
    amount: Decimal

@dataclass(frozen=True)
class OverheadLine:
    expense_id: int
    name: str
    amount: Decimal

@dataclass
class CalculationResult:
    produced_qty: Decimal
    suzerain_input_amount: Decimal
    physical_total: Decimal
    overhead_total: Decimal
    total_cost: Decimal
    cost_per_unit: Decimal
    physical_breakdown: Tuple[PhysicalLine, ...]
    overhead_breakdown: Tuple[OverheadLine, ...]


# ────────────────────────────────────────────────────────────────────────────────
# High-level API (блок 4.1 — снапшоты по дате, без BOM)
# ────────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def build_and_save_snapshot(
    *,
    product: Product,
    date: Optional[date] = None,
    produced_qty: Optional[Decimal] = None,
    suzerain_input_amount: Optional[Decimal] = None,
    production_totals_by_product: Optional[Dict[int, Decimal]] = None,
    revenue: Decimal = QZERO,
) -> CostSnapshot:
    """
    Главная точка входа:
    - определяет produced_qty из suzerain, если он задан
    - считает физические расходы (по пропорциям и ценам)
    - собирает «пул» накладных (сумма логов за день) и распределяет по товарам
    - создаёт/обновляет CostSnapshot за дату
    """
    date = date or timezone.localdate()

    # 1) Выпуск (шт/кг)
    resolved_produced = _resolve_produced_qty(product, produced_qty, suzerain_input_amount)

    # 2) Физические расходы
    physical_lines, physical_sum = _calc_physical_costs(product, resolved_produced)

    # 3) Накладные
    overhead_lines, overhead_sum = _calc_overheads_for_product(
        product=product,
        date=date,
        produced_qty=resolved_produced,
        production_totals_by_product=production_totals_by_product,
    )

    total_cost = q2(physical_sum + overhead_sum)
    cpu = q3(total_cost / resolved_produced) if resolved_produced > 0 else QZERO

    # 4) Сохраняем снапшот
    snap, _created = CostSnapshot.objects.update_or_create(
        product=product,
        date=date,
        defaults=dict(
            produced_qty=resolved_produced,
            suzerain_input_amount=_to_dec(suzerain_input_amount),
            physical_cost=physical_sum,
            overhead_cost=overhead_sum,
            total_cost=total_cost,
            cost_per_unit=cpu,
            revenue=revenue,
            net_profit=q2(revenue - total_cost),
            breakdown=_pack_breakdown(physical_lines, overhead_lines),
        ),
    )
    return snap


# ────────────────────────────────────────────────────────────────────────────────
# Physical costs
# ────────────────────────────────────────────────────────────────────────────────

def _resolve_produced_qty(
    product: Product,
    produced_qty: Optional[Decimal],
    suzerain_input_amount: Optional[Decimal],
) -> Decimal:
    """
    Если задано produced_qty — используем.
    Иначе при наличии объёма Сюзерена и связи product←SUZERAIN:
        produced = suzerain_amount / ratio_per_product_unit
    Иначе — 0.
    """
    if produced_qty is not None:
        return _to_dec(produced_qty)

    if suzerain_input_amount:
        link = (
            ProductExpense.objects
            .select_related("expense")
            .filter(
                product=product,
                expense__status=Expense.ExpenseStatus.SUZERAIN,
                expense__type=Expense.ExpenseType.PHYSICAL,
                is_active=True,
            )
            .first()
        )
        if link and link.ratio_per_product_unit and link.ratio_per_product_unit > 0:
            return q3(_to_dec(suzerain_input_amount) / link.ratio_per_product_unit)

    return QZERO


def _calc_physical_costs(product: Product, produced_qty: Decimal) -> Tuple[Tuple[PhysicalLine, ...], Decimal]:
    """
    Для всех активных физических расходов product←expense:
      consumed = produced_qty * ratio
      amount   = consumed * expense.price_per_unit
    """
    if produced_qty <= 0:
        return tuple(), QZERO

    links = (
        ProductExpense.objects
        .select_related("expense")
        .filter(
            product=product,
            expense__type=Expense.ExpenseType.PHYSICAL,
            expense__is_active=True,
            is_active=True,
        )
    )

    lines: list[PhysicalLine] = []
    total = QZERO

    for link in links:
        exp = link.expense
        if exp.price_per_unit is None or exp.unit is None:
            # Неполный расход пропускаем; можно логировать
            continue

        consumed = q3(produced_qty * link.ratio_per_product_unit)
        amount = q2(consumed * exp.price_per_unit)

        lines.append(
            PhysicalLine(
                expense_id=exp.id,
                name=exp.name,
                unit=exp.unit,
                consumed_qty=consumed,
                amount=amount,
            )
        )
        total += amount

    return tuple(lines), q2(total)


# ────────────────────────────────────────────────────────────────────────────────
# Overheads (allocation)
# ────────────────────────────────────────────────────────────────────────────────

def _collect_overhead_pool(date_: date) -> Dict[int, Decimal]:
    """
    Собираем «пул» накладных расходов за дату по MechanicalExpenseLog.
    Возвращает {expense_id: amount}.
    """
    logs = (
        MechanicalExpenseLog.objects
        .select_related("expense")
        .filter(
            date=date_,
            expense__type=Expense.ExpenseType.OVERHEAD,
            expense__is_active=True,
        )
    )
    pool: Dict[int, Decimal] = defaultdict(lambda: QZERO)
    for lg in logs:
        pool[lg.expense_id] = q2(pool[lg.expense_id] + _to_dec(lg.amount))
    return dict(pool)


def _calc_overheads_for_product(
    *,
    product: Product,
    date: date,
    produced_qty: Decimal,
    production_totals_by_product: Optional[Dict[int, Decimal]],
) -> Tuple[Tuple[OverheadLine, ...], Decimal]:
    """
    Распределяем сумму накладных по товарам пропорционально объёму производства за дату.
    Если production_totals_by_product не передан — весь пул уйдёт в текущий товар.
    """
    pool = _collect_overhead_pool(date)
    if not pool:
        return tuple(), QZERO

    # Суммарный выпуск всех товаров (для долей)
    if production_totals_by_product is None:
        production_totals_by_product = {product.id: produced_qty}

    total_production = QZERO
    for v in production_totals_by_product.values():
        total_production += _to_dec(v)

    if total_production <= 0:
        return tuple(), QZERO

    share = q3(_to_dec(produced_qty) / total_production) if produced_qty > 0 else QZERO

    lines: list[OverheadLine] = []
    subtotal = QZERO
    for exp_id, amount in pool.items():
        part = q2(amount * share)
        if part == QZERO:
            continue
        name = Expense.objects.only("id", "name").get(id=exp_id).name
        lines.append(OverheadLine(expense_id=exp_id, name=name, amount=part))
        subtotal += part

    return tuple(lines), q2(subtotal)


# ────────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────────

def _pack_breakdown(
    physical: Iterable[PhysicalLine],
    overhead: Iterable[OverheadLine],
) -> Dict:
    """
    JSON для CostSnapshot.breakdown
    """
    phys = {
        str(l.expense_id): {
            "name": l.name,
            "unit": l.unit,
            "consumed_qty": str(l.consumed_qty),
            "amount": str(l.amount),
        }
        for l in physical
    }
    over = {
        str(l.expense_id): {
            "name": l.name,
            "amount": str(l.amount),
        }
        for l in overhead
    }
    return {"physical": phys, "overhead": over}


# ────────────────────────────────────────────────────────────────────────────────
# BOM — исключения, стратегии и расчёт
# ────────────────────────────────────────────────────────────────────────────────

class BOMNotFound(Exception):
    """Нет активного BOM для продукта."""
    pass

class BOMCycleError(Exception):
    """Обнаружен цикл в многоуровневом BOM (цепочка product_id)."""
    def __init__(self, chain: List[int]):
        self.chain = chain
        super().__init__(f"BOM cycle detected: {' -> '.join(map(str, chain))}")

class BOMPriceResolveError(Exception):
    """Ошибка получения цены ингредиента (единицы/цена/снапшот)."""
    pass


# Хуки/стратегии
ExpenseUnitPriceResolver = Callable[[Expense, str, date], Decimal]
OverheadsAllocator       = Callable[[Decimal, Product, date], Decimal]

def default_expense_price_resolver(expense: Expense, unit: str, as_of: date) -> Decimal:
    """
    Базовый резолвер цены за 1 единицу расхода на дату as_of.
    По умолчанию берёт expense.price_per_unit и проверяет совпадение единиц.
    Если у тебя цена берётся из снапшотов/логов — подменяй на свою функцию.
    """
    exp_unit = getattr(expense, "unit", None)
    price    = getattr(expense, "price_per_unit", None)
    if exp_unit is None or price is None:
        raise BOMPriceResolveError(f"Expense#{expense.pk} must provide unit and price_per_unit for BOM.")
    if exp_unit != unit:
        raise BOMPriceResolveError(f"Expense#{expense.pk} unit mismatch: expense={exp_unit} vs line={unit}")
    return q2(Decimal(price))

def default_overheads_allocator(base_cost: Decimal, product: Product, as_of: date) -> Decimal:
    """
    Базовый аллокатор накладных/наценки: ничего не добавляет.
    Подменяй на распределение из блока 4.1.
    """
    return QZERO


# Результат для BOM-калькулятора
@dataclass(frozen=True)
class ProductCostBreakdown:
    product_id: int
    as_of: date
    base_cost: Decimal        # стоимость сырья/полуфабрикатов на 1 ед. продукта
    overheads_addon: Decimal  # добавка накладных/наценки
    final_cost: Decimal       # base_cost + overheads_addon


class BomCostCalculator:
    """
    Рекурсивный расчёт себестоимости по BOM.
    - Мемоизация по product_id
    - Защита от циклов
    - Мягкая политика при отсутствии BOM: 0 (можно сделать строгой через BOMNotFound)
    """

    def __init__(
        self,
        as_of: date,
        expense_price_resolver: ExpenseUnitPriceResolver = default_expense_price_resolver,
        overheads_allocator: OverheadsAllocator = default_overheads_allocator,
        strict_on_missing_bom: bool = False,
    ) -> None:
        self.as_of = as_of
        self._memo_cost: Dict[int, Decimal] = {}
        self._expense_resolver = expense_price_resolver
        self._overheads_allocator = overheads_allocator
        self._strict_on_missing_bom = strict_on_missing_bom

    # Публичное API
    def compute(self, product: Product | int) -> ProductCostBreakdown:
        """
        Возвращает base/overheads/final для продукта на дату as_of.
        """
        product_id = product.id if isinstance(product, Product) else int(product)
        base = self._product_base_cost(product_id, path=[])

        # На случай если аллокатору нужны поля продукта — грузим объект
        product_obj = Product.objects.only("id").get(pk=product_id)
        overheads = q2(self._overheads_allocator(base, product_obj, self.as_of))
        final_cost = q2(base + overheads)

        return ProductCostBreakdown(
            product_id=product_id,
            as_of=self.as_of,
            base_cost=base,
            overheads_addon=overheads,
            final_cost=final_cost,
        )

    # Внутреннее: рекурсия по BOM
    def _product_base_cost(self, product_id: int, path: List[int]) -> Decimal:
        # Мемо
        if product_id in self._memo_cost:
            return self._memo_cost[product_id]

        # Анти-цикл
        if product_id in path:
            raise BOMCycleError(path + [product_id])
        path.append(product_id)

        # Активный BOM
        try:
            bom = (
                BillOfMaterial.objects
                .select_related("product")
                .prefetch_related(
                    Prefetch("lines", queryset=BOMLine.objects.select_related("expense", "component_product"))
                )
                .get(product_id=product_id, is_active=True)
            )
        except BillOfMaterial.DoesNotExist:
            path.pop()
            if self._strict_on_missing_bom:
                raise BOMNotFound(f"Active BOM not found for product #{product_id}")
            self._memo_cost[product_id] = QZERO
            return QZERO

        total = QZERO
        for line in bom.lines.all():
            qty = q3(line.quantity)
            if qty <= 0:
                continue

            if line.expense_id:
                # Сырьё/упаковка
                unit_price = self._expense_resolver(line.expense, line.unit, self.as_of)
            else:
                # Полуфабрикат → рекурсия
                unit_price = self._product_base_cost(line.component_product_id, path=path)

            total += (unit_price * qty)

        path.pop()
        total = q2(total)
        self._memo_cost[product_id] = total
        return total
