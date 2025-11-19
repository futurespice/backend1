# apps/notifications/serializers.py

from rest_framework import serializers

from .models import Notification, NotificationChannel, NotificationType


class NotificationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для чтения уведомлений пользователем.
    """

    type_display = serializers.CharField(source="get_type_display", read_only=True)
    channel_display = serializers.CharField(
        source="get_channel_display", read_only=True
    )

    class Meta:
        model = Notification
        fields = (
            "id",
            "title",
            "message",
            "type",
            "type_display",
            "channel",
            "channel_display",
            "payload",
            "is_read",
            "read_at",
            "created_at",
        )
        read_only_fields = fields


class NotificationCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания уведомления (используется админом/сервисами).
    """

    class Meta:
        model = Notification
        fields = (
            "user",
            "title",
            "message",
            "type",
            "channel",
            "payload",
        )

    def validate_type(self, value):
        if value not in NotificationType.values:
            raise serializers.ValidationError("Некорректный тип уведомления")
        return value

    def validate_channel(self, value):
        if value not in NotificationChannel.values:
            raise serializers.ValidationError("Некорректный канал уведомления")
        return value
