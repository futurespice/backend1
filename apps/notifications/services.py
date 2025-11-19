# apps/notifications/services.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import Notification, NotificationChannel, NotificationType

User = get_user_model()


@dataclass
class NotificationPayload:
    user: User
    title: str
    message: str
    type: str = NotificationType.INFO
    channel: str = NotificationChannel.IN_APP
    payload: Optional[dict] = None


class NotificationService:
    """
    Единая точка создания уведомлений.

    Использование:
        NotificationService.create(
            user=user,
            title="Новый заказ",
            message="У вас новый заказ",
            type=NotificationType.ORDER,
        )
    """

    @classmethod
    @transaction.atomic
    def create(
        cls,
        *,
        user: User,
        title: str,
        message: str,
        type: str = NotificationType.INFO,
        channel: str = NotificationChannel.IN_APP,
        payload: Optional[dict] = None,
    ) -> Notification:
        notification = Notification.objects.create(
            user=user,
            title=title,
            message=message,
            type=type,
            channel=channel,
            payload=payload or {},
        )

        # Немедленная отправка email при channel=email
        if channel == NotificationChannel.EMAIL and user.email:
            cls._send_email_notification(user, title, message)

        return notification

    @classmethod
    @transaction.atomic
    def bulk_create_for_users(
        cls,
        users: Iterable[User],
        *,
        title: str,
        message: str,
        type: str = NotificationType.INFO,
        channel: str = NotificationChannel.IN_APP,
        payload: Optional[dict] = None,
    ) -> list[Notification]:
        now = timezone.now()
        users_list = list(users)

        notifications = [
            Notification(
                user=u,
                title=title,
                message=message,
                type=type,
                channel=channel,
                payload=payload or {},
                created_at=now,
            )
            for u in users_list
        ]
        created = Notification.objects.bulk_create(notifications)

        if channel == NotificationChannel.EMAIL:
            for u in users_list:
                if u.email:
                    cls._send_email_notification(u, title, message)

        return created

    # ----- low-level helpers -------------------------------------------------

    @staticmethod
    def _send_email_notification(user: User, title: str, message: str) -> None:
        """
        Простейшая отправка email. В реальном проде можно заменить на Celery.
        """
        try:
            if not user.email:
                return
            send_mail(
                subject=title,
                message=message,
                from_email=None,  # возьмётся DEFAULT_FROM_EMAIL
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            # не роняем бизнес-логику из-за ошибки email
            pass

    # ----- high-level сценарии (под проект БайЭл) ----------------------------

    @classmethod
    def notify_admins_new_store(cls, store) -> None:
        """
        Новый магазин отправил заявку — уведомляем админов.
        """
        from users.models import User  # локальный импорт, чтобы избежать циклов

        admins = User.objects.filter(is_active=True, role="admin")
        title = "Новая заявка магазина"
        message = f"Новый магазин '{store.name}' отправил заявку на модерацию."
        payload = {"store_id": store.id}
        cls.bulk_create_for_users(
            admins,
            title=title,
            message=message,
            type=NotificationType.STORE,
            channel=NotificationChannel.IN_APP,
            payload=payload,
        )

    @classmethod
    def notify_store_approved(cls, store) -> None:
        """
        Магазин одобрен — уведомляем владельца/пользователей магазина.
        """
        from stores.models import StoreSelection  # если нужны пользователи магазина

        users_qs = StoreSelection.objects.filter(store=store).select_related("user")
        users = [obj.user for obj in users_qs]
        if not users:
            owner = getattr(store, "created_by", None)
            if owner:
                users = [owner]

        if not users:
            return

        title = "Магазин одобрен"
        message = f"Ваш магазин '{store.name}' был одобрен администратором."
        payload = {"store_id": store.id}
        cls.bulk_create_for_users(
            users,
            title=title,
            message=message,
            type=NotificationType.STORE,
            channel=NotificationChannel.IN_APP,
            payload=payload,
        )

    @classmethod
    def notify_store_rejected(cls, store, reason: str = "") -> None:
        """
        Магазин отклонён — уведомляем владельца/пользователей магазина.
        """
        from stores.models import StoreSelection

        users_qs = StoreSelection.objects.filter(store=store).select_related("user")
        users = [obj.user for obj in users_qs]
        if not users:
            owner = getattr(store, "created_by", None)
            if owner:
                users = [owner]

        if not users:
            return

        title = "Магазин отклонён"
        message = (
            f"Ваш магазин '{store.name}' был отклонён."
            + (f" Причина: {reason}" if reason else "")
        )
        payload = {"store_id": store.id, "reason": reason}
        cls.bulk_create_for_users(
            users,
            title=title,
            message=message,
            type=NotificationType.WARNING,
            channel=NotificationChannel.IN_APP,
            payload=payload,
        )

    @classmethod
    def notify_partner_new_order(cls, store_order) -> None:
        """
        Новый заказ магазина — уведомляем партнёра.
        """
        partner = getattr(store_order, "partner", None)
        if not partner:
            return

        title = "Новый заказ магазина"
        message = (
            f"Магазин '{store_order.store.name}' создал новый заказ "
            f"№{store_order.id} на сумму {store_order.total_amount}."
        )
        payload = {"store_order_id": store_order.id}
        cls.create(
            user=partner,
            title=title,
            message=message,
            type=NotificationType.ORDER,
            channel=NotificationChannel.IN_APP,
            payload=payload,
        )

    @classmethod
    def mark_as_read(cls, notification: Notification) -> Notification:
        """
        Отметить уведомление как прочитанное.
        """
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
        return notification

    @classmethod
    def mark_all_as_read(cls, user: User) -> int:
        """
        Отметить все уведомления пользователя как прочитанные.

        Возвращает количество обновлённых записей.
        """
        now = timezone.now()
        updated = (
            Notification.objects.filter(user=user, is_read=False)
            .update(is_read=True, read_at=now)
        )
        return updated
