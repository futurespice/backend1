# apps/notifications/admin.py

from django.contrib import admin

from .models import Notification, NotificationChannel, NotificationType


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "title",
        "type",
        "channel",
        "is_read",
        "created_at",
        "read_at",
    )
    list_filter = ("type", "channel", "is_read", "created_at")
    search_fields = ("title", "message", "user__phone", "user__email")
    readonly_fields = ("created_at", "read_at")
