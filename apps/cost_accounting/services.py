from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple, NamedTuple
from datetime import date
from django.db import transaction
from django.db.models import Sum, Q

from .models import (
    Expense, ProductExpense, DailyExpenseLog,
    ProductionBatch, MonthlyOverheadBudget, BillOfMaterial, BOMLine
)
from products.models import Product


class PhysicalCostItem(NamedTuple):
    """Элемент физического расхода"""
    expense_id: int
    name: str
    unit: str
    quantity_per_product: Decimal
    consumed_quantity: Decimal
    unit_price: Decimal
    total_cost: Decimal


class ComponentCostItem(NamedTuple):
    """Элемент стоимости компонента-продукта"""
    component_product_id: int
    name: str
    unit: str
    quantity_per_product: Decimal
    consumed_quantity: Decimal
    unit_price: Decimal
    total_cost: Decimal


class OverheadCostItem(NamedTuple):
    """Элемент накладного расхода"""
    expense_id: int
    name: str
    daily_budget: Decimal
    product_share: Decimal  # доля товара в общем объеме
    allocated_cost: Decimal


class CostBreakdown(NamedTuple):
    """Полная разбивка себестоимости"""
    product_id: int
    date: date
    produced_quantity: Decimal
    physical_costs: List[PhysicalCostItem]
    component_costs: List[ComponentCostItem]
    overhead_costs: List[OverheadCostItem]
    total_physical: Decimal
    total_components: Decimal
    total_overhead: Decimal
    total_cost: Decimal
    cost_per_unit: Decimal


class CostCalculationService:
    """
    Сервис динамического расчета себестоимости.
    Реализует логику из реального примера заказчика + BOM система.
    """

    @staticmethod
    def q2(value) -> Decimal:
        """Округление до 2 знаков (суммы)"""
        return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @staticmethod
    def q3(value) -> Decimal:
        """Округление до 3 знаков (количества)"""
        return Decimal(str(value)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)

    def calculate_daily_costs(
            self,
            production_data: Dict[int, Dict],  # {product_id: {'quantity': .., 'suzerain_input': ..}}
            calculation_date: date = None
    ) -> List[CostBreakdown]:
        """
        Главный метод расчета себестоимости за день.

        Пример production_data:
        {
            1: {'quantity': 1100, 'suzerain_input': None},  # пельмени
            2: {'quantity': 440, 'suzerain_input': None},   # тесто
            3: {'quantity': None, 'suzerain_input': 105}    # через объем фарша
        }
        """
        if calculation_date is None:
            calculation_date = date.today()

        results = []

        # 1. Собираем все продукты и их объемы производства
        total_production_volume = self._calculate_total_production_volume(
            production_data, calculation_date
        )

        for product_id, prod_data in production_data.items():
            try:
                product = Product.objects.get(id=product_id, is_active=True)

                # 2. Определяем количество произведенного товара
                produced_qty = self._resolve_production_quantity(
                    product, prod_data, calculation_date
                )

                if produced_qty <= 0:
                    continue

                # 3. Рассчитываем стоимость компонентов через BOM (если есть)
                component_costs, total_components = self._calculate_bom_component_costs(
                    product, produced_qty, calculation_date
                )

                # 4. Рассчитываем физические расходы (традиционная система)
                physical_costs, total_physical = self._calculate_physical_costs(
                    product, produced_qty, calculation_date
                )

                # 5. Рассчитываем накладные расходы с умным распределением
                overhead_costs, total_overhead = self._calculate_overhead_costs(
                    product, produced_qty, total_production_volume, calculation_date
                )

                # 6. Итоговые расчеты
                total_cost = self.q2(total_physical + total_components + total_overhead)
                cost_per_unit = self.q3(total_cost / produced_qty) if produced_qty > 0 else Decimal('0')

                # 7. Создаем разбивку
                breakdown = CostBreakdown(
                    product_id=product.id,
                    date=calculation_date,
                    produced_quantity=produced_qty,
                    physical_costs=physical_costs,
                    component_costs=component_costs,
                    overhead_costs=overhead_costs,
                    total_physical=total_physical,
                    total_components=total_components,
                    total_overhead=total_overhead,
                    total_cost=total_cost,
                    cost_per_unit=cost_per_unit
                )

                results.append(breakdown)

            except Product.DoesNotExist:
                continue

        return results

    def _calculate_bom_component_costs(
            self,
            product: Product,
            produced_qty: Decimal,
            calculation_date: date
    ) -> Tuple[List[ComponentCostItem], Decimal]:
        """
        Расчет стоимости компонентов-продуктов через BOM систему.

        Если у товара есть спецификация с компонентами-продуктами,
        рассчитываем их стоимость.
        """
        if not hasattr(product, 'bom_specification') or not product.bom_specification.is_active:
            return [], Decimal('0')

        bom = product.bom_specification
        component_lines = bom.lines.filter(
            component_product__isnull=False
        ).select_related('component_product')

        costs = []
        total = Decimal('0')

        for line in component_lines:
            component_product = line.component_product

            # Количество компонента на весь объем производства
            consumed_qty = self.q3(produced_qty * line.quantity)

            # Проверяем наличие компонента на складе
            if not component_product.is_in_stock(consumed_qty):
                # Можно логировать предупреждение или использовать доступное количество
                continue

            # Стоимость компонента
            component_cost = component_product.calculate_price(consumed_qty)

            cost_item = ComponentCostItem(
                component_product_id=component_product.id,
                name=component_product.name,
                unit=line.unit,
                quantity_per_product=line.quantity,
                consumed_quantity=consumed_qty,
                unit_price=component_product.price,
                total_cost=component_cost
            )

            costs.append(cost_item)
            total += component_cost

        return costs, self.q2(total)

    def _calculate_total_production_volume(
            self,
            production_data: Dict[int, Dict],
            calculation_date: date
    ) -> Dict[int, Decimal]:
        """
        Рассчитывает общий объем производства по всем товарам.
        Нужен для умного распределения накладных расходов.
        """
        volume_by_product = {}

        for product_id, prod_data in production_data.items():
            try:
                product = Product.objects.get(id=product_id, is_active=True)
                quantity = self._resolve_production_quantity(product, prod_data, calculation_date)
                if quantity > 0:
                    volume_by_product[product_id] = quantity
            except Product.DoesNotExist:
                continue

        return volume_by_product

    def _resolve_production_quantity(
            self,
            product: Product,
            prod_data: Dict,
            calculation_date: date
    ) -> Decimal:
        """
        Определяет количество произведенного товара.

        Способы:
        1. Прямой ввод количества
        2. Расчет от объема "Сюзерена" (главного ингредиента) через BOM
        3. Расчет от объема "Сюзерена" через ProductExpense (старая система)
        """
        # Способ 1: прямой ввод
        if prod_data.get('quantity') is not None:
            return self.q3(prod_data['quantity'])

        # Способ 2: через Сюзерена в BOM системе
        suzerain_input = prod_data.get('suzerain_input')
        if suzerain_input is not None:
            # Сначала пробуем BOM систему
            bom_result = self._calculate_from_bom_suzerain(product, suzerain_input)
            if bom_result > 0:
                return bom_result

            # Если не получилось через BOM, используем старую систему
            return self._calculate_from_productexpense_suzerain(product, suzerain_input)

        return Decimal('0')

    def _calculate_from_bom_suzerain(self, product: Product, suzerain_amount: Decimal) -> Decimal:
        """
        Расчет количества продукции от объема Сюзерена через BOM систему.

        Пример: 105 кг фарша → 1100 шт пельменей
        Если в BOM указано 0.095 кг фарша на 1 шт пельменей
        Результат: 105 / 0.095 = 1105 шт
        """
        if not hasattr(product, 'bom_specification') or not product.bom_specification.is_active:
            return Decimal('0')

        bom = product.bom_specification
        suzerain_line = bom.lines.filter(is_primary=True).first()

        if not suzerain_line or suzerain_line.quantity <= 0:
            return Decimal('0')

        # produced = suzerain_amount / quantity_per_unit
        produced = self.q3(suzerain_amount / suzerain_line.quantity)
        return produced

    def _calculate_from_productexpense_suzerain(self, product: Product, suzerain_amount: Decimal) -> Decimal:
        """
        Расчет количества продукции от объема Сюзерена через старую ProductExpense систему.
        """
        suzerain_link = ProductExpense.objects.filter(
            product=product,
            expense__status=Expense.ExpenseStatus.SUZERAIN,
            expense__type=Expense.ExpenseType.PHYSICAL,
            is_active=True
        ).select_related('expense').first()

        if not suzerain_link or suzerain_link.ratio_per_product_unit <= 0:
            return Decimal('0')

        # produced = suzerain_amount / ratio_per_unit
        produced = self.q3(suzerain_amount / suzerain_link.ratio_per_product_unit)
        return produced

    def _calculate_physical_costs(
            self,
            product: Product,
            produced_qty: Decimal,
            calculation_date: date
    ) -> Tuple[List[PhysicalCostItem], Decimal]:
        """
        Расчет физических расходов через ProductExpense систему.
        Использует актуальные цены на день расчета.
        """
        physical_links = ProductExpense.objects.filter(
            product=product,
            expense__type=Expense.ExpenseType.PHYSICAL,
            expense__is_active=True,
            is_active=True
        ).select_related('expense')

        costs = []
        total = Decimal('0')

        for link in physical_links:
            expense = link.expense

            # Получаем актуальную цену на день
            actual_price = self._get_actual_expense_price(expense, calculation_date)
            if actual_price is None or actual_price <= 0:
                continue

            # Количество расхода на весь объем производства
            consumed_qty = self.q3(produced_qty * link.ratio_per_product_unit)
            total_cost = self.q2(consumed_qty * actual_price)

            cost_item = PhysicalCostItem(
                expense_id=expense.id,
                name=expense.name,
                unit=expense.unit or 'шт',
                quantity_per_product=link.ratio_per_product_unit,
                consumed_quantity=consumed_qty,
                unit_price=actual_price,
                total_cost=total_cost
            )

            costs.append(cost_item)
            total += total_cost

        return costs, self.q2(total)

    def _get_actual_expense_price(self, expense: Expense, calculation_date: date) -> Optional[Decimal]:
        """
        Получает актуальную цену расхода на дату.

        Порядок поиска:
        1. Цена из дневного лога (actual_price_per_unit)
        2. Базовая цена из модели Expense
        """
        # Ищем дневной лог с актуальной ценой
        daily_log = DailyExpenseLog.objects.filter(
            expense=expense,
            date=calculation_date
        ).first()

        if daily_log and daily_log.actual_price_per_unit:
            return daily_log.actual_price_per_unit

        # Возвращаем базовую цену
        return expense.price_per_unit

    def _calculate_overhead_costs(
            self,
            product: Product,
            produced_qty: Decimal,
            total_production_volume: Dict[int, Decimal],
            calculation_date: date
    ) -> Tuple[List[OverheadCostItem], Decimal]:
        """
        Умное распределение накладных расходов по объему производства.

        Логика: популярный товар несет большую долю накладных расходов.
        """
        # Общий объем производства за день
        total_volume = sum(total_production_volume.values())
        if total_volume <= 0:
            return [], Decimal('0')

        # Доля текущего товара в общем объеме
        product_share = produced_qty / total_volume

        # Собираем накладные расходы за день
        overhead_costs = []
        total_overhead = Decimal('0')

        # Получаем все накладные расходы с дневными бюджетами
        daily_overheads = self._get_daily_overhead_budget(calculation_date)

        for expense_id, daily_budget in daily_overheads.items():
            try:
                expense = Expense.objects.get(id=expense_id, is_active=True)

                # Распределяем пропорционально объему производства
                allocated_cost = self.q2(daily_budget * product_share)

                overhead_item = OverheadCostItem(
                    expense_id=expense.id,
                    name=expense.name,
                    daily_budget=daily_budget,
                    product_share=product_share,
                    allocated_cost=allocated_cost
                )

                overhead_costs.append(overhead_item)
                total_overhead += allocated_cost

            except Expense.DoesNotExist:
                continue

        return overhead_costs, self.q2(total_overhead)

    def _get_daily_overhead_budget(self, calculation_date: date) -> Dict[int, Decimal]:
        """
        Получает дневной бюджет накладных расходов.

        Логика:
        1. Ищем фактические суммы в DailyExpenseLog
        2. Если нет - берем плановые из месячного бюджета / 30 дней
        """
        overhead_budget = {}

        # 1. Фактические расходы из дневных логов
        daily_logs = DailyExpenseLog.objects.filter(
            date=calculation_date,
            expense__type=Expense.ExpenseType.OVERHEAD,
            expense__is_active=True
        ).select_related('expense')

        logged_expense_ids = set()
        for log in daily_logs:
            if log.daily_amount and log.daily_amount > 0:
                overhead_budget[log.expense.id] = log.daily_amount
                logged_expense_ids.add(log.expense.id)

        # 2. Плановые расходы из месячного бюджета (для тех, что не в логах)
        year = calculation_date.year
        month = calculation_date.month

        monthly_budgets = MonthlyOverheadBudget.objects.filter(
            year=year,
            month=month,
            expense__is_active=True
        ).exclude(
            expense_id__in=logged_expense_ids
        ).select_related('expense')

        for budget in monthly_budgets:
            # Делим месячный бюджет на 30 дней
            daily_amount = self.q2(budget.planned_amount / 30)
            overhead_budget[budget.expense.id] = daily_amount

        return overhead_budget

    @transaction.atomic
    def save_production_batch(self, breakdown: CostBreakdown) -> ProductionBatch:
        """
        Сохраняет результат расчета в ProductionBatch.
        """
        product = Product.objects.get(id=breakdown.product_id)

        # Формируем детальную разбивку для JSON
        cost_breakdown_json = {
            'physical_costs': [
                {
                    'expense_id': item.expense_id,
                    'name': item.name,
                    'unit': item.unit,
                    'quantity_per_product': float(item.quantity_per_product),
                    'consumed_quantity': float(item.consumed_quantity),
                    'unit_price': float(item.unit_price),
                    'total_cost': float(item.total_cost)
                }
                for item in breakdown.physical_costs
            ],
            'component_