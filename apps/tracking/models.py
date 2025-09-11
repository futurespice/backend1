from django.db import models
from django.conf import settings
from decimal import Decimal
from django.core.validators import MinValueValidator


class DeliveryTracking(models.Model):
    """Отслеживание доставки"""

    STATUS_CHOICES = [
        ('pending', 'Ожидает отправки'),
        ('picked_up', 'Забран со склада'),
        ('in_transit', 'В пути'),
        ('delivered', 'Доставлен'),
        ('failed', 'Доставка не удалась'),
        ('returned', 'Возвращен'),
    ]

    # Связанные объекты
    application = models.OneToOneField(
        'orders.StoreApplication',
        on_delete=models.CASCADE,
        related_name='delivery_tracking',
        null=True,
        blank=True,
        verbose_name='Заявка'
    )
    product_request = models.OneToOneField(
        'orders.ProductRequest',
        on_delete=models.CASCADE,
        related_name='delivery_tracking',
        null=True,
        blank=True,
        verbose_name='Запрос товаров'
    )

    # Информация о доставке
    tracking_number = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Номер отслеживания'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )

    # Водитель и транспорт
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deliveries',
        verbose_name='Водитель'
    )
    vehicle_number = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Номер машины'
    )

    # Адреса
    pickup_address = models.TextField(verbose_name='Адрес забора')
    delivery_address = models.TextField(verbose_name='Адрес доставки')

    # GPS координаты
    pickup_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Широта забора'
    )
    pickup_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Долгота забора'
    )
    delivery_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Широта доставки'
    )
    delivery_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Долгота доставки'
    )

    # Временные метки
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    picked_up_at = models.DateTimeField(null=True, blank=True, verbose_name='Забрано')
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name='Доставлено')

    # Дополнительная информация
    estimated_delivery = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Ожидаемая доставка'
    )
    delivery_notes = models.TextField(blank=True, verbose_name='Примечания к доставке')

    # Расходы на доставку
    fuel_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        verbose_name='Расход на топливо'
    )
    driver_payment = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        verbose_name='Оплата водителю'
    )

    class Meta:
        db_table = 'delivery_tracking'
        verbose_name = 'Отслеживание доставки'
        verbose_name_plural = 'Отслеживание доставок'
        ordering = ['-created_at']

    def __str__(self):
        return f"Доставка {self.tracking_number} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        # Автогенерация номера отслеживания
        if not self.tracking_number:
            import uuid
            self.tracking_number = f"TRK{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class TrackingEvent(models.Model):
    """События отслеживания"""

    EVENT_TYPES = [
        ('created', 'Создана доставка'),
        ('assigned', 'Назначен водитель'),
        ('picked_up', 'Забрано со склада'),
        ('in_transit', 'Отправлено'),
        ('location_update', 'Обновление местоположения'),
        ('delivered', 'Доставлено'),
        ('failed', 'Ошибка доставки'),
        ('returned', 'Возвращено'),
        ('note_added', 'Добавлено примечание'),
    ]

    tracking = models.ForeignKey(
        DeliveryTracking,
        on_delete=models.CASCADE,
        related_name='events',
        verbose_name='Отслеживание'
    )
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPES,
        verbose_name='Тип события'
    )
    description = models.TextField(verbose_name='Описание')

    # GPS координаты события
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Широта'
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Долгота'
    )

    # Пользователь, создавший событие
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Создал'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Время события')

    class Meta:
        db_table = 'tracking_events'
        verbose_name = 'Событие отслеживания'
        verbose_name_plural = 'События отслеживания'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.tracking.tracking_number}: {self.get_event_type_display()}"


class GPSLocation(models.Model):
    """GPS местоположения водителей"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gps_locations',
        verbose_name='Пользователь'
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        verbose_name='Широта'
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        verbose_name='Долгота'
    )

    # Точность GPS
    accuracy = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Точность (м)'
    )

    # Скорость и направление
    speed = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Скорость (км/ч)'
    )
    bearing = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Направление (градусы)'
    )

    # Связанная доставка
    delivery = models.ForeignKey(
        DeliveryTracking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gps_points',
        verbose_name='Доставка'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Время записи')

    class Meta:
        db_table = 'gps_locations'
        verbose_name = 'GPS местоположение'
        verbose_name_plural = 'GPS местоположения'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.get_full_name()}: {self.latitude}, {self.longitude}"


class Vehicle(models.Model):
    """Транспортные средства"""

    VEHICLE_TYPES = [
        ('car', 'Легковая машина'),
        ('van', 'Фургон'),
        ('truck', 'Грузовик'),
        ('motorcycle', 'Мотоцикл'),
    ]

    number = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Номер машины'
    )
    vehicle_type = models.CharField(
        max_length=20,
        choices=VEHICLE_TYPES,
        verbose_name='Тип транспорта'
    )
    brand = models.CharField(max_length=50, blank=True, verbose_name='Марка')
    model = models.CharField(max_length=50, blank=True, verbose_name='Модель')
    year = models.PositiveIntegerField(null=True, blank=True, verbose_name='Год')

    # Грузоподъемность
    capacity_kg = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Грузоподъемность (кг)'
    )

    # Водители
    drivers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='vehicles',
        blank=True,
        verbose_name='Водители'
    )

    # Статус
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    is_available = models.BooleanField(default=True, verbose_name='Доступен')

    # Расходы
    fuel_consumption = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Расход топлива (л/100км)'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Добавлен')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')

    class Meta:
        db_table = 'vehicles'
        verbose_name = 'Транспорт'
        verbose_name_plural = 'Транспорт'
        ordering = ['number']

    def __str__(self):
        return f"{self.number} ({self.brand} {self.model})"

    @property
    def current_driver(self):
        """Текущий водитель (если машина в доставке)"""
        active_delivery = DeliveryTracking.objects.filter(
            vehicle_number=self.number,
            status__in=['picked_up', 'in_transit']
        ).first()

        return active_delivery.driver if active_delivery else None