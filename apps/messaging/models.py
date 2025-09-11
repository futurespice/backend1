from django.db import models
from django.conf import settings


class ChatRoom(models.Model):
    """Чат между участниками"""

    ROOM_TYPES = [
        ('private', 'Личный чат'),
        ('group', 'Групповой чат'),
        ('support', 'Техподдержка'),
        ('admin_broadcast', 'Рассылка админа'),
    ]

    name = models.CharField(max_length=200, blank=True, verbose_name='Название чата')
    room_type = models.CharField(
        max_length=20,
        choices=ROOM_TYPES,
        default='private',
        verbose_name='Тип чата'
    )

    # Участники
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='chat_rooms',
        verbose_name='Участники'
    )

    # Связанные объекты
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Магазин'
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Заказ'
    )
    application = models.ForeignKey(
        'orders.StoreApplication',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Заявка'
    )

    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')

    class Meta:
        db_table = 'chat_rooms'
        verbose_name = 'Чат'
        verbose_name_plural = 'Чаты'
        ordering = ['-updated_at']

    def __str__(self):
        if self.name:
            return self.name
        participants = list(self.participants.all()[:2])
        if len(participants) == 2:
            return f"Чат: {participants[0].get_full_name()} - {participants[1].get_full_name()}"
        return f"Чат #{self.id}"

    @property
    def last_message(self):
        return self.messages.order_by('-created_at').first()


class Message(models.Model):
    """Сообщение в чате"""

    MESSAGE_TYPES = [
        ('text', 'Текст'),
        ('image', 'Изображение'),
        ('file', 'Файл'),
        ('system', 'Системное'),
        ('notification', 'Уведомление'),
    ]

    chat_room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Чат'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages',
        verbose_name='Отправитель'
    )

    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPES,
        default='text',
        verbose_name='Тип сообщения'
    )
    content = models.TextField(verbose_name='Содержимое')

    # Файлы
    file = models.FileField(
        upload_to='messages/',
        null=True,
        blank=True,
        verbose_name='Файл'
    )

    # Статусы прочтения
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='Время прочтения')

    # Ответ на сообщение
    reply_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Ответ на'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Отправлено')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Изменено')

    class Meta:
        db_table = 'messages'
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.get_full_name()}: {self.content[:50]}..."


class Notification(models.Model):
    """Системные уведомления"""

    NOTIFICATION_TYPES = [
        ('order_created', 'Создан заказ'),
        ('order_completed', 'Заказ выполнен'),
        ('application_created', 'Создана заявка'),
        ('application_approved', 'Заявка одобрена'),
        ('debt_created', 'Создан долг'),
        ('debt_overdue', 'Долг просрочен'),
        ('bonus_earned', 'Начислен бонус'),
        ('inventory_low', 'Низкие остатки'),
        ('new_user_registered', 'Регистрация пользователя'),
        ('system_maintenance', 'Тех. обслуживание'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Получатель'
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPES,
        verbose_name='Тип уведомления'
    )
    title = models.CharField(max_length=200, verbose_name='Заголовок')
    message = models.TextField(verbose_name='Сообщение')

    # Связанные объекты
    related_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='ID связанного объекта'
    )
    related_object_type = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Тип связанного объекта'
    )

    # Статусы
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='Время прочтения')
    is_sent = models.BooleanField(default=False, verbose_name='Отправлено')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')

    class Meta:
        db_table = 'notifications'
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} для {self.recipient.get_full_name()}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            from django.utils import timezone
            self.read_at = timezone.now()
            self.save()


# Сигналы для автоматических уведомлений
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='orders.Order')
def create_order_notification(sender, instance, created, **kwargs):
    """Создание уведомлений при заказах"""
    if created:
        # Уведомление партнёру о новом заказе
        if hasattr(instance, 'store') and instance.store.partner:
            Notification.objects.create(
                recipient=instance.store.partner,
                notification_type='order_created',
                title='Новый заказ',
                message=f'Получен заказ #{instance.id} от магазина {instance.store.store_name}',
                related_object_id=instance.id,
                related_object_type='order'
            )


@receiver(post_save, sender='orders.StoreApplication')
def create_application_notification(sender, instance, created, **kwargs):
    """Уведомления при заявках"""
    if created:
        # Уведомление партнёру о новой заявке
        Notification.objects.create(
            recipient=instance.partner,
            notification_type='application_created',
            title='Новая заявка',
            message=f'Получена заявка #{instance.id} от магазина {instance.store.store_name}',
            related_object_id=instance.id,
            related_object_type='application'
        )