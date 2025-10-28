# apps/orders/signals.py
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Order, OrderReturn
from users.services import EmailService
import logging

logger = logging.getLogger(__name__)



@receiver(pre_save, sender=Order)
def cache_old_order_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.only('status').get(pk=instance.pk)
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Order)
def notify_on_order_action(sender, instance, created, **kwargs):
    # получатель
    user = getattr(getattr(instance, "store", None), "created_by", None)
    if not user or not getattr(user, "email", None):
        logger.warning("Skip email: no recipient for order %s", instance.pk)
        return

    if created:
        # новый заказ
        try:
            EmailService.send_approval_notification(
                user=user,
                is_approved=False,
                subject='Новый заказ',
                body=f"Заказ {instance.id} создан для "
                     f"{getattr(instance.store, 'name', getattr(instance.store, 'store_name', 'магазина'))}. "
                     f"Сумма: {instance.total_amount} сом."
            )
        except Exception as e:
            logger.exception("notify_on_order_action(create) failed: %s", e)
        return

    # изменение статуса
    old_status = getattr(instance, "_old_status", None)
    if old_status and old_status != instance.status:

        def _send():
            try:
                if instance.status == 'confirmed':
                    EmailService.send_approval_notification(
                        user=user,
                        is_approved=True,
                        subject='Заказ подтвержден',
                        body=f"Заказ {instance.id} подтвержден. Сумма: {instance.total_amount} сом."
                    )
                elif instance.status == 'rejected':
                    EmailService.send_approval_notification(
                        user=user,
                        is_approved=False,
                        subject='Заказ отклонен',
                        body=f"Заказ {instance.id} отклонен."
                    )
            except Exception as e:
                logger.exception("notify_on_order_action(status change) failed: %s", e)

        transaction.on_commit(_send)


# ---------- OrderReturn ----------

@receiver(pre_save, sender=OrderReturn)
def cache_old_return_status(sender, instance, **kwargs):
    # кэшируем старый статус возврата до сохранения
    if instance.pk:
        try:
            old = sender.objects.only('status').get(pk=instance.pk)
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=OrderReturn)
def notify_on_return_action(sender, instance, created, **kwargs):
    user = getattr(getattr(getattr(instance, "order", None), "store", None), "created_by", None)
    if not user or not getattr(user, "email", None):
        logger.warning("Skip email: no recipient for order return %s", instance.pk)
        return

    if created:
        try:
            EmailService.send_approval_notification(
                user=user,
                is_approved=False,
                subject='Создан запрос на возврат',
                body=f"Создан запрос на возврат для заказа {instance.order.id}. "
                     f"Причина: {instance.reason}"
            )
        except Exception as e:
            logger.exception("notify_on_return_action(create) failed: %s", e)
        return

    old_status = getattr(instance, "_old_status", None)
    if old_status and old_status != instance.status and instance.status == 'approved':

        def _send():
            try:
                EmailService.send_approval_notification(
                    user=user,
                    is_approved=True,
                    subject='Возврат подтвержден',
                    body=f"Возврат для заказа {instance.order.id} подтвержден. "
                         f"Сумма: {instance.total_amount} сом."
                )
            except Exception as e:
                logger.exception("notify_on_return_action(approved) failed: %s", e)

        transaction.on_commit(_send)
