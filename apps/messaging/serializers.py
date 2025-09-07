from __future__ import annotations

from typing import Iterable

from django.conf import settings

from rest_framework import serializers

from .models import (
    Chat,
    ChatMember,
    Message,
    MessageAttachment,
    MessageReceipt,
    HiddenMessage,
)

# Константы из settings (с дефолтами на случай отсутствия)
CHAT_ALLOWED_MIME = getattr(
    settings,
    "CHAT_ALLOWED_MIME",
    {"image/jpeg", "image/png", "application/pdf", "video/mp4", "audio/mpeg"},
)
CHAT_MAX_FILE_MB: int = int(getattr(settings, "CHAT_MAX_FILE_MB", 20))
CHAT_MAX_FILE_BYTES: int = CHAT_MAX_FILE_MB * 1024 * 1024


# -----------------------------
#        ATTACHMENTS
# -----------------------------
class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageAttachment
        fields = ("id", "mime", "size", "file", "image_w", "image_h")


# -----------------------------
#        MESSAGES (read)
# -----------------------------
class MessageSerializer(serializers.ModelSerializer):
    attachments = AttachmentSerializer(many=True, read_only=True)
    sender_id = serializers.IntegerField(source="sender.id", read_only=True)
    is_own = serializers.SerializerMethodField()
    is_deleted = serializers.SerializerMethodField()
    reply_to = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            "id",
            "chat",
            "sender_id",
            "type",
            "text",
            "reply_to",
            "created_at",
            "edited_at",
            "is_deleted_for_everyone",
            "is_deleted",
            "is_own",
            "attachments",
        )

    def get_is_own(self, obj: Message) -> bool:
        user = self._user()
        return bool(user and obj.sender_id == user.id)

    def get_is_deleted(self, obj: Message) -> bool:
        """Клиенту удобно иметь единый флаг с учётом 'удалить у себя'."""
        if obj.is_deleted_for_everyone:
            return True
        user = self._user()
        if not user:
            return False
        return HiddenMessage.objects.filter(message=obj, user=user).exists()

    def get_reply_to(self, obj: Message):
        if not obj.reply_to_id:
            return None
        # отдаём минимальный слепок reply
        rt = obj.reply_to
        return {
            "id": rt.id,
            "sender_id": rt.sender_id,
            "type": rt.type,
            "text": (rt.text[:120] if rt.text else ""),
        }

    def to_representation(self, instance: Message):
        data = super().to_representation(instance)
        # Если удалено у всех — не отдаём текст и вложения
        if instance.is_deleted_for_everyone:
            data["text"] = ""
            data["attachments"] = []
        return data

    # helpers
    def _user(self):
        req = self.context.get("request")
        return getattr(req, "user", None) if req else None


# -----------------------------
#     MESSAGES (create)
# -----------------------------
class MessageCreateSerializer(serializers.Serializer):
    """Приём нового сообщения с файлами."""
    text = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    reply_to = serializers.IntegerField(required=False)
    client_msg_id = serializers.CharField(required=False, allow_blank=True)
    files = serializers.ListField(
        child=serializers.FileField(allow_empty_file=False),
        required=False,
        allow_empty=True,
    )

    def validate_files(self, files: Iterable) -> Iterable:
        for f in files:
            ctype = getattr(f, "content_type", None)
            size = getattr(f, "size", 0) or 0
            if not ctype or ctype not in CHAT_ALLOWED_MIME:
                raise serializers.ValidationError(
                    f"Unsupported file type. Allowed: {', '.join(sorted(CHAT_ALLOWED_MIME))}"
                )
            if size > CHAT_MAX_FILE_BYTES:
                raise serializers.ValidationError(f"Max {CHAT_MAX_FILE_MB} MB per file.")
        return files


# -----------------------------
#            CHATS
# -----------------------------
class ChatSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    unread = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ("id", "kind", "title", "metadata", "updated_at", "last_message", "unread")

    def get_last_message(self, obj: Chat):
        user = self._user()
        qs = obj.messages.exclude(is_deleted_for_everyone=True)
        if user:
            qs = qs.exclude(hidden_for__user=user)
        m = qs.select_related("sender").order_by("-created_at").first()
        return MessageSerializer(m, context=self.context).data if m else None

    def get_unread(self, obj: Chat) -> int:
        """Считаем непрочитанные для текущего пользователя, исключая 'удалено у меня'."""
        user = self._user()
        if not user:
            return 0
        member = ChatMember.objects.filter(chat=obj, user=user).only("last_read_message_id").first()
        if not member:
            return 0
        last_id = member.last_read_message_id or 0
        return obj.messages.filter(id__gt=last_id).exclude(hidden_for__user=user).count()

    def get_peer(self, obj: Chat):
        user = getattr(self.context.get("request"), "user", None)
        if not user: return None
        member = obj.members.select_related("user").exclude(user=user).first()
        if not member: return None
        u = member.user
        # предполагаем у User: name, second_name, phone, role, date_joined, last_login
        name = f"{getattr(u,'name','')} {getattr(u,'second_name','')}".strip()
        peer = {
            "id": u.id,
            "name": name or getattr(u,"username", ""),
            "phone": getattr(u, "phone", ""),
            "role": getattr(u, "role", ""),
            "registered_at": getattr(u, "date_joined", None),
            "last_login": getattr(u, "last_login", None),
        }
        # для магазинов подтянем метаданные (если есть)
        meta = obj.metadata or {}
        for k in ("store_name","inn","region","city"):
            if k in meta: peer[k] = meta[k]
        return peer

    def _user(self):
        req = self.context.get("request")
        return getattr(req, "user", None) if req else None


# -----------------------------
#     (optional) MEMBERS
# -----------------------------
class ChatMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = ChatMember
        fields = ("id", "chat", "user_id", "role_in_chat", "last_read_message")
