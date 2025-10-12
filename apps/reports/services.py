from django.db.models import Sum, Count, F, Q
from orders.models import Order, OrderHistory, OrderItem
from stores.models import Store
from products.models import BonusHistory, DefectiveProduct, ProductionItem
from datetime import date, timedelta
from decimal import Decimal
import pdfkit
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from io import BytesIO


class ReportGeneratorService:
    @staticmethod
    def generate_sales_report(date_from, date_to, city=None, partner=None, store=None):
        queryset = Order.objects.filter(created_at__range=[date_from, date_to], status='confirmed')
        if city:
            queryset = queryset.filter(store__city=city)
        if partner:
            queryset = queryset.filter(partner=partner)
        if store:
            queryset = queryset.filter(store=store)
        sales = queryset.aggregate(
            total_income=Sum('total_amount'),
            total_orders=Count('id')
        )
        stores = queryset.values('store__name').annotate(amount=Sum('total_amount'))
        total = sales['total_income'] or 0
        shares = {s['store__name']: s['amount'] / total if total > 0 else 0 for s in stores}
        return {'total_income': total, 'total_orders': sales['total_orders'] or 0, 'stores': list(stores), 'shares': shares}

    @staticmethod
    def generate_debt_report(date_from, date_to, city=None, partner=None, store=None):
        queryset = Store.objects.all()
        if city:
            queryset = queryset.filter(city=city)
        if store:
            queryset = queryset.filter(id=store.id)
        debts = queryset.aggregate(
            total_debt=Sum('debt'),
            count=Count('id')
        )
        stores = queryset.values('name').annotate(debt=Sum('debt'))
        total = debts['total_debt'] or 0
        shares = {s['name']: s['debt'] / total if total > 0 else 0 for s in stores}
        return {'total_debt': total, 'store_count': debts['count'], 'stores': list(stores), 'shares': shares}

    @staticmethod
    def generate_cost_report(date_from, date_to, city=None, partner=None, store=None):
        queryset = ProductionItem.objects.filter(record__date__range=[date_from, date_to])
        costs = queryset.aggregate(
            total_cost=Sum('total_cost'),
            net_profit=Sum('net_profit'),
            total_revenue=Sum('revenue')
        )
        products = queryset.values('product__name').annotate(cost=Sum('total_cost'))
        total_revenue = costs['total_revenue'] or 0
        shares = {p['product__name']: p['cost'] / total_revenue if total_revenue > 0 else 0 for p in products}
        return {
            'total_cost': costs['total_cost'] or 0,
            'net_profit': costs['net_profit'] or 0,
            'total_revenue': total_revenue,
            'products': list(products),
            'shares': shares
        }

    @staticmethod
    def generate_bonus_report(date_from, date_to, city=None, partner=None, store=None):
        queryset = BonusHistory.objects.filter(date__range=[date_from, date_to])
        if city:
            queryset = queryset.filter(store__city=city)
        if partner:
            queryset = queryset.filter(partner=partner)
        if store:
            queryset = queryset.filter(store=store)
        bonuses = queryset.aggregate(
            total_bonus=Sum('bonus_count'),
            total_amount=Sum(F('bonus_count') * F('product__price'))
        )
        products = queryset.values('product__name').annotate(count=Sum('bonus_count'))
        total = bonuses['total_amount'] or 0
        shares = {p['product__name']: p['count'] / total if total > 0 else 0 for p in products}
        return {'total_bonus': bonuses['total_bonus'] or 0, 'total_amount': total, 'products': list(products), 'shares': shares}

    @staticmethod
    def generate_brak_report(date_from, date_to, city=None, partner=None, store=None):
        queryset = DefectiveProduct.objects.filter(date__range=[date_from, date_to])
        if partner:
            queryset = queryset.filter(partner=partner)
        if store:
            queryset = queryset.filter(order__store=store)
        brak = queryset.aggregate(
            total_brak=Sum('quantity'),
            total_amount=Sum('amount')
        )
        products = queryset.values('product__name').annotate(quantity=Sum('quantity'))
        total = brak['total_amount'] or 0
        shares = {p['product__name']: p['quantity'] / total if total > 0 else 0 for p in products}
        return {'total_brak': brak['total_brak'] or 0, 'total_amount': total, 'products': list(products), 'shares': shares}

    @staticmethod
    def generate_balance_report(date_from, date_to, city=None, partner=None, store=None):
        sales = ReportGeneratorService.generate_sales_report(date_from, date_to, city, partner, store)['total_income']
        costs = ReportGeneratorService.generate_cost_report(date_from, date_to, city, partner, store)['total_cost']
        debts = ReportGeneratorService.generate_debt_report(date_from, date_to, city, partner, store)['total_debt']
        bonuses = ReportGeneratorService.generate_bonus_report(date_from, date_to, city, partner, store)['total_amount']
        balance = sales - costs - debts - bonuses
        total = sales + costs + debts + bonuses
        shares = {
            'sales_share': sales / total if total > 0 else 0,
            'costs_share': costs / total if total > 0 else 0,
            'debts_share': debts / total if total > 0 else 0,
            'bonuses_share': bonuses / total if total > 0 else 0
        }
        return {'balance': balance, 'sales': sales, 'costs': costs, 'debts': debts, 'bonuses': bonuses, 'shares': shares}

    @staticmethod
    def generate_orders_report(date_from, date_to, city=None, partner=None, store=None):
        queryset = Order.objects.filter(created_at__range=[date_from, date_to])
        if city:
            queryset = queryset.filter(store__city=city)
        if partner:
            queryset = queryset.filter(partner=partner)
        if store:
            queryset = queryset.filter(store=store)
        orders = queryset.aggregate(
            total_orders=Count('id'),
            total_amount=Sum('total_amount'),
            confirmed=Count('id', filter=Q(status='confirmed'))
        )
        stores = queryset.values('store__name').annotate(amount=Sum('total_amount'))
        total = orders['total_amount'] or 0
        shares = {s['store__name']: s['amount'] / total if total > 0 else 0 for s in stores}
        return {
            'total_orders': orders['total_orders'] or 0,
            'total_amount': total,
            'confirmed_orders': orders['confirmed'] or 0,
            'stores': list(stores),
            'shares': shares
        }

    @staticmethod
    def generate_products_report(date_from, date_to, city=None, partner=None, store=None):
        queryset = OrderItem.objects.filter(order__created_at__range=[date_from, date_to])
        if city:
            queryset = queryset.filter(order__store__city=city)
        if partner:
            queryset = queryset.filter(order__partner=partner)
        if store:
            queryset = queryset.filter(order__store=store)
        products = queryset.values('product__name').annotate(
            total_quantity=Sum('quantity'),
            total_amount=Sum(F('quantity') * F('price'))
        )
        total_amount = queryset.aggregate(total=Sum(F('quantity') * F('price')))['total'] or 0
        shares = {p['product__name']: p['total_amount'] / total_amount if total_amount > 0 else 0 for p in products}
        return {'products': list(products), 'total_amount': total_amount, 'shares': shares}

    @staticmethod
    def generate_markup_report(date_from, date_to, city=None, partner=None, store=None):
        """Умная наценка: сравнение себестоимости и продаж"""
        costs = ProductionItem.objects.filter(record__date__range=[date_from, date_to]).aggregate(
            total_cost=Sum('total_cost')
        )
        sales = ReportGeneratorService.generate_sales_report(date_from, date_to, city, partner, store)['total_income']
        markup = (sales - (costs['total_cost'] or 0)) / (costs['total_cost'] or 1) * 100
        products = ProductionItem.objects.filter(record__date__range=[date_from, date_to]).values('product__name').annotate(
            cost=Sum('total_cost'),
            revenue=Sum('revenue')
        )
        shares = {p['product__name']: p['revenue'] / sales if sales > 0 else 0 for p in products}
        return {
            'markup_percentage': round(markup, 2),
            'total_cost': costs['total_cost'] or 0,
            'total_sales': sales,
            'products': list(products),
            'shares': shares
        }

    @staticmethod
    def export_to_pdf(report):
        """Экспорт отчета в PDF"""
        html = render_to_string('reports/report_template.html', {'report': report})
        output = BytesIO()
        pdfkit.from_string(html, output)
        return ContentFile(output.getvalue(), f'report_{report.id}.pdf')