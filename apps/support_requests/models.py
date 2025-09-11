# apps/support_requests/models.py
from django.db import models
from django.conf import settings


class SupportRequest(models.Model):
    """Заявка в службу поддержки"""

    STATUS_CHOICES = [
        ('open', 'Открыта'),
        ('in_progress', 'В работе'),
        ('resolved', 'Решена'),
        ('closed', 'Закрыта'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Низкий'),
        ('medium', 'Средний'),
        ('high', 'Высокий'),
        ('urgent', 'Срочный'),
    ]

    CATEGORY_CHOICES = [
        ('technical', 'Техническая проблема'),
        ('billing', 'Вопросы по оплате'),
        ('account', 'Проблемы с аккаунтом'),
        ('order', 'Вопросы по заказам'),
        ('general', 'Общие вопросы'),
        ('feature', 'Запрос функций'),
        ('bug', 'Сообщение об ошибке'),
    ]

    # Основная информация
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_requests',
        verbose_name='Пользователь'
    )

    subject = models.CharField(max_length=200, verbose_name='Тема')
    description = models.TextField(verbose_name='Описание проблемы')
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='general',
        verbose_name='Категория'
    )

    # Статус и приоритет
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='open',
        verbose_name='Статус'
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='medium',
        verbose_name='Приоритет'
    )

    # Ответственный
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_support_requests',
        verbose_name='Назначено'
    )

    # Связанные объекты
    related_order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Связанный заказ'
    )

    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Решена')
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='Закрыта')

    # Дополнительная информация
    attachment = models.FileField(
        upload_to='support_attachments/',
        null=True,
        blank=True,
        verbose_name='Вложение'
    )
    internal_notes = models.TextField(blank=True, verbose_name='Внутренние заметки')

    class Meta:
        db_table = 'support_requests'
        verbose_name = 'Заявка поддержки'
        verbose_name_plural = 'Заявки поддержки'
        ordering = ['-created_at']

    def __str__(self):
        return f"#{self.id} - {self.subject}"


class SupportResponse(models.Model):
    """Ответ на заявку поддержки"""

    request = models.ForeignKey(
        SupportRequest,
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name='Заявка'
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='Автор'
    )

    message = models.TextField(verbose_name='Сообщение')
    is_internal = models.BooleanField(
        default=False,
        verbose_name='Внутреннее сообщение'
    )

    attachment = models.FileField(
        upload_to='support_responses/',
        null=True,
        blank=True,
        verbose_name='Вложение'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')

    class Meta:
        db_table = 'support_responses'
        verbose_name = 'Ответ поддержки'
        verbose_name_plural = 'Ответы поддержки'
        ordering = ['created_at']

    def __str__(self):
        return f"Ответ на #{self.request.id} от {self.author.get_full_name()}"


class SupportCategory(models.Model):
    """Категория заявок поддержки"""

    name = models.CharField(max_length=100, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')

    # Автоматическое назначение
    auto_assign_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Автоназначение'
    )

    # Шаблон ответа
    response_template = models.TextField(
        blank=True,
        verbose_name='Шаблон ответа'
    )

    is_active = models.BooleanField(default=True, verbose_name='Активна')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        db_table = 'support_categories'
        verbose_name = 'Категория поддержки'
        verbose_name_plural = 'Категории поддержки'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name