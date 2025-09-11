from django.db import models
from django.conf import settings
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.utils import timezone


class BonusRule(models.Model):
    """Правила бонусной системы"""

    name = models.CharField(max_length=200, verbose_name='Название правила')
    description = models.TextField(verbose_name='Описание')

    # Основное правило: каждый N-й товар бесплатно
    every_nth_free = models.PositiveIntegerField(
        default=21,
        verbose_name='Каждый N-й товар бесплатно'
    )

    # Дополнительные типы бонусов
    BONUS_TYPES = [
        ('nth_free', 'Каждый N-й товар бесплатно'),
        ('percentage', 'Процентная скидка'),
        ('fixed_amount', 'Фиксированная сумма'),
        ('points', 'Бонусные очки'),
    ]
    bonus_type = models.CharField(
        max_length=20,
        choices=BONUS_TYPES,
        default='nth_free',
        verbose_name='Тип бонуса'
    )

    # Параметры для разных типов бонусов
    percentage_discount = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Процент скидки'
    )
    fixed_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Фиксированная сумма'
    )
    points_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Множитель очков'
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
    categories = models.ManyToManyField(
        'products.Category',
        blank=True,
        verbose_name='Категории'
    )

    # Ограничения по пользователям
    applies_to_all_stores = models.BooleanField(
        default=True,
        verbose_name='Применяется ко всем магазинам'
    )
    stores = models.ManyToManyField(
        'stores.Store',
        blank=True,
        verbose_name='Магазины'
    )

    # Ограничения по суммам
    min_order_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Минимальная сумма заказа'
    )
    max_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Максимальная сумма скидки'
    )

    # Временные ограничения
    is_active = models.BooleanField(default=True, verbose_name='Активно')
    start_date = models.DateField(null=True, blank=True, verbose_name='Дата начала')
    end_date = models.DateField(null=True, blank=True, verbose_name='Дата окончания')

    # Ограничения по использованию
    max_uses_per_store = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Максимум использований на магазин'
    )
    max_uses_total = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Максимум использований всего'
    )

    # Приоритет
    priority = models.PositiveIntegerField(
        default=0,
        verbose_name='Приоритет (больше = выше)'
    )

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Создал'
    )

    class Meta:
        db_table = 'bonus_rules'
        verbose_name = 'Правило бонусов'
        verbose_name_plural = 'Правила бонусов'
        ordering = ['-priority', 'name']

    def __str__(self):
        return self.name

    def is_valid_for_date(self, date=None):
        """Проверка действительности правила на дату"""
        if date is None:
            date = timezone.now().date()

        if not self.is_active:
            return False

        if self.start_date and date < self.start_date:
            return False

        if self.end_date and date > self.end_date:
            return False

        return True

    def is_applicable_to_product(self, product):
        """Проверка применимости к товару"""
        if self.applies_to_all_products:
            return True

        # Проверяем конкретные товары
        if self.products.filter(id=product.id).exists():
            return True

        # Проверяем категории
        if self.categories.filter(id=product.category.id).exists():
            return True

        return False

    def is_applicable_to_store(self, store):
        """Проверка применимости к магазину"""
        if self.applies_to_all_stores:
            return True

        return self.stores.filter(id=store.id).exists()

    def calculate_bonus(self, order_items, store):
        """Расчёт бонуса для заказа"""
        if not self.is_applicable_to_store(store):
            return {'bonus_items': 0, 'discount_amount': 0, 'points': 0}

        if self.bonus_type == 'nth_free':
            return self._calculate_nth_free_bonus(order_items)
        elif self.bonus_type == 'percentage':
            return self._calculate_percentage_bonus(order_items)
        elif self.bonus_type == 'fixed_amount':
            return self._calculate_fixed_amount_bonus(order_items)
        elif self.bonus_type == 'points':
            return self._calculate_points_bonus(order_items)

        return {'bonus_items': 0, 'discount_amount': 0, 'points': 0}

    def _calculate_nth_free_bonus(self, order_items):
        """Расчёт бонуса 'каждый N-й товар бесплатно'"""
        bonus_items = 0

        for item in order_items:
            if self.is_applicable_to_product(item.product):
                # Считаем количество бонусных товаров
                quantity = int(item.quantity)
                bonus_items += quantity // self.every_nth_free

        return {
            'bonus_items': bonus_items,
            'discount_amount': 0,
            'points': 0
        }

    def _calculate_percentage_bonus(self, order_items):
        """Расчёт процентной скидки"""
        total_amount = 0

        for item in order_items:
            if self.is_applicable_to_product(item.product):
                total_amount += item.quantity * item.unit_price

        discount_amount = total_amount * (self.percentage_discount / 100)

        # Применяем ограничение максимальной скидки
        if self.max_discount_amount:
            discount_amount = min(discount_amount, self.max_discount_amount)

        return {
            'bonus_items': 0,
            'discount_amount': discount_amount,
            'points': 0
        }

    def _calculate_fixed_amount_bonus(self, order_items):
        """Расчёт фиксированной скидки"""
        return {
            'bonus_items': 0,
            'discount_amount': self.fixed_amount,
            'points': 0
        }

    def _calculate_points_bonus(self, order_items):
        """Расчёт бонусных очков"""
        points = 0

        for item in order_items:
            if self.is_applicable_to_product(item.product):
                points += int(item.quantity * self.points_multiplier)

        return {
            'bonus_items': 0,
            'discount_amount': 0,
            'points': points
        }


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
        null=True,
        blank=True,
        verbose_name='Заказ'
    )
    rule = models.ForeignKey(
        BonusRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Правило бонуса'
    )

    # Количества
    total_items_purchased = models.PositiveIntegerField(
        verbose_name='Всего товаров куплено'
    )
    bonus_items = models.PositiveIntegerField(
        default=0,
        verbose_name='Бонусных товаров получено'
    )

    # Бонусные очки
    points_earned = models.PositiveIntegerField(
        default=0,
        verbose_name='Очков заработано'
    )
    points_used = models.PositiveIntegerField(
        default=0,
        verbose_name='Очков потрачено'
    )

    # Скидки
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Сумма скидки'
    )

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')
    notes = models.TextField(blank=True, verbose_name='Примечания')

    class Meta:
        db_table = 'bonus_history'
        verbose_name = 'История бонусов'
        verbose_name_plural = 'История бонусов'
        ordering = ['-created_at']

    def __str__(self):
        return f"Бонус для {self.store.store_name} - {self.product.name}"


class BonusBalance(models.Model):
    """Баланс бонусных очков магазина"""

    store = models.OneToOneField(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='bonus_balance',
        verbose_name='Магазин'
    )

    # Очки
    total_points_earned = models.PositiveIntegerField(
        default=0,
        verbose_name='Всего очков заработано'
    )
    total_points_used = models.PositiveIntegerField(
        default=0,
        verbose_name='Всего очков потрачено'
    )
    current_points = models.PositiveIntegerField(
        default=0,
        verbose_name='Текущие очки'
    )

    # Статистика по товарам
    total_items_purchased = models.PositiveIntegerField(
        default=0,
        verbose_name='Всего товаров куплено'
    )
    total_bonus_items_received = models.PositiveIntegerField(
        default=0,
        verbose_name='Всего бонусных товаров получено'
    )

    # Суммы
    total_amount_saved = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Всего сэкономлено'
    )

    # Метаданные
    last_bonus_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата последнего бонуса'
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'bonus_balances'
        verbose_name = 'Баланс бонусов'
        verbose_name_plural = 'Балансы бонусов'

    def __str__(self):
        return f"Бонусы {self.store.store_name} - {self.current_points} очков"

    def add_points(self, points, order=None):
        """Добавить бонусные очки"""
        self.total_points_earned += points
        self.current_points += points
        self.last_bonus_date = timezone.now()
        self.save()

    def use_points(self, points):
        """Использовать бонусные очки"""
        if self.current_points >= points:
            self.total_points_used += points
            self.current_points -= points
            self.save()
            return True
        return False

    def add_bonus_items(self, items_count, bonus_count, saved_amount):
        """Добавить статистику по бонусным товарам"""
        self.total_items_purchased += items_count
        self.total_bonus_items_received += bonus_count
        self.total_amount_saved += saved_amount
        self.last_bonus_date = timezone.now()
        self.save()


class BonusRuleUsage(models.Model):
    """Статистика использования правил бонусов"""

    rule = models.ForeignKey(
        BonusRule,
        on_delete=models.CASCADE,
        related_name='usage_stats',
        verbose_name='Правило'
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        verbose_name='Магазин'
    )

    # Счётчики использования
    times_used = models.PositiveIntegerField(
        default=0,
        verbose_name='Количество использований'
    )

    # Суммы
    total_discount_given = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Общая сумма скидок'
    )
    total_bonus_items_given = models.PositiveIntegerField(
        default=0,
        verbose_name='Общее количество бонусных товаров'
    )

    # Даты
    first_used = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Первое использование'
    )
    last_used = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Последнее использование'
    )

    class Meta:
        db_table = 'bonus_rule_usage'
        verbose_name = 'Использование правила бонусов'
        verbose_name_plural = 'Использования правил бонусов'
        unique_together = ['rule', 'store']

    def __str__(self):
        return f"{self.rule.name} - {self.store.store_name} ({self.times_used} раз)"

    def record_usage(self, discount_amount=0, bonus_items=0):
        """Записать использование правила"""
        self.times_used += 1
        self.total_discount_given += discount_amount
        self.total_bonus_items_given += bonus_items

        now = timezone.now()
        if not self.first_used:
            self.first_used = now
        self.last_used = now

        self.save()


class BonusCalculator:
    """Сервис для расчёта бонусов"""

    @staticmethod
    def calculate_order_bonuses(order_items, store):
        """Рассчитать все бонусы для заказа"""
        # Получаем активные правила, отсортированные по приоритету
        active_rules = BonusRule.objects.filter(
            is_active=True
        ).order_by('-priority')

        total_bonus = {
            'bonus_items': 0,
            'discount_amount': Decimal('0'),
            'points': 0,
            'applied_rules': []
        }

        for rule in active_rules:
            if not rule.is_valid_for_date():
                continue

            if not rule.is_applicable_to_store(store):
                continue

            # Проверяем ограничения по использованию
            if not BonusCalculator._check_usage_limits(rule, store):
                continue

            # Рассчитываем бонус по этому правилу
            rule_bonus = rule.calculate_bonus(order_items, store)

            if any(rule_bonus.values()):  # Если есть какой-то бонус
                total_bonus['bonus_items'] += rule_bonus['bonus_items']
                total_bonus['discount_amount'] += rule_bonus['discount_amount']
                total_bonus['points'] += rule_bonus['points']
                total_bonus['applied_rules'].append({
                    'rule': rule,
                    'bonus': rule_bonus
                })

        return total_bonus

    @staticmethod
    def _check_usage_limits(rule, store):
        """Проверить ограничения по использованию правила"""
        try:
            usage = BonusRuleUsage.objects.get(rule=rule, store=store)
        except BonusRuleUsage.DoesNotExist:
            return True  # Правило ещё не использовалось

        # Проверяем лимит на магазин
        if rule.max_uses_per_store and usage.times_used >= rule.max_uses_per_store:
            return False

        # Проверяем общий лимит
        if rule.max_uses_total:
            total_usage = BonusRuleUsage.objects.filter(rule=rule).aggregate(
                total=models.Sum('times_used')
            )['total'] or 0

            if total_usage >= rule.max_uses_total:
                return False

        return True

    @staticmethod
    def apply_bonuses_to_order(order):
        """Применить бонусы к заказу"""
        bonuses = BonusCalculator.calculate_order_bonuses(
            order.items.all(),
            order.store
        )

        # Применяем бонусы к позициям заказа
        BonusCalculator._apply_nth_free_bonuses(order, bonuses)

        # Обновляем общие суммы заказа
        order.bonus_discount = bonuses['discount_amount']
        order.bonus_points_earned = bonuses['points']
        order.save()

        # Записываем статистику использования правил
        for rule_data in bonuses['applied_rules']:
            rule = rule_data['rule']
            bonus = rule_data['bonus']

            usage, created = BonusRuleUsage.objects.get_or_create(
                rule=rule,
                store=order.store
            )
            usage.record_usage(
                discount_amount=bonus['discount_amount'],
                bonus_items=bonus['bonus_items']
            )

        return bonuses

    @staticmethod
    def _apply_nth_free_bonuses(order, bonuses):
        """Применить бонусы 'каждый N-й товар бесплатно' к позициям заказа"""
        if bonuses['bonus_items'] == 0:
            return

        # Простая логика: распределяем бонусные товары пропорционально
        total_quantity = sum(item.quantity for item in order.items.all())
        remaining_bonus_items = bonuses['bonus_items']

        for item in order.items.all():
            if remaining_bonus_items <= 0:
                break

            # Рассчитываем долю этой позиции от общего количества
            item_ratio = item.quantity / total_quantity
            item_bonus = min(
                remaining_bonus_items,
                int(bonuses['bonus_items'] * item_ratio)
            )

            if item_bonus > 0:
                item.bonus_quantity = item_bonus
                item.save()
                remaining_bonus_items -= item_bonus