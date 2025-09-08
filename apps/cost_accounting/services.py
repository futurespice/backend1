from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple, NamedTuple
from datetime import date
from django.db import transaction
from django.db.models import Sum, Q
import logging

from .models import (
    Expense, ProductExpense, DailyExpenseLog,
    ProductionBatch, MonthlyOverheadBudget, BillOfMaterial, BOMLine
)
from products.models import Product

logger = logging.getLogger(__name__)


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


class ProductRecipeManager:
    """
    НОВЫЙ КЛАСС: Управление рецептами продуктов (BOM).

    Примеры использования:
    - Пельмени = Тесто + Фарш + Специи
    - Булочки = Мука + Молоко + Дрожжи
    - Тесто = Мука + Яйца + Соль
    """

    @staticmethod
    def get_product_recipe(product: Product) -> Optional[BillOfMaterial]:
        """Получает активную спецификацию продукта"""
        return BillOfMaterial.objects.filter(
            product=product,
            is_active=True
        ).prefetch_related(
            'lines__expense',
            'lines__component_product'
        ).first()

    @staticmethod
    def validate_recipe(bom: BillOfMaterial) -> List[str]:
        """Валидация корректности рецепта"""
        errors = []

        # Проверяем наличие компонентов
        if not bom.lines.exists():
            errors.append("Рецепт не содержит компонентов")

        # Проверяем, что есть только один Сюзерен
        suzerain_count = bom.lines.filter(is_primary=True).count()
        if suzerain_count > 1:
            errors.append("Может быть только один главный компонент (Сюзерен)")

        # Проверяем активность компонентов-продуктов
        for line in bom.lines.filter(component_product__isnull=False):
            if not line.component_product.is_active:
                errors.append(f"Компонент '{line.component_product.name}' неактивен")

        return errors

    def create_recipe_from_template(self, product: Product, template_data: Dict) -> BillOfMaterial:
        """
        Создает рецепт по шаблону

        template_data = {
            'components': [
                {'type': 'product', 'id': 2, 'quantity': 1.0, 'unit': 'шт', 'is_primary': True},  # тесто
                {'type': 'expense', 'id': 5, 'quantity': 0.5, 'unit': 'кг'},  # фарш
                {'type': 'expense', 'id': 7, 'quantity': 0.02, 'unit': 'кг'}, # специи
            ]
        }
        """
        with transaction.atomic():
            # Создаем BOM
            bom = BillOfMaterial.objects.create(
                product=product,
                version="1.0",
                is_active=True
            )

            # Добавляем компоненты
            for idx, component in enumerate(template_data.get('components', [])):
                line_data = {
                    'bom': bom,
                    'quantity': Decimal(str(component['quantity'])),
                    'unit': component.get('unit', 'шт'),
                    'is_primary': component.get('is_primary', False),
                    'order': idx
                }

                if component['type'] == 'product':
                    # Компонент - другой продукт
                    component_product = Product.objects.get(id=component['id'])
                    line_data['component_product'] = component_product

                elif component['type'] == 'expense':
                    # Компонент - расход/ингредиент
                    expense = Expense.objects.get(id=component['id'])
                    line_data['expense'] = expense

                BOMLine.objects.create(**line_data)

            return bom


class CostCalculationService:
    """
    РАСШИРЕННЫЙ СЕРВИС: Добавлена поддержка BOM для создания продуктов из продуктов.

    Пример: Пельмени состоят из Теста (продукт) + Фарша (расход)
    """

    def __init__(self):
        self.recipe_manager = ProductRecipeManager()

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
        РАСШИРЕННЫЙ МЕТОД: Главный метод расчета себестоимости с поддержкой BOM.

        Пример production_data:
        {
            1: {'quantity': 1100, 'suzerain_input': None},  # пельмени (из теста + фарша)
            2: {'quantity': 440, 'suzerain_input': None},   # тесто (из муки + яиц)
            3: {'quantity': None, 'suzerain_input': 105}    # через объем фарша
        }
        """
        if calculation_date is None:
            calculation_date = date.today()

        results = []

        try:
            # 1. Собираем все продукты и их объемы производства
            total_production_volume = self._calculate_total_production_volume(
                production_data, calculation_date
            )

            # 2. Сортируем продукты по зависимостям (сначала базовые, потом составные)
            sorted_products = self._sort_products_by_dependencies(list(production_data.keys()))

            for product_id in sorted_products:
                prod_data = production_data[product_id]

                try:
                    product = Product.objects.get(id=product_id, is_active=True)

                    # 3. Определяем количество произведенного товара
                    produced_qty = self._resolve_production_quantity(
                        product, prod_data, calculation_date
                    )

                    if produced_qty <= 0:
                        logger.warning(f"Пропущен продукт {product_id}: нулевое количество")
                        continue

                    # 4. НОВОЕ: Рассчитываем стоимость компонентов-продуктов через BOM
                    component_costs, total_components = self._calculate_bom_component_costs(
                        product, produced_qty, calculation_date, results  # Передаем уже рассчитанные продукты
                    )

                    # 5. Рассчитываем физические расходы (традиционная система)
                    physical_costs, total_physical = self._calculate_physical_costs(
                        product, produced_qty, calculation_date
                    )

                    # 6. Рассчитываем накладные расходы с умным распределением
                    overhead_costs, total_overhead = self._calculate_overhead_costs(
                        product, produced_qty, total_production_volume, calculation_date
                    )

                    # 7. Итоговые расчеты
                    total_cost = self.q2(total_physical + total_components + total_overhead)

                    # Защита от деления на ноль
                    if produced_qty > 0:
                        cost_per_unit = self.q3(total_cost / produced_qty)
                    else:
                        cost_per_unit = Decimal('0')
                        logger.error(f"Деление на ноль для продукта {product_id}")

                    # 8. Создаем разбивку
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
                    logger.info(f"Рассчитана себестоимость для {product.name}: {cost_per_unit}")

                except Product.DoesNotExist:
                    logger.error(f"Продукт с ID {product_id} не найден")
                    continue
                except Exception as e:
                    logger.error(f"Ошибка расчета для продукта {product_id}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Критическая ошибка в расчете себестоимости: {str(e)}")
            raise

        return results

    def _sort_products_by_dependencies(self, product_ids: List[int]) -> List[int]:
        """
        НОВЫЙ МЕТОД: Сортирует продукты по зависимостям.

        Сначала рассчитываются базовые продукты (тесто, фарш),
        потом составные (пельмени из теста и фарша).
        """
        # Простая реализация: сначала продукты без BOM, потом с BOM
        products_with_bom = []
        products_without_bom = []

        for product_id in product_ids:
            try:
                product = Product.objects.get(id=product_id)
                bom = self.recipe_manager.get_product_recipe(product)

                if bom and bom.lines.filter(component_product__isnull=False).exists():
                    # Продукт состоит из других продуктов
                    products_with_bom.append(product_id)
                else:
                    # Простой продукт или только из расходов
                    products_without_bom.append(product_id)

            except Product.DoesNotExist:
                products_without_bom.append(product_id)

        # Возвращаем сначала простые, потом сложные
        return products_without_bom + products_with_bom

    def _calculate_total_production_volume(
            self,
            production_data: Dict[int, Dict],
            calculation_date: date
    ) -> Dict[int, Decimal]:
        """
        Рассчитывает общий объем производства для распределения накладных.
        """
        volume = {}

        for product_id, prod_data in production_data.items():
            try:
                product = Product.objects.get(id=product_id, is_active=True)
                produced_qty = self._resolve_production_quantity(
                    product, prod_data, calculation_date
                )
                if produced_qty > 0:
                    volume[product_id] = produced_qty
            except Product.DoesNotExist:
                continue

        return volume

    def _resolve_production_quantity(
            self,
            product: Product,
            prod_data: Dict,
            calculation_date: date
    ) -> Decimal:
        """
        Определяет количество произведенного товара.

        Логика:
        1. Если указано quantity - используем его
        2. Если указан suzerain_input - рассчитываем через Сюзерена
        3. Иначе - 0
        """
        # Прямое указание количества
        if prod_data.get('quantity'):
            return self.q3(Decimal(str(prod_data['quantity'])))

        # Расчет через Сюзерена
        suzerain_input = prod_data.get('suzerain_input')
        if suzerain_input:
            return self._calculate_quantity_from_suzerain(
                product, Decimal(str(suzerain_input)), calculation_date
            )

        return Decimal('0')

    def _calculate_quantity_from_suzerain(
            self,
            product: Product,
            suzerain_amount: Decimal,
            calculation_date: date
    ) -> Decimal:
        """
        Рассчитывает количество товара через объем Сюзерена.

        Пример: 105 кг фарша → сколько пельменей
        """
        try:
            # Сначала ищем Сюзерена в BOM спецификации
            bom = self.recipe_manager.get_product_recipe(product)
            if bom:
                suzerain_line = bom.lines.filter(is_primary=True).first()
                if suzerain_line:
                    if suzerain_line.component_product:
                        # Сюзерен - другой продукт
                        logger.info(f"Сюзерен для {product.name} - продукт {suzerain_line.component_product.name}")
                        # Логика расчета через продукт-компонент
                        if suzerain_line.quantity > 0:
                            return self.q3(suzerain_amount / suzerain_line.quantity)
                    elif suzerain_line.expense:
                        # Сюзерен - расход/ингредиент
                        if suzerain_line.quantity > 0:
                            return self.q3(suzerain_amount / suzerain_line.quantity)

            # Если не нашли в BOM, ищем в старой системе ProductExpense
            suzerain_link = ProductExpense.objects.filter(
                product=product,
                expense__status=Expense.ExpenseStatus.SUZERAIN,
                expense__is_active=True,
                is_active=True
            ).first()

            if not suzerain_link:
                logger.warning(f"Сюзерен не найден для продукта {product.name}")
                return Decimal('0')

            # Рассчитываем: если на 1 единицу товара нужно X кг фарша,
            # то из Y кг фарша получится Y/X единиц товара
            if suzerain_link.ratio_per_product_unit > 0:
                calculated_qty = suzerain_amount / suzerain_link.ratio_per_product_unit
                return self.q3(calculated_qty)
            else:
                logger.error(f"Некорректное соотношение Сюзерена для {product.name}")
                return Decimal('0')

        except Exception as e:
            logger.error(f"Ошибка расчета через Сюзерена для {product.name}: {str(e)}")
            return Decimal('0')

    def _calculate_bom_component_costs(
            self,
            product: Product,
            produced_qty: Decimal,
            calculation_date: date,
            previous_results: List[CostBreakdown] = None
    ) -> Tuple[List[ComponentCostItem], Decimal]:
        """
        РАСШИРЕННЫЙ МЕТОД: Расчет стоимости компонентов-продуктов через BOM систему.

        Поддерживает:
        1. Компоненты-расходы (мука, соль) - берем цену из Expense
        2. Компоненты-продукты (тесто) - берем себестоимость из уже рассчитанных или из базы

        Пример: Пельмени = 1 шт Теста (продукт) + 0.5 кг Фарша (расход)
        """
        try:
            # Получаем BOM спецификацию
            bom = self.recipe_manager.get_product_recipe(product)
            if not bom:
                return [], Decimal('0')

            # Валидируем рецепт
            validation_errors = self.recipe_manager.validate_recipe(bom)
            if validation_errors:
                logger.warning(f"Ошибки в рецепте {product.name}: {validation_errors}")

            costs = []
            total = Decimal('0')
            previous_results = previous_results or []

            # Обрабатываем каждую строку BOM
            for line in bom.lines.all():

                # Случай 1: Компонент - другой продукт (тесто, полуфабрикат)
                if line.component_product:
                    component_cost_item, component_cost = self._calculate_product_component_cost(
                        line, produced_qty, calculation_date, previous_results
                    )
                    if component_cost_item:
                        costs.append(component_cost_item)
                        total += component_cost

                # Случай 2: Компонент - расход/ингредиент (мука, соль)
                elif line.expense:
                    expense_cost_item, expense_cost = self._calculate_expense_component_cost(
                        line, produced_qty, calculation_date
                    )
                    if expense_cost_item:
                        costs.append(expense_cost_item)
                        total += expense_cost

            return costs, self.q2(total)

        except Exception as e:
            logger.error(f"Ошибка расчета BOM компонентов для {product.name}: {str(e)}")
            return [], Decimal('0')

    def _calculate_product_component_cost(
            self,
            bom_line: BOMLine,
            produced_qty: Decimal,
            calculation_date: date,
            previous_results: List[CostBreakdown]
    ) -> Tuple[Optional[ComponentCostItem], Decimal]:
        """
        НОВЫЙ МЕТОД: Рассчитывает стоимость компонента-продукта.

        Пример: Для пельменей нужно 1 шт теста на 1 пельмень.
        Ищем себестоимость теста из уже рассчитанных или из базы.
        """
        component = bom_line.component_product

        if not component or not component.is_active:
            logger.warning(f"Компонент-продукт {component} неактивен")
            return None, Decimal('0')

        # Количество компонента на весь объем производства
        consumed_qty = self.q3(produced_qty * bom_line.quantity)

        # Ищем себестоимость компонента
        unit_cost = self._get_component_product_cost(
            component, calculation_date, previous_results
        )

        if unit_cost <= 0:
            logger.warning(f"Не найдена себестоимость для компонента {component.name}")
            # Используем базовую цену продукта как fallback
            unit_cost = component.price

        total_cost = self.q2(consumed_qty * unit_cost)

        cost_item = ComponentCostItem(
            component_product_id=component.id,
            name=f"{component.name} (продукт)",
            unit=bom_line.unit or 'шт',
            quantity_per_product=bom_line.quantity,
            consumed_quantity=consumed_qty,
            unit_price=unit_cost,
            total_cost=total_cost
        )

        return cost_item, total_cost

    def _calculate_expense_component_cost(
            self,
            bom_line: BOMLine,
            produced_qty: Decimal,
            calculation_date: date
    ) -> Tuple[Optional[ComponentCostItem], Decimal]:
        """
        НОВЫЙ МЕТОД: Рассчитывает стоимость компонента-расхода в BOM.

        Пример: Для пельменей нужно 0.5 кг фарша на 1 пельмень.
        """
        expense = bom_line.expense

        if not expense or not expense.is_active:
            logger.warning(f"Компонент-расход {expense} неактивен")
            return None, Decimal('0')

        # Количество расхода на весь объем производства
        consumed_qty = self.q3(produced_qty * bom_line.quantity)

        # Получаем актуальную цену расхода
        unit_price = self._get_actual_expense_price(expense, calculation_date)
        if not unit_price or unit_price <= 0:
            logger.warning(f"Нет цены для расхода {expense.name}")
            return None, Decimal('0')

        total_cost = self.q2(consumed_qty * unit_price)

        cost_item = ComponentCostItem(
            component_product_id=expense.id,  # Используем ID расхода
            name=f"{expense.name} (BOM)",
            unit=bom_line.unit or expense.unit or 'шт',
            quantity_per_product=bom_line.quantity,
            consumed_quantity=consumed_qty,
            unit_price=unit_price,
            total_cost=total_cost
        )

        return cost_item, total_cost

    def _get_component_product_cost(
            self,
            component: Product,
            calculation_date: date,
            previous_results: List[CostBreakdown]
    ) -> Decimal:
        """
        НОВЫЙ МЕТОД: Получает себестоимость компонента-продукта.

        Порядок поиска:
        1. Из уже рассчитанных в этой же сессии (previous_results)
        2. Из последней производственной смены
        3. Базовая цена продукта
        """
        # 1. Ищем в уже рассчитанных результатах
        for result in previous_results:
            if result.product_id == component.id:
                logger.info(f"Найдена себестоимость {component.name} в текущих расчетах: {result.cost_per_unit}")
                return result.cost_per_unit

        # 2. Ищем в последних производственных сменах
        latest_batch = ProductionBatch.objects.filter(
            product=component,
            date__lte=calculation_date
        ).order_by('-date').first()

        if latest_batch and latest_batch.cost_per_unit > 0:
            logger.info(f"Найдена себестоимость {component.name} в истории: {latest_batch.cost_per_unit}")
            return latest_batch.cost_per_unit

        # 3. Используем базовую цену продукта
        logger.info(f"Используем базовую цену для {component.name}: {component.price}")
        return component.price

    def _calculate_physical_costs(
            self,
            product: Product,
            produced_qty: Decimal,
            calculation_date: date
    ) -> Tuple[List[PhysicalCostItem], Decimal]:
        """
        Рассчитывает физические расходы (старая система ProductExpense).
        Теперь работает параллельно с BOM системой.
        """
        try:
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
                    logger.warning(f"Нет цены для расхода {expense.name}")
                    continue

                # Количество расхода на весь объем производства
                consumed_qty = self.q3(produced_qty * link.ratio_per_product_unit)
                total_cost = self.q2(consumed_qty * actual_price)

                cost_item = PhysicalCostItem(
                    expense_id=expense.id,
                    name=f"{expense.name} (физ.)",
                    unit=expense.unit or 'шт',
                    quantity_per_product=link.ratio_per_product_unit,
                    consumed_quantity=consumed_qty,
                    unit_price=actual_price,
                    total_cost=total_cost
                )

                costs.append(cost_item)
                total += total_cost

            return costs, self.q2(total)

        except Exception as e:
            logger.error(f"Ошибка расчета физических расходов для {product.name}: {str(e)}")
            return [], Decimal('0')

    def _get_actual_expense_price(self, expense: Expense, calculation_date: date) -> Optional[Decimal]:
        """
        Получает актуальную цену расхода на дату.

        Порядок поиска:
        1. Цена из дневного лога (actual_price_per_unit)
        2. Базовая цена из модели Expense
        """
        try:
            # Ищем дневной лог с актуальной ценой
            daily_log = DailyExpenseLog.objects.filter(
                expense=expense,
                date=calculation_date
            ).first()

            if daily_log and daily_log.actual_price_per_unit:
                return daily_log.actual_price_per_unit

            # Возвращаем базовую цену
            return expense.price_per_unit

        except Exception as e:
            logger.error(f"Ошибка получения цены для {expense.name}: {str(e)}")
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
        try:
            # Получаем накладные расходы для продукта
            overhead_links = ProductExpense.objects.filter(
                product=product,
                expense__type=Expense.ExpenseType.OVERHEAD,
                expense__is_active=True,
                is_active=True
            ).select_related('expense')

            if not overhead_links.exists():
                return [], Decimal('0')

            # Вычисляем общий объем производства за день
            total_volume = sum(total_production_volume.values())
            if total_volume <= 0:
                logger.warning("Нулевой общий объем производства")
                return [], Decimal('0')

            # Доля текущего продукта
            product_share = produced_qty / total_volume

            costs = []
            total = Decimal('0')

            for link in overhead_links:
                expense = link.expense

                # Получаем дневной бюджет накладного расхода
                daily_budget = self._get_daily_overhead_budget(expense, calculation_date)
                if daily_budget <= 0:
                    logger.warning(f"Нет бюджета для накладного расхода {expense.name}")
                    continue

                # Распределяем пропорционально объему производства
                allocated_cost = self.q2(daily_budget * product_share)

                cost_item = OverheadCostItem(
                    expense_id=expense.id,
                    name=expense.name,
                    daily_budget=daily_budget,
                    product_share=product_share,
                    allocated_cost=allocated_cost
                )

                costs.append(cost_item)
                total += allocated_cost

            return costs, self.q2(total)

        except Exception as e:
            logger.error(f"Ошибка расчета накладных расходов для {product.name}: {str(e)}")
            return [], Decimal('0')

    def _get_daily_overhead_budget(self, expense: Expense, calculation_date: date) -> Decimal:
        """
        Получает дневной бюджет накладного расхода.

        Логика:
        1. Ищем месячный бюджет
        2. Делим на количество дней в месяце
        3. Если нет - используем базовую цену
        """

    def _get_daily_overhead_budget(self, expense: Expense, calculation_date: date) -> Decimal:
        """
        Получает дневной бюджет накладного расхода.

        Логика:
        1. Ищем месячный бюджет
        2. Делим на количество дней в месяце
        3. Если нет - используем базовую цену
        """
        try:
            # Ищем месячный бюджет
            monthly_budget = MonthlyOverheadBudget.objects.filter(
                expense=expense,
                year=calculation_date.year,
                month=calculation_date.month
            ).first()

            if monthly_budget and monthly_budget.planned_amount > 0:
                # Получаем количество дней в месяце
                import calendar
                days_in_month = calendar.monthrange(calculation_date.year, calculation_date.month)[1]

                return self.q2(monthly_budget.planned_amount / days_in_month)

            # Используем базовую цену как дневную
            return expense.price_per_unit or Decimal('0')

        except Exception as e:
            logger.error(f"Ошибка получения дневного бюджета для {expense.name}: {str(e)}")
            return expense.price_per_unit or Decimal('0')

    @transaction.atomic
    def save_production_batch(self, breakdown: CostBreakdown) -> ProductionBatch:
        """
        Сохраняет результаты расчета в базу с транзакцией.

        Использует update_or_create для избежания дублирования.
        """
        try:
            # Подготавливаем данные для JSON
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
                'component_costs': [
                    {
                        'component_product_id': item.component_product_id,
                        'name': item.name,
                        'unit': item.unit,
                        'quantity_per_product': float(item.quantity_per_product),
                        'consumed_quantity': float(item.consumed_quantity),
                        'unit_price': float(item.unit_price),
                        'total_cost': float(item.total_cost)
                    }
                    for item in breakdown.component_costs
                ],
                'overhead_costs': [
                    {
                        'expense_id': item.expense_id,
                        'name': item.name,
                        'daily_budget': float(item.daily_budget),
                        'product_share': float(item.product_share),
                        'allocated_cost': float(item.allocated_cost)
                    }
                    for item in breakdown.overhead_costs
                ]
            }

            # Сохраняем или обновляем запись
            batch, created = ProductionBatch.objects.update_or_create(
                date=breakdown.date,
                product_id=breakdown.product_id,
                defaults={
                    'produced_quantity': breakdown.produced_quantity,
                    'physical_cost': breakdown.total_physical,
                    'overhead_cost': breakdown.total_overhead,
                    'total_cost': breakdown.total_cost,
                    'cost_per_unit': breakdown.cost_per_unit,
                    'cost_breakdown': cost_breakdown_json,
                }
            )

            action = "создана" if created else "обновлена"
            logger.info(f"Производственная смена {action}: {batch}")

            return batch

        except Exception as e:
            logger.error(f"Ошибка сохранения производственной смены: {str(e)}")
            raise


# НОВЫЙ КЛАСС: Утилиты для работы с BOM
class BOMUtilities:
    """Утилиты для работы с рецептами продуктов"""

    @staticmethod
    def create_pelmen_recipe_example():
        """
        Пример создания рецепта пельменей:
        1 пельмень = 1 шт теста + 0.5 кг фарша + 0.02 кг специй
        """
        from products.models import Product

        # Получаем продукты
        pelmen = Product.objects.get(name__icontains='пельмени')
        testo = Product.objects.get(name__icontains='тесто')

        # Получаем расходы
        farsh = Expense.objects.get(name__icontains='фарш')
        specii = Expense.objects.get(name__icontains='специи')

        recipe_manager = ProductRecipeManager()

        template_data = {
            'components': [
                {'type': 'product', 'id': testo.id, 'quantity': 1.0, 'unit': 'шт', 'is_primary': True},
                {'type': 'expense', 'id': farsh.id, 'quantity': 0.5, 'unit': 'кг'},
                {'type': 'expense', 'id': specii.id, 'quantity': 0.02, 'unit': 'кг'},
            ]
        }

        return recipe_manager.create_recipe_from_template(pelmen, template_data)

    @staticmethod
    def create_testo_recipe_example():
        """
        Пример создания рецепта теста:
        1 шт теста = 0.1 кг муки + 1 яйцо + 0.01 кг соли
        """
        from products.models import Product

        testo = Product.objects.get(name__icontains='тесто')
        muka = Expense.objects.get(name__icontains='мука')
        eggs = Expense.objects.get(name__icontains='яйца')
        salt = Expense.objects.get(name__icontains='соль')

        recipe_manager = ProductRecipeManager()

        template_data = {
            'components': [
                {'type': 'expense', 'id': muka.id, 'quantity': 0.1, 'unit': 'кг', 'is_primary': True},
                {'type': 'expense', 'id': eggs.id, 'quantity': 1, 'unit': 'шт'},
                {'type': 'expense', 'id': salt.id, 'quantity': 0.01, 'unit': 'кг'},
            ]
        }

        return recipe_manager.create_recipe_from_template(testo, template_data)