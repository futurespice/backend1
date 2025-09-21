import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class Command(BaseCommand):
    help = 'Диагностика проблем с регистрацией пользователей'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔍 Начинаем диагностику...'))

        # 1. Проверяем модель User
        self.test_user_model()

        # 2. Проверяем API регистрации
        self.test_registration_api()

        # 3. Проверяем URLs
        self.test_urls()

    def test_user_model(self):
        """Тестируем создание пользователей через модель"""
        self.stdout.write('\n📝 Тестируем User модель...')

        # Очищаем тестовых пользователей
        User.objects.filter(email__contains='test.com').delete()

        # Тестируем создание партнёра
        try:
            partner = User.objects.create_user(
                phone='+996555111111',
                email='partner.test@test.com',
                name='Тест',
                second_name='Партнёр',
                password='SecurePass123p!8Rt'  # Более надёжный пароль
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Партнёр создан: {partner.full_name}, роль: {partner.role}, статус: {partner.approval_status}'
                )
            )

            # Проверяем, что маркер удалён из пароля
            if partner.check_password('SecurePass123'):
                self.stdout.write(self.style.SUCCESS('✅ Маркер корректно удалён из пароля'))
            else:
                self.stdout.write(self.style.ERROR('❌ Проблема с удалением маркера'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Ошибка создания партнёра: {e}'))

        # Тестируем создание магазина
        try:
            store = User.objects.create_user(
                phone='+996555222222',
                email='store.test@test.com',
                name='Тест',
                second_name='Магазин',
                password='SecurePass123'
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Магазин создан: {store.full_name}, роль: {store.role}, статус: {store.approval_status}'
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Ошибка создания магазина: {e}'))

    def test_registration_api(self):
        """Тестируем API регистрации"""
        self.stdout.write('\n🌐 Тестируем API регистрации...')

        client = APIClient()

        # Очищаем тестовых пользователей
        User.objects.filter(email__contains='apitest.com').delete()

        # Тестируем регистрацию партнёра
        partner_data = {
            'name': 'Иван',
            'second_name': 'Петров',
            'email': 'partner@apitest.com',
            'phone': '+996555333333',
            'password': 'SecurePass123p!8Rt'  # Более надёжный пароль
        }

        try:
            response = client.post('/api/auth/register/', partner_data, format='json')
            self.stdout.write(f'Партнёр - Status Code: {response.status_code}')

            if response.status_code == status.HTTP_201_CREATED:
                self.stdout.write(self.style.SUCCESS('✅ API регистрация партнёра успешна'))
                self.stdout.write(f'Response: {response.data}')
            else:
                self.stdout.write(self.style.ERROR('❌ API регистрация партнёра неуспешна'))
                self.stdout.write(f'Errors: {response.data}')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Ошибка API партнёра: {e}'))

        # Тестируем регистрацию магазина
        store_data = {
            'name': 'Петр',
            'second_name': 'Сидоров',
            'email': 'store@apitest.com',
            'phone': '+996555444444',
            'password': 'SecurePass123'
        }

        try:
            response = client.post('/api/auth/register/', store_data, format='json')
            self.stdout.write(f'Магазин - Status Code: {response.status_code}')

            if response.status_code == status.HTTP_201_CREATED:
                self.stdout.write(self.style.SUCCESS('✅ API регистрация магазина успешна'))
                self.stdout.write(f'Response: {response.data}')
            else:
                self.stdout.write(self.style.ERROR('❌ API регистрация магазина неуспешна'))
                self.stdout.write(f'Errors: {response.data}')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Ошибка API магазина: {e}'))

    def test_urls(self):
        """Проверяем доступность URLs"""
        self.stdout.write('\n🔗 Проверяем URLs...')

        try:
            from django.urls import reverse
            register_url = reverse('users:register')
            self.stdout.write(self.style.SUCCESS(f'✅ URL регистрации: {register_url}'))

            login_url = reverse('users:login')
            self.stdout.write(self.style.SUCCESS(f'✅ URL входа: {login_url}'))

            profile_url = reverse('users:profile')
            self.stdout.write(self.style.SUCCESS(f'✅ URL профиля: {profile_url}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Проблема с URL: {e}'))

        # Тестируем вход
        self.test_login_api()

        self.stdout.write('\n🏁 Диагностика завершена!')

    def test_login_api(self):
        """Тестируем API входа"""
        self.stdout.write('\n🔐 Тестируем API входа...')

        client = APIClient()

        # Создаем тестового пользователя если его нет
        try:
            user = User.objects.get(phone='+996555999999')
        except User.DoesNotExist:
            user = User.objects.create_user(
                phone='+996555999999',
                email='login.test@test.com',
                name='Логин',
                second_name='Тест',
                password='SecurePass123'
            )
            self.stdout.write(self.style.SUCCESS(f'✅ Создан тестовый пользователь для входа: {user.full_name}'))

        # Тестируем вход
        login_data = {
            'phone': '+996555999999',
            'password': 'SecurePass123'
        }

        try:
            response = client.post('/api/auth/login/', login_data, format='json')
            self.stdout.write(f'Вход - Status Code: {response.status_code}')

            if response.status_code == status.HTTP_200_OK:
                self.stdout.write(self.style.SUCCESS('✅ API вход успешен'))
                self.stdout.write(
                    f'Получены токены: access={bool(response.data.get("access"))}, refresh={bool(response.data.get("refresh"))}')
            else:
                self.stdout.write(self.style.ERROR('❌ API вход неуспешен'))
                self.stdout.write(f'Errors: {response.data}')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Ошибка API входа: {e}'))