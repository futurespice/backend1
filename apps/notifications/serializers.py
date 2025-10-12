from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Сериализатор уведомлений"""

    type_display = serializers.CharField(source='get_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'type', 'type_display', 'title', 'message',
            'related_object_type', 'related_object_id',
            'is_read', 'read_at', 'created_at'
        ]
        read_only_fields = ['created_at']