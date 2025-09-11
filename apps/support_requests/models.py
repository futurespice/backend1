from django.db import models
from django.conf import settings


class SupportTicket(models.Model):
    """Тикет техподдержки"""

    PRIORITY_CHOICES = [
        ('low', 'Низкий'),
        ('medium', 'Средний'),
        ('high', 'Высокий'),
        ('urgent', 'Критический'),
    ]

    STATUS_CHOICES = [
        ('open', 'Открыт'),
        ('in_progress', 'В работе'),
        ('waiting_customer', 'Ожидает клиента'),
        ('resolved', 'Решен'),
        ('closed', 'Закрыт'),
    ]

    CATEGORY_CHOICES = [
        ('technical', 'Техническая проблема'),
        ('account', 'Проблемы с аккаунтом'),
        ('billing', 'Вопросы по оплате'),
        ('feature_request', 'Запрос функции'),
        ('bug_report', 'Сообщение об ошибке'),
        ('general', 'Общий вопрос'),
    ]

    # Основная информация
    ticket_number = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Номер тикета'
    )
    title = models.CharField(max_length=200, verbose_name='Заголовок')
    description = models.TextField(verbose_name='Описание проблемы')

    # Классификация
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='general',
        verbose_name='Категория'
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium',
        verbose_name='Приоритет'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='open',
        verbose_name='Статус'
    )

    # Участники
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_tickets',
        verbose_name='Заявитель'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
        limit_choices_to={'role': 'admin'},
        verbose_name='Назначен'
    )

    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Решен')
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='Закрыт')

    # Дополнительные поля
    tags = models.CharField(max_length=200, blank=True, verbose_name='Теги')

    class Meta:
        db_table = 'support_tickets'
        verbose_name = 'Тикет поддержки'
        verbose_name_plural = 'Тикеты поддержки'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ticket_number}: {self.title}"

    def save(self, *args, **kwargs):
        # Автогенерация номера тикета
        if not self.ticket_number:
            import uuid
            self.ticket_number = f"SUP{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def close(self):
        """Закрыть тикет"""
        from django.utils import timezone
        self.status = 'closed'
        self.closed_at = timezone.now()
        self.save()

    def resolve(self):
        """Отметить как решенный"""
        from django.utils import timezone
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.save()


class SupportMessage(models.Model):
    """Сообщения в тикете поддержки"""

    MESSAGE_TYPES = [
        ('message', 'Сообщение'),
        ('internal_note', 'Внутренняя заметка'),
        ('status_change', 'Изменение статуса'),
        ('assignment', 'Назначение'),
    ]

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Тикет'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='Отправитель'
    )

    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPES,
        default='message',
        verbose_name='Тип сообщения'
    )
    content = models.TextField(verbose_name='Содержимое')

    # Файлы
    attachment = models.FileField(
        upload_to='support_attachments/',
        null=True,
        blank=True,
        verbose_name='Вложение'
    )

    # Видимость
    is_internal = models.BooleanField(
        default=False,
        verbose_name='Внутреннее сообщение'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Отправлено')

    class Meta:
        db_table = 'support_messages'
        verbose_name = 'Сообщение поддержки'
        verbose_name_plural = 'Сообщения поддержки'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.ticket.ticket_number}: {self.sender.get_full_name()}"


class FAQ(models.Model):
    """База знаний - часто задаваемые вопросы"""

    question = models.CharField(max_length=300, verbose_name='Вопрос')
    answer = models.TextField(verbose_name='Ответ')

    # Категоризация
    category = models.CharField(
        max_length=20,
        choices=SupportTicket.CATEGORY_CHOICES,
        default='general',
        verbose_name='Категория'
    )

    # Статистика
    view_count = models.PositiveIntegerField(default=0, verbose_name='Просмотры')
    helpful_count = models.PositiveIntegerField(default=0, verbose_name='Полезно')
    not_helpful_count = models.PositiveIntegerField(default=0, verbose_name='Не полезно')

    # Управление
    is_published = models.BooleanField(default=True, verbose_name='Опубликован')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Создал'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')

    class Meta:
        db_table = 'faq'
        verbose_name = 'Вопрос FAQ'
        verbose_name_plural = 'FAQ'
        ordering = ['-helpful_count', '-view_count']

    def __str__(self):
        return self.question[:100]

    def mark_helpful(self, helpful=True):
        """Отметить как полезный/неполезный"""
        if helpful:
            self.helpful_count += 1
        else:
            self.not_helpful_count += 1
        self.save()

    @property
    def helpfulness_ratio(self):
        """Коэффициент полезности"""
        total = self.helpful_count + self.not_helpful_count
        if total == 0:
            return 0
        return self.helpful_count / total


class SupportCategory(models.Model):
    """Категории поддержки"""

    name = models.CharField(max_length=100, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    icon = models.CharField(max_length=50, blank=True, verbose_name='Иконка')

    # Иерархия
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Родительская категория'
    )

    # Статистика
    ticket_count = models.PositiveIntegerField(default=0, verbose_name='Количество тикетов')

    is_active = models.BooleanField(default=True, verbose_name='Активна')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        db_table = 'support_categories'
        verbose_name = 'Категория поддержки'
        verbose_name_plural = 'Категории поддержки'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name