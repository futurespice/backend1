from rest_framework import serializers
from .models import Region, DeliveryZone


class RegionSerializer(serializers.ModelSerializer):
    """Базовый сериализатор для регионов"""

    parent_name = serializers.CharField(source='parent.name', read_only=True)
    full_name = serializers.CharField(read_only=True)
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = [
            'id', 'name', 'code', 'parent', 'parent_name',
            'region_type', 'latitude', 'longitude',
            'is_active', 'full_name', 'children_count',
            'created_at', 'updated_at'
        ]

    def get_children_count(self, obj):
        return obj.children.filter(is_active=True).count()


class RegionTreeSerializer(serializers.ModelSerializer):
    """Сериализатор для дерева регионов"""

    children = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Region
        fields = [
            'id', 'name', 'code', 'region_type',
            'latitude', 'longitude', 'is_active',
            'full_name', 'children'
        ]

    def get_children(self, obj):
        children = obj.children.filter(is_active=True)
        return RegionTreeSerializer(children, many=True).data


class RegionCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания/обновления регионов"""

    class Meta:
        model = Region
        fields = [
            'name', 'code', 'parent', 'region_type',
            'latitude', 'longitude', 'is_active'
        ]

    def validate_parent(self, value):
        """Проверить корректность родительского региона"""
        if value:
            # Проверяем что не создаем цикл
            if self.instance and value.is_ancestor_of(self.instance):
                raise serializers.ValidationError(
                    "Нельзя установить потомка в качестве родителя"
                )
        return value

    def validate(self, data):
        """Дополнительная валидация"""
        # Проверяем уникальность code
        code = data.get('code')
        if code:
            qs = Region.objects.filter(code=code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'code': 'Регион с таким кодом уже существует'
                })

        # Проверяем координаты
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        if latitude is not None and not (-90 <= latitude <= 90):
            raise serializers.ValidationError({
                'latitude': 'Широта должна быть от -90 до 90'
            })
        if longitude is not None and not (-180 <= longitude <= 180):
            raise serializers.ValidationError({
                'longitude': 'Долгота должна быть от -180 до 180'
            })

        return data


class DeliveryZoneSerializer(serializers.ModelSerializer):
    """Сериализатор для зон доставки"""

    region_name = serializers.CharField(source='region.full_name', read_only=True)

    class Meta:
        model = DeliveryZone
        fields = [
            'id', 'region', 'region_name', 'name',
            'polygon_coordinates', 'delivery_radius',
            'delivery_cost', 'delivery_time_hours',
            'is_active'
        ]

    def validate(self, data):
        # Должен быть указан либо полигон, либо радиус
        polygon = data.get('polygon_coordinates')
        radius = data.get('delivery_radius')

        if not polygon and not radius:
            raise serializers.ValidationError(
                "Должен быть указан либо полигон координат, либо радиус доставки"
            )

        # Валидация полигона
        if polygon:
            if not isinstance(polygon, list) or len(polygon) < 3:
                raise serializers.ValidationError({
                    'polygon_coordinates': 'Полигон должен содержать минимум 3 точки'
                })

            for i, point in enumerate(polygon):
                if not isinstance(point, list) or len(point) != 2:
                    raise serializers.ValidationError({
                        'polygon_coordinates': f'Точка {i + 1} должна содержать [lat, lng]'
                    })

                try:
                    lat, lng = float(point[0]), float(point[1])
                    if not (-90 <= lat <= 90):
                        raise serializers.ValidationError({
                            'polygon_coordinates': f'Некорректная широта в точке {i + 1}'
                        })
                    if not (-180 <= lng <= 180):
                        raise serializers.ValidationError({
                            'polygon_coordinates': f'Некорректная долгота в точке {i + 1}'
                        })
                except (ValueError, TypeError):
                    raise serializers.ValidationError({
                        'polygon_coordinates': f'Некорректные координаты в точке {i + 1}'
                    })

        # Валидация радиуса
        if radius and radius <= 0:
            raise serializers.ValidationError({
                'delivery_radius': 'Радиус доставки должен быть положительным'
            })

        return data


class RegionStatsSerializer(serializers.Serializer):
    """Сериализатор статистики региона"""

    region = RegionSerializer(read_only=True)
    total_stores = serializers.IntegerField()
    active_stores = serializers.IntegerField()
    total_partners = serializers.IntegerField()
    total_orders = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    avg_order_value = serializers.DecimalField(max_digits=10, decimal_places=2)