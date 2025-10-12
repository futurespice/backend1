# from django.contrib import admin
# from django.utils.html import format_html
# from .models import Order, OrderItem, ProductRequest, ProductRequestItem
#
# class OrderItemInline(admin.TabularInline):
#     model = OrderItem
#     extra = 0
#     readonly_fields = ['total_price', 'bonus_discount']
#     fields = ['product', 'quantity', 'unit_price', 'total_price', 'bonus_quantity', 'bonus_discount']
#
# @admin.register(Order)
# class OrderAdmin(admin.ModelAdmin):
#     list_display = [
#         'id', 'store_info', 'status_display',
#         'total_amount_display', 'debt_amount_display', 'order_date'
#     ]
#     list_filter = ['status', 'order_date', 'confirmed_date']
#     search_fields = ['store__store_name', 'notes']
#     ordering = ['-order_date']
#     inlines = [OrderItemInline]
#
#     fieldsets = (
#         ('Участники', {
#             'fields': ('store',)
#         }),
#         ('Статус и даты', {
#             'fields': ('status', 'order_date', 'confirmed_date', 'completed_date')
#         }),
#         ('Суммы', {
#             'fields': ('subtotal', 'bonus_discount', 'total_amount', 'payment_amount', 'debt_amount')
#         }),
#         ('Бонусы', {
#             'fields': ('bonus_items_count',)
#         }),
#         ('Комментарии', {
#             'fields': ('notes',)
#         }),
#     )
#
#     readonly_fields = ['order_date', 'confirmed_date', 'completed_date']
#
#     def store_info(self, obj):
#         return format_html(
#             '<strong>{}</strong><br/><small>{}</small>',
#             obj.store.store_name,
#             obj.store.user.get_full_name()
#         )
#     store_info.short_description = 'Магазин'
#
#     def status_display(self, obj):
#         colors = {
#             'pending': 'orange',
#             'confirmed': 'blue',
#             'completed': 'green',
#             'cancelled': 'red'
#         }
#         return format_html(
#             '<span style="color: {};">{}</span>',
#             colors.get(obj.status, 'black'),
#             obj.get_status_display()
#         )
#     status_display.short_description = 'Статус'
#
#     def total_amount_display(self, obj):
#         return f"{obj.total_amount} сом"
#     total_amount_display.short_description = 'Сумма'
#
#     def debt_amount_display(self, obj):
#         if obj.debt_amount > 0:
#             return format_html('<span style="color: red;">{} сом</span>', obj.debt_amount)
#         return "0 сом"
#     debt_amount_display.short_description = 'Долг'
#
# class ProductRequestItemInline(admin.TabularInline):
#     model = ProductRequestItem
#     extra = 0
#     fields = ['product', 'requested_quantity', 'approved_quantity', 'unit_price', 'notes']
#
# @admin.register(ProductRequest)
# class ProductRequestAdmin(admin.ModelAdmin):
#     list_display = [
#         'id', 'partner', 'status', 'total_requested_amount',
#         'total_approved_amount', 'requested_at'
#     ]
#     list_filter = ['status', 'requested_at', 'reviewed_at']
#     search_fields = ['partner__name', 'partner_notes']
#     ordering = ['-requested_at']
#     inlines = [ProductRequestItemInline]
#
#     fieldsets = (
#         ('Основная информация', {
#             'fields': ('partner', 'status')
#         }),
#         ('Даты', {
#             'fields': ('requested_at', 'reviewed_at', 'reviewed_by')
#         }),
#         ('Суммы', {
#             'fields': ('total_requested_amount', 'total_approved_amount')
#         }),
#         ('Комментарии', {
#             'fields': ('partner_notes', 'admin_notes')
#         }),
#     )
#
#     readonly_fields = ['requested_at', 'reviewed_at']