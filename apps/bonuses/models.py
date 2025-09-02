from django.db import models
from django.conf import settings
from decimal import Decimal


class BonusRule(models.Model):
    """Правила бонусной системы"""
    name = models.CharField(max_length=100, verbose_name='Название правила')
    description = models.TextField(verbose_name='Описание')

    # Каждый N-й товар бесплатно
    bonus_threshold = models.PositiveIntegerField(
        default=21,
        verbose_name='Каждый N-й товар бесплатно'
    )

    # Активность
    is_active = models.BooleanField(default=True, verbose_name='Активно')

    # Применимость
    applies_to_partners = models.BooleanField(default=True, verbose_name='Применяется к партнерам')
    applies_to_stores = models.BooleanField(default=True, verbose_name='Применяется к магазинам')

    # Даты
    valid_from = models.DateTimeField(verbose_name='Действует с')
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name='Действует до')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bonus_rules'
        verbose_name = 'Правило бонусной системы'
        verbose_name_plural = 'Правила бонусной системы'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} (каждый {self.bonus_threshold}-й товар)"

    def is_valid_now(self):
        """Проверить, действует ли правило сейчас"""
        from django.utils import timezone
        now = timezone.now()

        if not self.is_active:
            return False

        if now < self.valid_from:
            return False

        if self.valid_until and now > self.valid_until:
            return False

        return True


class BonusCounter(models.Model):
    """Счетчик бонусов для каждого магазина"""
    store = models.OneToOneField(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='bonus_counter',
        verbose_name='Магазин'
    )

    # Счетчики
    total_items_ordered = models.PositiveIntegerField(default=0, verbose_name='Всего заказано товаров')
    bonus_items_received = models.PositiveIntegerField(default=0, verbose_name='Получено бонусных товаров')

    # Текущий прогресс до следующего бонуса
    current_count = models.PositiveIntegerField(default=0, verbose_name='Текущий счет')
    next_bonus_at = models.PositiveIntegerField(default=21, verbose_name='Следующий бонус на')

    # Метаданные
    last_bonus_date = models.DateTimeField(null=True, blank=True, verbose_name='Дата последнего бонуса')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bonus_counters'
        verbose_name = 'Счетчик бонусов'
        verbose_name_plural = 'Счетчики бонусов'

    def __str__(self):
        return f"Бонусы {self.store.name}: {self.current_count}/{self.next_bonus_at}"

    def add_items(self, quantity):
        """Добавить товары в счетчик"""
        from django.utils import timezone

        bonus_rule = BonusRule.objects.filter(is_active=True).first()
        if not bonus_rule:
            return 0

        threshold = bonus_rule.bonus_threshold

        self.total_items_ordered += quantity
        self.current_count += quantity

        # Подсчитываем сколько бонусов заработано
        bonus_items = 0
        while self.current_count >= self.next_bonus_at:
            bonus_items += 1
            self.bonus_items_received += 1
            self.current_count -= threshold
            self.last_bonus_date = timezone.now()

        self.save()
        return bonus_items

    def get_progress_to_next_bonus(self):
        """Получить прогресс до следующего бонуса"""
        bonus_rule = BonusRule.objects.filter(is_active=True).first()
        if not bonus_rule:
            return {'current': 0, 'needed': 21, 'progress': 0}

        threshold = bonus_rule.bonus_threshold
        needed = threshold - (self.current_count % threshold)
        progress = (self.current_count % threshold) / threshold * 100

        return {
            'current': self.current_count % threshold,
            'needed': needed,
            'progress': round(progress, 1)
        }


class BonusTransaction(models.Model):
    """История бонусных операций"""
    TRANSACTION_TYPES = [
        ('earned', 'Заработан'),
        ('used', 'Использован'),
        ('expired', 'Истек'),
        ('cancelled', 'Отменен'),
    ]

    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='bonus_transactions')
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, null=True, blank=True)

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, verbose_name='Тип операции')
    quantity = models.PositiveIntegerField(verbose_name='Количество товаров')
    amount_saved = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Сэкономленная сумма'
    )

    description = models.TextField(verbose_name='Описание')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата операции')

    class Meta:
        db_table = 'bonus_transactions'
        verbose_name = 'Бонусная операция'
        verbose_name_plural = 'Бонусные операции'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()}: {self.quantity} шт. ({self.store.name})"


class BonusStatistics(models.Model):
    """Статистика бонусов по периодам"""
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='bonus_stats')
    partner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'partner'}
    )

    # Период
    period_start = models.DateTimeField(verbose_name='Начало периода')
    period_end = models.DateTimeField(verbose_name='Конец периода')

    # Статистика
    total_bonus_items = models.PositiveIntegerField(default=0, verbose_name='Всего бонусных товаров')
    total_bonus_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Общая стоимость бонусов'
    )

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bonus_statistics'
        verbose_name = 'Статистика бонусов'
        verbose_name_plural = 'Статистика бонусов'
        unique_together = ['store', 'partner', 'period_start', 'period_end']
        ordering = ['-period_start']

    def __str__(self):
        return f"Бонусы {self.store.name}: {self.total_bonus_items} шт."