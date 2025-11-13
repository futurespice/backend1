from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Product, Expense, ProductExpenseRelation,
    ProductionRecord, ProductionItem, MechanicalExpenseEntry,
    StoreProductCounter, BonusHistory
)


class CostCalculator:
    """Сервис расчёта себестоимости товаров"""

    @staticmethod
    @transaction.atomic
    def calculate_production_item(production_item: ProductionItem):
        """
        Рассчитать себестоимость производственной позиции

        Логика:
        1. Ingredient_cost = физические расходы (ингредиенты)
        2. Overhead_cost = накладные расходы (пропорционально объёму)
        3. Total_cost = ingredient_cost + overhead_cost
        4. Cost_price = total_cost / quantity
        5. Revenue = price * quantity
        6. Net_profit = revenue - total_cost
        """
        record = production_item.record
        product = production_item.product

        # Определяем количество
        if production_item.suzerain_amount > 0 and product.expense_relations.exists():
            # Рассчитываем из Сюзерена
            quantity = CostCalculator._calculate_quantity_from_suzerain(
                product, production_item.suzerain_amount
            )
            production_item.quantity_produced = quantity
        else:
            quantity = production_item.quantity_produced

        if quantity <= 0:
            return

        # 1. Физические расходы (ингредиенты)
        ingredient_cost = CostCalculator._calculate_ingredient_cost(product, quantity)

        # 2. Накладные расходы (пропорция по объёму производства)
        overhead_cost = CostCalculator._calculate_overhead_cost(record, product, quantity)

        # 3. Общие расходы
        total_cost = ingredient_cost + overhead_cost

        # 4. Себестоимость (на единицу)
        cost_price = total_cost / quantity if quantity > 0 else Decimal('0')

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
        # Находим связь с Сюзереном
        suzerain_relations = product.expense_relations.filter(
            expense__status='suzerain'
        )

        if suzerain_relations.exists():
            suzerain_rel = suzerain_relations.first()
            if suzerain_rel.proportion > 0:
                return suzerain_amount / suzerain_rel.proportion

        return Decimal('0')

    @staticmethod
    def _calculate_ingredient_cost(product, quantity):
        """Расчёт физических расходов (ингредиенты)"""
        cost = Decimal('0')

        for rel in product.expense_relations.filter(expense__expense_type='physical'):
            if rel.expense.price_per_unit:
                unit_cost = rel.expense.price_per_unit
                cost += unit_cost * rel.proportion * quantity

        return cost

    @staticmethod
    def _calculate_overhead_cost(record, product, quantity):
        """
        Расчёт накладных расходов.
        Распределяются пропорционально объёму производства.
        """
        # Все товары в этом ProductionRecord
        all_items = ProductionItem.objects.filter(record=record)

        total_production = Decimal('0')
        for item in all_items:
            total_production += item.quantity_produced

        if total_production <= 0:
            return Decimal('0')

        # Доля этого товара
        share = quantity / total_production

        # Все накладные расходы
        overhead_expenses = Expense.objects.filter(
            expense_type='overhead',
            is_active=True
        )

        daily_overhead = Decimal('0')

        for expense in overhead_expenses:
            if expense.state == 'mechanical':
                # Механический учёт (берём из MechanicalExpenseEntry)
                entry = MechanicalExpenseEntry.objects.filter(
                    record=record,
                    expense=expense
                ).first()

                if entry:
                    daily_overhead += entry.amount_spent
            else:
                # Автоматический (месячную сумму делим на 30)
                if expense.monthly_amount:
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
    """
    Система бонусов: каждый 21-й товар ВСЕГО бесплатно
    Весовые товары НЕ участвуют в бонусах
    """

    @staticmethod
    @transaction.atomic
    def add_product_to_counter(store, partner, product, quantity: int):
        """
        Добавляем товары в счётчик и проверяем бонус.
        Возвращает количество бонусов.
        """
        # Весовые товары не участвуют в бонусах
        if product.is_weight_based:
            return 0

        # Получаем или создаём счётчик
        counter, _ = StoreProductCounter.objects.select_for_update().get_or_create(
            store=store,
            partner=partner,
            product=product,
            defaults={
                'total_count': 0,
                'product_count': 0
            }
        )

        # Увеличиваем счётчики
        counter.total_count += quantity
        counter.product_count += quantity
        counter.save()

        # Проверяем бонус (каждый 21-й)
        bonus_count = 0
        if counter.check_bonus():
            bonus_count = counter.total_count // 21

            # Создаём запись о бонусе
            BonusHistory.objects.create(
                store=store,
                partner=partner,
                product=product,
                quantity=bonus_count,
                bonus_value=product.price * bonus_count
            )

            # Обновляем время последнего бонуса
            counter.last_bonus_at = timezone.now()
            counter.save()

        return bonus_count

    @staticmethod
    @transaction.atomic
    def apply_bonus_to_order(order):
        """
        Применить бонусы к заказу магазина.
        Проверяет все товары в заказе и добавляет бонусные позиции.
        """
        from orders.models import StoreOrderItem  # Избегаем циклического импорта

        bonus_applied = Decimal('0')

        for item in order.items.all():
            # Весовые товары не участвуют в бонусах
            if item.product.is_weight_based:
                continue

            # Получаем счётчик
            counter = StoreProductCounter.objects.select_for_update().filter(
                store=order.store,
                partner=order.partner,
                product=item.product
            ).first()

            if counter and counter.check_bonus():
                bonus_quantity = counter.total_count // 21

                # Создаём бонусную позицию
                StoreOrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=bonus_quantity,
                    price=Decimal('0'),  # Бонус = бесплатно
                    is_bonus=True
                )

                bonus_applied += item.product.price * bonus_quantity

                # Записываем в историю
                BonusHistory.objects.create(
                    store=order.store,
                    partner=order.partner,
                    product=item.product,
                    quantity=bonus_quantity,
                    bonus_value=item.product.price * bonus_quantity,
                    order=order
                )

        order.bonus_applied = bonus_applied
        order.save()

        return bonus_applied

    @staticmethod
    def get_bonus_status(store, partner, product):
        """Получить статус бонуса для товара"""
        counter = StoreProductCounter.objects.filter(
            store=store,
            partner=partner,
            product=product
        ).first()

        if not counter:
            return {
                'total_count': 0,
                'product_count': 0,
                'next_bonus_at': 21,
                'bonus_available': False
            }

        return {
            'total_count': counter.total_count,
            'product_count': counter.product_count,
            'next_bonus_at': 21 - (counter.total_count % 21),
            'bonus_available': counter.check_bonus(),
            'last_bonus_at': counter.last_bonus_at
        }