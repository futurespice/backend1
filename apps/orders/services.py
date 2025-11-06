from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
import uuid

from .models import (
    PartnerOrder, PartnerOrderItem,
    StoreOrder, StoreOrderItem,
    OrderHistory, OrderReturn, OrderReturnItem
)
from products.models import Product
from products.services import BonusService
from stores.services import InventoryService


class OrderService:
    """Сервис управления заказами"""

    @staticmethod
    @transaction.atomic
    def create_partner_order(partner, items_data, note='', idempotency_key=None):
        """Создание заказа партнёра к админу"""
        if idempotency_key:
            existing = PartnerOrder.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        order = PartnerOrder.objects.create(
            partner=partner,
            note=note,
            total_amount=Decimal('0'),
            idempotency_key=idempotency_key or str(uuid.uuid4())
        )

        total = Decimal('0')

        for item_data in items_data:
            product = Product.objects.select_for_update().get(id=item_data['product'])
            quantity = Decimal(item_data['quantity'])

            if product.is_weight_based:
                product.validate_quantity(quantity)

            price = product.price

            PartnerOrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                price=price
            )

            total += price * quantity

        order.total_amount = total
        order.save()

        OrderHistory.objects.create(
            order_type='partner',
            order_id=order.id,
            type='general',
            amount=total,
            note=f'Создан заказ партнёра #{order.id}'
        )

        return order

    @staticmethod
    @transaction.atomic
    def confirm_partner_order(order):
        """Подтверждение заказа партнёра админом"""
        if order.status != 'pending':
            raise ValidationError('Заказ уже обработан')

        for item in order.items.select_related('product'):
            if item.product.stock_quantity < item.quantity:
                raise ValidationError(
                    f'Недостаточно товара {item.product.name} на складе'
                )

        for item in order.items.select_related('product'):
            product = item.product
            product.stock_quantity -= item.quantity
            product.save()

            InventoryService.add_to_inventory(
                partner=order.partner,
                product=product,
                quantity=item.quantity
            )

        order.status = 'confirmed'
        order.save()

        OrderHistory.objects.create(
            order_type='partner',
            order_id=order.id,
            type='general',
            amount=order.total_amount,
            note='Заказ подтверждён админом'
        )

        return order

    @staticmethod
    @transaction.atomic
    def create_store_order_from_request(store_request, partner, idempotency_key=None):
        """Создание заказа магазина из StoreRequest"""
        if idempotency_key:
            existing = StoreOrder.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        order = StoreOrder.objects.create(
            store=store_request.store,
            partner=partner,
            store_request=store_request,
            note=store_request.note,
            total_amount=Decimal('0'),
            idempotency_key=idempotency_key or str(uuid.uuid4())
        )

        total = Decimal('0')

        for req_item in store_request.items.filter(is_cancelled=False):
            StoreOrderItem.objects.create(
                order=order,
                product=req_item.product,
                quantity=req_item.quantity,
                price=req_item.price,
                is_bonus=False
            )

            total += req_item.total

        bonus_applied = BonusService.apply_bonus_to_order(order)

        order.total_amount = total
        order.bonus_applied = bonus_applied
        order.save()

        OrderHistory.objects.create(
            order_type='store',
            order_id=order.id,
            type='general',
            amount=total,
            note=f'Создан заказ магазина #{order.id}'
        )

        return order

    @staticmethod
    @transaction.atomic
    def fulfill_store_order(order):
        """Выполнение заказа магазина"""
        if order.is_fulfilled:
            raise ValidationError('Заказ уже выполнен')

        store = order.store
        partner = order.partner

        for item in order.items.filter(is_bonus=False):
            from stores.models import PartnerInventory
            partner_inv = PartnerInventory.objects.filter(
                partner=partner,
                product=item.product
            ).first()

            if not partner_inv or partner_inv.quantity < item.quantity:
                raise ValidationError(
                    f'Недостаточно товара {item.product.name} у партнёра'
                )

        for item in order.items.select_related('product'):
            if item.is_bonus:
                InventoryService.add_to_inventory(
                    store=store,
                    product=item.product,
                    quantity=item.quantity
                )
            else:
                InventoryService.remove_from_inventory(
                    partner=partner,
                    product=item.product,
                    quantity=item.quantity
                )

                InventoryService.add_to_inventory(
                    store=store,
                    product=item.product,
                    quantity=item.quantity
                )

                store.debt += item.total

        store.save()

        order.is_fulfilled = True
        order.save()

        OrderHistory.objects.create(
            order_type='store',
            order_id=order.id,
            type='general',
            amount=order.total_amount,
            note='Заказ выполнен'
        )

        return order

    @staticmethod
    @transaction.atomic
    def create_return(order, items_data, reason='', idempotency_key=None):
        """Создание возврата товаров"""
        if idempotency_key:
            existing = OrderReturn.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        order_return = OrderReturn.objects.create(
            order=order,
            reason=reason,
            total_amount=Decimal('0'),
            idempotency_key=idempotency_key or str(uuid.uuid4())
        )

        total = Decimal('0')

        for item_data in items_data:
            product = Product.objects.get(id=item_data['product'])
            quantity = Decimal(item_data['quantity'])

            order_item = order.items.filter(product=product).first()
            if not order_item:
                raise ValidationError(f'Товар {product.name} не был в заказе')

            if quantity > order_item.quantity:
                raise ValidationError(f'Нельзя вернуть больше чем было заказано')

            OrderReturnItem.objects.create(
                return_request=order_return,
                product=product,
                quantity=quantity,
                price=order_item.price
            )

            total += order_item.price * quantity

        order_return.total_amount = total
        order_return.save()

        return order_return

    @staticmethod
    @transaction.atomic
    def approve_return(order_return):
        """Подтверждение возврата"""
        if order_return.status != 'pending':
            raise ValidationError('Возврат уже обработан')

        order = order_return.order
        store = order.store
        partner = order.partner

        for item in order_return.items.select_related('product'):
            InventoryService.remove_from_inventory(
                store=store,
                product=item.product,
                quantity=item.quantity
            )

            InventoryService.add_to_inventory(
                partner=partner,
                product=item.product,
                quantity=item.quantity
            )

            store.debt -= item.total

        store.save()

        order_return.status = 'approved'
        order_return.save()

        OrderHistory.objects.create(
            order_type='store',
            order_id=order.id,
            type='returned',
            amount=order_return.total_amount,
            note=f'Возврат #{order_return.id} подтверждён'
        )

        return order_return