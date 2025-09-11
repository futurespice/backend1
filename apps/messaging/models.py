from django.db import models
from django.conf import settings


class ChatRoom(models.Model):
    """Комната чата между пользователями"""

    ROOM_TYPES = [
        ('private', 'Приватный чат'),
        ('support', 'Поддержка'),
        ('group', 'Групповой чат'),
    ]

    name = models.CharField(max_length=200, verbose_name='Название')
    room_type = models.CharField(
        max_length=20,
        choices=ROOM_TYPES,
        default='private',
        verbose_name='Тип комнаты'
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='chat_rooms',
        verbose_name='Участники'
    )

    # УБРАЛИ проблемное поле application
    # application = models.ForeignKey(
    #     'orders.StoreApplication',  # Эта модель не существует
    #     on_delete=models.CASCADE,
    #     null=True,
    #     blank=True
    # )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')
    is_active = models.BooleanField(default=True, verbose_name='Активна')

    class Meta:
        db_table = 'chat_rooms'
        verbose_name = 'Комната чата'
        verbose_name_plural = 'Комнаты чата'
        ordering = ['-updated_at']

    def __str__(self):
        return self.name


class Message(models.Model):
    """Сообщение в чате"""

    MESSAGE_TYPES = [
        ('text', 'Текст'),
        ('image', 'Изображение'),
        ('file', 'Файл'),
        ('system', 'Системное'),
    ]

    chat_room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Комната чата'
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

    # Для файлов и изображений
    file = models.FileField(
        upload_to='chat_files/',
        null=True,
        blank=True,
        verbose_name='Файл'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Отправлено')
    is_edited = models.BooleanField(default=False, verbose_name='Отредактировано')
    edited_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата редактирования')

    class Meta:
        db_table = 'chat_messages'
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.get_full_name()}: {self.content[:50]}"


class MessageRead(models.Model):
    """Отметки о прочтении сообщений"""

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='read_marks',
        verbose_name='Сообщение'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='Пользователь'
    )
    read_at = models.DateTimeField(auto_now_add=True, verbose_name='Прочитано')

    class Meta:
        db_table = 'message_reads'
        verbose_name = 'Отметка о прочтении'
        verbose_name_plural = 'Отметки о прочтении'
        unique_together = ['message', 'user']