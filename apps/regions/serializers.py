from rest_framework import serializers
from .models import Region, City


class CitySerializer(serializers.ModelSerializer):
    """Сериализатор города"""
    region_name = serializers.CharField(source='region.name', read_only=True)

    class Meta:
        model = City
        fields = ['id', 'name', 'region', 'region_name', 'created_at']
        read_only_fields = ['created_at']


class CityCreateSerializer(serializers.ModelSerializer):
    """Создание города"""

    class Meta:
        model = City
        fields = ['name', 'region']

    def validate(self, attrs):
        # Проверяем, что город с таким названием не существует в данном регионе
        if City.objects.filter(name=attrs['name'], region=attrs['region']).exists():
            raise serializers.ValidationError("Город с таким названием уже существует в данном регионе")
        return attrs


class RegionSerializer(serializers.ModelSerializer):
    """Сериализатор региона"""
    cities_count = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = ['id', 'name', 'cities_count', 'created_at']
        read_only_fields = ['created_at']

    def get_cities_count(self, obj):
        return obj.cities.count()


class RegionWithCitiesSerializer(serializers.ModelSerializer):
    """Регион со списком городов"""
    cities = CitySerializer(many=True, read_only=True)
    cities_count = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = ['id', 'name', 'cities_count', 'cities', 'created_at']
        read_only_fields = ['created_at']

    def get_cities_count(self, obj):
        return obj.cities.count()


class RegionCreateSerializer(serializers.ModelSerializer):
    """Создание региона"""

    class Meta:
        model = Region
        fields = ['name']

    def validate_name(self, value):
        if Region.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Регион с таким названием уже существует")
        return value.title()