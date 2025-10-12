from celery import shared_task
from .models import Order, OrderHistory
from datetime import date, timedelta


@shared_task
def daily_order_history():
    yesterday = date.today() - timedelta(days=1)
    orders = Order.objects.filter(status='confirmed', updated_at__date=yesterday)
    for order in orders:
        total_quantity = sum(item.quantity for item in order.items.all())
        OrderHistory.objects.create(
            order=order,
            type='sold',
            amount=order.total_amount,
            quantity=total_quantity,
            note='Ежедневная запись продаж'
        )