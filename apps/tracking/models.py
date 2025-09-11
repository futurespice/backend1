from django.db import models
from django.conf import settings


class Vehicle(models.Model):
    """Транспортное средство для доставки"""

    VEHICLE_TYPES = [
        ('car', 'Легковой автомобиль'),
        ('van', 'Фургон'),
        ('truck', 'Грузовик'),
        ('motorcycle', 'Мотоцикл'),
    ]

    number = models.CharField(max_length=20, unique=True, verbose_name='Номер')
    vehicle_type = models.CharField(
        max_length=20,
        choices=VEHICLE_TYPES,
        verbose_name='Тип транспорта'
    )
    brand = models.CharField(max_length=50, blank=True, verbose_name='Марка')
    model = models.CharField(max_length=50, blank=True, verbose_name='Модель')

    # Водители
    drivers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='vehicles',
        blank=True,
        verbose_name='Водители'
    )

    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Добавлен')

    class Meta:
        db_table = 'vehicles'
        verbose_name = 'Транспорт'
        verbose_name_plural = 'Транспорт'
        ordering = ['number']

    def __str__(self):
        return f"{self.number} ({self.brand} {self.model})"


class DeliveryTracking(models.Model):
    """Отслеживание доставки заказа"""

    STATUS_CHOICES = [
        ('pending', 'Ожидает отправки'),
        ('picked_up', 'Забран со склада'),
        ('in_transit', 'В пути'),
        ('delivered', 'Доставлен'),
        ('failed', 'Не доставлен'),
        ('returned', 'Возвращен'),
    ]

    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='tracking',
        verbose_name='Заказ'
    )

    # УБРАЛИ проблемное поле application
    # application = models.ForeignKey(
    #     'orders.StoreApplication',  # Эта модель не существует
    #     on_delete=models.CASCADE,
    #     null=True,
    #     blank=True
    # )

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Транспорт'
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Водитель'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )

    # Текущие координаты
    current_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Текущая широта'
    )
    current_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Текущая долгота'
    )

    # Важные даты
    pickup_time = models.DateTimeField(null=True, blank=True, verbose_name='Время забора')
    delivery_time = models.DateTimeField(null=True, blank=True, verbose_name='Время доставки')
    estimated_delivery = models.DateTimeField(null=True, blank=True, verbose_name='Ожидаемая доставка')

    # Дополнительная информация
    notes = models.TextField(blank=True, verbose_name='Примечания')
    distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Расстояние (км)'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        db_table = 'delivery_tracking'
        verbose_name = 'Отслеживание доставки'
        verbose_name_plural = 'Отслеживание доставок'
        ordering = ['-created_at']

    def __str__(self):
        return f"Доставка заказа #{self.order.id} - {self.get_status_display()}"


class TrackingPoint(models.Model):
    """Точка маршрута доставки"""

    tracking = models.ForeignKey(
        DeliveryTracking,
        on_delete=models.CASCADE,
        related_name='points',
        verbose_name='Отслеживание'
    )

    latitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name='Широта')
    longitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name='Долгота')

    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='Время')
    speed_kmh = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Скорость (км/ч)'
    )

    class Meta:
        db_table = 'tracking_points'
        verbose_name = 'Точка маршрута'
        verbose_name_plural = 'Точки маршрута'
        ordering = ['timestamp']

    def __str__(self):
        return f"Точка {self.latitude}, {self.longitude} в {self.timestamp}"
