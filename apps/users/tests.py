from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import PasswordResetRequest

User = get_user_model()


class UserRegistrationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_partner_registration_with_marker(self):
        """Тест регистрации партнера с маркером p!8Rt"""
        data = {
            'name': 'Иван',
            'second_name': 'Петров',
            'email': 'partner@test.com',
            'phone': '+996555123456',
            'password': 'SecurePass123p!8Rt'  # Более надёжный пароль с маркером
        }

        response = self.client.post(reverse('users:register'), data)

        # ОТЛАДКА: выводим ответ при ошибке
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Status code: {response.status_code}")
            print(f"Response data: {response.data}")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(phone='+996555123456')
        self.assertEqual(user.role, 'partner')
        self.assertEqual(user.approval_status, 'pending')  # Партнеры ждут одобрения

        # Проверяем, что маркер удален из пароля
        self.assertTrue(user.check_password('SecurePass123'))

    def test_store_registration_without_marker(self):
        """Тест регистрации магазина без маркера"""
        data = {
            'name': 'Петр',
            'second_name': 'Сидоров',
            'email': 'store@test.com',
            'phone': '+996555123457',
            'password': 'SecurePass123'  # Без маркера
        }

        response = self.client.post(reverse('users:register'), data)

        # ОТЛАДКА: выводим ответ при ошибке
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Status code: {response.status_code}")
            print(f"Response data: {response.data}")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(phone='+996555123457')
        self.assertEqual(user.role, 'store')
        self.assertEqual(user.approval_status, 'approved')  # Магазины одобряются автоматически

    def test_invalid_phone_format(self):
        """Тест валидации номера телефона"""
        data = {
            'name': 'Тест',
            'second_name': 'Тестов',
            'email': 'test@test.com',
            'phone': '996555123456',  # Без +
            'password': 'SecurePass123'
        }

        response = self.client.post(reverse('users:register'), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone', response.data)

    def test_email_validation(self):
        """Тест валидации email"""
        data = {
            'name': 'Тест',
            'second_name': 'Тестов',
            'email': 'invalid@@email.com',  # Два символа @
            'phone': '+996555123458',
            'password': 'SecurePass123'
        }

        response = self.client.post(reverse('users:register'), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)


class LoginLogoutTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Создаем тестового пользователя
        self.user = User.objects.create_user(
            phone='+996555123456',
            email='test@test.com',
            name='Тест',
            second_name='Тестов',
            password='SecurePass123'
        )

    def test_login_with_phone_and_password(self):
        """Тест входа по номеру телефона и паролю"""
        data = {
            'phone': '+996555123456',
            'password': 'SecurePass123'
        }

        response = self.client.post(reverse('users:login'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_login_wrong_password(self):
        """Тест входа с неверным паролем"""
        data = {
            'phone': '+996555123456',
            'password': 'wrongpassword'
        }

        response = self.client.post(reverse('users:login'), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_with_remember_me(self):
        """Тест входа с функцией запомнить меня"""
        data = {
            'phone': '+996555123456',
            'password': 'SecurePass123',
            'remember_me': True
        }

        response = self.client.post(reverse('users:login'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_logout(self):
        """Тест выхода из системы"""
        # Сначала логинимся
        login_data = {
            'phone': '+996555123456',
            'password': 'SecurePass123'
        }
        login_response = self.client.post(reverse('users:login'), login_data)
        refresh_token = login_response.data['refresh']
        access_token = login_response.data['access']

        # Затем выходим
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        logout_data = {'refresh': refresh_token}

        response = self.client.post(reverse('users:logout'), logout_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ProfileTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone='+996555123456',
            email='test@test.com',
            name='Тест',
            second_name='Тестов',
            password='SecurePass123'
        )
        self.client.force_authenticate(user=self.user)

    def test_get_profile(self):
        """Тест получения профиля"""
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Тест')

    def test_patch_profile(self):
        """Тест частичного обновления профиля"""
        data = {'name': 'Новое Имя'}

        response = self.client.patch(reverse('users:profile'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertEqual(self.user.name, 'Новое Имя')

    def test_put_profile(self):
        """Тест полного обновления профиля"""
        data = {
            'name': 'Новое Имя',
            'second_name': 'Новая Фамилия',
            'email': 'new@test.com',
            'phone': '+996555999888'
        }

        response = self.client.put(reverse('users:profile'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertEqual(self.user.name, 'Новое Имя')
        self.assertEqual(self.user.email, 'new@test.com')


class AdminUserManagementTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Создаем админа
        self.admin = User.objects.create_user(
            phone='+996555000000',
            email='admin@test.com',
            name='Админ',
            second_name='Админов',
            password='AdminPass123',
            role='admin'
        )
        # Создаем партнёра, ожидающего одобрения
        self.partner = User.objects.create_user(
            phone='+996555111111',
            email='partner@test.com',
            name='Партнёр',
            second_name='Партнёров',
            password='PartnerPass123p!8Rt'
        )
        self.client.force_authenticate(user=self.admin)

    def test_get_all_users(self):
        """Тест получения списка всех пользователей админом"""
        response = self.client.get(reverse('users:admin-users-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) >= 2)  # минимум админ и партнёр

    def test_approve_user(self):
        """Тест одобрения пользователя админом"""
        response = self.client.patch(
            reverse('users:admin-users-approve', kwargs={'pk': self.partner.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.partner.refresh_from_db()
        self.assertEqual(self.partner.approval_status, 'approved')

    def test_reject_user(self):
        """Тест отклонения пользователя админом"""
        response = self.client.patch(
            reverse('users:admin-users-reject', kwargs={'pk': self.partner.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.partner.refresh_from_db()
        self.assertEqual(self.partner.approval_status, 'rejected')

    def test_block_user(self):
        """Тест блокировки пользователя админом"""
        response = self.client.patch(
            reverse('users:admin-users-block', kwargs={'pk': self.partner.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.partner.refresh_from_db()
        self.assertFalse(self.partner.is_active)

    def test_unblock_user(self):
        """Тест разблокировки пользователя админом"""
        # Сначала блокируем
        self.partner.is_active = False
        self.partner.save()

        response = self.client.patch(
            reverse('users:admin-users-unblock', kwargs={'pk': self.partner.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.partner.refresh_from_db()
        self.assertTrue(self.partner.is_active)

    def test_pending_approval_list(self):
        """Тест получения списка пользователей, ожидающих одобрения"""
        response = self.client.get(reverse('users:admin-users-pending-approval'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)  # только partner ждёт одобрения

    def test_user_stats(self):
        """Тест получения статистики пользователей"""
        response = self.client.get(reverse('users:admin-users-stats'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_users', response.data)
        self.assertIn('partners', response.data)
        self.assertIn('stores', response.data)
        self.assertIn('pending_approval', response.data)
        self.assertIn('blocked_users', response.data)


class PasswordResetTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone='+996555123456',
            email='test@test.com',
            name='Тест',
            second_name='Тестов',
            password='SecurePass123'
        )

    def test_password_reset_request_with_email(self):
        """Тест запроса сброса пароля только с email"""
        data = {
            'email': 'test@test.com'
        }

        response = self.client.post(reverse('users:password_reset'), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Проверяем, что код создался
        self.assertTrue(
            PasswordResetRequest.objects.filter(user=self.user).exists()
        )

    def test_password_reset_invalid_email(self):
        """Тест запроса сброса с несуществующим email"""
        data = {
            'email': 'nonexistent@test.com'
        }

        response = self.client.post(reverse('users:password_reset'), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)