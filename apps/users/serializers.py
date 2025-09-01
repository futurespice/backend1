from rest_framework import serializers
from django.contrib.auth import authenticate
from django.core.validators import RegexValidator
from django.db import models
from .models import User, PasswordResetRequest
from .services import EmailService
import random
from django.utils import timezone
from datetime import timedelta


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Сериализатор для регистрации пользователей"""

    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('email', 'phone', 'name', 'second_name', 'password', 'password_confirm')

    def validate_email(self, value):
        """Проверка формата и уникальности email"""
        if '@' not in value or value.count('@') != 1:
            raise serializers.ValidationError("Email должен содержать ровно один символ @")

        if len(value) > 50:
            raise serializers.ValidationError("Email не должен превышать 50 символов")

        return value.lower()

    def validate_name(self, value):
        """Проверка имени"""
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Имя должно содержать минимум 2 символа")
        return value.title()

    def validate_second_name(self, value):
        """Проверка фамилии"""
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Фамилия должна содержать минимум 2 символа")
        return value.title()

    def validate(self, attrs):
        """Проверка совпадения паролей"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Пароли не совпадают")

        # Проверка общей длины ФИО (15-24 символа по ТЗ)
        full_name_length = len(attrs['name']) + len(attrs['second_name']) + 1  # +1 за пробел
        if full_name_length < 15 or full_name_length > 24:
            raise serializers.ValidationError("ФИО должно содержать от 15 до 24 символов")

        return attrs

    def create(self, validated_data):
        """Создание пользователя через UserManager"""
        validated_data.pop('password_confirm')

        # UserManager.create_user автоматически определит роль и очистит пароль
        user = User.objects.create_user(**validated_data)

        # Отправляем приветственное письмо
        EmailService.send_welcome_email(user)

        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """Сериализатор профиля пользователя"""
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = ('id', 'email', 'phone', 'name', 'second_name', 'full_name', 'role',
                  'avatar', 'is_approved', 'is_active', 'created_at')
        read_only_fields = ('id', 'role', 'is_approved', 'created_at')

    def validate_avatar(self, value):
        """Валидация загружаемого аватара"""
        if value:
            # Проверка размера файла (максимум 5MB)
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError("Размер файла не должен превышать 5MB")

            # Проверка типа файла
            if not value.content_type.startswith('image/'):
                raise serializers.ValidationError("Файл должен быть изображением")

        return value


class UserListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка пользователей (для админа)"""
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = ('id', 'email', 'name', 'second_name', 'full_name', 'phone', 'role',
                  'is_approved', 'is_active', 'avatar', 'created_at')


class UserModerationSerializer(serializers.ModelSerializer):
    """Сериализатор для модерации пользователей админом"""

    class Meta:
        model = User
        fields = ('id', 'is_approved', 'is_active')

    def update(self, instance, validated_data):
        """Обновление статуса с отправкой уведомления"""
        old_approved = instance.is_approved
        new_approved = validated_data.get('is_approved', instance.is_approved)

        instance = super().update(instance, validated_data)

        # Отправляем уведомление если статус одобрения изменился
        if old_approved != new_approved:
            EmailService.send_approval_notification(instance, new_approved)

        return instance


class PasswordResetRequestSerializer(serializers.Serializer):
    """Запрос на сброс пароля"""
    email = serializers.EmailField()

    def validate_email(self, value):
        """Проверяем существование пользователя"""
        try:
            user = User.objects.get(email=value)
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь с таким email не найден")

    def create(self, validated_data):
        """Создание запроса на сброс пароля"""
        email = validated_data['email']
        user = User.objects.get(email=email)

        # Генерируем 5-значный код
        code = str(random.randint(10000, 99999))

        # Создаем запрос на сброс
        reset_request = PasswordResetRequest.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=15)
        )

        # Отправляем код на email
        EmailService.send_password_reset_code(user, code)

        return reset_request


class PasswordResetCodeSerializer(serializers.Serializer):
    """Проверка кода сброса"""
    code = serializers.CharField(max_length=5, min_length=5)

    def validate_code(self, value):
        try:
            reset_request = PasswordResetRequest.objects.get(
                code=value,
                is_used=False,
                expires_at__gt=timezone.now()
            )
            return value
        except PasswordResetRequest.DoesNotExist:
            raise serializers.ValidationError("Неверный или истёкший код")


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Сброс пароля по коду"""
    code = serializers.CharField(max_length=5, min_length=5)
    new_password = serializers.CharField(min_length=6)

    def validate_code(self, value):
        try:
            reset_request = PasswordResetRequest.objects.get(
                code=value,
                is_used=False,
                expires_at__gt=timezone.now()
            )
            return value
        except PasswordResetRequest.DoesNotExist:
            raise serializers.ValidationError("Неверный или истёкший код")

    def save(self):
        code = self.validated_data['code']
        new_password = self.validated_data['new_password']

        reset_request = PasswordResetRequest.objects.get(
            code=code,
            is_used=False
        )

        user = reset_request.user
        user.set_password(new_password)
        user.save()

        reset_request.is_used = True
        reset_request.save()

        return user