from django.db import models
from django.conf import settings
from decimal import Decimal
from django.core.validators import MinValueValidator


class Order(models.Model):
    """Заказ"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает подтверждения'),
        ('confirmed', 'Подтвержден'),
        ('completed', 'Выполнен'),
        ('cancelled', 'Отменен'),
    ]

    # Участники
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='orders', verbose_name='Магазин')
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='partner_orders',
        limit_choices_to={'role': 'partner'},
        verbose_name='Партнер'
    )

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
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Сумма оплаты'
    )
    debt_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Сумма долга')

    # Бонусная информация
    bonus_items_count = models.PositiveIntegerField(default=0, verbose_name='Количество бонусных товаров')

    # Комментарии
    notes = models.TextField(blank=True, verbose_name='Комментарии')

    class Meta:
        db_table = 'orders'
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-order_date']

    def __str__(self):
        return f"Заказ #{self.id} - {self.store.name} ({self.order_date.strftime('%d.%m.%Y')})"

    def calculate_totals(self):
        """Пересчитать суммы заказа"""
        items = self.items.all()

        self.subtotal = sum(item.total_price for item in items)
        self.bonus_discount = sum(item.bonus_discount for item in items)
        self.total_amount = self.subtotal - self.bonus_discount
        self.bonus_items_count = sum(item.bonus_quantity for item in items)

        # Рассчитываем долг
        self.debt_amount = max(self.total_amount - self.payment_amount, 0)

        self.save()

    def apply_bonus_system(self):
        """Применить бонусную систему (каждый 21-й товар бесплатно)"""
        # Получаем все бонусные товары в заказе
        bonus_eligible_items = self.items.filter(product__is_bonus_eligible=True)

        for item in bonus_eligible_items:
            # Каждый 21-й товар бесплатно
            bonus_count = item.quantity // 21
            item.bonus_quantity = bonus_count
            item.bonus_discount = bonus_count * item.unit_price
            item.save()

    def mark_as_confirmed(self):
        """Подтвердить заказ"""
        from django.utils import timezone

        self.status = 'confirmed'
        self.confirmed_date = timezone.now()

        # Списываем товары со склада
        for item in self.items.all():
            if not item.product.reduce_stock(item.quantity):
                raise ValueError(f"Недостаточно товара {item.product.name} на складе")

        # Создаем долг если есть неоплаченная сумма
        if self.debt_amount > 0:
            from debts.models import Debt
            Debt.objects.create(
                store=self.store,
                order=self,
                amount=self.debt_amount,
                description=f"Долг по заказу #{self.id}"
            )

        self.save()

    def mark_as_completed(self):
        """Завершить заказ"""
        from django.utils import timezone

        self.status = 'completed'
        self.completed_date = timezone.now()
        self.save()


class OrderItem(models.Model):
    """Позиция в заказе"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='Заказ')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, verbose_name='Товар')

    # Количество и цены
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,  # Для весовых товаров
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Количество'
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена за единицу')
    total_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Общая стоимость')

    # Бонусная система
    bonus_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=0,
        verbose_name='Бонусное количество'
    )
    bonus_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Бонусная скидка')

    class Meta:
        db_table = 'order_items'
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказов'
        unique_together = ['order', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def save(self, *args, **kwargs):
        # Сохраняем цену товара на момент заказа
        self.unit_price = self.product.price

        # Рассчитываем общую стоимость
        if self.product.category_type == 'weight':
            self.total_price = self.product.calculate_price(self.quantity)
        else:
            self.total_price = self.unit_price * self.quantity

        super().save(*args, **kwargs)


class ProductRequest(models.Model):
    """Запрос товаров партнером у администратора"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает рассмотрения'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонен'),
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

    # Комментарии
    partner_notes = models.TextField(blank=True, verbose_name='Комментарий партнера')
    admin_notes = models.TextField(blank=True, verbose_name='Комментарий администратора')

    class Meta:
        db_table = 'product_requests'
        verbose_name = 'Запрос товаров'
        verbose_name_plural = 'Запросы товаров'
        ordering = ['-requested_at']

    def __str__(self):
        return f"Запрос #{self.id} от {self.partner.full_name}"

    def approve(self, admin_user):
        """Одобрить запрос"""
        from django.utils import timezone

        self.status = 'approved'
        self.processed_at = timezone.now()

        # Переносим товары на склад партнера
        for item in self.items.all():
            # Здесь можно реализовать логику перемещения товаров
            # на виртуальный склад партнера
            pass

        self.save()

    def reject(self, admin_user, reason=""):
        """Отклонить запрос"""
        from django.utils import timezone

        self.status = 'rejected'
        self.processed_at = timezone.now()
        if reason:
            self.admin_notes = reason
        self.save()


class ProductRequestItem(models.Model):
    """Позиция в запросе товаров"""
    request = models.ForeignKey(ProductRequest, on_delete=models.CASCADE, related_name='items', verbose_name='Запрос')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, verbose_name='Товар')
    requested_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Запрашиваемое количество'
    )

    class Meta:
        db_table = 'product_request_items'
        verbose_name = 'Позиция запроса товаров'
        verbose_name_plural = 'Позиции запросов товаров'
        unique_together = ['request', 'product']

    def __str__(self):
        return f"{self.product.name} x {self.requested_quantity}"