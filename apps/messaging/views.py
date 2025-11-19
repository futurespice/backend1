# apps/messaging/views.py

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.contrib.auth import get_user_model

from .models import ChatThread, Message
from .permissions import IsThreadParticipant
from .serializers import (
    ChatThreadCreateSerializer,
    ChatThreadSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)
from .services import MessagingService

User = get_user_model()


class ChatThreadViewSet(viewsets.ModelViewSet):
    """
    Чаты (диалоги).

    - list: список чатов пользователя
    - POST /threads/open/ — открыть/создать чат с пользователем
    - GET /threads/{id}/messages/ — список сообщений
    - POST /threads/{id}/send/ — отправка сообщения
    """

    queryset = ChatThread.objects.all().prefetch_related("participants")
    serializer_class = ChatThreadSerializer
    permission_classes = [IsAuthenticated, IsThreadParticipant]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if getattr(user, "role", None) == "admin" or user.is_superuser:
            return qs
        return qs.filter(participants=user)

    def get_serializer_class(self):
        if self.action == "open":
            return ChatThreadCreateSerializer
        return super().get_serializer_class()

    def perform_destroy(self, instance):
        # при необходимости можно ограничить удаление только админам
        return super().perform_destroy(instance)

    # ----- кастомные действия ------------------------------------------------

    @action(detail=False, methods=["post"], url_path="open")
    def open_thread(self, request):
        """
        Открыть/создать диалог с пользователем.

        Вход:
            { "user_id": <id> }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        other_user_id = serializer.validated_data["user_id"]
        other_user = get_object_or_404(User, id=other_user_id, is_active=True)

        thread = MessagingService.get_or_create_thread(request.user, other_user)
        return Response(ChatThreadSerializer(thread, context={"request": request}).data)

    @action(
        detail=True,
        methods=["get"],
        url_path="messages",
    )
    def list_messages(self, request, pk=None):
        """
        Список сообщений в чате.

        /messaging/threads/{id}/messages/
        """
        thread = self.get_object()
        messages = thread.messages.select_related("sender").order_by("created_at")
        page = self.paginate_queryset(messages)
        serializer = MessageSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path="send",
    )
    def send_message(self, request, pk=None):
        """
        Отправить сообщение в чат.

        Поддерживаются:
        - text (type=text, text)
        - image/file (type=image/file + attachment)
        - sticker (type=sticker + sticker_code)
        """

        thread = self.get_object()
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        msg = MessagingService.send_message(
            thread=thread,
            sender=request.user,
            msg_type=data.get("type"),
            text=data.get("text"),
            attachment=data.get("attachment"),
            sticker_code=data.get("sticker_code"),
        )
        return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)
