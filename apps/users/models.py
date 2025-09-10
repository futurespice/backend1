from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Кастомная модель пользователя"""

    ROLE_CHOICES = [
        ('admin', 'Администратор'),
        ('partner', 'Партнёр'),
        ('store', 'Магазин'),
    ]

    # Основные поля
    email = models.EmailField(unique=True, verbose_name='Email')
    phone = models.CharField(max_length=20, unique=True, verbose_name='Телефон')
    name = models.CharField(max_length=100, verbose_name='Имя')
    second_name = models.CharField(max_length=100, verbose_name='Фамилия и отчество')

    # Роль и статусы
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='store', verbose_name='Роль')
    is_approved = models.BooleanField(default=True, verbose_name='Одобрен')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    is_staff = models.BooleanField(default=False, verbose_name='Персонал')

    # Дополнительные поля
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name='Аватар')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name', 'second_name', 'phone']

    class Meta:
        db_table = 'users'
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def get_full_name(self):
        """Возвращает полное имя пользователя"""
        return f"{self.name} {self.second_name}".strip()

    def get_short_name(self):
        """Возвращает короткое имя пользователя"""
        return self.name

    @property
    def full_name(self):
        """Свойство для полного имени"""
        return self.get_full_name()

    def is_admin(self):
        """Проверка на администратора"""
        return self.role == 'admin'

    def is_partner(self):
        """Проверка на партнёра"""
        return self.role == 'partner'

    def is_store(self):
        """Проверка на магазин"""
        return self.role == 'store'


class PasswordResetRequest(models.Model):
    """Модель для запросов сброса пароля"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    code = models.CharField(max_length=5, verbose_name='Код')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    expires_at = models.DateTimeField(verbose_name='Истекает')
    is_used = models.BooleanField(default=False, verbose_name='Использован')

    class Meta:
        db_table = 'password_reset_requests'
        verbose_name = 'Запрос сброса пароля'
        verbose_name_plural = 'Запросы сброса пароля'
        ordering = ['-created_at']

    def __str__(self):
        return f"Сброс пароля для {self.user.email} - {self.code}"

    def is_expired(self):
        """Проверка истечения кода"""
        return timezone.now() > self.expires_at

    def save(self, *args, **kwargs):
        # Деактивируем предыдущие неиспользованные коды для этого пользователя
        if not self.pk:
            PasswordResetRequest.objects.filter(
                user=self.user,
                is_used=False
            ).update(is_used=True)
        super().save(*args, **kwargs)