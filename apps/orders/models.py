from django.db import models
from django.conf import settings
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist


class StoreApplication(models.Model):
    """Заявка магазина партнёру на поставку товаров (не заказ клиента!)"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает рассмотрения'),
        ('approved', 'Одобрена'),
        ('rejected', 'Отклонена'),
        ('fulfilled', 'Выполнена'),
        ('cancelled', 'Отменена'),
    ]

    # Участники
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='applications',
        verbose_name='Магазин'
    )
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='store_applications',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )

    # Статус и даты
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    application_date = models.DateTimeField(auto_now_add=True, verbose_name='Дата заявки')
    approved_date = models.DateTimeField(null=True, blank=True, verbose_name='Дата одобрения')
    fulfilled_date = models.DateTimeField(null=True, blank=True, verbose_name='Дата выполнения')

    # Комментарии
    store_notes = models.TextField(blank=True, verbose_name='Комментарий магазина')
    partner_notes = models.TextField(blank=True, verbose_name='Комментарий партнёра')

    class Meta:
        db_table = 'store_applications'
        verbose_name = 'Заявка магазина'
        verbose_name_plural = 'Заявки магазинов'
        ordering = ['-application_date']

    def __str__(self):
        return f"Заявка #{self.id} от {self.store.store_name}"

    def approve(self):
        """Одобрить заявку и зарезервировать товары у партнёра."""
        if self.status == 'pending':
            self.status = 'approved'
            self.approved_date = timezone.now()
            self.save()

            # Резервируем товары у партнёра
            for item in self.items.all():
                try:
                    partner_inventory = self.partner.partner_inventory.get(product=item.product)
                    partner_inventory.reserved_quantity += item.final_quantity
                    partner_inventory.save()
                except ObjectDoesNotExist:
                    # Если у партнера нет такой позиции в инвентаре, это ошибка в данных
                    # В реальном проекте здесь стоит добавить логирование
                    pass

    def fulfill(self):
        """Выполнить заявку - передать товары магазину."""
        if self.status == 'approved':
            self.status = 'fulfilled'
            self.fulfilled_date = timezone.now()
            self.save()

            # Переносим товары от партнёра к магазину
            for item in self.items.all():
                quantity_to_transfer = item.final_quantity

                # Уменьшаем количество на складе партнёра
                try:
                    partner_inventory = self.partner.partner_inventory.get(product=item.product)
                    partner_inventory.quantity -= quantity_to_transfer
                    partner_inventory.reserved_quantity -= quantity_to_transfer
                    partner_inventory.save()
                except ObjectDoesNotExist:
                    # Эта ошибка не должна происходить, если заявка была корректно одобрена
                    pass

                # Добавляем на склад магазина
                store_inventory, created = self.store.inventory.get_or_create(
                    product=item.product,
                    defaults={'quantity': Decimal('0')}
                )
                store_inventory.quantity += quantity_to_transfer
                store_inventory.save()


class StoreApplicationItem(models.Model):
    """Позиция в заявке магазина."""

    application = models.ForeignKey(
        StoreApplication,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Заявка'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name='Товар'
    )
    requested_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Запрашиваемое количество'
    )

    # Партнёр может одобрить меньшее количество
    approved_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Одобренное количество'
    )

    class Meta:
        db_table = 'store_application_items'
        verbose_name = 'Позиция заявки'
        verbose_name_plural = 'Позиции заявок'
        unique_together = ['application', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.requested_quantity}"

    @property
    def final_quantity(self):
        """Итоговое количество для передачи (одобренное или, если нет, запрошенное)."""
        return self.approved_quantity if self.approved_quantity is not None else self.requested_quantity


# --- Заказы клиентов в магазинах ---

class Order(models.Model):
    """Заказ клиента в магазине (продажа)."""
    STATUS_CHOICES = [
        ('pending', 'Ожидает подтверждения'),
        ('confirmed', 'Подтвержден'),
        ('completed', 'Выполнен'),
        ('cancelled', 'Отменен'),
    ]

    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='customer_orders',
        verbose_name='Магазин'
    )
    # Клиент (опционально)
    customer_name = models.CharField(max_length=200, blank=True, verbose_name='Имя клиента')
    customer_phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон клиента')

    # Статус и даты
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    order_date = models.DateTimeField(auto_now_add=True, verbose_name='Дата заказа')
    confirmed_date = models.DateTimeField(null=True, blank=True, verbose_name='Дата подтверждения')
    completed_date = models.DateTimeField(null=True, blank=True, verbose_name='Дата выполнения')

    # Суммы
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Подытог')
    bonus_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Скидка по бонусам')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Итоговая сумма')

    # Оплата
    payment_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Сумма оплаты'
    )
    debt_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Сумма долга')

    # Бонусная информация
    bonus_items_count = models.PositiveIntegerField(default=0, verbose_name='Количество бонусных товаров')
    notes = models.TextField(blank=True, verbose_name='Комментарии')

    class Meta:
        db_table = 'customer_orders'
        verbose_name = 'Заказ клиента'
        verbose_name_plural = 'Заказы клиентов'
        ordering = ['-order_date']

    def __str__(self):
        return f"Заказ #{self.id} в {self.store.store_name}"

    def calculate_totals(self):
        """Пересчёт итоговых сумм заказа на основе его позиций."""
        items = self.items.all()

        self.subtotal = sum(item.total_price for item in items)
        self.bonus_discount = sum(item.bonus_discount for item in items)
        self.bonus_items_count = sum(item.bonus_quantity for item in items)
        self.total_amount = self.subtotal - self.bonus_discount
        self.debt_amount = max(self.total_amount - self.payment_amount, Decimal('0'))

        self.save()

    def complete(self):
        """Завершить заказ, списать товары и создать долг, если необходимо."""
        if self.status in ['pending', 'confirmed']:
            self.status = 'completed'
            self.completed_date = timezone.now()
            self.save()

            # Списываем товары со склада магазина
            for item in self.items.all():
                try:
                    inventory = self.store.inventory.get(product=item.product)
                    inventory.quantity -= item.quantity
                    inventory.save()
                except ObjectDoesNotExist:
                    # Ошибка: пытаемся продать товар, которого нет в инвентаре магазина
                    pass

            # Создаём долг, если оплачено не всё
            if self.debt_amount > 0:
                from apps.debts.models import Debt
                Debt.objects.create(
                    store=self.store,
                    amount=self.debt_amount,
                    order=self,
                    description=f'Долг по заказу #{self.id}'
                )


class OrderItem(models.Model):
    """Позиция в заказе клиента."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='Заказ')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, verbose_name='Товар')

    quantity = models.DecimalField(
        max_digits=8, decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Количество'
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена за единицу')
    total_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Общая стоимость')

    # Бонусная система
    bonus_quantity = models.DecimalField(max_digits=8, decimal_places=3, default=0, verbose_name='Бонусное количество')
    bonus_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Бонусная скидка')

    class Meta:
        db_table = 'order_items'
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказов'
        unique_together = ['order', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def save(self, *args, **kwargs):
        # Если цена не указана, берём текущую цену товара
        if self.unit_price is None:
            self.unit_price = self.product.price

        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def calculate_bonus_discount(self):
        """Расчёт бонусной скидки (например, каждый 21-й товар бесплатно)."""
        from apps.bonuses.models import BonusCalculation

        # Получаем историю покупок этого товара в данном магазине
        previous_quantity = OrderItem.objects.filter(
            order__store=self.order.store,
            product=self.product,
            order__status='completed'
        ).exclude(pk=self.pk).aggregate(
            total=models.Sum('quantity')
        )['total'] or Decimal('0')

        calculator = BonusCalculation()
        bonus_info = calculator.calculate_bonus(
            previous_quantity=previous_quantity,
            current_quantity=self.quantity,
            unit_price=self.unit_price
        )

        self.bonus_quantity = bonus_info['bonus_quantity']
        self.bonus_discount = bonus_info['bonus_discount']
        self.save()


# --- Запросы товаров партнёрами у администратора ---

class ProductRequest(models.Model):
    """Запрос товаров партнёром у администратора."""
    STATUS_CHOICES = [
        ('pending', 'Ожидает рассмотрения'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонен'),
        ('fulfilled', 'Выполнен'),  # Добавлен статус для физической передачи товара
        ('cancelled', 'Отменен'),
    ]

    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_requests',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')

    # Даты
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата запроса')
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата обработки')
    fulfilled_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата выполнения')

    # Комментарии
    partner_notes = models.TextField(blank=True, verbose_name='Комментарий партнера')
    admin_notes = models.TextField(blank=True, verbose_name='Комментарий администратора')

    class Meta:
        db_table = 'product_requests'
        verbose_name = 'Запрос товаров'
        verbose_name_plural = 'Запросы товаров'
        ordering = ['-requested_at']

    def __str__(self):
        return f"Запрос #{self.id} от {self.partner.get_full_name()}"

    def approve(self):
        """Одобрить запрос администратором."""
        if self.status == 'pending':
            self.status = 'approved'
            self.processed_at = timezone.now()
            self.save()

    def reject(self, reason=""):
        """Отклонить запрос администратором."""
        if self.status == 'pending':
            self.status = 'rejected'
            self.processed_at = timezone.now()
            if reason:
                self.admin_notes = reason
            self.save()

    def fulfill(self):
        """Выполнить запрос - передать товары партнёру."""
        if self.status == 'approved':
            self.status = 'fulfilled'
            self.fulfilled_at = timezone.now()
            self.save()

            # Переносим товары от админа к партнёру
            for item in self.items.all():
                quantity_to_transfer = item.approved_quantity or item.requested_quantity

                # Списываем с главного склада (если он есть)
                # Предполагается, что у продукта есть связь с инвентарём админа,
                # например, `product.admin_inventory`
                try:
                    admin_inventory = item.product.admin_inventory
                    admin_inventory.quantity -= quantity_to_transfer
                    admin_inventory.save()
                except (AttributeError, ObjectDoesNotExist):
                    # Продукт не связан с инвентарём админа
                    pass

                # Добавляем на склад партнёра
                partner_inventory, created = self.partner.partner_inventory.get_or_create(
                    product=item.product,
                    defaults={'quantity': Decimal('0')}
                )
                partner_inventory.quantity += quantity_to_transfer
                partner_inventory.save()


class ProductRequestItem(models.Model):
    """Позиция в запросе товаров."""

    request = models.ForeignKey(
        ProductRequest,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Запрос'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        verbose_name='Товар'
    )
    requested_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Запрашиваемое количество'
    )
    # Администратор может одобрить другое количество
    approved_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Одобренное количество'
    )

    class Meta:
        db_table = 'product_request_items'
        verbose_name = 'Позиция запроса товаров'
        verbose_name_plural = 'Позиции запросов товаров'
        unique_together = ['request', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.requested_quantity}"