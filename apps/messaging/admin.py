from django.contrib import admin
from .models import ChatRoom, Message, Notification


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ['name', 'room_type', 'participants_count', 'is_active', 'created_at']
    list_filter = ['room_type', 'is_active']
    filter_horizontal = ['participants']

    def participants_count(self, obj):
        return obj.participants.count()

    participants_count.short_description = 'Участников'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['chat_room', 'sender', 'message_type', 'content_preview', 'is_read', 'created_at']
    list_filter = ['message_type', 'is_read', 'created_at']
    search_fields = ['content', 'sender__name']

    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content

    content_preview.short_description = 'Содержимое'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'message', 'recipient__name']
