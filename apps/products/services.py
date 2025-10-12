from decimal import Decimal
from django.db.models import Sum
from .models import (
    Product, ProductionRecord, ProductionItem, Expense,
    ProductExpenseRelation, MechanicalExpenseEntry,
    StoreProductCounter, BonusHistory, ExpenseType, ExpenseState, ExpenseStatus
)


class CostCalculator:
    """Расчёт себестоимости"""

    @staticmethod
    def calculate_production_item(production_item: ProductionItem):
        """
        Расчёт по одной строке таблицы производства.
        Логика: либо вводим quantity_produced, либо suzerain_amount.
        """
        product = production_item.product
        record = production_item.record

        # Определяем количество товара
        if production_item.suzerain_amount > 0 and product.suzerain_expense:
            # Вводим объём Сюзерена (например, 105 кг фарша)
            quantity = CostCalculator._calculate_quantity_from_suzerain(
                product, production_item.suzerain_amount
            )
            production_item.quantity_produced = quantity
        else:
            # Вводим количество товара напрямую
            quantity = production_item.quantity_produced

        if quantity <= 0:
            production_item.ingredient_cost = 0
            production_item.overhead_cost = 0
            production_item.total_cost = 0
            production_item.cost_price = 0
            production_item.revenue = 0
            production_item.net_profit = 0
            production_item.save()
            return

        # 1. Физические расходы (ингредиенты)
        ingredient_cost = CostCalculator._calculate_ingredient_cost(product, quantity)

        # 2. Накладные расходы (пропорция по объёму производства)
        overhead_cost = CostCalculator._calculate_overhead_cost(record, product, quantity)

        # 3. Общие расходы
        total_cost = ingredient_cost + overhead_cost

        # 4. Себестоимость (на единицу)
        cost_price = total_cost / quantity if quantity > 0 else 0

        # 5. Доход (цена * количество)
        revenue = product.price * quantity

        # 6. Чистая прибыль
        net_profit = revenue - total_cost

        # Сохраняем
        production_item.ingredient_cost = ingredient_cost
        production_item.overhead_cost = overhead_cost
        production_item.total_cost = total_cost
        production_item.cost_price = cost_price
        production_item.revenue = revenue
        production_item.net_profit = net_profit
        production_item.save()

    @staticmethod
    def _calculate_quantity_from_suzerain(product: Product, suzerain_amount: Decimal) -> Decimal:
        """
        Вычисляем количество товара по объёму Сюзерена.
        Например: 105 кг фарша → ??? пельменей (если 1 пельмень = 10г фарша)
        """
        if not product.suzerain_expense:
            return Decimal(0)

        # Пропорция Сюзерена на 1 товар
        relation = ProductExpenseRelation.objects.filter(
            product=product,
            expense=product.suzerain_expense
        ).first()

        if not relation or relation.proportion <= 0:
            return Decimal(0)

        # suzerain_amount (кг) / proportion (г на 1 шт)
        # Переводим кг в граммы
        suzerain_grams = suzerain_amount * 1000
        quantity = suzerain_grams / relation.proportion

        return quantity

    @staticmethod
    def _calculate_ingredient_cost(product: Product, quantity: Decimal) -> Decimal:
        """
        Физические расходы (ингредиенты).
        Берём все связи товара с расходами, умножаем пропорцию на количество.
        """
        relations = ProductExpenseRelation.objects.filter(
            product=product,
            expense__expense_type=ExpenseType.PHYSICAL,
            expense__is_active=True
        ).select_related('expense')

        total_cost = Decimal(0)

        for rel in relations:
            expense = rel.expense
            proportion = rel.proportion  # Например, 10 г фарша на 1 пельмень

            # Сколько всего израсходовано (в граммах)
            total_used_grams = proportion * quantity

            # Стоимость
            if expense.unit == 'kg':
                # Цена за кг, переводим граммы в кг
                total_used_kg = total_used_grams / 1000
                cost = total_used_kg * expense.price_per_unit
            elif expense.unit == 'gram':
                cost = total_used_grams * expense.price_per_unit
            else:  # piece
                cost = quantity * expense.price_per_unit

            total_cost += cost

        return total_cost

    @staticmethod
    def _calculate_overhead_cost(record: ProductionRecord, product: Product, quantity: Decimal) -> Decimal:
        """
        Накладные расходы (аренда, свет, зарплата и т.д.).
        Распределяются пропорционально объёму производства.
        """
        # Все товары в этом ProductionRecord
        all_items = ProductionItem.objects.filter(record=record)

        total_production = Decimal(0)
        for item in all_items:
            total_production += item.quantity_produced

        if total_production <= 0:
            return Decimal(0)

        # Доля этого товара
        share = quantity / total_production

        # Все накладные расходы
        overhead_expenses = Expense.objects.filter(
            expense_type=ExpenseType.OVERHEAD,
            is_active=True
        )

        daily_overhead = Decimal(0)

        for expense in overhead_expenses:
            if expense.state == ExpenseState.MECHANICAL:
                # Механический учёт (берём из MechanicalExpenseEntry)
                entry = MechanicalExpenseEntry.objects.filter(
                    record=record,
                    expense=expense
                ).first()

                if entry:
                    daily_overhead += entry.amount_spent
            else:
                # Автоматический (месячную сумму делим на 30)
                daily_overhead += expense.monthly_amount / 30

        # Доля этого товара
        overhead_cost = daily_overhead * share

        return overhead_cost

    @staticmethod
    def recalculate_all_items(record: ProductionRecord):
        """Пересчитать все строки в таблице"""
        items = ProductionItem.objects.filter(record=record)
        for item in items:
            CostCalculator.calculate_production_item(item)


class BonusService:
    """Система бонусов: каждый 21-й товар бесплатно"""

    @staticmethod
    def add_product_to_counter(store, partner, product, quantity: int):
        """
        Добавляем товары в счётчик.
        Возвращает количество бонусов.
        """
        if not product.is_bonus:
            return 0

        counter, _ = StoreProductCounter.objects.get_or_create(
            store=store,
            partner=partner,
            product=product,
            defaults={'total_count': 0, 'bonus_eligible_count': 0}
        )

        counter.total_count += quantity
        counter.bonus_eligible_count += quantity

        # Сколько бонусов
        bonus_count = counter.bonus_eligible_count // 21

        if bonus_count > 0:
            # Обнуляем счётчик
            counter.bonus_eligible_count = counter.bonus_eligible_count % 21

            # Записываем историю
            BonusHistory.objects.create(
                partner=partner,
                store=store,
                product=product,
                bonus_count=bonus_count
            )

        counter.save()

        return bonus_count

    @staticmethod
    def get_bonus_progress(store, partner, product):
        """Прогресс до бонуса (0-20)"""
        counter = StoreProductCounter.objects.filter(
            store=store,
            partner=partner,
            product=product
        ).first()

        if not counter:
            return 0

        return counter.bonus_eligible_count

from decimal import Decimal
from django.db.models import Sum
from .models import (
    Product, ProductionRecord, ProductionItem, Expense,
    ProductExpenseRelation, MechanicalExpenseEntry,
    StoreProductCounter, BonusHistory, ExpenseType, ExpenseState, ExpenseStatus, DefectiveProduct
)


class CostCalculator:
    """Расчёт себестоимости"""

    @staticmethod
    def calculate_production_item(production_item: ProductionItem):
        """
        Расчёт по одной строке таблицы производства.
        Логика: либо вводим quantity_produced, либо suzerain_amount.
        """
        product = production_item.product
        record = production_item.record

        # Определяем количество товара
        if production_item.suzerain_amount > 0 and product.suzerain_expense:
            # Вводим объём Сюзерена (например, 105 кг фарша)
            quantity = CostCalculator._calculate_quantity_from_suzerain(
                product, production_item.suzerain_amount
            )
            production_item.quantity_produced = quantity
        else:
            # Вводим количество товара напрямую
            quantity = production_item.quantity_produced

        if quantity <= 0:
            production_item.ingredient_cost = 0
            production_item.overhead_cost = 0
            production_item.total_cost = 0
            production_item.cost_price = 0
            production_item.revenue = 0
            production_item.net_profit = 0
            production_item.save()
            return

        # 1. Физические расходы (ингредиенты)
        ingredient_cost = CostCalculator._calculate_ingredient_cost(product, quantity)

        # 2. Накладные расходы (пропорция по объёму производства)
        overhead_cost = CostCalculator._calculate_overhead_cost(record, product, quantity)

        # 3. Общие расходы
        total_cost = ingredient_cost + overhead_cost

        # 4. Себестоимость (на единицу)
        cost_price = total_cost / quantity if quantity > 0 else 0

        # 5. Доход (цена * количество)
        revenue = product.price * quantity

        # 6. Чистая прибыль
        net_profit = revenue - total_cost

        # Сохраняем
        production_item.ingredient_cost = ingredient_cost
        production_item.overhead_cost = overhead_cost
        production_item.total_cost = total_cost
        production_item.cost_price = cost_price
        production_item.revenue = revenue
        production_item.net_profit = net_profit
        production_item.save()

    @staticmethod
    def _calculate_quantity_from_suzerain(product, suzerain_amount):
        """Количество товаров из объёма Сюзерена"""
        suzerain_rel = ProductExpenseRelation.objects.filter(
            product=product, expense=product.suzerain_expense
        ).first()
        if suzerain_rel and suzerain_rel.proportion > 0:
            return suzerain_amount / suzerain_rel.proportion
        return 0

    @staticmethod
    def _calculate_ingredient_cost(product, quantity):
        """Расчёт физических расходов"""
        cost = Decimal(0)
        for rel in product.expense_relations.all():
            if rel.expense.expense_type == ExpenseType.PHYSICAL:
                unit_cost = rel.expense.price_per_unit or 0
                cost += unit_cost * rel.proportion * quantity
        return cost

    @staticmethod
    def _calculate_overhead_cost(record, product, quantity):
        """Расчёт накладных расходов (пропорционально)"""
        # Общий объём производства за день
        total_day_quantity = ProductionItem.objects.filter(record=record).aggregate(
            Sum('quantity_produced')
        )['quantity_produced__sum'] or Decimal(1)  # Избежать /0

        # Доля этого товара
        share = quantity / total_day_quantity

        # Накладные расходы
        overhead_expenses = Expense.objects.filter(
            expense_type=ExpenseType.OVERHEAD,
            is_active=True
        )

        daily_overhead = Decimal(0)

        for expense in overhead_expenses:
            if expense.state == ExpenseState.MECHANICAL:
                # Механический учёт (берём из MechanicalExpenseEntry)
                entry = MechanicalExpenseEntry.objects.filter(
                    record=record,
                    expense=expense
                ).first()

                if entry:
                    daily_overhead += entry.amount_spent
            else:
                # Автоматический (месячную сумму делим на 30)
                daily_overhead += expense.monthly_amount / 30

        # Доля этого товара
        overhead_cost = daily_overhead * share

        return overhead_cost

    @staticmethod
    def recalculate_all_items(record: ProductionRecord):
        """Пересчитать все строки в таблице"""
        items = ProductionItem.objects.filter(record=record)
        for item in items:
            CostCalculator.calculate_production_item(item)


class BonusService:
    """Система бонусов: каждый 21-й товар бесплатно"""

    @staticmethod
    def add_product_to_counter(store, partner, product, quantity: int):
        """
        Добавляем товары в счётчик.
        Возвращает количество бонусов.
        """
        if not product.is_bonus or product.category == 'weight':
            return 0  # По ТЗ не для весовых

        counter, _ = StoreProductCounter.objects.get_or_create(
            store=store,
            partner=partner,
            product=product,
            defaults={'total_count': 0, 'bonus_eligible_count': 0}
        )

        counter.total_count += quantity
        counter.bonus_eligible_count += quantity

        # Сколько бонусов
        bonus_count = counter.bonus_eligible_count // 21

        if bonus_count > 0:
            # Обнуляем счётчик
            counter.bonus_eligible_count = counter.bonus_eligible_count % 21

            # Записываем историю
            BonusHistory.objects.create(
                partner=partner,
                store=store,
                product=product,
                bonus_count=bonus_count
            )

        counter.save()

        return bonus_count

    @staticmethod
    def get_bonus_progress(store, partner, product):
        """Прогресс до бонуса (0-20)"""
        counter = StoreProductCounter.objects.filter(
            store=store,
            partner=partner,
            product=product
        ).first()

        if not counter:
            return 0

        return counter.bonus_eligible_count


class DefectiveProductService:
    """Сервис для работы с бракованными товарами"""

    @staticmethod
    def add_defective(partner, product, quantity: Decimal, amount: Decimal = Decimal('0'), reason=''):
        """
        Зафиксировать брак товара партнером.
        Автоматически рассчитывает сумму, если не указана.
        """
        if amount == Decimal('0'):
            amount = product.get_price_for_weight(quantity) if product.category == 'weight' else product.price * quantity

        defective = DefectiveProduct.objects.create(
            partner=partner,
            product=product,
            quantity=quantity,
            amount=amount,
            reason=reason
        )

        # Списываем со склада партнера
        from stores.services import InventoryService
        InventoryService.remove_from_inventory(partner=partner, product=product, quantity=quantity)

        return defective

    @staticmethod
    def get_defects(partner=None, date_from=None, date_to=None):
        """Получить список брака с фильтрами"""
        queryset = DefectiveProduct.objects.all()
        if partner:
            queryset = queryset.filter(partner=partner)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        return queryset

    @staticmethod
    def get_defect_stats(partner=None, date_from=None, date_to=None):
        """Статистика брака (кол-во, сумма)"""
        queryset = DefectiveProductService.get_defects(partner, date_from, date_to)
        stats = queryset.aggregate(
            total_count=Sum('quantity'),
            total_amount=Sum('amount')
        )
        return {
            'total_count': stats['total_count'] or 0,
            'total_amount': stats['total_amount'] or 0
        }