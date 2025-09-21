import math
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Region(models.Model):
    """Регионы для группировки магазинов и маршрутов доставки"""

    name = models.CharField(max_length=100, unique=True, verbose_name='Название региона')
    code = models.CharField(max_length=10, unique=True, verbose_name='Код региона')
    description = models.TextField(blank=True, verbose_name='Описание')
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    # Координаты для GPS и карт
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True, blank=True,
        verbose_name='Широта'
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True, blank=True,
        verbose_name='Долгота'
    )

    # Метаданные для маршрутизации
    delivery_radius_km = models.PositiveIntegerField(
        default=20,
        verbose_name='Радиус доставки (км)'
    )
    delivery_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Стоимость доставки'
    )

    # Приоритет обслуживания
    priority = models.PositiveIntegerField(
        default=5,
        verbose_name='Приоритет обслуживания (1-10)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'regions'
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'
        ordering = ['priority', 'name']

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def stores_count(self):
        """Количество магазинов в регионе"""
        return self.stores.filter(is_active=True).count()

    @property
    def active_orders_count(self):
        """Количество активных заказов в регионе"""
        return sum(
            store.orders.filter(
                status__in=['pending', 'confirmed', 'production', 'ready', 'delivering']
            ).count()
            for store in self.stores.filter(is_active=True)
        )


class DeliveryZone(models.Model):
    """Модель зон доставки"""

    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name='delivery_zones',
        verbose_name='Регион'
    )
    name = models.CharField(max_length=100, verbose_name='Название зоны')

    # Полигон зоны доставки
    polygon_coordinates = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Координаты полигона',
        help_text='Координаты полигона зоны доставки в формате [[lat, lng], ...]'
    )

    # Альтернативно - радиус доставки
    delivery_radius = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Радиус доставки (м)',
        help_text='Радиус доставки в метрах'
    )

    # Стоимость и время доставки
    delivery_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        verbose_name='Стоимость доставки'
    )
    delivery_time_hours = models.IntegerField(
        default=24,
        verbose_name='Время доставки (часы)'
    )

    # Статус
    is_active = models.BooleanField(default=True, verbose_name='Активна')

    class Meta:
        db_table = 'delivery_zones'
        verbose_name = 'Зона доставки'
        verbose_name_plural = 'Зоны доставки'
        ordering = ['region', 'name']

    def __str__(self):
        return f"{self.name} ({self.region.name})"

    def is_point_in_zone(self, latitude, longitude):
        """Проверить попадает ли точка в зону доставки"""
        if not self.is_active:
            return False

        # Если задан радиус доставки
        if self.delivery_radius and self.region.latitude and self.region.longitude:
            distance = self._calculate_distance(
                float(self.region.latitude),
                float(self.region.longitude),
                latitude,
                longitude
            )
            return distance <= self.delivery_radius

        # Если задан полигон
        if self.polygon_coordinates:
            return self._point_in_polygon(latitude, longitude, self.polygon_coordinates)

        return False

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Рассчитать расстояние между двумя точками в метрах (формула Haversine)"""
        R = 6371000  # Радиус Земли в метрах

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (math.sin(dlat/2) * math.sin(dlat/2) +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(dlon/2) * math.sin(dlon/2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        return R * c

    def _point_in_polygon(self, lat, lon, polygon):
        """Проверить находится ли точка внутри полигона (Ray casting algorithm)"""
        if not polygon or len(polygon) < 3:
            return False

        x, y = lat, lon
        n = len(polygon)
        inside = False

        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside