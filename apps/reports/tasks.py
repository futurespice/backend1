



"""
Файл с Celery-задачами.
По текущему ТЗ автоматическая генерация отчётов не требуется,
поэтому задачи временно отключены.
Если решим вернуться к авто-режиму (ежедневные/еженедельные отчёты,
алёрты по долгам/остаткам и пр.), этот код можно раскомментировать и доработать!!!
"""

# from celery import shared_task
# from datetime import date, timedelta
# from decimal import Decimal
# from django.utils import timezone
#
# from .services import SalesReportService, InventoryService
# from .models import Report
# from apps.messaging.models import Notification
# from apps.stores.models import StoreInventory
# from apps.debts.models import Debt
# from apps.users.models import User
#
#
# @shared_task
# def generate_daily_sales_reports():
#     """Ежедневная генерация отчетов по продажам"""
#     yesterday = date.today() - timedelta(days=1)
#
#     try:
#         SalesReportService.update_daily_sales_report(yesterday)
#         return f"Daily sales report generated for {yesterday}"
#     except Exception as e:
#         return f"Error generating daily sales report: {str(e)}"
#
#
# @shared_task
# def check_low_stock_alerts():
#     """Проверка низких остатков и отправка уведомлений"""
#     try:
#         InventoryService.check_low_stock()
#         return "Low stock alerts checked and sent"
#     except Exception as e:
#         return f"Error checking low stock: {str(e)}"
#
#
# @shared_task
# def send_overdue_debt_notifications():
#     """Отправка уведомлений о просроченных долгах"""
#     try:
#         overdue_debts = Debt.objects.filter(
#             is_paid=False,
#             due_date__lt=date.today()
#         ).select_related('store', 'store__user')
#
#         notifications_sent = 0
#
#         for debt in overdue_debts:
#             # Проверяем, не отправляли ли уже уведомление сегодня
#             today_notifications = Notification.objects.filter(
#                 recipient=debt.store.user,
#                 notification_type='debt_overdue',
#                 created_at__date=date.today(),
#                 related_object_id=debt.id
#             ).exists()
#
#             if not today_notifications:
#                 days_overdue = (date.today() - debt.due_date).days
#
#                 Notification.objects.create(
#                     recipient=debt.store.user,
#                     notification_type='debt_overdue',
#                     title='Просроченный долг',
#                     message=f'Долг #{debt.id} на сумму {debt.remaining_amount} сом просрочен на {days_overdue} дней',
#                     related_object_id=debt.id,
#                     related_object_type='debt'
#                 )
#
#                 notifications_sent += 1
#
#         return f"Sent {notifications_sent} overdue debt notifications"
#     except Exception as e:
#         return f"Error sending overdue debt notifications: {str(e)}"
#
#
# @shared_task
# def generate_weekly_reports():
#     """Еженедельная генерация отчетов"""
#     try:
#         from .services import ReportGeneratorService
#
#         # Период - прошлая неделя
#         end_date = date.today() - timedelta(days=1)
#         start_date = end_date - timedelta(days=6)
#
#         # Генерируем отчеты для админов
#         admin_users = User.objects.filter(role='admin', is_active=True)
#
#         generator = ReportGeneratorService()
#         reports_created = 0
#
#         for admin in admin_users:
#             # Отчет по продажам
#             sales_report = generator.generate_report(
#                 report_type='sales',
#                 period='weekly',
#                 date_from=start_date,
#                 date_to=end_date,
#                 created_by=admin,
#                 filters={}
#             )
#
#             # Отчет по долгам
#             debts_report = generator.generate_report(
#                 report_type='debts',
#                 period='weekly',
#                 date_from=start_date,
#                 date_to=end_date,
#                 created_by=admin,
#                 filters={}
#             )
#
#             reports_created += 2
#
#             # Отправляем уведомление
#             Notification.objects.create(
#                 recipient=admin,
#                 notification_type='system_maintenance',
#                 title='Еженедельные отчеты готовы',
#                 message=f'Созданы отчеты за период {start_date} - {end_date}'
#             )
#
#         return f"Generated {reports_created} weekly reports"
#     except Exception as e:
#         return f"Error generating weekly reports: {str(e)}"
#
#
# @shared_task
# def cleanup_old_reports():
#     """Очистка старых отчетов"""
#     try:
#         # Удаляем автоматические отчеты старше 90 дней
#         cutoff_date = timezone.now() - timedelta(days=90)
#
#         deleted_count = Report.objects.filter(
#             is_automated=True,
#             created_at__lt=cutoff_date
#         ).delete()[0]
#
#         return f"Deleted {deleted_count} old automated reports"
#     except Exception as e:
#         return f"Error cleaning up old reports: {str(e)}"
#
#
# @shared_task
# def update_inventory_reports():
#     """Обновление отчетов по остаткам"""
#     try:
#         from .models import InventoryReport
#
#         yesterday = date.today() - timedelta(days=1)
#
#         # Получаем все активные склады
#         inventories = StoreInventory.objects.select_related(
#             'store', 'product'
#         ).filter(
#             store__is_active=True,
#             product__is_active=True
#         )
#
#         updated_count = 0
#
#         for inventory in inventories:
#             # Создаем/обновляем запись в отчете
#             report, created = InventoryReport.objects.get_or_create(
#                 date=yesterday,
#                 store=inventory.store,
#                 product=inventory.product,
#                 defaults={
#                     'opening_balance': inventory.quantity,
#                     'closing_balance': inventory.quantity,
#                     'received_quantity': Decimal('0'),
#                     'sold_quantity': Decimal('0'),
#                     'opening_value': inventory.quantity * inventory.product.price,
#                     'closing_value': inventory.quantity * inventory.product.price
#                 }
#             )
#
#             if not created:
#                 # Обновляем существующую запись
#                 report.closing_balance = inventory.quantity
#                 report.closing_value = inventory.quantity * inventory.product.price
#                 report.save()
#
#             updated_count += 1
#
#         return f"Updated {updated_count} inventory report records"
#     except Exception as e:
#         return f"Error updating inventory reports: {str(e)}"
#
#
# @shared_task
# def calculate_monthly_costs():
#     """Ежемесячный расчет себестоимости"""
#     try:
#         from apps.cost_accounting.models import MonthlyOverheadBudget, Expense
#         from apps.products.models import Product
#
#         # Текущий месяц
#         current_date = date.today().replace(day=1)  # Первое число месяца
#
#         # Получаем все активные товары
#         products = Product.objects.filter(is_active=True)
#
#         # Месячные накладные расходы
#         monthly_overhead = MonthlyOverheadBudget.objects.filter(
#             month=current_date
#         ).aggregate(
#             total=models.Sum('planned_amount')
#         )['total'] or Decimal('0')
#
#         # Дневная ставка накладных
#         days_in_month = 30  # Упрощенно
#         daily_overhead_rate = monthly_overhead / days_in_month
#
#         calculations_done = 0
#
#         for product in products:
#             try:
#                 # Рассчитываем себестоимость
#                 cost_price = product.calculate_cost_price()
#
#                 if cost_price:
#                     # Добавляем накладные расходы (пропорционально)
#                     # Это упрощенная формула, реальная может быть сложнее
#                     total_cost = cost_price + (daily_overhead_rate / 1000)  # Условное распределение
#
#                     # Сохраняем результат (можно создать отдельную модель для истории цен)
#                     calculations_done += 1
#
#             except Exception as product_error:
#                 # Логируем ошибку для конкретного товара
#                 continue
#
#         return f"Calculated costs for {calculations_done} products"
#     except Exception as e:
#         return f"Error calculating monthly costs: {str(e)}"
#
#
# @shared_task
# def send_partner_performance_reports():
#     """Отправка отчетов о производительности партнерам"""
#     try:
#         from .services import ReportGeneratorService
#
#         # Период - прошлый месяц
#         today = date.today()
#         end_date = date(today.year, today.month, 1) - timedelta(days=1)  # Последний день прошлого месяца
#         start_date = end_date.replace(day=1)  # Первый день прошлого месяца
#
#         partners = User.objects.filter(role='partner', is_active=True)
#         generator = ReportGeneratorService()
#
#         reports_sent = 0
#
#         for partner in partners:
#             # Генерируем отчет для партнера
#             report = generator.generate_report(
#                 report_type='partner_performance',
#                 period='monthly',
#                 date_from=start_date,
#                 date_to=end_date,
#                 created_by=partner,
#                 filters={'partner_id': partner.id}
#             )
#
#             # Отправляем уведомление
#             Notification.objects.create(
#                 recipient=partner,
#                 notification_type='system_maintenance',
#                 title='Месячный отчет готов',
#                 message=f'Ваш отчет о работе за {start_date.strftime("%B %Y")} готов к просмотру',
#                 related_object_id=report.id,
#                 related_object_type='report'
#             )
#
#             reports_sent += 1
#
#         return f"Sent performance reports to {reports_sent} partners"
#     except Exception as e:
#         return f"Error sending partner performance reports: {str(e)}"