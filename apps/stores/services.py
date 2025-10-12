from decimal import Decimal
from django.db import transaction
from .models import Store, StoreRequest, StoreRequestItem, StoreInventory, PartnerInventory
from products.models import Product
from products.services import BonusService, CostCalculator
from users.services import EmailService


class StoreRequestService:
    """Управление запросами магазина"""

    @staticmethod
    @transaction.atomic
    def create_request(store, created_by, items_data, note=''):
        """Создать запрос магазина"""
        request = StoreRequest.objects.create(
            store=store,
            created_by=created_by,
            note=note,
            total_amount=Decimal('0')
        )

        total_amount = Decimal('0')

        for item_data in items_data:
            product = Product.objects.get(id=item_data['product'])
            quantity = Decimal(item_data['quantity'])

            # Цена на момент запроса
            price = product.price

            StoreRequestItem.objects.create(
                request=request,
                product=product,
                quantity=quantity,
                price=price
            )

            total_amount += quantity * price

        request.total_amount = total_amount
        request.save()

        return request

    @staticmethod
    @transaction.atomic
    def cancel_item(item):
        """Отменить позицию в запросе"""
        if item.is_cancelled:
            raise ValueError("Позиция уже отменена")

        item.is_cancelled = True
        item.save()

        # Пересчитываем общую сумму запроса
        request = item.request
        active_items = request.items.filter(is_cancelled=False)

        total = sum(i.quantity * i.price for i in active_items)
        request.total_amount = total
        request.save()

        # Если все позиции отменены, отменяем запрос
        if not active_items.exists():
            request.status = 'cancelled'
            request.save()


class InventoryService:
    """Управление инвентарём"""

    @staticmethod
    @transaction.atomic
    def add_to_inventory(store=None, partner=None, product=None, quantity=0):
        """Добавить товар в инвентарь"""
        if store:
            inventory, _ = StoreInventory.objects.get_or_create(
                store=store,
                product=product,
                defaults={'quantity': 0}
            )
            inventory.quantity += Decimal(quantity)
            inventory.save()
            return inventory
        elif partner:
            inventory, _ = PartnerInventory.objects.get_or_create(
                partner=partner,
                product=product,
                defaults={'quantity': 0}
            )
            inventory.quantity += Decimal(quantity)
            inventory.save()
            return inventory
        raise ValueError("Укажите store или partner")

    @staticmethod
    @transaction.atomic
    def remove_from_inventory(store=None, partner=None, product=None, quantity=0):
        """Списать товар из инвентаря"""
        if store:
            inventory = StoreInventory.objects.filter(
                store=store,
                product=product
            ).first()
        elif partner:
            inventory = PartnerInventory.objects.filter(
                partner=partner,
                product=product
            ).first()
        else:
            raise ValueError("Укажите store или partner")

        if not inventory or inventory.quantity < Decimal(quantity):
            raise ValueError(f"Недостаточно товара {product.name} на складе")

        inventory.quantity -= Decimal(quantity)
        if inventory.quantity <= 0:
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
        """Перемещение товара от партнера к магазину с учетом долга и бонусов"""
        partner_inventory = PartnerInventory.objects.filter(
            partner=partner, product=product
        ).first()
        if not partner_inventory or partner_inventory.quantity < Decimal(quantity):
            raise ValueError(f"Недостаточно товара {product.name} у партнера")

        # Списываем у партнера
        partner_inventory.quantity -= Decimal(quantity)
        if partner_inventory.quantity <= 0:
            partner_inventory.delete()
        else:
            partner_inventory.save()

        # Добавляем в магазин
        store_inventory, _ = StoreInventory.objects.get_or_create(
            store=store, product=product, defaults={'quantity': 0}
        )
        store_inventory.quantity += Decimal(quantity)
        store_inventory.save()

        # Обновляем долг магазина
        store.debt += product.price * Decimal(quantity)
        store.save()

        # Проверяем бонусы
        bonus_count = BonusService.add_product_to_counter(store, partner, product, int(quantity))
        if bonus_count > 0:
            EmailService.send_bonus_notification(store, partner, product, bonus_count)

        return store_inventory