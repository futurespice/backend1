from decimal import Decimal
from typing import Dict, List, NamedTuple
from datetime import date
from django.db import transaction

from products.models import Product


class BonusCalculation(NamedTuple):
    """Результат расчета бонусов"""
    payable_quantity: int
    bonus_quantity: int
    payable_amount: Decimal
    bonus_discount: Decimal
    final_amount: Decimal


class ProductSaleInfo(NamedTuple):
    """Информация о продаже товара с учетом бонусов"""
    product_id: int
    sold_quantity: int
    payable_quantity: int
    bonus_quantity: int
    revenue: Decimal
    bonus_discount: Decimal
    net_revenue: Decimal


class BonusIntegrationService:
    """
    Сервис интеграции бонусной системы с расчетом себестоимости.

    Учитывает влияние бонусов на:
    - Фактическую выручку
    - Прибыль/убыток
    - Рентабельность товаров
    """

    @staticmethod
    def calculate_bonus_for_quantity(product: Product, quantity: int) -> BonusCalculation:
        """
        Рассчитывает бонусы для конкретного количества товара.

        Логика из ТЗ: каждый 21-й товар бесплатно (по умолчанию).
        """
        if not product.is_bonus_eligible or product.is_weight or quantity < product.bonus_every_n:
            # Нет бонусов
            payable_qty = quantity
            bonus_qty = 0
        else:
            # Каждый N-й товар бесплатно
            bonus_qty = quantity // product.bonus_every_n
            payable_qty = quantity - bonus_qty

        payable_amount = product.price * payable_qty
        bonus_discount = product.price * bonus_qty
        final_amount = payable_amount  # итоговая сумма к оплате

        return BonusCalculation(
            payable_quantity=payable_qty,
            bonus_quantity=bonus_qty,
            payable_amount=payable_amount,
            bonus_discount=bonus_discount,
            final_amount=final_amount
        )

    @staticmethod
    def calculate_multiple_products_bonus(
            sales_data: Dict[int, int]  # {product_id: sold_quantity}
    ) -> List[ProductSaleInfo]:
        """
        Рассчитывает бонусы для множества товаров.

        Args:
            sales_data: {product_id: количество_продано}

        Returns:
            List[ProductSaleInfo]: Информация по каждому товару с бонусами
        """
        results = []

        for product_id, sold_qty in sales_data.items():
            try:
                product = Product.objects.get(id=product_id, is_active=True)

                bonus_calc = BonusIntegrationService.calculate_bonus_for_quantity(
                    product, sold_qty
                )

                # Полная выручка без учета бонусов
                full_revenue = product.price * sold_qty

                sale_info = ProductSaleInfo(
                    product_id=product.id,
                    sold_quantity=sold_qty,
                    payable_quantity=bonus_calc.payable_quantity,
                    bonus_quantity=bonus_calc.bonus_quantity,
                    revenue=full_revenue,
                    bonus_discount=bonus_calc.bonus_discount,
                    net_revenue=bonus_calc.final_amount
                )

                results.append(sale_info)

            except Product.DoesNotExist:
                continue

        return results

    @staticmethod
    def integrate_bonus_with_cost_calculation(
            production_batch_id: int,
            sales_data: Dict[int, int]  # {product_id: sold_quantity}
    ):
        """
        Интегрирует бонусную систему с расчетом себестоимости.

        Обновляет ProductionBatch с учетом:
        - Фактической выручки (с вычетом бонусов)
        - Реальной прибыли
        - Корректной рентабельности
        """
        from .models import ProductionBatch

        try:
            batch = ProductionBatch.objects.get(id=production_batch_id)
            product_id = batch.product.id

            if product_id not in sales_data:
                return batch

            sold_qty = sales_data[product_id]

            # Рассчитываем бонусы для этого товара
            bonus_calc = BonusIntegrationService.calculate_bonus_for_quantity(
                batch.product, sold_qty
            )

            # Обновляем batch с учетом бонусов
            batch.revenue = bonus_calc.final_amount  # выручка с учетом бонусов
            batch.net_profit = bonus_calc.final_amount - batch.total_cost

            # Добавляем информацию о бонусах в cost_breakdown
            if not batch.cost_breakdown:
                batch.cost_breakdown = {}

            batch.cost_breakdown.update({
                'bonus_info': {
                    'sold_quantity': sold_qty,
                    'payable_quantity': bonus_calc.payable_quantity,
                    'bonus_quantity': bonus_calc.bonus_quantity,
                    'bonus_discount': float(bonus_calc.bonus_discount),
                    'net_revenue': float(bonus_calc.final_amount)
                }
            })

            batch.save()
            return batch

        except ProductionBatch.DoesNotExist:
            return None

    @staticmethod
    def get_bonus_impact_analysis(calculation_date: date) -> Dict:
        """
        Анализ влияния бонусной системы на финансовые показатели за день.
        """
        from .models import ProductionBatch

        batches = ProductionBatch.objects.filter(
            date=calculation_date,
            product__is_bonus_eligible=True,
            product__category_type=Product.CategoryType.PIECE
        ).select_related('product')

        total_bonus_discount = Decimal('0')
        total_bonus_items = 0
        affected_products = 0

        bonus_details = []

        for batch in batches:
            bonus_info = batch.cost_breakdown.get('bonus_info', {})
            if bonus_info:
                bonus_discount = Decimal(str(bonus_info.get('bonus_discount', 0)))
                bonus_qty = bonus_info.get('bonus_quantity', 0)

                total_bonus_discount += bonus_discount
                total_bonus_items += bonus_qty
                affected_products += 1

                bonus_details.append({
                    'product_id': batch.product.id,
                    'product_name': batch.product.name,
                    'sold_quantity': bonus_info.get('sold_quantity', 0),
                    'bonus_quantity': bonus_qty,
                    'bonus_discount': float(bonus_discount),
                    'bonus_rule': f"каждый {batch.product.bonus_every_n}-й товар"
                })

        # Рассчитываем процент влияния на общую выручку
        total_revenue = sum(batch.revenue for batch in batches) + total_bonus_discount
        bonus_impact_percent = float(total_bonus_discount / total_revenue * 100) if total_revenue > 0 else 0

        return {
            'date': calculation_date,
            'total_bonus_discount': float(total_bonus_discount),
            'total_bonus_items': total_bonus_items,
            'affected_products_count': affected_products,
            'bonus_impact_percent': round(bonus_impact_percent, 2),
            'bonus_details': bonus_details,
            'summary': {
                'message': f'Бонусная программа: {total_bonus_items} бесплатных товаров на сумму {total_bonus_discount} сом',
                'efficiency': 'высокая' if bonus_impact_percent < 5 else 'средняя' if bonus_impact_percent < 10 else 'требует внимания'
            }
        }

    @staticmethod
    def simulate_bonus_rule_change(
            product_id: int,
            current_sales: int,
            new_bonus_every_n: int
    ) -> Dict:
        """
        Симулирует изменение правила бонусов (например, с каждого 21-го на каждый 25-й).
        Показывает влияние на выручку.
        """
        try:
            product = Product.objects.get(id=product_id, is_active=True)

            # Текущее правило
            current_calc = BonusIntegrationService.calculate_bonus_for_quantity(
                product, current_sales
            )

            # Новое правило (временно меняем)
            original_bonus_n = product.bonus_every_n
            product.bonus_every_n = new_bonus_every_n

            new_calc = BonusIntegrationService.calculate_bonus_for_quantity(
                product, current_sales
            )

            # Возвращаем обратно
            product.bonus_every_n = original_bonus_n

            # Анализ разницы
            revenue_difference = new_calc.final_amount - current_calc.final_amount
            bonus_difference = current_calc.bonus_quantity - new_calc.bonus_quantity

            return {
                'product_name': product.name,
                'sales_quantity': current_sales,
                'current_rule': f"каждый {original_bonus_n}-й",
                'proposed_rule': f"каждый {new_bonus_every_n}-й",
                'current_bonus_qty': current_calc.bonus_quantity,
                'proposed_bonus_qty': new_calc.bonus_quantity,
                'current_revenue': float(current_calc.final_amount),
                'proposed_revenue': float(new_calc.final_amount),
                'revenue_impact': float(revenue_difference),
                'bonus_items_difference': bonus_difference,
                'recommendation': 'увеличить выручку' if revenue_difference > 0 else 'сохранить лояльность'
            }

        except Product.DoesNotExist:
            return {'error': 'Товар не найден'}

    @staticmethod
    @transaction.atomic
    def apply_mass_bonus_calculation(
            calculation_date: date,
            sales_by_product: Dict[int, int]  # {product_id: sold_quantity}
    ) -> Dict:
        """
        Массовое применение бонусной системы ко всем продажам за день.
        Обновляет все ProductionBatch с корректными данными по бонусам.
        """
        from .models import ProductionBatch

        updated_batches = []
        total_bonus_discount = Decimal('0')
        total_bonus_items = 0

        for product_id, sold_qty in sales_by_product.items():
            try:
                batch = ProductionBatch.objects.get(
                    date=calculation_date,
                    product_id=product_id
                )

                # Интегрируем бонусы
                updated_batch = BonusIntegrationService.integrate_bonus_with_cost_calculation(
                    batch.id, {product_id: sold_qty}
                )

                if updated_batch:
                    updated_batches.append(updated_batch)

                    # Суммируем бонусы
                    bonus_info = updated_batch.cost_breakdown.get('bonus_info', {})
                    if bonus_info:
                        total_bonus_discount += Decimal(str(bonus_info.get('bonus_discount', 0)))
                        total_bonus_items += bonus_info.get('bonus_quantity', 0)

            except ProductionBatch.DoesNotExist:
                continue

        return {
            'date': calculation_date,
            'processed_products': len(updated_batches),
            'total_bonus_discount': float(total_bonus_discount),
            'total_bonus_items': total_bonus_items,
            'message': f'Бонусы применены к {len(updated_batches)} товарам'
        }


class BonusReportingService:
    """Отчетность по бонусной системе"""

    @staticmethod
    def get_monthly_bonus_report(year: int, month: int) -> Dict:
        """Месячный отчет по бонусам"""
        from .models import ProductionBatch
        from django.db.models import Sum, Count, Q
        from calendar import monthrange

        # Период месяца
        days_in_month = monthrange(year, month)[1]
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)

        # Все смены за месяц с бонусной информацией
        bonus_batches = ProductionBatch.objects.filter(
            date__range=[start_date, end_date],
            cost_breakdown__has_key='bonus_info'
        ).select_related('product')

        monthly_stats = {
            'period': {'year': year, 'month': month},
            'total_days': days_in_month,
            'days_with_bonuses': 0,
            'total_bonus_discount': 0,
            'total_bonus_items': 0,
            'affected_products': set(),
            'daily_breakdown': []
        }

        # Группируем по дням
        daily_data = {}

        for batch in bonus_batches:
            batch_date = batch.date
            if batch_date not in daily_data:
                daily_data[batch_date] = {
                    'date': batch_date,
                    'bonus_discount': 0,
                    'bonus_items': 0,
                    'products': []
                }

            bonus_info = batch.cost_breakdown.get('bonus_info', {})
            discount = Decimal(str(bonus_info.get('bonus_discount', 0)))
            items = bonus_info.get('bonus_quantity', 0)

            daily_data[batch_date]['bonus_discount'] += float(discount)
            daily_data[batch_date]['bonus_items'] += items
            daily_data[batch_date]['products'].append({
                'name': batch.product.name,
                'bonus_items': items,
                'bonus_discount': float(discount)
            })

            monthly_stats['total_bonus_discount'] += float(discount)
            monthly_stats['total_bonus_items'] += items
            monthly_stats['affected_products'].add(batch.product.name)

        monthly_stats['days_with_bonuses'] = len(daily_data)
        monthly_stats['affected_products'] = list(monthly_stats['affected_products'])
        monthly_stats['daily_breakdown'] = list(daily_data.values())

        # Средние показатели
        if monthly_stats['days_with_bonuses'] > 0:
            monthly_stats['avg_daily_bonus_discount'] = round(
                monthly_stats['total_bonus_discount'] / monthly_stats['days_with_bonuses'], 2
            )
            monthly_stats['avg_daily_bonus_items'] = round(
                monthly_stats['total_bonus_items'] / monthly_stats['days_with_bonuses'], 1
            )

        return monthly_stats