from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Store, StoreSelection, StoreRequest, StoreRequestItem, StoreInventory, PartnerInventory, Region, City
from products.models import Product
from decimal import Decimal
from django.core.exceptions import ValidationError
from .services import StoreRequestService, InventoryService
from .views import StoreViewSet

User = get_user_model()


class StoreTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            phone='+996123456789',
            email='admin@test.com',
            password='testpass',
            role='admin',
            approval_status='approved'
        )
        self.store_user = User.objects.create_user(
            phone='+996987654321',
            email='store@test.com',
            password='testpass',
            role='store',
            approval_status='approved'
        )
        self.partner = User.objects.create_user(
            phone='+996555555555',
            email='partner@test.com',
            password='p!8Rttestpass',
            role='partner',
            approval_status='approved'
        )
        self.product = Product.objects.create(
            name='Test Product',
            price=Decimal('100.00'),
            category='piece',
            stock_quantity=Decimal('1000')
        )
        self.region = Region.objects.create(name='Test Region', code='TR')
        self.city = City.objects.create(name='Test City', region=self.region)
        self.store = Store.objects.create(
            name='Test Store',
            inn='123456789012',
            owner_name='Test Owner',
            phone='+996111222333',
            region=self.region,
            city=self.city,
            address='123 Test St',
            debt=Decimal('5000.00'),
            approval_status='approved',
            created_by=self.admin
        )
        self.selection = StoreSelection.objects.create(user=self.store_user, store=self.store)

    def test_unique_inn(self):
        """Тест уникальности ИНН"""
        with self.assertRaises(ValidationError):
            Store.objects.create(
                name='Another Store',
                inn='123456789012',  # Same INN
                owner_name='Another Owner',
                phone='+996444555666',
                region=self.region,
                city=self.city,
                address='456 Test St',
                created_by=self.admin
            )

    def test_store_request_creation(self):
        """Тест создания запроса магазина"""
        items_data = [
            {'product': self.product.id, 'quantity': Decimal('10.0')}
        ]
        request = StoreRequestService.create_request(
            store=self.store,
            created_by=self.store_user,
            items_data=items_data,
            note='Test request'
        )
        self.assertEqual(request.total_amount, Decimal('1000.00'))
        self.assertEqual(request.items.count(), 1)
        self.assertEqual(request.items.first().quantity, Decimal('10.0'))

    def test_inventory_transfer(self):
        """Тест перемещения товара от партнера к магазину"""
        PartnerInventory.objects.create(
            partner=self.partner,
            product=self.product,
            quantity=Decimal('50.0')
        )
        InventoryService.transfer_to_store(
            partner=self.partner,
            store=self.store,
            product=self.product,
            quantity=Decimal('20.0')
        )
        store_inventory = StoreInventory.objects.get(store=self.store, product=self.product)
        partner_inventory = PartnerInventory.objects.get(partner=self.partner, product=self.product)
        self.assertEqual(store_inventory.quantity, Decimal('20.0'))
        self.assertEqual(partner_inventory.quantity, Decimal('30.0'))
        self.assertEqual(self.store.debt, Decimal('7000.00'))  # 5000 + 20*100

    def test_repay_debt(self):
        """Тест погашения долга"""
        self.store.debt = Decimal('5000.00')
        self.store.save()
        view = StoreViewSet()
        view.request = type('Request', (), {'user': self.admin, 'data': {'amount': '2000'}})
        view.get_object = lambda: self.store
        response = view.repay_debt(None, pk=self.store.id)
        self.store.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.debt, Decimal('3000.00'))

    def test_approve_store(self):
        """Тест одобрения магазина"""
        pending_store = Store.objects.create(
            name='Pending Store',
            inn='987654321012',
            owner_name='Pending Owner',
            phone='+996777888999',
            region=self.region,
            city=self.city,
            address='789 Test St',
            created_by=self.store_user,
            approval_status='pending'
        )
        view = StoreViewSet()
        view.request = type('Request', (), {'user': self.admin})
        view.get_object = lambda: pending_store
        response = view.approve(None, pk=pending_store.id)
        pending_store.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pending_store.approval_status, 'approved')
        self.assertTrue(pending_store.is_active)