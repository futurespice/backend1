from __future__ import annotations

import os
import uuid
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# --- Константы из settings с дефолтами по ТЗ ---
CHAT_ALLOWED_MIME = getattr(
    settings,
    "CHAT_ALLOWED_MIME",
    {"image/jpeg", "image/png", "application/pdf", "video/mp4", "audio/mpeg"},
)
CHAT_MAX_FILE_MB: int = int(getattr(settings, "CHAT_MAX_FILE_MB", 20))
CHAT_MAX_FILE_BYTES: int = CHAT_MAX_FILE_MB * 1024 * 1024


# --- helpers ---
def _attachment_upload_to(instance: "MessageAttachment", filename: str) -> str:
    # uploads/chat_attachments/YYYY/MM/DD/<chat_id>/<uuid>.<ext>
    ext = os.path.splitext(filename)[1].lower()
    return "chat_attachments/{date}/{chat}/{uid}{ext}".format(
        date=timezone.now().strftime("%Y/%m/%d"),
        chat=instance.message.chat_id if instance.message_id else "tmp",
        uid=uuid.uuid4().hex,
        ext=ext,
    )


# ==========================
#         МОДЕЛИ
# ==========================

class Chat(models.Model):
    """Диалоги по ролям из ТЗ (партнёр↔админ, партнёр↔магазин, админ↔магазин)."""

    class Kind(models.TextChoices):
        ADMIN_PARTNER = "admin_partner", "Admin ↔ Partner"
        PARTNER_STORE = "partner_store", "Partner ↔ Store"
        ADMIN_STORE = "admin_store", "Admin ↔ Store"

    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=255, blank=True)
    # Привязки к домену (store_id, city, region и т.п.) — чтобы фильтровать списки
    metadata = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_chats"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["kind"]),
            models.Index(fields=["-updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} #{self.pk}"


class ChatMember(models.Model):
    """Участник чата с ролью (для прав на удаление 'у всех' и т.п.)."""

    class RoleInChat(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        OBSERVER = "observer", "Observer"

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_memberships")
    role_in_chat = models.CharField(
        max_length=16, choices=RoleInChat.choices, default=RoleInChat.MEMBER
    )
    mute_until = models.DateTimeField(null=True, blank=True)
    # для расчёта непрочитанных
    last_read_message = models.ForeignKey(
        "Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        unique_together = ("chat", "user")

    def __str__(self) -> str:
        return f"{self.user} in chat#{self.chat_id}"


class Message(models.Model):
    """Сообщения: текст/файл/системные (без отправителя)."""

    class Type(models.TextChoices):
        TEXT = "text", "Text"
        FILE = "file", "File"
        SYSTEM = "system", "System"

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages"
    )  # null → системные

    type = models.CharField(max_length=12, choices=Type.choices, default=Type.TEXT)
    text = models.TextField(blank=True)
    reply_to = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies"
    )

    client_msg_id = models.CharField(
        max_length=64, blank=True, db_index=True
    )  # idempotency с клиента
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    # Удаление "как в Telegram"
    is_deleted_for_everyone = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="deleted_messages"
    )

    class Meta:
        indexes = [
            models.Index(fields=["chat", "-created_at"]),
            models.Index(fields=["client_msg_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["chat", "client_msg_id"],
                name="unique_client_msg_in_chat",
                condition=~models.Q(client_msg_id="")
            )
        ]

    def __str__(self) -> str:
        return f"m#{self.pk} in c#{self.chat_id}"

    @property
    def is_system(self) -> bool:
        return self.sender_id is None

    def mark_edited(self) -> None:
        self.edited_at = timezone.now()

    def clean(self) -> None:
        # Для TEXT-сообщения нужен текст (или это может быть чистый reply с пустым текстом)
        if self.type == self.Type.TEXT and not self.text and not self.reply_to_id:
            raise ValidationError("Text message must have text or be a reply.")


class HiddenMessage(models.Model):
    """Персональное скрытие сообщения ('удалить у себя')."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="hidden_for")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="hidden_messages")

    class Meta:
        unique_together = ("message", "user")


class MessageAttachment(models.Model):
    """Вложение сообщения, валидации по ТЗ."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=_attachment_upload_to)
    mime = models.CharField(max_length=64)
    size = models.PositiveBigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)  # опционально
    image_w = models.IntegerField(null=True, blank=True)
    image_h = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["mime"]), models.Index(fields=["size"])]

    def __str__(self) -> str:
        return f"att#{self.pk} m#{self.message_id} {self.mime} {self.size}B"

    def clean(self) -> None:
        # MIME строго по allow-list
        if self.mime not in CHAT_ALLOWED_MIME:
            raise ValidationError("Unsupported file type per TЗ.")
        # Размер ≤ 20MB
        size = self.size or getattr(self.file, "size", 0) or 0
        if size > CHAT_MAX_FILE_BYTES:
            raise ValidationError(f"File too large (> {CHAT_MAX_FILE_MB} MB).")

    def save(self, *args, **kwargs):
        # авто-проставление размера, если не задан
        if not self.size and self.file:
            try:
                self.size = self.file.size or 0
            except Exception:
                self.size = 0
        # всегда валидируем перед сохранением (страховка, если обойдут сериалайзер)
        self.full_clean()
        super().save(*args, **kwargs)


class MessageReceipt(models.Model):
    """Квитанции: доставлено/прочитано (для бейджей непрочитанного)."""

    class Status(models.TextChoices):
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="receipts")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="message_receipts")
    status = models.CharField(max_length=16, choices=Status.choices)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user")
        indexes = [models.Index(fields=["user", "message"])]

    def __str__(self) -> str:
        return f"rcpt {self.status} m#{self.message_id} by u#{self.user_id}"


# ==========================
#       СИГНАЛЫ (минимум)
# ==========================

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=Message)
def _touch_chat_on_message(sender, instance: Message, created: bool, **kwargs):
    """Обновляем updated_at чата при новых сообщениях и ставим READ для автора."""
    if created:
        Chat.objects.filter(pk=instance.chat_id).update(updated_at=instance.created_at)
        if instance.sender_id:
            MessageReceipt.objects.update_or_create(
                message=instance, user_id=instance.sender_id,
                defaults={"status": MessageReceipt.Status.READ}
            )
