from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Chat,
    ChatMember,
    Message,
    MessageAttachment,
    MessageReceipt,
    HiddenMessage,
)


# -----------------------------
#   helpers / list filters
# -----------------------------
class CityFilter(admin.SimpleListFilter):
    title = "Город (metadata.city)"
    parameter_name = "meta_city"

    def lookups(self, request, model_admin):
        qs = model_admin.get_queryset(request)
        # соберём уникальные города из metadata
        cities = (
            qs.exclude(metadata__city__isnull=True)
              .values_list("metadata__city", flat=True)
              .distinct()
              .order_by("metadata__city")
        )
        return [(c, c) for c in cities if c]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(metadata__city=value)
        return queryset


class RegionFilter(admin.SimpleListFilter):
    title = "Регион (metadata.region)"
    parameter_name = "meta_region"

    def lookups(self, request, model_admin):
        qs = model_admin.get_queryset(request)
        regions = (
            qs.exclude(metadata__region__isnull=True)
              .values_list("metadata__region", flat=True)
              .distinct()
              .order_by("metadata__region")
        )
        return [(r, r) for r in regions if r]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(metadata__region=value)
        return queryset


# -----------------------------
#   Inlines
# -----------------------------
class ChatMemberInline(admin.TabularInline):
    model = ChatMember
    extra = 0
    autocomplete_fields = ["user"]
    readonly_fields = ["last_read_message"]
    fields = ("user", "role_in_chat", "mute_until", "last_read_message")


class MessageAttachmentInline(admin.TabularInline):
    model = MessageAttachment
    extra = 0
    fields = ("file", "mime", "size", "image_w", "image_h")
    readonly_fields = ("mime", "size", "image_w", "image_h")

    def has_add_permission(self, request, obj=None):
        # вложения создаются только через API
        return False


class MessageReceiptInline(admin.TabularInline):
    model = MessageReceipt
    extra = 0
    readonly_fields = ("user", "status", "timestamp")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# -----------------------------
#   Admin: Chat
# -----------------------------
@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "kind",
        "title",
        "city",
        "region",
        "created_by_link",
        "updated_at",
    )
    list_filter = ("kind", CityFilter, RegionFilter)
    search_fields = ("id", "title", "metadata")
    autocomplete_fields = ["created_by"]
    inlines = [ChatMemberInline]
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("created_by")

    # удобные колонки по metadata
    def city(self, obj: Chat):
        return (obj.metadata or {}).get("city", "")

    def region(self, obj: Chat):
        return (obj.metadata or {}).get("region", "")

    @admin.display(description="Создал")
    def created_by_link(self, obj: Chat):
        if not obj.created_by_id:
            return "-"
        return format_html(
            '<a href="/admin/{app_label}/{model}/{pk}/change/">{name}</a>',
            app_label=obj.created_by._meta.app_label,
            model=obj.created_by._meta.model_name,
            pk=obj.created_by_id,
            name=getattr(obj.created_by, "email", str(obj.created_by)),
        )


# -----------------------------
#   Admin: Message
# -----------------------------
@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "chat_id",
        "chat_kind",
        "sender_id",
        "type",
        "short_text",
        "created_at",
        "edited_at",
        "is_deleted_for_everyone",
    )
    list_filter = ("type", "is_deleted_for_everyone")
    search_fields = ("id", "text", "client_msg_id")
    date_hierarchy = "created_at"
    autocomplete_fields = ["chat", "sender", "reply_to", "deleted_by"]
    readonly_fields = ("created_at", "edited_at", "client_msg_id", "deleted_by")
    inlines = [MessageAttachmentInline, MessageReceiptInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("chat", "sender", "reply_to", "deleted_by")

    # удобные колонки
    @admin.display(description="Кинд чата")
    def chat_kind(self, obj: Message):
        return obj.chat.kind if obj.chat_id else "-"

    @admin.display(description="Текст")
    def short_text(self, obj: Message):
        if obj.is_deleted_for_everyone:
            return "— удалено у всех —"
        return (obj.text or "")[:80]

    # actions
    actions = ["mark_deleted_for_everyone"]

    @admin.action(description="Удалить выбранные сообщения для всех")
    def mark_deleted_for_everyone(self, request, queryset):
        updated = queryset.update(is_deleted_for_everyone=True)
        self.message_user(request, f"Помечено как удалённое у всех: {updated}")


# -----------------------------
#   Admin: MessageAttachment
# -----------------------------
@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message_id", "mime", "size", "image_w", "image_h", "file")
    list_filter = ("mime",)
    search_fields = ("id", "message__id")
    autocomplete_fields = ["message"]
    readonly_fields = ("mime", "size", "image_w", "image_h")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("message")


# -----------------------------
#   Admin: ChatMember
# -----------------------------
@admin.register(ChatMember)
class ChatMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "chat_id", "user_id", "role_in_chat", "mute_until", "last_read_message_id")
    list_filter = ("role_in_chat",)
    search_fields = ("chat__id", "user__id")
    autocomplete_fields = ["chat", "user", "last_read_message"]


# -----------------------------
#   Admin: MessageReceipt
# -----------------------------
@admin.register(MessageReceipt)
class MessageReceiptAdmin(admin.ModelAdmin):
    list_display = ("id", "message_id", "user_id", "status", "timestamp")
    list_filter = ("status",)
    search_fields = ("message__id", "user__id")
    autocomplete_fields = ["message", "user"]
    readonly_fields = ("timestamp",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("message", "user")


# -----------------------------
#   Admin: HiddenMessage
# -----------------------------
@admin.register(HiddenMessage)
class HiddenMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "message_id", "user_id")
    search_fields = ("message__id", "user__id")
    autocomplete_fields = ["message", "user"]
