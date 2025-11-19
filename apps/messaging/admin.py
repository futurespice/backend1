# apps/messaging/admin.py

from django.contrib import admin

from .models import ChatThread, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("created_at", "sender", "type", "text", "attachment", "sticker_code")


@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "participants_list", "created_at", "updated_at")
    search_fields = ("id", "participants__phone", "participants__email")
    inlines = [MessageInline]

    def participants_list(self, obj):
        return ", ".join(
            f"{u.id}:{u.phone or u.email}" for u in obj.participants.all()
        )


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "thread",
        "sender",
        "type",
        "short_text",
        "attachment",
        "is_read",
        "created_at",
    )
    list_filter = ("type", "is_read", "created_at")
    search_fields = ("text", "sender__phone", "sender__email")
    readonly_fields = ("created_at",)

    def short_text(self, obj):
        if not obj.text:
            return ""
        return obj.text[:40] + ("..." if len(obj.text) > 40 else "")
