# apps/messaging/serializers.py

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import ChatThread, Message, MessageType

User = get_user_model()


class UserShortSerializer(serializers.ModelSerializer):
    """
    Минимальная информация о пользователе в чатах.
    """

    class Meta:
        model = User
        fields = ("id", "phone", "full_name", "role")
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    sender = UserShortSerializer(read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Message
        fields = (
            "id",
            "thread",
            "sender",
            "type",
            "type_display",
            "text",
            "attachment",
            "sticker_code",
            "is_read",
            "read_at",
            "created_at",
        )
        read_only_fields = (
            "id",
            "thread",
            "sender",
            "is_read",
            "read_at",
            "created_at",
        )


class MessageCreateSerializer(serializers.ModelSerializer):
    """
    Создание сообщения в существующем чате.
    """

    class Meta:
        model = Message
        fields = ("type", "text", "attachment", "sticker_code")

    def validate(self, attrs):
        msg_type = attrs.get("type") or MessageType.TEXT

        if msg_type == MessageType.TEXT and not attrs.get("text"):
            raise serializers.ValidationError("Текст обязателен для text сообщения.")
        if msg_type in (MessageType.IMAGE, MessageType.FILE) and not attrs.get("attachment"):
            raise serializers.ValidationError("Файл обязателен для этого типа сообщения.")
        if msg_type == MessageType.STICKER and not attrs.get("sticker_code"):
            raise serializers.ValidationError("Код стикера обязателен.")
        return attrs


class ChatThreadSerializer(serializers.ModelSerializer):
    participants = UserShortSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatThread
        fields = (
            "id",
            "participants",
            "last_message",
            "unread_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_last_message(self, obj: ChatThread):
        msg = obj.last_message
        if not msg:
            return None
        return MessageSerializer(msg).data

    def get_unread_count(self, obj: ChatThread):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return 0
        return obj.messages.filter(is_read=False).exclude(sender=user).count()


class ChatThreadCreateSerializer(serializers.Serializer):
    """
    Создание/открытие диалога.

    Вход:
        {
          "user_id": 123
        }
    """

    user_id = serializers.IntegerField()

    def validate_user_id(self, value):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Требуется аутентификация.")

        if user.id == value:
            raise serializers.ValidationError("Нельзя открыть чат с самим собой.")

        try:
            other = User.objects.get(id=value, is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь не найден.")

        # проверку ролей делаем в сервисе
        return value
