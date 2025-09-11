from django.db import models
from django.conf import settings
from decimal import Decimal
from django.core.validators import MinValueValidator


class BonusRule(models.Model):
    """Правила бонусной системы"""

    name = models.CharField(max_length=200, verbose_name='Название правила')
    description = models.TextField(verbose_name='Описание')

    # Правило: каждый N-й товар бесплатно
    every_nth_free = models.PositiveIntegerField(
        default=21,
        verbose_name='Каждый N-й товар бесплатно'
    )

    # Применимость
    applies_to_all_products = models.BooleanField(
        default=True,
        verbose_name='Применяется ко всем товарам'
    )
    products = models.ManyToManyField(
        'products.Product',
        blank=True,
        verbose_name='Товары',
        help_text='Если не выбрано - применяется ко всем'
    )

    # Активность
    is_active = models.BooleanField(default=True, verbose_name='Активно')
    start_date = models.DateField(null=True, blank=True, verbose_name='Дата начала')
    end_date = models.DateField(null=True, blank=True, verbose_name='Дата окончания')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'bonus_rules'
        verbose_name = 'Правило бонусов'
        verbose_name_plural = 'Правила бонусов'
        ordering = ['name']

    def __str__(self):
        return self.name


class BonusHistory(models.Model):
    """История начисления бонусов"""

    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='bonus_history',
        verbose_name='Магазин'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='bonus_history',
        verbose_name='Товар'
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='bonus_history',
        verbose_name='Заказ'
    )
    order_item = models.ForeignKey(
        'orders.OrderItem',
        on_delete=models.CASCADE,
        related_name='bonus_history',
        verbose_name='Позиция заказа'
    )

    # Количества
    purchased_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        verbose_name='Купленное количество'
    )
    bonus_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=0,
        verbose_name='Бонусное количество'
    )

    # Накопленное количество до этой покупки
    cumulative_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        verbose_name='Накопленное количество'
    )

    # Стоимости
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Цена за единицу'
    )
    bonus_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Размер скидки'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        db_table = 'bonus_history'
        verbose_name = 'История бонусов'
        verbose_name_plural = 'История бонусов'
        ordering = ['-created_at']
        unique_together = ['order_item']

    def __str__(self):
        return f"Бонус {self.store.store_name} - {self.product.name}"


class BonusCalculation:
    """Калькулятор бонусов"""

    def __init__(self, rule_every_nth=21):
        self.rule_every_nth = rule_every_nth

    def calculate_bonus(self, previous_quantity, current_quantity, unit_price):
        """
        Рассчитать бонус для покупки

        Args:
            previous_quantity: Количество товара, купленного ранее
            current_quantity: Количество в текущей покупке
            unit_price: Цена за единицу товара

        Returns:
            dict: {
                'bonus_quantity': Decimal,  # Количество бонусных товаров
                'bonus_discount': Decimal,  # Размер скидки
                'new_cumulative': Decimal   # Новое накопленное количество
            }
        """
        previous_quantity = Decimal(str(previous_quantity))
        current_quantity = Decimal(str(current_quantity))
        unit_price = Decimal(str(unit_price))

        # Новое накопленное количество
        new_cumulative = previous_quantity + current_quantity

        # Сколько было "бесплатных" товаров до этой покупки
        previous_free_count = int(previous_quantity // self.rule_every_nth)

        # Сколько будет "бесплатных" товаров после покупки
        new_free_count = int(new_cumulative // self.rule_every_nth)

        # Количество новых бонусных товаров
        bonus_quantity = new_free_count - previous_free_count
        bonus_quantity = max(0, min(bonus_quantity, int(current_quantity)))

        # Размер скидки
        bonus_discount = Decimal(str(bonus_quantity)) * unit_price

        return {
            'bonus_quantity': Decimal(str(bonus_quantity)),
            'bonus_discount': bonus_discount,
            'new_cumulative': new_cumulative
        }

    def get_store_product_total(self, store, product):
        """Получить общее количество купленного товара магазином"""
        from apps.orders.models import OrderItem

        total = OrderItem.objects.filter(
            order__store=store,
            product=product,
            order__status='completed'
        ).aggregate(
            total=models.Sum('quantity')
        )['total']

        return total or Decimal('0')

    def preview_bonus(self, store, product, quantity):
        """Предварительный расчёт бонуса без сохранения"""
        current_total = self.get_store_product_total(store, product)
        return self.calculate_bonus(
            previous_quantity=current_total,
            current_quantity=quantity,
            unit_price=product.price
        )