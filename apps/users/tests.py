# apps/users/tests.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import PasswordResetRequest

User = get_user_model()


class AuthenticationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_partner_registration_with_marker(self):
        """Тест регистрации партнера с маркером"""
        data = {
            'email': 'partner@test.com',
            'phone': '+996555123456',
            'name': 'Иван',
            'second_name': 'Иванович Петров',
            'password': 'test123p!8Rt',
            'password_confirm': 'test123p!8Rt'
        }

        response = self.client.post(reverse('register'), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email='partner@test.com')
        self.assertEqual(user.role, 'partner')
        self.assertFalse(user.is_approved)  # Партнеры требуют одобрения

    def test_store_registration_without_marker(self):
        """Тест регистрации магазина без маркера"""
        data = {
            'email': 'store@test.com',
            'phone': '+996555123457',
            'name': 'Петр',
            'second_name': 'Петрович Сидоров',
            'password': 'test12345',
            'password_confirm': 'test12345'
        }

        response = self.client.post(reverse('register'), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email='store@test.com')
        self.assertEqual(user.role, 'store')
        self.assertTrue(user.is_approved)  # Магазины одобряются автоматически

    def test_login_approved_user(self):
        """Тест входа одобренного пользователя"""
        user = User.objects.create_user(
            email='test@test.com',
            phone='+996555123458',
            name='Тест',
            second_name='Тестович',
            password='test12345',
            is_approved=True
        )

        data = {
            'email': 'test@test.com',
            'password': 'test12345'
        }

        response = self.client.post(reverse('token_obtain_pair'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)

    def test_login_unapproved_user(self):
        """Тест входа неодобренного пользователя"""
        user = User.objects.create_user(
            email='unapproved@test.com',
            phone='+996555123459',
            name='Неодобренный',
            second_name='Пользователь',
            password='test12345',
            is_approved=False
        )

        data = {
            'email': 'unapproved@test.com',
            'password': 'test12345'
        }

        response = self.client.post(reverse('token_obtain_pair'), data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_password_reset_flow(self):
        """Тест полного флоу сброса пароля"""
        user = User.objects.create_user(
            email='reset@test.com',
            phone='+996555123460',
            name='Сброс',
            second_name='Пароля',
            password='oldpassword'
        )

        # Запрос сброса
        data = {'email': 'reset@test.com'}
        response = self.client.post(reverse('password_reset'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Получаем код
        reset_request = PasswordResetRequest.objects.get(user=user)
        code = reset_request.code

        # Проверка кода
        data = {'code': code}
        response = self.client.post(reverse('password_reset_check_code'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Установка нового пароля
        data = {'code': code, 'new_password': 'newpassword123'}
        response = self.client.post(reverse('password_reset_confirm'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Проверяем, что можем войти с новым паролем
        user.refresh_from_db()
        self.assertTrue(user.check_password('newpassword123'))

    def test_profile_access(self):
        """Тест доступа к профилю"""
        user = User.objects.create_user(
            email='profile@test.com',
            phone='+996555123461',
            name='Профиль',
            second_name='Тестовый',
            password='test12345',
            is_approved=True
        )

        # Без токена
        response = self.client.get(reverse('user_profile'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # С токеном
        self.client.force_authenticate(user=user)
        response = self.client.get(reverse('user_profile'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'profile@test.com')

    def test_admin_users_access(self):
        """Тест доступа админа к управлению пользователями"""
        # Создаем админа
        admin_user = User.objects.create_user(
            email='admin@test.com',
            phone='+996555123462',
            name='Админ',
            second_name='Системный',
            password='admin123',
            role='admin',
            is_approved=True
        )

        # Создаем обычного пользователя
        regular_user = User.objects.create_user(
            email='regular@test.com',
            phone='+996555123463',
            name='Обычный',
            second_name='Пользователь',
            password='user123',
            is_approved=True
        )

        # Обычный пользователь не может получить список всех пользователей
        self.client.force_authenticate(user=regular_user)
        response = self.client.get(reverse('admin-users-list'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Админ может
        self.client.force_authenticate(user=admin_user)
        response = self.client.get(reverse('admin-users-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


if __name__ == '__main__':
    import django
    import os

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.testing')
    django.setup()

    from django.test.utils import get_runner
    from django.conf import settings

    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(['users.tests'])
    exit(failures)