from django.db import transaction
from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from .models import Order, OrderItem, OrderHistory, OrderReturn, OrderReturnItem
from stores.models import Store, StoreInventory
from products.models import Product
from products.services import BonusService, DefectiveProductService
from stores.services import InventoryService
from django_redis import get_redis_connection
import uuid

from decimal import Decimal, ROUND_HALF_UP

Q2 = Decimal('0.01')


def _q2(x: Decimal) -> Decimal:
    return (x or Decimal('0')).quantize(Q2, rounding=ROUND_HALF_UP)


class OrderService:
    @staticmethod
    def check_idempotency(key):
        """Проверка идемпотентности для предотвращения дублирования"""
        redis = get_redis_connection("default")
        cached = redis.get(f"idempotency:{key}")
        if cached:
            # Возвращаем информацию о том, что запрос уже обработан
            return {
                'duplicate': True,
                'order_id': cached.decode('utf-8') if cached else None
            }
        return {'duplicate': False}

    @staticmethod
    def set_idempotency(key, order_id):
        """Сохраняем информацию об успешно обработанном запросе"""
        redis = get_redis_connection("default")
        redis.setex(f"idempotency:{key}", 3600, str(order_id))

    @staticmethod
    @transaction.atomic
    def create_order(store, partner, items_data, note='', idempotency_key=None):
        if idempotency_key:
            check_result = OrderService.check_idempotency(idempotency_key)
            if check_result['duplicate']:
                # Возвращаем существующий заказ
                order_id = check_result['order_id']
                if order_id:
                    try:
                        existing_order = Order.objects.get(id=int(order_id))
                        return existing_order
                    except Order.DoesNotExist:
                        pass
                # Если заказ не найден, но ключ существует
                raise DRFValidationError({
                    "idempotency_key": "Запрос уже обработан, но заказ не найден. Попробуйте с новым idempotency_key"
                })

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
            total += _q2(quantity * price)
            total_quantity += quantity
        order.total_amount = _q2(total)
        order.debt_increase = Decimal('0')
        order.save(update_fields=['total_amount', 'debt_increase'])
        OrderHistory.objects.create(
            order=order,
            type='general',
            amount=total,
            quantity=total_quantity,
            note='Заказ создан'
        )

        # Сохраняем идемпотентность только после успешного создания
        if idempotency_key:
            OrderService.set_idempotency(idempotency_key, order.id)

        return order

    @staticmethod
    @transaction.atomic
    def confirm_order(order, idempotency_key=None):
        if idempotency_key:
            check_result = OrderService.check_idempotency(idempotency_key)
            if check_result['duplicate']:
                raise DRFValidationError({
                    "idempotency_key": "Запрос уже обработан"
                })

        if order.status != 'pending':
            raise ValueError("Заказ уже обработан")

        for item in order.items.all():
            InventoryService.transfer_to_store(
                partner=order.partner,
                store=order.store,
                product=item.product,
                quantity=item.quantity
            )
            if getattr(item.product, 'category', None) != 'weight':
                bonus = BonusService.add_product_to_counter(order.store, order.partner, item.product,
                                                            int(item.quantity))
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
        order.debt_increase = _q2(order.total_amount)
        order.store.debt = _q2(order.store.debt + order.total_amount)
        order.store.save(update_fields=['debt'])
        order.save(update_fields=['status', 'debt_increase'])
        OrderHistory.objects.create(
            order=order,
            type='sold',
            amount=order.total_amount,
            quantity=sum(item.quantity for item in order.items.all()),
            note='Заказ подтвержден'
        )

        if idempotency_key:
            OrderService.set_idempotency(idempotency_key, f"confirm_{order.id}")

    @staticmethod
    @transaction.atomic
    def create_return(order, items_data, reason='', idempotency_key=None):
        if idempotency_key:
            check_result = OrderService.check_idempotency(idempotency_key)
            if check_result['duplicate']:
                # Возвращаем существующий возврат
                return_id = check_result['order_id']
                if return_id and return_id.startswith('return_'):
                    try:
                        existing_return = OrderReturn.objects.get(id=int(return_id.replace('return_', '')))
                        return existing_return
                    except OrderReturn.DoesNotExist:
                        pass
                raise DRFValidationError({
                    "idempotency_key": "Запрос уже обработан"
                })

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

        if idempotency_key:
            OrderService.set_idempotency(idempotency_key, f"return_{order_return.id}")

        return order_return

    # approve_return остается без изменений
    @staticmethod
    @transaction.atomic
    def approve_return(order_return):
        if order_return.status != 'pending':
            raise ValueError("Возврат уже обработан")
        for item in order_return.items.all():
            InventoryService.remove_from_inventory(
                store=order_return.order.store,
                product=item.product,
                quantity=item.quantity
            )
            InventoryService.add_to_inventory(
                partner=order_return.order.partner,
                product=item.product,
                quantity=item.quantity
            )
            line_total = _q2(item.quantity * item.price)
            order_return.order.debt_increase = _q2(order_return.order.debt_increase - line_total)
            order_return.order.store.debt = _q2(order_return.order.store.debt - line_total)
            order_return.order.store.save(update_fields=['debt'])
            order_return.order.save(update_fields=['debt_increase'])
            if 'брак' in order_return.reason.lower():
                DefectiveProductService.add_defective(
                    partner=order_return.order.partner,
                    product=item.product,
                    quantity=item.quantity,
                    amount=line_total,
                )
                OrderHistory.objects.create(
                    order=order_return.order,
                    type='defect',
                    amount=line_total,
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