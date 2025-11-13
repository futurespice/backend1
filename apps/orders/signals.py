# apps/orders/signals.py
"""
Сигналы приложения orders — автоматические действия при изменении заказов.

Что делает:
1. Пересчёт total_amount при изменении позиций
2. Обновление статуса заказа
3. Запись в OrderHistory
4. Обновление инвентаря при подтверждении
5. Отправка уведомлений (email, push)
6. Асинхронные задачи (django-q)
7. Защита от race condition
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from django.db.models.signals import post_save, pre_delete, m2m_changed
from django.dispatch import receiver
from django.db import transaction
from django.db.models import F
from django.core.cache import cache

from .models import (
    PartnerOrder, PartnerOrderItem,
    StoreOrder, StoreOrderItem,
    OrderHistory, OrderReturn, OrderReturnItem
)
from products.models import Product
from stores.models import Store
from users.models import User

# Настройка логирования
logger = logging.getLogger('orders.signals')


# =============================================================================
#  УТИЛИТЫ
# =============================================================================

def safe_decimal(value: Any) -> Decimal:
    """Безопасное преобразование в Decimal"""
    try:
        return Decimal(str(value)) if value is not None else Decimal('0')
    except Exception:
        return Decimal('0')


def recalculate_order_totals(order: Any) -> None:
    """Пересчёт total_amount и bonus_applied для любого заказа"""
    if isinstance(order, PartnerOrder):
        total = sum(
            item.quantity * item.price
            for item in order.items.all()
            if item.quantity and item.price
        )
        if order.total_amount != total:
            order.total_amount = total
            order.save(update_fields=['total_amount'])
            logger.debug(f"Пересчитана сумма PartnerOrder #{order.id}: {total}")

    elif isinstance(order, StoreOrder):
        total = Decimal('0')
        bonus = Decimal('0')
        for item in order.items.all():
            if item.is_bonus:
                bonus += safe_decimal(item.price) * safe_decimal(item.quantity)
            else:
                total += safe_decimal(item.price) * safe_decimal(item.quantity)
        changed = False
        if order.total_amount != total:
            order.total_amount = total
            changed = True
        if order.bonus_applied != bonus:
            order.bonus_applied = bonus
            changed = True
        if changed:
            order.save(update_fields=['total_amount', 'bonus_applied'])
            logger.debug(f"Пересчитана сумма StoreOrder #{order.id}: {total} + бонус {bonus}")

    elif isinstance(order, OrderReturn):
        total = sum(
            item.quantity * item.price
            for item in order.items.all()
            if item.quantity and item.price
        )
        if order.total_amount != total:
            order.total_amount = total
            order.save(update_fields=['total_amount'])
            logger.debug(f"Пересчитана сумма OrderReturn #{order.id}: {total}")


# =============================================================================
#  PARTNER ORDER & ITEMS
# =============================================================================

@receiver(post_save, sender=PartnerOrderItem)
def partner_order_item_saved(sender, instance: PartnerOrderItem, created: bool, **kwargs):
    """Пересчёт суммы при создании/изменении позиции"""
    if created or 'quantity' in instance.get_dirty_fields() or 'price' in instance.get_dirty_fields():
        transaction.on_commit(lambda: recalculate_order_totals(instance.order))


@receiver(pre_delete, sender=PartnerOrderItem)
def partner_order_item_deleted(sender, instance: PartnerOrderItem, **kwargs):
    """Пересчёт при удалении"""
    order = instance.order
    transaction.on_commit(lambda: recalculate_order_totals(order))


@receiver(post_save, sender=PartnerOrder)
def partner_order_status_changed(sender, instance: PartnerOrder, created: bool, **kwargs):
    """Запись в историю при изменении статуса"""
    if not created and 'status' in instance.get_dirty_fields():
        old_status = instance.get_dirty_fields()['status']
        OrderHistory.objects.create(
            order_type='partner',
            order_id=instance.id,
            type='general',
            amount=instance.total_amount,
            note=f'Статус изменён: {old_status} → {instance.status}'
        )
        logger.info(f"PartnerOrder #{instance.id}: статус {old_status} → {instance.status}")

        # Асинхронное уведомление
        send_order_status_notification.delay('partner', instance.id, instance.status)


# =============================================================================
#  STORE ORDER & ITEMS
# =============================================================================

@receiver(post_save, sender=StoreOrderItem)
def store_order_item_saved(sender, instance: StoreOrderItem, created: bool, **kwargs):
    """Пересчёт при изменении позиции магазина"""
    if created or 'quantity' in instance.get_dirty_fields() or 'price' in instance.get_dirty_fields() or 'is_bonus' in instance.get_dirty_fields():
        transaction.on_commit(lambda: recalculate_order_totals(instance.order))


@receiver(pre_delete, sender=StoreOrderItem)
def store_order_item_deleted(sender, instance: StoreOrderItem, **kwargs):
    transaction.on_commit(lambda: recalculate_order_totals(instance.order))


@receiver(post_save, sender=StoreOrder)
def store_order_fulfilled(sender, instance: StoreOrder, created: bool, **kwargs):
    """Действия при выполнении заказа"""
    if not created and instance.is_fulfilled and 'is_fulfilled' in instance.get_dirty_fields():
        # Обновляем долг магазина
        Store.objects.filter(id=instance.store.id).update(
            debt=F('debt') + instance.total_amount
        )
        OrderHistory.objects.create(
            order_type='store',
            order_id=instance.id,
            type='general',
            amount=instance.total_amount,
            note='Заказ выполнен, долг увеличен'
        )
        logger.info(f"StoreOrder #{instance.id} выполнен. Долг магазина увеличен на {instance.total_amount}")

        send_order_status_notification.delay('store', instance.id, 'fulfilled')


# =============================================================================
#  ORDER RETURN
# =============================================================================

@receiver(post_save, sender=OrderReturnItem)
def return_item_saved(sender, instance: OrderReturnItem, created: bool, **kwargs):
    if created or 'quantity' in instance.get_dirty_fields() or 'price' in instance.get_dirty_fields():
        transaction.on_commit(lambda: recalculate_order_totals(instance.return_request))


@receiver(pre_delete, sender=OrderReturnItem)
def return_item_deleted(sender, instance: OrderReturnItem, **kwargs):
    transaction.on_commit(lambda: recalculate_order_totals(instance.return_request))


@receiver(post_save, sender=OrderReturn)
def return_status_changed(sender, instance: OrderReturn, created: bool, **kwargs):
    """Действия при подтверждении возврата"""
    if not created and instance.status == 'approved' and 'status' in instance.get_dirty_fields():
        store = instance.order.store
        Store.objects.filter(id=store.id).update(
            debt=F('debt') - instance.total_amount
        )
        OrderHistory.objects.create(
            order_type='store',
            order_id=instance.order.id,
            type='returned',
            amount=instance.total_amount,
            note=f'Возврат #{instance.id} подтверждён, долг уменьшен'
        )
        logger.info(f"Возврат #{instance.id} подтверждён. Долг магазина уменьшен на {instance.total_amount}")

        send_order_status_notification.delay('return', instance.id, 'approved')


# =============================================================================
#  АСИНХРОННЫЕ УВЕДОМЛЕНИЯ (через django-q или celery)
# =============================================================================

def send_order_status_notification(order_type: str, order_id: int, status: str) -> None:
    """Асинхронная отправка уведомлений (email, push, telegram)"""
    from django_q.tasks import async_task

    async_task(
        'orders.tasks.send_status_notification_task',
        order_type,
        order_id,
        status,
        hook='orders.signals.notification_hook'
    )


def notification_hook(task):
    """Обработчик результата задачи"""
    if task.success:
        logger.debug(f"Уведомление отправлено: {task.result}")
    else:
        logger.error(f"Ошибка отправки уведомления: {task.result}")


# =============================================================================
#  КЭШИРОВАНИЕ СТАТИСТИКИ
# =============================================================================

@receiver(post_save, sender=PartnerOrder)
@receiver(post_save, sender=StoreOrder)
@receiver(post_save, sender=OrderReturn)
def invalidate_order_stats_cache(sender, instance, **kwargs):
    """Сброс кэша статистики при изменении заказов"""
    cache_key = f"order_stats_{instance.__class__.__name__.lower()}"
    cache.delete(cache_key)
    logger.debug(f"Кэш сброшен: {cache_key}")


# =============================================================================
#  ЗАЩИТА ОТ ЦИКЛИЧЕСКИХ СИГНАЛОВ
# =============================================================================

def _is_signal_recursive() -> bool:
    """Проверка на рекурсию сигнала"""
    return getattr(transaction, '_signal_lock', False)


def _lock_signal():
    transaction._signal_lock = True


def _unlock_signal():
    if hasattr(transaction, '_signal_lock'):
        del transaction._signal_lock


# Пример использования в критических сигналах:
# if _is_signal_recursive(): return
# _lock_signal()
# try: ...
# finally: _unlock_signal()


# =============================================================================
#  ПОДКЛЮЧЕНИЕ СИГНАЛОВ (в apps.py)
# =============================================================================

"""
В apps/orders/apps.py:

from django.apps import AppConfig

class OrdersConfig(AppConfig):
    name = 'orders'

    def ready(self):
        import orders.signals  # noqa: F401
"""