# apps/orders/services.py
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Any
from django.db import transaction
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.db.models import F
import logging

from .models import (
    PartnerOrder, PartnerOrderItem,
    StoreOrder, StoreOrderItem,
    OrderHistory, OrderReturn, OrderReturnItem
)
from products.models import Product
from products.services import BonusService
from stores.services import InventoryService
from stores.models import Store, PartnerInventory

logger = logging.getLogger(__name__)


class OrderService:
    """Сервис управления заказами — атомарные, безопасные, идемпотентные операции"""

    # =========================================================================
    #  PARTNER ORDER (партнёр → админ)
    # =========================================================================

    @staticmethod
    @transaction.atomic
    def create_partner_order(
        partner: Any,
        items_data: List[Dict[str, Any]],
        note: str = '',
        idempotency_key: Optional[str] = None
    ) -> PartnerOrder:
        """
        Создание заказа партнёра к админу.
        - Идемпотентность
        - Проверка весовых товаров
        - Пересчёт суммы
        - История
        """
        if not items_data:
            raise ValidationError("Список товаров не может быть пустым")

        # Идемпотентность
        if idempotency_key:
            existing = PartnerOrder.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                logger.info(f"Идемпотентный заказ партнёра: {idempotency_key} → {existing.id}")
                return existing

        # Создаём заказ
        order = PartnerOrder.objects.create(
            partner=partner,
            note=note.strip(),
            total_amount=Decimal('0'),
            idempotency_key=idempotency_key or str(uuid.uuid4())
        )

        total = Decimal('0')
        seen_products = set()

        for idx, item_data in enumerate(items_data):
            product_id = item_data.get('product')
            quantity_raw = item_data.get('quantity')

            if not product_id or not isinstance(product_id, int):
                raise ValidationError(f"Позиция {idx + 1}: укажите корректный product ID")

            if product_id in seen_products:
                raise ValidationError(f"Позиция {idx + 1}: дублирование товара")
            seen_products.add(product_id)

            try:
                quantity = Decimal(str(quantity_raw))
                if quantity <= 0:
                    raise ValidationError("quantity должен быть > 0")
            except (InvalidOperation, TypeError, ValueError):
                raise ValidationError(f"Позиция {idx + 1}: некорректное значение quantity")

            # Блокируем товар
            product = Product.objects.select_for_update().get(id=product_id)

            if product.is_weight_based:
                try:
                    product.validate_quantity(quantity)
                except ValidationError as e:
                    raise ValidationError(f"Товар {product.name}: {e}")

            price = product.price
            if price <= 0:
                raise ValidationError(f"Товар {product.name} имеет нулевую или отрицательную цену")

            # Создаём позицию
            PartnerOrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                price=price
            )

            total += price * quantity

        # Обновляем сумму
        order.total_amount = total
        order.save(update_fields=['total_amount'])

        # История
        OrderHistory.objects.create(
            order_type='partner',
            order_id=order.id,
            type='general',
            amount=total,
            note=f'Создан заказ партнёра #{order.id}'
        )

        logger.info(f"Создан заказ партнёра #{order.id} на {total} сом")
        return order

    @staticmethod
    @transaction.atomic
    def confirm_partner_order(order: PartnerOrder) -> PartnerOrder:
        """Подтверждение заказа партнёра админом"""
        if order.status != 'pending':
            raise ValidationError(f"Заказ #{order.id} уже обработан (статус: {order.status})")

        insufficient = []
        for item in order.items.select_related('product').all():
            if item.product.stock_quantity < item.quantity:
                insufficient.append(f"{item.product.name}: {item.product.stock_quantity} < {item.quantity}")

        if insufficient:
            raise ValidationError("Недостаточно товара на складе:\n" + "\n".join(insufficient))

        # Снимаем со склада и добавляем в инвентарь партнёра
        for item in order.items.select_related('product').all():
            product = item.product

            # Снимаем со склада
            Product.objects.filter(id=product.id).update(
                stock_quantity=F('stock_quantity') - item.quantity
            )

            # Добавляем в инвентарь партнёра
            InventoryService.add_to_inventory(
                partner=order.partner,
                product=product,
                quantity=item.quantity,
                commit=False  # внутри add_to_inventory есть save()
            )

        order.status = 'confirmed'
        order.save(update_fields=['status'])

        OrderHistory.objects.create(
            order_type='partner',
            order_id=order.id,
            type='general',
            amount=order.total_amount,
            note='Заказ подтверждён админом'
        )

        logger.info(f"Заказ партнёра #{order.id} подтверждён")
        return order

    # =========================================================================
    #  STORE ORDER (магазин → партнёр)
    # =========================================================================

    @staticmethod
    @transaction.atomic
    def create_store_order_from_request(
        store_request: Any,
        partner: Any,
        idempotency_key: Optional[str] = None
    ) -> StoreOrder:
        """Создание заказа магазина из подтверждённого StoreRequest"""
        if store_request.status != 'confirmed':
            raise ValidationError("Запрос магазина должен быть подтверждён")

        if idempotency_key:
            existing = StoreOrder.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                logger.info(f"Идемпотентный заказ магазина: {idempotency_key} → {existing.id}")
                return existing

        order = StoreOrder.objects.create(
            store=store_request.store,
            partner=partner,
            store_request=store_request,
            note=store_request.note or '',
            total_amount=Decimal('0'),
            bonus_applied=Decimal('0'),
            idempotency_key=idempotency_key or str(uuid.uuid4())
        )

        total = Decimal('0')
        bonus = Decimal('0')

        # Копируем позиции
        for req_item in store_request.items.filter(is_cancelled=False).select_related('product'):
            price = req_item.price or req_item.product.price

            StoreOrderItem.objects.create(
                order=order,
                product=req_item.product,
                quantity=req_item.quantity,
                price=price,
                is_bonus=False
            )

            total += price * req_item.quantity

        # Применяем бонусы
        bonus_applied = BonusService.apply_bonus_to_order(order)
        bonus = bonus_applied

        order.total_amount = total
        order.bonus_applied = bonus
        order.save(update_fields=['total_amount', 'bonus_applied'])

        OrderHistory.objects.create(
            order_type='store',
            order_id=order.id,
            type='general',
            amount=total,
            note=f'Создан заказ магазина #{order.id}'
        )

        logger.info(f"Создан заказ магазина #{order.id} на {total} сом (бонус: {bonus})")
        return order

    @staticmethod
    @transaction.atomic
    def fulfill_store_order(order: StoreOrder) -> StoreOrder:
        """Выполнение заказа магазина"""
        if order.is_fulfilled:
            raise ValidationError(f"Заказ #{order.id} уже выполнен")

        store = order.store
        partner = order.partner

        # Проверка наличия у партнёра
        insufficient = []
        for item in order.items.filter(is_bonus=False).select_related('product'):
            inv = PartnerInventory.objects.filter(partner=partner, product=item.product).first()
            if not inv or inv.quantity < item.quantity:
                available = inv.quantity if inv else 0
                insufficient.append(f"{item.product.name}: {available} < {item.quantity}")

        if insufficient:
            raise ValidationError("Недостаточно товара у партнёра:\n" + "\n".join(insufficient))

        # Выполняем перемещение
        for item in order.items.select_related('product').all():
            if item.is_bonus:
                # Бонус: просто добавляем в магазин
                InventoryService.add_to_inventory(
                    store=store,
                    product=item.product,
                    quantity=item.quantity
                )
            else:
                # Снимаем у партнёра
                InventoryService.remove_from_inventory(
                    partner=partner,
                    product=item.product,
                    quantity=item.quantity
                )
                # Добавляем в магазин
                InventoryService.add_to_inventory(
                    store=store,
                    product=item.product,
                    quantity=item.quantity
                )
                # Увеличиваем долг
                store.debt = F('debt') + item.total

        store.save(update_fields=['debt'])

        order.is_fulfilled = True
        order.save(update_fields=['is_fulfilled'])

        OrderHistory.objects.create(
            order_type='store',
            order_id=order.id,
            type='general',
            amount=order.total_amount,
            note='Заказ выполнен'
        )

        logger.info(f"Заказ магазина #{order.id} выполнен. Долг магазина: {store.debt}")
        return order

    # =========================================================================
    #  ORDER RETURNS
    # =========================================================================

    @staticmethod
    @transaction.atomic
    def create_return(
        order: StoreOrder,
        items_data: List[Dict[str, Any]],
        reason: str,
        idempotency_key: Optional[str] = None
    ) -> OrderReturn:
        """Создание возврата товаров"""
        if not order.is_fulfilled:
            raise ValidationError("Можно вернуть только выполненный заказ")

        if not items_data:
            raise ValidationError("Укажите хотя бы одну позицию для возврата")

        if idempotency_key:
            existing = OrderReturn.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                logger.info(f"Идемпотентный возврат: {idempotency_key} → {existing.id}")
                return existing

        return_request = OrderReturn.objects.create(
            order=order,
            reason=reason.strip(),
            total_amount=Decimal('0'),
            idempotency_key=idempotency_key or str(uuid.uuid4())
        )

        total = Decimal('0')
        seen_products = set()

        for idx, item_data in enumerate(items_data):
            product_id = item_data.get('product')
            quantity_raw = item_data.get('quantity')

            if not product_id or not isinstance(product_id, int):
                raise ValidationError(f"Позиция {idx + 1}: укажите product ID")

            if product_id in seen_products:
                raise ValidationError(f"Позиция {idx + 1}: дублирование")
            seen_products.add(product_id)

            try:
                quantity = Decimal(str(quantity_raw))
                if quantity <= 0:
                    raise ValidationError("quantity > 0")
            except (InvalidOperation, TypeError):
                raise ValidationError(f"Позиция {idx + 1}: некорректное quantity")

            product = get_object_or_404(Product, id=product_id)
            order_item = order.items.filter(product=product).first()

            if not order_item:
                raise ValidationError(f"Товар {product.name} не был в заказе")

            if quantity > order_item.quantity:
                raise ValidationError(
                    f"Нельзя вернуть больше чем было: {quantity} > {order_item.quantity} ({product.name})"
                )

            OrderReturnItem.objects.create(
                return_request=return_request,
                product=product,
                quantity=quantity,
                price=order_item.price
            )

            total += order_item.price * quantity

        return_request.total_amount = total
        return_request.save(update_fields=['total_amount'])

        logger.info(f"Создан возврат #{return_request.id} на {total} сом")
        return return_request

    @staticmethod
    @transaction.atomic
    def approve_return(order_return: OrderReturn) -> OrderReturn:
        """Подтверждение возврата"""
        if order_return.status != 'pending':
            raise ValidationError(f"Возврат #{order_return.id} уже обработан")

        order = order_return.order
        store = order.store
        partner = order.partner

        # Перемещаем обратно
        for item in order_return.items.select_related('product').all():
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
            # Уменьшаем долг
            store.debt = F('debt') - item.total

        store.save(update_fields=['debt'])

        order_return.status = 'approved'
        order_return.save(update_fields=['status'])

        OrderHistory.objects.create(
            order_type='store',
            order_id=order.id,
            type='returned',
            amount=order_return.total_amount,
            note=f'Возврат #{order_return.id} подтверждён'
        )

        logger.info(f"Возврат #{order_return.id} подтверждён. Долг магазина: {store.debt}")
        return order_return