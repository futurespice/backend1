from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from decimal import Decimal

from .models import Region

User = get_user_model()


class RegionModelTestCase(TestCase):
    """Тесты модели Region"""

    def test_create_region(self):
        """Тест создания региона"""
        region = Region.objects.create(
            name='Бишкек',
            code='BIS',
            description='Столица Кыргызстана',
            delivery_cost=Decimal('100.00'),
            delivery_radius_km=30,
            priority=1
        )

        self.assertEqual(region.name, 'Бишкек')
        self.assertEqual(region.code, 'BIS')
        self.assertTrue(region.is_active)
        self.assertEqual(region.priority, 1)

    def test_region_str(self):
        """Тест строкового представления"""
        region = Region.objects.create(name='Ош', code='OSH')
        self.assertEqual(str(region), 'Ош (OSH)')


class RegionAPITestCase(TestCase):
    """Тесты API регионов"""

    def setUp(self):
        self.client = APIClient()

        # Создаём админа
        self.admin = User.objects.create_user(
            phone='+996555000000',
            email='admin@test.com',
            name='Админ',
            second_name='Тестов',
            password='admin123',
            role='admin'
        )

        # Создаём партнёра
        self.partner = User.objects.create_user(
            phone='+996555111111',
            email='partner@test.com',
            name='Партнёр',
            second_name='Тестов',
            password='partner123p!8Rt'
        )
        self.partner.approval_status = 'approved'
        self.partner.save()

        # Создаём тестовый регион
        self.region = Region.objects.create(
            name='Тестовый регион',
            code='TEST',
            delivery_cost=Decimal('50.00')
        )

    def test_admin_can_create_region(self):
        """Тест создания региона админом"""
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': 'Новый регион',
            'code': 'NEW',
            'description': 'Тестовое описание',
            'delivery_cost': '75.00',
            'delivery_radius_km': 25,
            'priority': 3
        }

        response = self.client.post(reverse('regions:region-list'), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Region.objects.count(), 2)

    def test_partner_can_list_regions(self):
        """Тест получения списка регионов партнёром"""
        self.client.force_authenticate(user=self.partner)

        response = self.client.get(reverse('regions:region-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_partner_cannot_create_region(self):
        """Тест что партнёр не может создавать регионы"""
        self.client.force_authenticate(user=self.partner)

        data = {
            'name': 'Запрещённый регион',
            'code': 'FORBIDDEN'
        }

        response = self.client.post(reverse('regions:region-list'), data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_active_regions_endpoint(self):
        """Тест endpoint активных регионов"""
        # Создаём неактивный регион
        Region.objects.create(name='Неактивный', code='INACTIVE', is_active=False)

        self.client.force_authenticate(user=self.partner)
        response = self.client.get(reverse('regions:region-active'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)  # Только активные

    def test_region_stats_endpoint(self):
        """Тест endpoint статистики региона"""
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            reverse('regions:region-stats', kwargs={'pk': self.region.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('region_info', response.data)
        self.assertIn('stores_count', response.data)
        self.assertIn('delivery_settings', response.data)