# from django.contrib import admin
# from .models import SalesReport, InventoryReport, CostReport, BonusReport
#
# @admin.register(SalesReport)
# class SalesReportAdmin(admin.ModelAdmin):
#     list_display = ['period_type', 'start_date', 'end_date', 'total_orders', 'total_revenue', 'total_profit']
#     list_filter = ['period_type', 'start_date']
#
# @admin.register(InventoryReport)
# class InventoryReportAdmin(admin.ModelAdmin):
#     list_display = ['date', 'product', 'opening_balance', 'received', 'sold', 'closing_balance']
#     list_filter = ['date']
#     search_fields = ['product__name']
#
# @admin.register(CostReport)
# class CostReportAdmin(admin.ModelAdmin):
#     list_display = ['date', 'product', 'quantity_produced', 'total_cost', 'cost_per_unit']
#     list_filter = ['date']
#     search_fields = ['product__name']
#
# @admin.register(BonusReport)
# class BonusReportAdmin(admin.ModelAdmin):
#     list_display = ['date', 'store', 'bonuses_earned', 'bonuses_used', 'bonus_balance']
#     list_filter = ['date']
#     search_fields = ['store__name']