# apps/messaging/consumers.py

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from .models import ChatThread


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket для real-time чатов.

    Подключение:
      ws://…/ws/chat/{thread_id}/

    Логика:
    - проверяем, что user аутентифицирован и является участником чата;
    - подписываем на группу chat_{thread_id};
    - отправка сообщений в группу делается из MessagingService._broadcast_message.
    """

    async def connect(self):
        user = self.scope.get("user") or AnonymousUser()
        if not user.is_authenticated:
            await self.close()
            return

        self.thread_id = self.scope["url_route"]["kwargs"].get("thread_id")
        if not self.thread_id:
            await self.close()
            return

        if not await self._user_in_thread(user, self.thread_id):
            await self.close()
            return

        self.group_name = f"chat_{self.thread_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """
        На этом этапе можно было бы реализовать отправку сообщений через WebSocket.
        Сейчас отправка идёт через REST, а WS используется для доставки новых сообщений.
        """
        # можно игнорировать или реализовать echo/command
        pass

    async def chat_message(self, event):
        """
        Handler для события group_send(type="chat.message").
        """
        data = event.get("data") or {}
        await self.send_json(data)

    # ---- helpers ------------------------------------------------------------

    @database_sync_to_async
    def _user_in_thread(self, user, thread_id: int) -> bool:
        try:
            t = ChatThread.objects.get(id=thread_id)
        except ChatThread.DoesNotExist:
            return False

        if getattr(user, "role", None) == "admin" or user.is_superuser:
            return True
        return t.participants.filter(id=user.id).exists()
