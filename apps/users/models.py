from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.core.validators import RegexValidator
from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin', 'Администратор'),
        ('partner', 'Партнер'),
        ('store', 'Магазин'),
    ]

    # Основные поля
    email = models.EmailField(
        unique=True,
        max_length=50,
        validators=[RegexValidator(r'^[^@]+@[^@]+\.[^@]+$', 'Неверный формат email')]
    )
    phone = models.CharField(
        max_length=20,
        unique=True,
        validators=[RegexValidator(r'^\+?[0-9]{10,15}$')]
    )
    name = models.CharField(
        max_length=100,
        validators=[RegexValidator(r'^[a-zA-Zа-яА-Я\s]+$', 'ФИО должно содержать только буквы')])
    second_name = models.CharField(
        max_length=100,
        validators=[RegexValidator(r'^[a-zA-Zа-яА-Я\s]+$', 'Фамилия должно содержать только буквы')])
    # Роль и статусы
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='store')
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # Дополнительные поля
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Настройки для AbstractBaseUser
    USERNAME_FIELD = 'email'  # Вход по email
    REQUIRED_FIELDS = ['phone', 'full_name']  # Поля обязательные при создании суперпользователя

    # Подключаем кастомный менеджер
    objects = UserManager()

    class Meta:
        db_table = 'users'
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"

    def is_partner(self):
        return self.role == 'partner'

    def is_store(self):
        return self.role == 'store'

    def is_admin_user(self):
        return self.role == 'admin'


class PasswordResetRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=5)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'password_reset_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"Сброс пароля для {self.user.email}"