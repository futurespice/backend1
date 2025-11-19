# apps/messaging/services.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from notifications.services import NotificationService
from notifications.models import NotificationType
from .models import ChatThread, Message, MessageType

User = get_user_model()


@dataclass
class MessagePayload:
    type: str
    text: str | None = None
    attachment = None
    sticker_code: str | None = None


class MessagingService:
    """
    Сервис чатов с бизнес-правилами ролей.

    Роли:
    - admin ↔ любой
    - partner ↔ admin / store
    - store ↔ admin / partner
    """

    # ----- роли --------------------------------------------------------------

    @staticmethod
    def _validate_roles(user1: User, user2: User) -> None:
        r1 = getattr(user1, "role", None)
        r2 = getattr(user2, "role", None)

        # admin может со всеми
        if r1 == "admin" or r2 == "admin":
            return

        # partner <-> store (в обе стороны) — ОК
        if {r1, r2} == {"partner", "store"}:
            return

        # store-store нельзя
        if r1 == "store" and r2 == "store":
            raise ValidationError("Магазины не могут общаться между собой.")

        # partner-partner нельзя
        if r1 == "partner" and r2 == "partner":
            raise ValidationError("Партнёры не могут общаться между собой.")

        # прочие комбинации считаем невозможными
        raise ValidationError("Данная комбинация ролей не поддерживается для чата.")

    # ----- чаты --------------------------------------------------------------

    @classmethod
    @transaction.atomic
    def get_or_create_thread(cls, user1: User, user2: User) -> ChatThread:
        if user1.id == user2.id:
            raise ValidationError("Нельзя открыть чат с самим собой.")

        cls._validate_roles(user1, user2)

        # ищем существующий 1-1 чат с этими двумя
        existing = (
            ChatThread.objects.filter(participants=user1)
            .filter(participants=user2)
            .distinct()
            .first()
        )
        if existing:
            return existing

        thread = ChatThread.objects.create()
        thread.participants.add(user1, user2)
        return thread

    @classmethod
    @transaction.atomic
    def send_message(
        cls,
        *,
        thread: ChatThread,
        sender: User,
        msg_type: str,
        text: Optional[str] = None,
        attachment=None,
        sticker_code: Optional[str] = None,
    ) -> Message:
        # проверка участия
        if not thread.participants.filter(id=sender.id).exists():
            raise ValidationError("Пользователь не является участником чата.")

        # проверка ролей между участниками чата
        participants = list(thread.participants.all())
        if len(participants) == 2:
            other = participants[0] if participants[1].id == sender.id else participants[1]
            cls._validate_roles(sender, other)

        message = Message.objects.create(
            thread=thread,
            sender=sender,
            type=msg_type,
            text=text or "",
            attachment=attachment,
            sticker_code=sticker_code or "",
        )

        # уведомление получателю
        cls._notify_new_message(message)

        # WebSocket broadcast
        cls._broadcast_message(message)

        # обновим updated_at
        ChatThread.objects.filter(id=thread.id).update(updated_at=message.created_at)

        return message

    # ----- уведомления / WS --------------------------------------------------

    @staticmethod
    def _notify_new_message(message: Message) -> None:
        participants = list(message.thread.participants.all())
        for user in participants:
            if user.id == message.sender_id:
                continue
            title = "Новое сообщение"
            snippet = message.text or "[файл]" if message.attachment else ""
            NotificationService.create(
                user=user,
                title=title,
                message=f"Новое сообщение от {message.sender.full_name or message.sender.phone}: {snippet}",
                type=NotificationType.INFO,
                channel="in_app",
                payload={"thread_id": message.thread_id, "message_id": message.id},
            )

    @staticmethod
    def _broadcast_message(message: Message) -> None:
        """
        Шлём сообщение во websocket-группу chat_{thread_id}.
        """
        layer = get_channel_layer()
        if not layer:
            return

        from .serializers import MessageSerializer  # локальный импорт для избежания циклов

        data = MessageSerializer(message).data
        async_to_sync(layer.group_send)(
            f"chat_{message.thread_id}",
            {"type": "chat.message", "data": data},
        )
