from rest_framework import serializers
from .models import Region, DeliveryZone


class RegionSerializer(serializers.ModelSerializer):
    """Сериализатор региона"""

    full_name = serializers.CharField(read_only=True)
    stores_count = serializers.IntegerField(read_only=True)
    partners_count = serializers.IntegerField(read_only=True)
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    coordinates = serializers.SerializerMethodField()
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = [
            'id', 'name', 'code', 'region_type', 'parent', 'parent_name',
            'full_name', 'latitude', 'longitude', 'coordinates',
            'stores_count', 'partners_count', 'children_count',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_coordinates(self, obj):
        return obj.get_coordinates()

    def get_children_count(self, obj):
        return obj.children.filter(is_active=True).count()


class RegionTreeSerializer(serializers.ModelSerializer):
    """Сериализатор дерева регионов"""

    children = serializers.SerializerMethodField()
    stores_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Region
        fields = [
            'id', 'name', 'code', 'region_type',
            'stores_count', 'children'
        ]

    def get_children(self, obj):
        children = obj.children.filter(is_active=True)
        return RegionTreeSerializer(children, many=True).data


class RegionCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания/обновления региона"""

    class Meta:
        model = Region
        fields = [
            'name', 'code', 'region_type', 'parent',
            'latitude', 'longitude', 'is_active'
        ]

    def validate_parent(self, value):
        if value and not value.is_active:
            raise serializers.ValidationError("Родительский регион должен быть активным")
        return value

    def validate_code(self, value):
        # Проверяем уникальность кода
        if Region.objects.filter(code=value).exclude(id=getattr(self.instance, 'id', None)).exists():
            raise serializers.ValidationError("Регион с таким кодом уже существует")
        return value


class DeliveryZoneSerializer(serializers.ModelSerializer):
    """Сериализатор зоны доставки"""

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