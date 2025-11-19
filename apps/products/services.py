from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, F, Value
from django.core.exceptions import ValidationError
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    Product, Expense, ProductExpenseRelation,
    ProductionRecord, ProductionItem, MechanicalExpenseEntry,
    StoreProductCounter, BonusHistory
)


class CostCalculator:
    """Сервис расчёта себестоимости товаров — полностью соответствует ТЗ 4.1"""

    @staticmethod
    @transaction.atomic
    def calculate_production_item(production_item: "ProductionItem") -> None:
        """
        Основной метод расчёта себестоимости одной позиции производства.
        """
        record = production_item.record
        product = production_item.product
        quantity_produced = production_item.quantity_produced or Decimal('0')

        # 1. Определяем количество (если от Сюзерена — пересчитываем)
        if production_item.suzerain_amount and production_item.suzerain_amount > 0:
            calculated_qty = CostCalculator._calculate_quantity_from_suzerain(
                product, production_item.suzerain_amount
            )
            if calculated_qty > 0:
                quantity_produced = calculated_qty
                production_item.quantity_produced = quantity_produced

        if quantity_produced <= 0:
            production_item.cost_price = Decimal('0')
            production_item.total_cost = Decimal('0')
            production_item.net_profit = Decimal('0')
            production_item.save(update_fields=[
                'cost_price', 'total_cost', 'net_profit',
                'ingredient_cost', 'overhead_cost', 'revenue'
            ])
            return

        # 2. Физические расходы (ингредиенты)
        ingredient_cost = CostCalculator._calculate_ingredient_cost(product, quantity_produced)

        # 3. Накладные расходы — умная наценка по популярности
        overhead_cost = CostCalculator._calculate_overhead_cost(record, product, quantity_produced)

        # 4. Итоги
        total_cost = (ingredient_cost + overhead_cost).quantize(Decimal('0.01'))
        cost_price = (total_cost / quantity_produced).quantize(Decimal('0.01'))
        revenue = (product.price * quantity_produced).quantize(Decimal('0.01'))
        net_profit = (revenue - total_cost).quantize(Decimal('0.01'))

        # Сохраняем всё одним запросом
        production_item.ingredient_cost = ingredient_cost
        production_item.overhead_cost = overhead_cost
        production_item.total_cost = total_cost
        production_item.cost_price = cost_price
        production_item.revenue = revenue
        production_item.net_profit = net_profit
        production_item.save()

    # ===================================================================
    # Вспомогательные методы
    # ===================================================================

    @staticmethod
    def _calculate_quantity_from_suzerain(product: "Product", suzerain_amount: Decimal) -> Decimal:
        """Расчёт количества из объёма Сюзерена (например, 2 кг фарша → сколько пельменей)"""
        relations = product.expense_relations.filter(expense__status='suzerain')
        if not relations.exists():
            return Decimal('0')

        rel = relations.first()
        if rel.proportion <= 0:
            return Decimal('0')

        return (suzerain_amount / rel.proportion).quantize(Decimal('0.001'))

    @staticmethod
    def _calculate_ingredient_cost(product: "Product", quantity: Decimal) -> Decimal:
        """Физические расходы (ингредиенты)"""
        cost = Decimal('0')
        for rel in product.expense_relations.filter(expense__expense_type='physical'):
            if rel.expense.price_per_unit:
                cost += rel.expense.price_per_unit * rel.proportion * quantity
        return cost.quantize(Decimal('0.01'))

    @staticmethod
    def _get_daily_overhead_total(record: "ProductionRecord") -> Decimal:
        """Единая точка расчёта всех накладных расходов за день (авто + мех)"""
        from .models import Expense, MechanicalExpenseEntry

        # Автоматические (ежемесячные / 30)
        auto_total = Expense.objects.filter(
            expense_type='overhead',
            state='automatic',
            is_active=True
        ).aggregate(
            total=Coalesce(Sum(F('monthly_amount') / Value(30)), Decimal('0'))
        )['total']

        # Механические (из записей)
        mech_total = MechanicalExpenseEntry.objects.filter(
            record=record,
            expense__expense_type='overhead',
            expense__is_active=True
        ).aggregate(
            total=Coalesce(Sum('amount_spent'), Decimal('0'))
        )['total']

        return (auto_total + mech_total).quantize(Decimal('0.01'))

    @staticmethod
    def _calculate_overhead_cost(record: "ProductionRecord", product: "Product", quantity: Decimal) -> Decimal:
        """
        УМНАЯ НАЦЕНКА — ТЗ 4.1.4
        Накладные расходы распределяются пропорционально (количество × popularity_weight)
        """
        if quantity <= 0:
            return Decimal('0')

        # Все позиции за день
        items = record.items.select_related('product').only('quantity_produced', 'product__popularity_weight')

        total_weighted_qty = Decimal('0')
        for item in items:
            if item.quantity_produced > 0:
                weight = item.product.popularity_weight or Decimal('1.0')
                total_weighted_qty += item.quantity_produced * weight

        if total_weighted_qty <= 0:
            return Decimal('0')

        product_weight = product.popularity_weight or Decimal('1.0')
        share = (quantity * product_weight) / total_weighted_qty

        daily_overhead = CostCalculator._get_daily_overhead_total(record)
        return (daily_overhead * share).quantize(Decimal('0.01'))

    @staticmethod
    def recalculate_all_items(record: "ProductionRecord") -> None:
        """Пересчитать себестоимость всех позиций в записи (после изменения популярности/расходов)"""
        items = ProductionItem.objects.filter(record=record).select_related('product', 'record')
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