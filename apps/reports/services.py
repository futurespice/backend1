from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import models
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone

from .models import Report, SalesReport, InventoryReport
from orders.models import Order, OrderItem
from stores.models import StoreInventory
from debts.models import Debt



class ReportGeneratorService:
    """Сервис генерации отчетов"""

    def generate_report(self, report_type: str, period: str, date_from: date,
                        date_to: date, created_by, filters: Dict[str, Any]) -> Report:
        """Основной метод генерации отчета"""

        # Генерируем данные в зависимости от типа отчета
        if report_type == 'sales':
            data = self._generate_sales_report_data(date_from, date_to, filters)
        elif report_type == 'inventory':
            data = self._generate_inventory_report_data(date_from, date_to, filters)
        elif report_type == 'debts':
            data = self._generate_debts_report_data(date_from, date_to, filters)
        elif report_type == 'profit':
            data = self._generate_profit_report_data(date_from, date_to, filters)
        else:
            data = {}

        # Создаем отчет
        report = Report.objects.create(
            name=self._generate_report_name(report_type, period, date_from, date_to),
            report_type=report_type,
            period=period,
            date_from=date_from,
            date_to=date_to,
            store_id=filters.get('store_id'),
            partner_id=filters.get('partner_id'),
            product_id=filters.get('product_id'),
            data=data,
            created_by=created_by
        )

        return report

    def _generate_sales_report_data(self, date_from: date, date_to: date,
                                    filters: Dict[str, Any], debts_qs=None) -> Dict[str, Any]:
        """Генерация данных отчета по продажам"""

        orders_qs = Order.objects.filter(
            order_date__date__gte=date_from,
            order_date__date__lte=date_to,
            status='completed'
        )

        # Применяем фильтры
        if filters.get('store_id'):
            debts_qs = debts_qs.filter(store_id=filters['store_id'])

        # Основная статистика
        total_stats = debts_qs.aggregate(
            total_debts=Count('id'),
            total_amount=Sum('amount'),
            total_paid=Sum('paid_amount'),
            active_debts=Count('id', filter=Q(is_paid=False)),
            overdue_debts=Count('id', filter=Q(is_paid=False, due_date__lt=date.today()))
        )

        # По магазинам
        by_stores = debts_qs.values(
            'store__store_name', 'store_id'
        ).annotate(
            total_debt=Sum('amount') - Sum('paid_amount'),
            count=Count('id')
        ).filter(total_debt__gt=0).order_by('-total_debt')

        # Динамика по дням
        daily_debts = debts_qs.extra(
            select={'day': 'date(created_at)'}
        ).values('day').annotate(
            new_debts=Count('id'),
            amount=Sum('amount')
        ).order_by('day')

        return {
            'summary': {
                'total_debts': total_stats['total_debts'] or 0,
                'total_amount': float(total_stats['total_amount'] or 0),
                'total_paid': float(total_stats['total_paid'] or 0),
                'remaining_debt': float((total_stats['total_amount'] or 0) - (total_stats['total_paid'] or 0)),
                'active_debts': total_stats['active_debts'] or 0,
                'overdue_debts': total_stats['overdue_debts'] or 0
            },
            'by_stores': list(by_stores),
            'daily_breakdown': list(daily_debts)
        }

    def _generate_profit_report_data(self, date_from: date, date_to: date,
                                     filters: Dict[str, Any]) -> Dict[str, Any]:
        """Генерация данных отчета по прибыли"""

        # Расчет прибыли = Выручка - Себестоимость - Расходы
        orders_qs = Order.objects.filter(
            order_date__date__gte=date_from,
            order_date__date__lte=date_to,
            status='completed'
        )

        if filters.get('store_id'):
            orders_qs = orders_qs.filter(store_id=filters['store_id'])

        # Выручка
        revenue_stats = orders_qs.aggregate(
            total_revenue=Sum('total_amount'),
            total_orders=Count('id')
        )

        # Себестоимость (примерная, так как может быть сложной)
        order_items = OrderItem.objects.filter(order__in=orders_qs)

        # Здесь должен быть расчет реальной себестоимости через BOM
        estimated_cost = Decimal('0')
        for item in order_items:
            # Упрощенный расчет - 60% от цены продажи
            estimated_cost += item.total_price * Decimal('0.6')

        gross_profit = (revenue_stats['total_revenue'] or 0) - estimated_cost

        return {
            'summary': {
                'total_revenue': float(revenue_stats['total_revenue'] or 0),
                'estimated_cost': float(estimated_cost),
                'gross_profit': float(gross_profit),
                'profit_margin': float(gross_profit / (revenue_stats['total_revenue'] or 1) * 100),
                'total_orders': revenue_stats['total_orders'] or 0
            },
            'note': 'Расчет себестоимости упрощенный. Для точного расчета требуется настройка BOM.'
        }

    def _generate_report_name(self, report_type: str, period: str,
                              date_from: date, date_to: date) -> str:
        """Генерация названия отчета"""

        type_names = {
            'sales': 'Отчет по продажам',
            'inventory': 'Отчет по остаткам',
            'debts': 'Отчет по долгам',
            'profit': 'Отчет по прибыли'
        }

        type_name = type_names.get(report_type, 'Отчет')

        if date_from == date_to:
            period_str = f"за {date_from.strftime('%d.%m.%Y')}"
        else:
            period_str = f"с {date_from.strftime('%d.%m.%Y')} по {date_to.strftime('%d.%m.%Y')}"

        return f"{type_name} {period_str}"


class SalesReportService:
    """Сервис для работы с отчетами продаж"""

    @staticmethod
    def update_daily_sales_report(date_for_report: date = None):
        """Обновление дневного отчета по продажам"""

        if date_for_report is None:
            date_for_report = date.today() - timedelta(days=1)

        # Получаем все завершенные заказы за день
        orders = Order.objects.filter(
            completed_date__date=date_for_report,
            status='completed'
        )

        # Группируем по магазинам и товарам
        for order in orders:
            for item in order.items.all():
                report, created = SalesReport.objects.get_or_create(
                    date=date_for_report,
                    store=order.store,
                    product=item.product,
                    defaults={
                        'orders_count': 0,
                        'total_quantity': Decimal('0'),
                        'total_revenue': Decimal('0'),
                        'total_bonus_discount': Decimal('0'),
                        'total_cost': Decimal('0'),
                        'profit': Decimal('0')
                    }
                )

                # Обновляем метрики
                report.orders_count += 1
                report.total_quantity += item.quantity
                report.total_revenue += item.total_price
                report.total_bonus_discount += item.bonus_discount

                # Себестоимость (упрощенно)
                cost = item.product.calculate_cost_price() or (item.unit_price * Decimal('0.6'))
                item_cost = cost * item.quantity
                report.total_cost += item_cost

                report.profit = report.total_revenue - report.total_cost
                report.save()


class EmailService:
    """Сервис отправки email уведомлений"""

    @staticmethod
    def send_approval_notification(user, approved: bool):
        """Отправка уведомления об одобрении"""
        # Здесь должна быть реальная отправка email
        pass

    @staticmethod
    def send_report_notification(report: Report, recipients: list):
        """Отправка отчета по email"""
        # Здесь должна быть отправка отчета
        pass


class InventoryService:
    """Сервис управления остатками"""

    @staticmethod
    def check_low_stock():
        """Проверка низких остатков"""
        from apps.stores.models import StoreInventory

        low_stock_items = StoreInventory.objects.filter(
            quantity__lte=models.F('product__low_stock_threshold')
        ).select_related('store', 'product')

        # Группируем по магазинам
        notifications = {}
        for item in low_stock_items:
            store_id = item.store.id
            if store_id not in notifications:
                notifications[store_id] = {
                    'store': item.store,
                    'items': []
                }

            notifications[store_id]['items'].append({
                'product': item.product.name,
                'current': item.quantity,
                'threshold': item.product.low_stock_threshold
            })

        # Отправляем уведомления
        for store_data in notifications.values():
            # Создаем уведомление
            from apps.messaging.models import Notification

            Notification.objects.create(
                recipient=store_data['store'].user,
                notification_type='inventory_low',
                title='Низкие остатки товаров',
                message=f"У вас заканчиваются товары: {len(store_data['items'])} позиций"
            )

    @staticmethod
    def transfer_inventory(from_inventory, to_inventory, quantity):
        """Перенос товаров между складами"""
        if from_inventory.available_quantity >= quantity:
            from_inventory.quantity -= quantity
            to_inventory.quantity += quantity

            from_inventory.save()
            to_inventory.save()

            return True
        return False
        фильтры
        if filters.get('store_id'):
            orders_qs = orders_qs.filter(store_id=filters['store_id'])
        if filters.get('partner_id'):
            orders_qs = orders_qs.filter(store__partner_id=filters['partner_id'])

        # Основная статистика
        total_stats = orders_qs.aggregate(
            total_orders=Count('id'),
            total_revenue=Sum('total_amount'),
            total_bonus_discount=Sum('bonus_discount'),
            avg_order_value=Avg('total_amount')
        )

        # Статистика по дням
        daily_stats = orders_qs.extra(
            select={'day': 'date(order_date)'}
        ).values('day').annotate(
            orders=Count('id'),
            revenue=Sum('total_amount'),
            bonus_discount=Sum('bonus_discount')
        ).order_by('day')

        # Топ товары
        top_products = OrderItem.objects.filter(
            order__in=orders_qs
        ).values(
            'product__name', 'product_id'
        ).annotate(
            quantity=Sum('quantity'),
            revenue=Sum('total_price'),
            orders=Count('order', distinct=True)
        ).order_by('-revenue')[:10]

        # Топ магазины
        top_stores = orders_qs.values(
            'store__store_name', 'store_id'
        ).annotate(
            orders=Count('id'),
            revenue=Sum('total_amount')
        ).order_by('-revenue')[:10]

        return {
            'summary': {
                'total_orders': total_stats['total_orders'] or 0,
                'total_revenue': float(total_stats['total_revenue'] or 0),
                'total_bonus_discount': float(total_stats['total_bonus_discount'] or 0),
                'avg_order_value': float(total_stats['avg_order_value'] or 0),
                'period_days': (date_to - date_from).days + 1
            },
            'daily_breakdown': [
                {
                    'date': item['day'],
                    'orders': item['orders'],
                    'revenue': float(item['revenue']),
                    'bonus_discount': float(item['bonus_discount'])
                }
                for item in daily_stats
            ],
            'top_products': [
                {
                    'product_id': item['product_id'],
                    'product_name': item['product__name'],
                    'quantity': float(item['quantity']),
                    'revenue': float(item['revenue']),
                    'orders': item['orders']
                }
                for item in top_products
            ],
            'top_stores': [
                {
                    'store_id': item['store_id'],
                    'store_name': item['store__store_name'],
                    'orders': item['orders'],
                    'revenue': float(item['revenue'])
                }
                for item in top_stores
            ]
        }

    def _generate_inventory_report_data(self, date_from: date, date_to: date,
                                        filters: Dict[str, Any]) -> Dict[str, Any]:
        """Генерация данных отчета по остаткам"""

        inventory_qs = StoreInventory.objects.select_related('store', 'product')

        # Применяем фильтры
        if filters.get('store_id'):
            inventory_qs = inventory_qs.filter(store_id=filters['store_id'])
        if filters.get('product_id'):
            inventory_qs = inventory_qs.filter(product_id=filters['product_id'])

        # Текущие остатки
        current_inventory = inventory_qs.values(
            'product__name', 'product_id', 'store__store_name', 'store_id'
        ).annotate(
            current_quantity=Sum('quantity'),
            reserved_quantity=Sum('reserved_quantity')
        )

        # Низкие остатки
        low_stock = inventory_qs.filter(
            quantity__lte=models.F('product__low_stock_threshold')
        ).values(
            'product__name', 'product_id', 'store__store_name',
            'quantity', 'product__low_stock_threshold'
        )

        # Оборачиваемость (продажи за период)
        orders_qs = Order.objects.filter(
            order_date__date__gte=date_from,
            order_date__date__lte=date_to,
            status='completed'
        )

        if filters.get('store_id'):
            orders_qs = orders_qs.filter(store_id=filters['store_id'])

        turnover = OrderItem.objects.filter(
            order__in=orders_qs
        ).values(
            'product__name', 'product_id'
        ).annotate(
            sold_quantity=Sum('quantity')
        )

        return {
            'summary': {
                'total_products': inventory_qs.values('product').distinct().count(),
                'total_stores': inventory_qs.values('store').distinct().count(),
                'low_stock_count': low_stock.count(),
                'report_date': date_to.isoformat()
            },
            'current_inventory': list(current_inventory),
            'low_stock_products': list(low_stock),
            'turnover_data': list(turnover)
        }

    def _generate_debts_report_data(self, date_from: date, date_to: date,
                                    filters: Dict[str, Any]) -> Dict[str, Any]:
        """Генерация данных отчета по долгам"""

        debts_qs = Debt.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to
        )

        # Применяем