from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Order, OrderItem, OrderHistory, OrderReturn, OrderReturnItem
from stores.models import Store, StoreInventory
from products.models import Product
from products.services import BonusService, DefectiveProductService
from stores.services import InventoryService
from django_redis import get_redis_connection
import uuid



class OrderService:
    @staticmethod
    def check_idempotency(key):
        """Проверка идемпотентности для предотвращения дублирования"""
        redis = get_redis_connection("default")
        if redis.get(f"idempotency:{key}"):
            raise ValidationError("Запрос уже обработан")
        redis.setex(f"idempotency:{key}", 3600, "processed")  # Храним 1 час

    @staticmethod
    @transaction.atomic
    def create_order(store, partner, items_data, note='', idempotency_key=None):
        if idempotency_key:
            OrderService.check_idempotency(idempotency_key)
        order = Order.objects.create(
            store=store,
            partner=partner,
            note=note,
            total_amount=Decimal('0'),
            debt_increase=Decimal('0'),
            idempotency_key=idempotency_key or uuid.uuid4()
        )
        total = Decimal('0')
        total_quantity = Decimal('0')
        for item_data in items_data:
            product = Product.objects.get(id=item_data['product'])
            quantity = Decimal(item_data['quantity'])
            price = product.price
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                price=price
            )
            total += quantity * price
            total_quantity += quantity
        order.total_amount = total
        order.debt_increase = total
        order.store.debt += total
        order.store.save()
        order.save()
        OrderHistory.objects.create(
            order=order,
            type='general',
            amount=total,
            quantity=total_quantity,
            note='Заказ создан'
        )
        return order

    @staticmethod
    @transaction.atomic
    def confirm_order(order, idempotency_key=None):
        if idempotency_key:
            OrderService.check_idempotency(idempotency_key)
        if order.status != 'pending':
            raise ValueError("Заказ уже обработан")
        for item in order.items.all():
            InventoryService.transfer_to_store(
                partner=order.partner,
                store=order.store,
                product=item.product,
                quantity=item.quantity
            )
            bonus = BonusService.add_product_to_counter(order.store, order.partner, item.product, int(item.quantity))
            if bonus > 0:
                OrderHistory.objects.create(
                    order=order,
                    type='bonus',
                    amount=Decimal(bonus) * item.price,
                    quantity=Decimal(bonus),
                    product=item.product,
                    note='Бонус получен'
                )
        order.status = 'confirmed'
        order.save()
        OrderHistory.objects.create(
            order=order,
            type='sold',
            amount=order.total_amount,
            quantity=sum(item.quantity for item in order.items.all()),
            note='Заказ подтвержден'
        )

    @staticmethod
    @transaction.atomic
    def create_return(order, items_data, reason='', idempotency_key=None):
        if idempotency_key:
            OrderService.check_idempotency(idempotency_key)
        order_return = OrderReturn.objects.create(
            order=order,
            reason=reason,
            total_amount=Decimal('0'),
            idempotency_key=idempotency_key or uuid.uuid4()
        )
        total = Decimal('0')
        total_quantity = Decimal('0')
        for item_data in items_data:
            product = Product.objects.get(id=item_data['product'])
            quantity = Decimal(item_data['quantity'])
            price = product.price
            # Проверяем наличие в StoreInventory
            inventory = StoreInventory.objects.filter(store=order.store, product=product).first()
            if not inventory or inventory.quantity < quantity:
                raise ValidationError(f"Недостаточно товара {product.name} в магазине")
            OrderReturnItem.objects.create(
                return_order=order_return,
                product=product,
                quantity=quantity,
                price=price
            )
            total += quantity * price
            total_quantity += quantity
        order_return.total_amount = total
        order_return.save()
        OrderHistory.objects.create(
            order=order,
            type='returned',
            amount=total,
            quantity=total_quantity,
            note=f'Возврат создан: {reason}'
        )
        return order_return

    @staticmethod
    @transaction.atomic
    def approve_return(order_return):
        if order_return.status != 'pending':
            raise ValueError("Возврат уже обработан")
        for item in order_return.items.all():
            # Списываем из магазина
            InventoryService.remove_from_inventory(
                store=order_return.order.store,
                product=item.product,
                quantity=item.quantity
            )
            # Возвращаем на склад партнера или админа
            InventoryService.add_to_inventory(
                partner=order_return.order.partner,
                product=item.product,
                quantity=item.quantity
            )
            # Уменьшаем долг
            order_return.order.debt_increase -= item.total
            order_return.order.store.debt -= item.total
            order_return.order.store.save()
            order_return.order.save()
            # Если брак, регистрируем
            if 'брак' in order_return.reason.lower():
                DefectiveProductService.add_defective(
                    partner=order_return.order.partner,
                    product=item.product,
                    quantity=item.quantity,
                    amount=item.total
                )
                OrderHistory.objects.create(
                    order=order_return.order,
                    type='defect',
                    amount=item.total,
                    quantity=item.quantity,
                    product=item.product,
                    note='Брак зарегистрирован'
                )
        order_return.status = 'approved'
        order_return.save()
        OrderHistory.objects.create(
            order=order_return.order,
            type='returned',
            amount=order_return.total_amount,
            quantity=sum(item.quantity for item in order_return.items.all()),
            note='Возврат подтвержден'
        )