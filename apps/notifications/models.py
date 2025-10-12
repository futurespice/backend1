from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class Notification(models.Model):
    """Система уведомлений"""

    NOTIFICATION_TYPES = [
        ('store_registered', 'Новый магазин'),
        ('store_approved', 'Магазин одобрен'),
        ('store_rejected', 'Магазин отклонён'),
        ('new_order', 'Новый заказ'),
        ('new_expense', 'Новый расход'),
        ('new_request', 'Новый запрос товаров'),
        ('message', 'Новое сообщение'),
        ('debt_reminder', 'Напоминание о долге'),
        ('system', 'Системное'),
    ]

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Получатель'
    )
    type = models.CharField(
        'Тип',
        max_length=50,
        choices=NOTIFICATION_TYPES
    )
    title = models.CharField('Заголовок', max_length=255)
    message = models.TextField('Сообщение')

    # Связь с объектом (полиморфная)
    related_object_type = models.CharField('Тип объекта', max_length=50, blank=True)
    related_object_id = models.PositiveIntegerField('ID объекта', null=True, blank=True)

    is_read = models.BooleanField('Прочитано', default=False)
    read_at = models.DateTimeField('Прочитано в', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"{self.recipient.get_full_name()}: {self.title}"