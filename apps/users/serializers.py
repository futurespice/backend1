from rest_framework import serializers
from django.contrib.auth import authenticate
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import User, PasswordResetRequest
import re


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Сериализатор регистрации пользователей"""

    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'email', 'phone', 'name', 'second_name',
            'password', 'password_confirm'
        ]

    def validate_email(self, value):
        """Валидация email"""
        try:
            validate_email(value)
        except ValidationError:
            raise serializers.ValidationError("Некорректный email адрес")

        # Проверка требований ТЗ: один символ @, максимум 50 символов
        if value.count('@') != 1:
            raise serializers.ValidationError("Email должен содержать ровно один символ @")

        if len(value) > 50:
            raise serializers.ValidationError("Email не должен превышать 50 символов")

        # Проверка уникальности
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует")

        return value.lower()

    def validate_phone(self, value):
        """Валидация телефона"""
        # Убираем все символы кроме цифр и +
        clean_phone = re.sub(r'[^\d+]', '', value)

        if not clean_phone:
            raise serializers.ValidationError("Некорректный номер телефона")

        # Проверка уникальности
        if User.objects.filter(phone=clean_phone).exists():
            raise serializers.ValidationError("Пользователь с таким телефоном уже существует")

        return clean_phone

    def validate_name(self, value):
        """Валидация имени"""
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Имя должно содержать минимум 2 символа")
        return value.strip().title()

    def validate_second_name(self, value):
        """Валидация Ф.И.О - согласно ТЗ от 15 до 24 символов"""
        cleaned = value.strip()
        if len(cleaned) < 15:
            raise serializers.ValidationError("Ф.И.О должно содержать минимум 15 символов")
        if len(cleaned) > 24:
            raise serializers.ValidationError("Ф.И.О не должно превышать 24 символа")
        return cleaned.title()

    def validate(self, attrs):
        """Общая валидация"""
        password = attrs.get('password')
        password_confirm = attrs.pop('password_confirm', None)

        if password != password_confirm:
            raise serializers.ValidationError({"password_confirm": "Пароли не совпадают"})

        return attrs

    def create(self, validated_data):
        """Создание пользователя через UserManager"""
        return User.objects.create_user(**validated_data)


class CustomTokenObtainSerializer(serializers.Serializer):
    """Кастомный сериализатор для получения токена по телефону"""

    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        phone = attrs.get('phone')
        password = attrs.get('password')

        if not phone or not password:
            raise serializers.ValidationError("Необходимо указать телефон и пароль")

        # Очищаем телефон
        clean_phone = re.sub(r'[^\d+]', '', phone)

        try:
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


class UserProfileSerializer(serializers.ModelSerializer):
    """Сериализатор профиля пользователя"""

    full_name = serializers.CharField(source='get_full_name', read_only=True)
    store_info = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'phone', 'name', 'second_name', 'full_name',
            'role', 'is_approved', 'avatar', 'store_info',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'email', 'role', 'is_approved', 'created_at', 'updated_at']

    def get_store_info(self, obj):
        """Информация о магазине для пользователей роли store"""
        if obj.role == 'store' and hasattr(obj, 'store_profile'):
            return {
                'store_name': obj.store_profile.store_name,
                'address': obj.store_profile.address,
                'is_active': obj.store_profile.is_active
            }
        return None


class UserListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка пользователей (для админов)"""

    full_name = serializers.CharField(source='get_full_name', read_only=True)
    store_name = serializers.SerializerMethodField()
    total_debt = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'phone', 'full_name', 'role',
            'is_approved', 'is_active', 'store_name', 'total_debt',
            'created_at'
        ]

    def get_store_name(self, obj):
        """Название магазина"""
        if obj.role == 'store' and hasattr(obj, 'store_profile'):
            return obj.store_profile.store_name
        return None

    def get_total_debt(self, obj):
        """Общий долг магазина"""
        if obj.role == 'store' and hasattr(obj, 'store_profile'):
            return float(obj.store_profile.total_debt)
        return 0


class UserModerationSerializer(serializers.ModelSerializer):
    """Сериализатор модерации пользователей (для админов)"""

    class Meta:
        model = User
        fields = ['is_approved', 'is_active']

    def update(self, instance, validated_data):
        """Обновление с отправкой уведомлений"""
        old_approved = instance.is_approved
        new_approved = validated_data.get('is_approved', old_approved)

        instance = super().update(instance, validated_data)

        # Отправляем уведомление при изменении статуса одобрения
        if old_approved != new_approved:
            from .services import EmailService
            EmailService.send_approval_notification(instance, new_approved)

        return instance


class PasswordResetRequestSerializer(serializers.Serializer):
    """Сериализатор запроса сброса пароля"""

    email = serializers.EmailField()

    def validate_email(self, value):
        """Проверяем существование пользователя"""
        try:
            user = User.objects.get(email=value.lower())
            if not user.is_active:
                raise serializers.ValidationError("Аккаунт заблокирован")
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь с таким email не найден")

        return value.lower()


class PasswordResetCodeSerializer(serializers.Serializer):
    """Сериализатор проверки кода сброса пароля"""

    email = serializers.EmailField()
    code = serializers.CharField(max_length=5, min_length=5)

    def validate(self, attrs):
        """Проверяем код"""
        email = attrs.get('email')
        code = attrs.get('code')

        try:
            user = User.objects.get(email=email)
            reset_request = PasswordResetRequest.objects.get(
                user=user,
                code=code,
                is_used=False
            )

            if reset_request.is_expired():
                raise serializers.ValidationError("Код истёк")

            attrs['reset_request'] = reset_request

        except (User.DoesNotExist, PasswordResetRequest.DoesNotExist):
            raise serializers.ValidationError("Неверный код или email")

        return attrs


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Сериализатор подтверждения нового пароля"""

    email = serializers.EmailField()
    code = serializers.CharField(max_length=5, min_length=5)
    new_password = serializers.CharField(min_length=6, write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Проверяем код и пароли"""
        email = attrs.get('email')
        code = attrs.get('code')
        new_password = attrs.get('new_password')
        new_password_confirm = attrs.get('new_password_confirm')

        # Проверяем совпадение паролей
        if new_password != new_password_confirm:
            raise serializers.ValidationError({"new_password_confirm": "Пароли не совпадают"})

        # Проверяем код
        try:
            user = User.objects.get(email=email)
            reset_request = PasswordResetRequest.objects.get(
                user=user,
                code=code,
                is_used=False
            )

            if reset_request.is_expired():
                raise serializers.ValidationError("Код истёк")

            attrs['user'] = user
            attrs['reset_request'] = reset_request

        except (User.DoesNotExist, PasswordResetRequest.DoesNotExist):
            raise serializers.ValidationError("Неверный код или email")

        return attrs