# apps/orders/services.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from products.models import Product
from stores.models import Store
from users.models import User
from .models import (
    OrderHistory,
    OrderReturn,
    OrderReturnItem,
    OrderReturnStatus,
    OrderType,
    PartnerOrder,
    PartnerOrderItem,
    PartnerOrderStatus,
    StoreOrder,
    StoreOrderItem,
    StoreOrderStatus,
)


@dataclass
class OrderItemPayload:
    product: Product
    quantity: Decimal
    price: Decimal
    is_bonus: bool = False
    reason: str = ""


class OrderService:
    """
    Сервис для работы с заказами:
    - создание партнёрских заказов
    - создание заказов магазинов
    - возвраты
    - смена статусов + история
    """

    # --- PartnerOrder --------------------------------------------------------

    @classmethod
    @transaction.atomic
    def create_partner_order(
        cls,
        *,
        partner: User,
        items: Iterable[dict],
        created_by: Optional[User],
        comment: str = "",
        idempotency_key: Optional[str] = None,
    ) -> PartnerOrder:
        if not partner:
            raise ValidationError("Не указан партнёр")

        if idempotency_key:
            existing = PartnerOrder.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            if existing:
                return existing

        order = PartnerOrder.objects.create(
            partner=partner,
            created_by=created_by,
            comment=comment,
            status=PartnerOrderStatus.PENDING,
            idempotency_key=idempotency_key,
        )

        total = Decimal("0")
        for raw in items:
            payload = cls._parse_item_payload(raw)
            if payload.quantity <= 0:
                raise ValidationError("Количество должно быть больше 0")
            if payload.price < 0:
                raise ValidationError("Цена не может быть отрицательной")

            item = PartnerOrderItem.objects.create(
                order=order,
                product=payload.product,
                quantity=payload.quantity,
                price=payload.price,
            )
            total += item.total

        order.total_amount = total
        order.save(update_fields=["total_amount"])
        cls._create_history(
            order_type=OrderType.PARTNER,
            order_id=order.pk,
            old_status="",
            new_status=order.status,
            changed_by=created_by,
            comment="Создание партнёрского заказа",
        )
        return order

    # --- StoreOrder ----------------------------------------------------------

    @classmethod
    @transaction.atomic
    def create_store_order(
        cls,
        *,
        store: Store,
        partner: User,
        items: Iterable[dict],
        created_by: Optional[User],
        store_request=None,
        idempotency_key: Optional[str] = None,
        debt_amount: Decimal = Decimal("0"),
        paid_amount: Decimal = Decimal("0"),
    ) -> StoreOrder:
        if not store:
            raise ValidationError("Не указан магазин")
        if not partner:
            raise ValidationError("Не указан партнёр")

        if idempotency_key:
            existing = StoreOrder.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            if existing:
                return existing

        order = StoreOrder.objects.create(
            store=store,
            partner=partner,
            store_request=store_request,
            created_by=created_by,
            status=StoreOrderStatus.PENDING,
            idempotency_key=idempotency_key,
            debt_amount=debt_amount or Decimal("0"),
            paid_amount=paid_amount or Decimal("0"),
        )

        total = Decimal("0")
        for raw in items:
            payload = cls._parse_item_payload(raw)
            if payload.quantity <= 0:
                raise ValidationError("Количество должно быть больше 0")
            if payload.price < 0:
                raise ValidationError("Цена не может быть отрицательной")

            item = StoreOrderItem.objects.create(
                order=order,
                product=payload.product,
                quantity=payload.quantity,
                price=payload.price,
                is_bonus=payload.is_bonus,
            )
            total += item.total

        order.total_amount = total
        order.save(update_fields=["total_amount"])

        cls._create_history(
            order_type=OrderType.STORE,
            order_id=order.pk,
            old_status="",
            new_status=order.status,
            changed_by=created_by,
            comment="Создание заказа магазина",
        )
        return order

    @classmethod
    @transaction.atomic
    def change_store_order_status(
        cls,
        *,
        order: StoreOrder,
        new_status: str,
        changed_by: Optional[User],
        comment: str = "",
    ) -> StoreOrder:
        old_status = order.status
        if old_status == new_status:
            return order

        # простая валидация переходов
        allowed = {
            StoreOrderStatus.PENDING: {
                StoreOrderStatus.CONFIRMED,
                StoreOrderStatus.CANCELLED,
            },
            StoreOrderStatus.CONFIRMED: {
                StoreOrderStatus.COMPLETED,
                StoreOrderStatus.CANCELLED,
            },
            StoreOrderStatus.COMPLETED: set(),
            StoreOrderStatus.CANCELLED: set(),
            StoreOrderStatus.DRAFT: {
                StoreOrderStatus.PENDING,
                StoreOrderStatus.CANCELLED,
            },
        }
        if new_status not in allowed.get(old_status, set()):
            raise ValidationError(
                f"Нельзя сменить статус {old_status} на {new_status}"
            )

        order.status = new_status
        order.save(update_fields=["status"])

        # Здесь можно добавить работу с инвентарём и долгом (stores.InventoryService)

        cls._create_history(
            order_type=OrderType.STORE,
            order_id=order.pk,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            comment=comment or f"Смена статуса заказа магазина {old_status}->{new_status}",
        )
        return order

    # --- OrderReturn ---------------------------------------------------------

    @classmethod
    @transaction.atomic
    def create_order_return(
        cls,
        *,
        store: Store,
        partner: User,
        order: Optional[StoreOrder],
        items: Iterable[dict],
        created_by: Optional[User],
        reason: str = "",
        idempotency_key: Optional[str] = None,
    ) -> OrderReturn:
        if not store:
            raise ValidationError("Не указан магазин")
        if not partner:
            raise ValidationError("Не указан партнёр")

        if idempotency_key:
            existing = OrderReturn.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            if existing:
                return existing

        order_return = OrderReturn.objects.create(
            store=store,
            partner=partner,
            order=order,
            created_by=created_by,
            reason=reason,
            status=OrderReturnStatus.PENDING,
            idempotency_key=idempotency_key,
        )

        total = Decimal("0")
        for raw in items:
            payload = cls._parse_item_payload(raw)
            if payload.quantity <= 0:
                raise ValidationError("Количество должно быть больше 0")
            if payload.price < 0:
                raise ValidationError("Цена не может быть отрицательной")

            item = OrderReturnItem.objects.create(
                order_return=order_return,
                product=payload.product,
                quantity=payload.quantity,
                price=payload.price,
                reason=payload.reason,
            )
            total += item.total

        order_return.total_amount = total
        order_return.save(update_fields=["total_amount"])

        cls._create_history(
            order_type=OrderType.RETURN,
            order_id=order_return.pk,
            old_status="",
            new_status=order_return.status,
            changed_by=created_by,
            comment="Создание возврата по заказу",
        )
        return order_return

    @classmethod
    @transaction.atomic
    def change_order_return_status(
        cls,
        *,
        order_return: OrderReturn,
        new_status: str,
        changed_by: Optional[User],
        comment: str = "",
    ) -> OrderReturn:
        old_status = order_return.status
        if old_status == new_status:
            return order_return

        allowed = {
            OrderReturnStatus.PENDING: {
                OrderReturnStatus.APPROVED,
                OrderReturnStatus.REJECTED,
                OrderReturnStatus.CANCELLED,
            },
            OrderReturnStatus.APPROVED: set(),
            OrderReturnStatus.REJECTED: set(),
            OrderReturnStatus.CANCELLED: set(),
        }
        if new_status not in allowed.get(old_status, set()):
            raise ValidationError(
                f"Нельзя сменить статус {old_status} на {new_status}"
            )

        order_return.status = new_status
        order_return.save(update_fields=["status"])

        cls._create_history(
            order_type=OrderType.RETURN,
            order_id=order_return.pk,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            comment=comment or f"Смена статуса возврата {old_status}->{new_status}",
        )
        return order_return

    # --- internal helpers ----------------------------------------------------

    @staticmethod
    def _parse_item_payload(raw: dict) -> OrderItemPayload:
        product = raw["product"]
        quantity = Decimal(str(raw["quantity"]))
        price = Decimal(str(raw.get("price")))
        is_bonus = bool(raw.get("is_bonus", False))
        reason = raw.get("reason", "")
        return OrderItemPayload(
            product=product,
            quantity=quantity,
            price=price,
            is_bonus=is_bonus,
            reason=reason,
        )

    @staticmethod
    def _create_history(
        *,
        order_type: str,
        order_id: int,
        old_status: str,
        new_status: str,
        changed_by: Optional[User],
        comment: str = "",
    ) -> OrderHistory:
        return OrderHistory.objects.create(
            order_type=order_type,
            order_id=order_id,
            old_status=old_status or "",
            new_status=new_status,
            changed_by=changed_by,
            comment=comment or "",
        )
