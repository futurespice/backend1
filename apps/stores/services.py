# apps/stores/services.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import (
    StoreProductRequest, StoreRequest, StoreRequestItem,
    StoreInventory, PartnerInventory
)
from products.models import Product, StoreProductCounter, BonusHistory


class StoreRequestService:
    """Сервис работы с запросами магазинов"""

    @staticmethod
    @transaction.atomic
    def create_from_product_requests(store, user, idempotency_key=None):
        """
        ИСПРАВЛЕНИЕ #5-6: Создание StoreRequest из StoreProductRequest
        ИСПРАВЛЕНИЕ #11: С защитой от race condition через idempotency_key
        """
        # Получаем все запросы магазина
        product_requests = StoreProductRequest.objects.select_for_update().filter(
            store=store
        ).select_related('product')

        if not product_requests.exists():
            raise ValidationError('Нет товаров для запроса')

        # Создаём StoreRequest
        store_request = StoreRequest.objects.create(
            store=store,
            created_by=user,
            idempotency_key=idempotency_key
        )

        # Переносим товары в StoreRequestItem
        total_amount = Decimal('0')
        for pr in product_requests:
            # ИСПРАВЛЕНИЕ #12: Валидация весовых товаров
            if pr.product.is_weight_based:
                pr.product.validate_quantity(pr.quantity)

            item = StoreRequestItem.objects.create(
                request=store_request,
                product=pr.product,
                quantity=pr.quantity,
                price=pr.product.price
            )
            total_amount += item.total

        # Обновляем общую сумму
        store_request.total_amount = total_amount
        store_request.save()

        # Удаляем временные запросы
        product_requests.delete()

        return store_request

    @staticmethod
    @transaction.atomic
    def cancel_item(request, item_id):
        """Отменить позицию в запросе"""
        item = StoreRequestItem.objects.select_for_update().get(
            id=item_id,
            request=request
        )

        if item.is_cancelled:
            raise ValidationError('Позиция уже отменена')

        item.is_cancelled = True
        item.save()

        # Пересчитываем сумму запроса
        active_items = request.items.filter(is_cancelled=False)
        request.total_amount = sum(
            item.total for item in active_items
        )
        request.save()

        # Если все позиции отменены, отменяем запрос
        if not active_items.exists():
            # Можно добавить поле status='cancelled' если нужно
            pass


class InventoryService:
    """
    ИСПРАВЛЕНИЕ #9: Управление инвентарём
    ИСПРАВЛЕНИЕ #16: Все операции в transaction.atomic
    """

    @staticmethod
    @transaction.atomic
    def add_to_inventory(store=None, partner=None, product=None, quantity=0):
        """Добавить товар в инвентарь"""
        quantity = Decimal(quantity)

        if store:
            inventory, _ = StoreInventory.objects.select_for_update().get_or_create(
                store=store,
                product=product,
                defaults={'quantity': Decimal('0')}
            )
            inventory.quantity += quantity
            inventory.save()
            return inventory
        elif partner:
            inventory, _ = PartnerInventory.objects.select_for_update().get_or_create(
                partner=partner,
                product=product,
                defaults={'quantity': Decimal('0')}
            )
            inventory.quantity += quantity
            inventory.save()
            return inventory

        raise ValueError("Укажите store или partner")

    @staticmethod
    @transaction.atomic
    def remove_from_inventory(store=None, partner=None, product=None, quantity=0):
        """Списать товар из инвентаря"""
        quantity = Decimal(quantity)

        if store:
            inventory = StoreInventory.objects.select_for_update().filter(
                store=store,
                product=product
            ).first()
        elif partner:
            inventory = PartnerInventory.objects.select_for_update().filter(
                partner=partner,
                product=product
            ).first()
        else:
            raise ValueError("Укажите store или partner")

        if not inventory or inventory.quantity < quantity:
            raise ValidationError(
                f"Недостаточно товара {product.name} на складе. "
                f"Доступно: {inventory.quantity if inventory else 0}"
            )

        inventory.quantity -= quantity

        if inventory.quantity <= Decimal('0'):
            inventory.delete()
        else:
            inventory.save()

        return inventory

    @staticmethod
    def get_inventory(store=None, partner=None):
        """Получить весь инвентарь"""
        if store:
            return StoreInventory.objects.filter(store=store).select_related('product')
        elif partner:
            return PartnerInventory.objects.filter(partner=partner).select_related('product')
        return []

    @staticmethod
    @transaction.atomic
    def transfer_to_store(partner, store, product, quantity):
        """
        Перемещение товара от партнера к магазину
        ИСПРАВЛЕНИЕ #12: С учетом бонусов
        """
        quantity = Decimal(quantity)

        # ИСПРАВЛЕНИЕ #12: Весовые товары НЕ участвуют в бонусах
        if product.is_weight_based:
            product.validate_quantity(quantity)

        # Проверяем наличие у партнёра
        partner_inventory = PartnerInventory.objects.select_for_update().filter(
            partner=partner,
            product=product
        ).first()

        if not partner_inventory or partner_inventory.quantity < quantity:
            raise ValidationError(
                f"Недостаточно товара {product.name} у партнера. "
                f"Доступно: {partner_inventory.quantity if partner_inventory else 0}"
            )

        # Списываем у партнера
        partner_inventory.quantity -= quantity
        if partner_inventory.quantity <= Decimal('0'):
            partner_inventory.delete()
        else:
            partner_inventory.save()

        # Добавляем в магазин
        store_inventory, _ = StoreInventory.objects.select_for_update().get_or_create(
            store=store,
            product=product,
            defaults={'quantity': Decimal('0')}
        )
        store_inventory.quantity += quantity
        store_inventory.save()

        # Обновляем долг магазина
        store.debt += product.price * quantity
        store.save()

        # ИСПРАВЛЕНИЕ #12: Проверяем бонусы (только для НЕ весовых товаров)
        bonus_count = 0
        if not product.is_weight_based:
            bonus_count = BonusService.add_product_to_counter(
                store, partner, product, int(quantity)
            )

        return store_inventory, bonus_count


class BonusService:
    """
    ИСПРАВЛЕНИЕ #12: Сервис бонусов
    Каждый 21-й товар ВСЕГО бесплатно (не по отдельности для каждого товара)
    """

    @staticmethod
    @transaction.atomic
    def add_product_to_counter(store, partner, product, quantity: int):
        """
        Добавить товары в счётчик и проверить бонус
        ИСПРАВЛЕНИЕ #12: Весовые товары НЕ участвуют
        """
        # Весовые товары не участвуют в бонусах
        if product.is_weight_based:
            return 0

        # Получаем или создаём счётчик
        counter, _ = StoreProductCounter.objects.select_for_update().get_or_create(
            store=store,
            partner=partner,
            product=product,
            defaults={
                'total_count': 0,
                'product_count': 0
            }
        )

        # Увеличиваем счётчики
        counter.total_count += quantity
        counter.product_count += quantity
        counter.save()

        # Проверяем бонус (каждый 21-й)
        bonus_count = 0
        if counter.check_bonus():
            bonus_count = counter.total_count // 21

            # Создаём запись о бонусе
            BonusHistory.objects.create(
                store=store,
                partner=partner,
                product=product,
                quantity=bonus_count,
                bonus_value=product.price * bonus_count
            )

            # Обновляем время последнего бонуса
            from django.utils import timezone
            counter.last_bonus_at = timezone.now()
            counter.save()

        return bonus_count

    @staticmethod
    @transaction.atomic
    def apply_bonus_to_order(order):
        """
        ИСПРАВЛЕНИЕ #12: Применить бонусы к заказу
        Проверяет все товары в заказе и добавляет бонусные позиции
        """
        from orders.models import StoreOrderItem

        bonus_applied = Decimal('0')

        for item in order.items.all():
            # Весовые товары не участвуют в бонусах
            if item.product.is_weight_based:
                continue

            # Получаем счётчик
            counter = StoreProductCounter.objects.select_for_update().filter(
                store=order.store,
                partner=order.partner,
                product=item.product
            ).first()

            if counter and counter.check_bonus():
                bonus_quantity = counter.total_count // 21

                # Создаём бонусную позицию
                StoreOrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=bonus_quantity,
                    price=Decimal('0'),  # Бонус = бесплатно
                    is_bonus=True
                )

                bonus_applied += item.product.price * bonus_quantity

                # Записываем в историю
                BonusHistory.objects.create(
                    store=order.store,
                    partner=order.partner,
                    product=item.product,
                    quantity=bonus_quantity,
                    bonus_value=item.product.price * bonus_quantity,
                    order=order
                )

        order.bonus_applied = bonus_applied
        order.save()

        return bonus_applied

    @staticmethod
    def get_bonus_status(store, partner, product):
        """Получить статус бонуса для товара"""
        counter = StoreProductCounter.objects.filter(
            store=store,
            partner=partner,
            product=product
        ).first()

        if not counter:
            return {
                'total_count': 0,
                'product_count': 0,
                'next_bonus_at': 21,
                'bonus_available': False
            }

        return {
            'total_count': counter.total_count,
            'product_count': counter.product_count,
            'next_bonus_at': 21 - (counter.total_count % 21),
            'bonus_available': counter.check_bonus(),
            'last_bonus_at': counter.last_bonus_at
        }