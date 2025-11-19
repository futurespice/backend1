# apps/notifications/models.py

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class NotificationType(models.TextChoices):
    INFO = "info", _("Информация")
    WARNING = "warning", _("Предупреждение")
    SUCCESS = "success", _("Успех")
    ERROR = "error", _("Ошибка")
    SYSTEM = "system", _("Системное")
    ORDER = "order", _("Заказ")
    STORE = "store", _("Магазин")


class NotificationChannel(models.TextChoices):
    IN_APP = "in_app", _("Внутри системы")
    EMAIL = "email", _("Email")
    TELEGRAM = "telegram", _("Telegram")


class Notification(models.Model):
    """
    Базовая модель уведомления.

    Может использоваться:
    - как in-app уведомление (список в личном кабинете),
    - как лог отправленных email / телеграм уведомлений,
    - как источник для пушей.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Получатель",
    )
    title = models.CharField(max_length=255, verbose_name="Заголовок")
    message = models.TextField(verbose_name="Текст")
    type = models.CharField(
        max_length=16,
        choices=NotificationType.choices,
        default=NotificationType.INFO,
        verbose_name="Тип",
    )
    channel = models.CharField(
        max_length=16,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
        verbose_name="Канал",
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Доп. данные (payload)",
        help_text="Любые доп. данные для фронта (id заказа, id магазина и т.д.)",
    )

    is_read = models.BooleanField(default=False, verbose_name="Прочитано")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="Прочитано в")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["type"]),
        ]

    def __str__(self) -> str:
        return f"[{self.get_type_display()}] {self.title} → {self.user_id}"
