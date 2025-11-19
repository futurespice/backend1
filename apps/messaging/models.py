# apps/messaging/models.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def validate_attachment_size(file):
    if not file:
        return
    if file.size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            _(f"Максимальный размер файла {MAX_FILE_SIZE_MB} МБ.")
        )


def validate_attachment_extension(file):
    if not file:
        return
    ext = Path(file.name).suffix.lower()
    allowed_exts = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
    }
    if ext not in allowed_exts:
        raise ValidationError(
            _(
                "Недопустимый тип файла. Разрешены изображения (jpg, png, webp, gif) "
                "и документы (pdf, doc, docx, xls, xlsx)."
            )
        )


class MessageType(models.TextChoices):
    TEXT = "text", _("Текст")
    IMAGE = "image", _("Изображение")
    FILE = "file", _("Файл")
    STICKER = "sticker", _("Стикер")


class ChatThread(models.Model):
    """
    Диалог (1-1 чат) между двумя пользователями.

    Роли:
    - admin ↔ любой
    - partner ↔ admin / store (но не partner-partner)
    - store ↔ admin / partner (но не store-store)
    """

    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="chat_threads",
        verbose_name="Участники",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        db_table = "chat_threads"
        ordering = ["-updated_at"]
        verbose_name = "Чат"
        verbose_name_plural = "Чаты"
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self) -> str:
        users = ", ".join(str(u_id) for u_id in self.participants.values_list("id", flat=True))
        return f"Thread #{self.pk} ({users})"

    @property
    def last_message(self) -> "Message | None":
        return self.messages.order_by("-created_at").first()


class Message(models.Model):
    """
    Сообщение в чате.

    Поддерживает:
    - текст
    - изображение
    - файл (pdf / word / excel и т.п.)
    - стикер (код/emoji)
    """

    thread = models.ForeignKey(
        ChatThread,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="Чат",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
        verbose_name="Отправитель",
    )
    type = models.CharField(
        max_length=16,
        choices=MessageType.choices,
        default=MessageType.TEXT,
        verbose_name="Тип сообщения",
    )

    text = models.TextField(blank=True, verbose_name="Текст")
    attachment = models.FileField(
        upload_to="chat_files/",
        null=True,
        blank=True,
        verbose_name="Файл",
        validators=[validate_attachment_size, validate_attachment_extension],
    )
    sticker_code = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Код стикера",
        help_text="Код стикера или emoji из клавиатуры",
    )

    is_read = models.BooleanField(default=False, verbose_name="Прочитано")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="Прочитано в")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        db_table = "chat_messages"
        ordering = ["created_at"]
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        indexes = [
            models.Index(fields=["thread", "created_at"]),
            models.Index(fields=["sender", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Message #{self.pk} in Thread #{self.thread_id}"

    def clean(self):
        # Базовая валидация содержимого в зависимости от типа
        if self.type == MessageType.TEXT and not self.text:
            raise ValidationError("Текст сообщения обязателен для text-типа.")
        if self.type == MessageType.IMAGE and not self.attachment:
            raise ValidationError("Изображение обязательно для image-типа.")
        if self.type == MessageType.FILE and not self.attachment:
            raise ValidationError("Файл обязателен для file-типа.")
        if self.type == MessageType.STICKER and not self.sticker_code:
            raise ValidationError("Код стикера обязателен для sticker-типа.")
        super().clean()
