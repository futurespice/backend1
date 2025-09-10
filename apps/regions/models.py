from django.db import models


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
        """Полное название с иерархией"""
        names = []
        current = self
        while current:
            names.append(current.name)
            current = current.parent
        return " > ".join(reversed(names))

    @property
    def stores_count(self):
        """Количество магазинов в регионе"""
        return self.stores.filter(is_active=True).count()

    @property
    def partners_count(self):
        """Количество партнёров в регионе"""
        return self.stores.filter(
            partner__isnull=False,
            is_active=True
        ).values('partner').distinct().count()

    def get_all_children(self):
        """Получить все дочерние регионы рекурсивно"""
        children = list(self.children.all())
        for child in list(children):
            children.extend(child.get_all_children())
        return children

    def get_coordinates(self):
        """Получить координаты"""
        if self.latitude and self.longitude:
            return {
                'latitude': float(self.latitude),
                'longitude': float(self.longitude)
            }
        return None


class DeliveryZone(models.Model):
    """Зоны доставки для регионов"""

    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name='delivery_zones',
        verbose_name='Регион'
    )

    name = models.CharField(max_length=100, verbose_name='Название зоны')

    # Полигон зоны доставки (JSON с координатами)
    polygon_coordinates = models.JSONField(
        default=list,
        blank=True,
        help_text='Координаты полигона зоны доставки в формате [[lat, lng], ...]',
        verbose_name='Координаты полигона'
    )

    # Радиус доставки (альтернатива полигону)
    delivery_radius = models.IntegerField(
        null=True,
        blank=True,
        help_text='Радиус доставки в метрах',
        verbose_name='Радиус доставки (м)'
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
        return f"{self.region.name} - {self.name}"

    def is_point_in_zone(self, latitude, longitude):
        """Проверить, находится ли точка в зоне доставки"""
        if self.delivery_radius and self.region.latitude and self.region.longitude:
            # Простая проверка по радиусу (приблизительная)
            import math

            lat1, lon1 = float(self.region.latitude), float(self.region.longitude)
            lat2, lon2 = float(latitude), float(longitude)

            # Формула гаверсинуса для расчёта расстояния
            R = 6371000  # Радиус Земли в метрах

            lat1_rad = math.radians(lat1)
            lat2_rad = math.radians(lat2)
            delta_lat = math.radians(lat2 - lat1)
            delta_lon = math.radians(longitude - lon1)

            a = (math.sin(delta_lat / 2) * math.sin(delta_lat / 2) +
                 math.cos(lat1_rad) * math.cos(lat2_rad) *
                 math.sin(delta_lon / 2) * math.sin(delta_lon / 2))
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance = R * c

            return distance <= self.delivery_radius

        # Для полигонов нужна более сложная логика
        # Можно использовать библиотеку shapely или PostGIS
        return False