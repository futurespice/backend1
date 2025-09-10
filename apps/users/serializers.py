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

    class Meta:
        model = User
        fields = ('email', 'phone', 'name', 'second_name', 'password')

    def validate_email(self, value):
        """Проверка формата и уникальности email"""
        if '@' not in value or value.count('@') != 1:
            raise serializers.ValidationError("Email должен содержать ровно один символ @")

        if len(value) > 50:
            raise serializers.ValidationError("Email не должен превышать 50 символов")

        # Проверка уникальности
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует")

        return value.lower()

    def validate_phone(self, value):
        """Проверка формата и уникальности телефона"""
        # Убираем все кроме цифр и +
        clean_phone = ''.join(char for char in value if char.isdigit() or char == '+')

        if not clean_phone.startswith('+996'):
            raise serializers.ValidationError("Телефон должен начинаться с +996")

        if len(clean_phone) != 13:  # +996XXXXXXXXX
            raise serializers.ValidationError("Некорректный формат номера телефона")

        # Проверка уникальности
        if User.objects.filter(phone=clean_phone).exists():
            raise serializers.ValidationError("Пользователь с таким номером уже существует")

        return clean_phone

    def validate_name(self, value):
        """Проверка имени"""
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Имя должно содержать минимум 2 символа")
        return value.strip().title()

    def validate_second_name(self, value):
        """Проверка фамилии"""
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Фамилия должна содержать минимум 2 символа")
        return value.strip().title()

    def validate_password(self, value):
        """Базовая проверка пароля"""
        if len(value) < 6:
            raise serializers.ValidationError("Пароль должен содержать минимум 6 символов")
        return value

    def create(self, validated_data):
        """Создание пользователя через UserManager с определением роли"""
        return User.objects.create_user(**validated_data)


class CustomTokenObtainSerializer(serializers.Serializer):
    """Кастомный сериализатор для получения токена"""

    username = serializers.CharField()  # email или phone
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')

        if username and password:
            # Пробуем найти пользователя по email или phone
            user = None
            try:
                # Сначала пробуем по email
                if '@' in username:
                    user = User.objects.get(email=username.lower())
                else:
                    # Затем по телефону
                    clean_phone = ''.join(char for char in username if char.isdigit() or char == '+')
                    user = User.objects.get(phone=clean_phone)
            except User.DoesNotExist:
                raise serializers.ValidationError("Неверные учетные данные")

            # Проверяем пароль
            if not user.check_password(password):
                raise serializers.ValidationError("Неверные учетные данные")

            # Проверяем статус пользователя
            if not user.is_active:
                raise serializers.ValidationError("Аккаунт заблокирован")

            if not user.is_approved:
                raise serializers.ValidationError("Аккаунт ожидает одобрения администратора")

            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError("Необходимо указать логин и пароль")


class UserProfileSerializer(serializers.ModelSerializer):
    """Сериализатор профиля пользователя"""

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'name', 'second_name', 'full_name', 'phone',
                  'role', 'is_approved', 'is_active', 'avatar', 'created_at')
        read_only_fields = ('id', 'email', 'role', 'is_approved', 'created_at')

    def get_full_name(self, obj):
        return obj.get_full_name()


class UserListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка пользователей (админ)"""

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
            user = User.objects.get(email=value.lower())
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь с таким email не найден")

    def create(self, validated_data):
        """Создание запроса на сброс пароля"""
        email = validated_data['email']
        user = User.objects.get(email=email.lower())

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

    def validate_new_password(self, value):
        """Проверка нового пароля"""
        if len(value) < 6:
            raise serializers.ValidationError("Пароль должен содержать минимум 6 символов")
        return value

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