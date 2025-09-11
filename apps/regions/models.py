from django.db import models
import math


class Region(models.Model):
    """Модель регионов"""

    name = models.CharField(max_length=100, verbose_name='Название региона')
    code = models.CharField(max_length=10, unique=True, verbose_name='Код региона')

    # Иерархия регионов (область -> район -> город)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Родительский регион'
    )

    # Тип региона
    REGION_TYPES = [
        ('country', 'Страна'),
        ('oblast', 'Область'),
        ('district', 'Район'),
        ('city', 'Город'),
        ('village', 'Село'),
    ]
    region_type = models.CharField(
        max_length=20,
        choices=REGION_TYPES,
        default='city',
        verbose_name='Тип региона'
    )

    # GPS координаты центра региона
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

    # Статус
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'regions'
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'
        ordering = ['name']
        unique_together = ['name', 'parent']  # Уникальность в рамках родителя

    def __str__(self):
        if self.parent:
            return f"{self.name} ({self.parent.name})"
        return self.name

    @property
    def full_name(self):
        """Полное имя региона с иерархией"""
        parts = []
        current = self
        while current:
            parts.append(current.name)
            current = current.parent
        return " > ".join(reversed(parts))

    def get_all_children(self):
        """Получить всех потомков рекурсивно"""
        children = []
        for child in self.children.all():
            children.append(child)
            children.extend(child.get_all_children())
        return children

    def get_ancestors(self):
        """Получить всех предков"""
        ancestors = []
        current = self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors

    def is_ancestor_of(self, region):
        """Проверить является ли предком"""
        current = region.parent
        while current:
            if current == self:
                return True
            current = current.parent
        return False


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