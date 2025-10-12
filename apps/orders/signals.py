from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order, OrderReturn
from users.services import EmailService


@receiver(post_save, sender=Order)
def notify_on_order_action(sender, instance, created, **kwargs):
    if created:
        EmailService.send_approval_notification(
            user=instance.store.created_by,
            is_approved=False,
            subject='Новый заказ создан',
            message=f"Заказ {instance.id} создан для {instance.store.name}. Сумма: {instance.total_amount} сом."
        )
    elif instance.status == 'confirmed':
        EmailService.send_approval_notification(
            user=instance.store.created_by,
            is_approved=True,
            subject='Заказ подтвержден',
            message=f"Заказ {instance.id} подтвержден. Сумма: {instance.total_amount} сом."
        )
    elif instance.status == 'rejected':
        EmailService.send_approval_notification(
            user=instance.store.created_by,
            is_approved=False,
            subject='Заказ отклонен',
            message=f"Заказ {instance.id} отклонен."
        )


@receiver(post_save, sender=OrderReturn)
def notify_on_return_action(sender, instance, created, **kwargs):
    if created:
        EmailService.send_approval_notification(
            user=instance.order.store.created_by,
            is_approved=False,
            subject='Новый запрос на возврат',
            message=f"Создан запрос на возврат для заказа {instance.order.id}. Причина: {instance.reason}"
        )
    elif instance.status == 'approved':
        EmailService.send_approval_notification(
            user=instance.order.store.created_by,
            is_approved=True,
            subject='Возврат подтвержден',
            message=f"Возврат для заказа {instance.order.id} подтвержден. Сумма: {instance.total_amount} сом."
        )