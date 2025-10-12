from rest_framework import serializers
from .models import (
    Region, City, Store, StoreSelection,
    StoreProductRequest, StoreRequest, StoreRequestItem,
    StoreInventory, PartnerInventory, ReturnRequest, ReturnRequestItem
)
from products.models import Product
from decimal import Decimal


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'name']


class RegionSerializer(serializers.ModelSerializer):
    cities = CitySerializer(many=True, read_only=True)

    class Meta:
        model = Region
        fields = ['id', 'name', 'cities']


class StoreSerializer(serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'inn', 'owner_name', 'phone',
            'region', 'region_name',
            'city', 'city_name',
            'address',
            'latitude', 'longitude',
            'debt', 'approval_status',
            'is_active',
            'created_by', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'approval_status']

    def validate_inn(self, value):
        """Проверка уникальности ИНН"""
        if Store.objects.filter(inn=value).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("Магазин с таким ИНН уже существует")
        return value

    def validate_phone(self, value):
        """Проверка уникальности телефона"""
        if Store.objects.filter(phone=value).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("Магазин с таким телефоном уже существует")
        return value


class StoreSelectionSerializer(serializers.ModelSerializer):
    store = StoreSerializer(read_only=True)

    class Meta:
        model = StoreSelection
        fields = ['id', 'store', 'selected_at']


class StoreProductRequestSerializer(serializers.ModelSerializer):
    """Общий список запрошенных товаров магазина"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)

    class Meta:
        model = StoreProductRequest
        fields = ['id', 'store', 'product', 'product_name', 'product_unit', 'quantity', 'created_at']

    def validate_quantity(self, value):
        """Валидация количества (весовые: шаг 0.1, штучные: целые)"""
        product = self.initial_data.get('product') or (self.instance.product if self.instance else None)
        if product:
            product = Product.objects.get(id=product)
            if product.category == 'weight':
                if value % Decimal('0.1') != 0:
                    raise serializers.ValidationError("Количество для весовых товаров должно быть кратно 0.1")
                if value < Decimal('0.1'):
                    raise serializers.ValidationError("Минимальное количество для весовых товаров: 0.1")
            else:
                if not value.is_integer():
                    raise serializers.ValidationError("Количество для штучных товаров должно быть целым")
        return value


class StoreRequestItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)

    class Meta:
        model = StoreRequestItem
        fields = [
            'id', 'product', 'product_name', 'product_unit',
            'quantity', 'price', 'total', 'is_cancelled'
        ]
        read_only_fields = ['total', 'is_cancelled']

    def validate_quantity(self, value):
        """Валидация количества"""
        product = self.initial_data.get('product') or (self.instance.product if self.instance else None)
        if product:
            product = Product.objects.get(id=product)
            if product.category == 'weight':
                if value % Decimal('0.1') != 0:
                    raise serializers.ValidationError("Количество для весовых товаров должно быть кратно 0.1")
                if value < Decimal('0.1'):
                    raise serializers.ValidationError("Минимальное количество для весовых товаров: 0.1")
            else:
                if not value.is_integer():
                    raise serializers.ValidationError("Количество для штучных товаров должно быть целым")
        return value


class CreateStoreRequestSerializer(serializers.Serializer):
    """Создание запроса магазина"""
    store = serializers.PrimaryKeyRelatedField(queryset=Store.objects.all())
    note = serializers.CharField(max_length=500, allow_blank=True)
    items = StoreRequestItemSerializer(many=True)

    def validate(self, attrs):
        items = attrs.get('items')
        if not items:
            raise serializers.ValidationError("Необходимо указать хотя бы одну позицию")
        return attrs


class StoreRequestSerializer(serializers.ModelSerializer):
    """История запросов магазина"""
    store_name = serializers.CharField(source='store.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    items = StoreRequestItemSerializer(many=True, read_only=True)

    class Meta:
        model = StoreRequest
        fields = [
            'id', 'store', 'store_name',
            'created_by', 'created_by_name',
            'total_amount', 'note', 'status',
            'items', 'created_at'
        ]
        read_only_fields = ['created_by', 'total_amount', 'status', 'created_at']


class StoreInventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)
    product_price = serializers.DecimalField(
        source='product.price',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    total_price = serializers.ReadOnlyField()

    class Meta:
        model = StoreInventory
        fields = [
            'id', 'product', 'product_name', 'product_unit',
            'product_price', 'quantity', 'total_price',
            'last_updated'
        ]

    def validate_quantity(self, value):
        """Валидация количества"""
        product = self.initial_data.get('product') or (self.instance.product if self.instance else None)
        if product:
            product = Product.objects.get(id=product)
            if product.category == 'weight':
                if value % Decimal('0.1') != 0:
                    raise serializers.ValidationError("Количество для весовых товаров должно быть кратно 0.1")
                if value < Decimal('0.1'):
                    raise serializers.ValidationError("Минимальное количество для весовых товаров: 0.1")
            else:
                if not value.is_integer():
                    raise serializers.ValidationError("Количество для штучных товаров должно быть целым")
        return value


class PartnerInventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)
    product_price = serializers.DecimalField(
        source='product.price',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = PartnerInventory
        fields = [
            'id', 'product', 'product_name', 'product_unit',
            'product_price', 'quantity', 'last_updated'
        ]

    def validate_quantity(self, value):
        """Валидация количества"""
        product = self.initial_data.get('product') or (self.instance.product if self.instance else None)
        if product:
            product = Product.objects.get(id=product)
            if product.category == 'weight':
                if value % Decimal('0.1') != 0:
                    raise serializers.ValidationError("Количество для весовых товаров должно быть кратно 0.1")
                if value < Decimal('0.1'):
                    raise serializers.ValidationError("Минимальное количество для весовых товаров: 0.1")
            else:
                if not value.is_integer():
                    raise serializers.ValidationError("Количество для штучных товаров должно быть целым")
        return value


class ReturnRequestItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)

    class Meta:
        model = ReturnRequestItem
        fields = ['id', 'product', 'product_name', 'product_unit', 'quantity', 'price', 'total']

    def validate_quantity(self, value):
        """Валидация количества"""
        product = self.initial_data.get('product') or (self.instance.product if self.instance else None)
        if product:
            product = Product.objects.get(id=product)
            if product.category == 'weight':
                if value % Decimal('0.1') != 0:
                    raise serializers.ValidationError("Количество для весовых товаров должно быть кратно 0.1")
                if value < Decimal('0.1'):
                    raise serializers.ValidationError("Минимальное количество для весовых товаров: 0.1")
            else:
                if not value.is_integer():
                    raise serializers.ValidationError("Количество для штучных товаров должно быть целым")
        return value


class ReturnRequestSerializer(serializers.ModelSerializer):
    items = ReturnRequestItemSerializer(many=True, read_only=True)
    partner_name = serializers.CharField(source='partner.name', read_only=True)

    class Meta:
        model = ReturnRequest
        fields = ['id', 'partner', 'partner_name', 'status', 'total_amount', 'items', 'created_at']
        read_only_fields = ['partner', 'total_amount', 'created_at']