# from django.contrib.auth import get_user_model
# from django.utils import timezone
# from .models import Notification
#
# User = get_user_model()
#
#
# class NotificationService:
#     """Сервис создания уведомлений"""
#
#     @staticmethod
#     def create_notification(recipient, type, title, message, related_object=None):
#         """Создать уведомление"""
#
#         notification_data = {
#             'recipient': recipient,
#             'type': type,
#             'title': title,
#             'message': message,
#         }
#
#         if related_object:
#             notification_data['related_object_type'] = related_object.__class__.__name__.lower()
#             notification_data['related_object_id'] = related_object.id
#
#         return Notification.objects.create(**notification_data)
#
#     @staticmethod
#     def notify_admins_new_store(store):
#         """Уведомить админов о новом магазине"""
#         admins = User.objects.filter(role='admin', is_active=True)
#
#         for admin in admins:
#             NotificationService.create_notification(
#                 recipient=admin,
#                 type='store_registered',
#                 title='Новая заявка на регистрацию магазина',
#                 message=f'Магазин "{store.store_name}" ожидает одобрения',
#                 related_object=store
#             )
#
#     @staticmethod
#     def notify_store_approved(store):
#         """Уведомить владельца об одобрении"""
#         NotificationService.create_notification(
#             recipient=store.user,
#             type='store_approved',
#             title='Ваш магазин одобрен! 🎉',
#             message=f'Магазин "{store.store_name}" успешно одобрен. Теперь вы можете делать заказы.',
#             related_object=store
#         )
#
#     @staticmethod
#     def notify_store_rejected(store):
#         """Уведомить владельца об отклонении"""
#         NotificationService.create_notification(
#             recipient=store.user,
#             type='store_rejected',
#             title='Заявка отклонена',
#             message=f'Магазин "{store.store_name}" отклонён. Причина: {store.rejection_reason}',
#             related_object=store
#         )
#
#     @staticmethod
#     def notify_partner_new_order(partner, order):
#         """Уведомить партнёра о новом заказе"""
#         NotificationService.create_notification(
#             recipient=partner,
#             type='new_order',
#             title='Новый заказ',
#             message=f'Магазин "{order.store.store_name}" создал заказ на сумму {order.total_amount}',
#             related_object=order
#         )