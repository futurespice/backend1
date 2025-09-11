from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Store, StoreInventory, StoreRequest, AdminInventory
from products.models import Product
from regions.models import Region

User = get_user_model()


class StoreSerializer(serializers.ModelSerializer):
    """Сериализатор магазина"""

    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    partner_name = serializers.CharField(source='partner.get_full_name', read_only=True)
    region_name = serializers.CharField(source='region.full_name', read_only=True)
    total_debt = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    orders_count = serializers.IntegerField(read_only=True)
    coordinates = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'store_name', 'address', 'latitude', 'longitude',
            'region', 'region_name', 'partner', 'partner_name',
            'user_name', 'user_phone', 'user_email',
            'total_debt', 'orders_count', 'coordinates',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_coordinates(self, obj):
        return obj.get_coordinates()


class StoreCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания/обновления магазина"""

    class Meta:
        model = Store
        fields = [
            'store_name', 'address', 'latitude', 'longitude',
            'region', 'partner'
        ]

    def validate_partner(self, value):
        if value and value.role != 'partner':
            raise serializers.ValidationError("Пользователь должен быть партнёром")
        return value

    def validate_region(self, value):
        if value and not value.is_active:
            raise serializers.ValidationError("Регион неактивен")
        return value


class StoreInventorySerializer(serializers.ModelSerializer):
    """Сериализатор остатков в магазине"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.unit', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    available_quantity = serializers.DecimalField(max_digits=8, decimal_places=3, read_only=True)

    class Meta:
        model = StoreInventory
        fields = [
            'id', 'product', 'product_name', 'product_unit', 'product_price',
            'quantity', 'reserved_quantity', 'available_quantity',
            'last_updated'
        ]
        read_only_fields = ['id', 'last_updated']


# apps/stores/serializers.py - исправляем сериализатор
class StoreRequestItemSerializer(serializers.ModelSerializer):
    """Сериализатор позиции запроса"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.unit', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = AdminInventory  # используем существующую модель
        fields = [
            'id', 'product', 'product_name', 'product_unit', 'product_price',
            'quantity', 'approved_quantity', 'delivered_quantity'
        ]
        read_only_fields = ['id']

class StoreRequestSerializer(serializers.ModelSerializer):
    """Сериализатор запроса товаров"""

    store_name = serializers.CharField(source='store.store_name', read_only=True)
    partner_name = serializers.CharField(source='partner.get_full_name', read_only=True)
    items = StoreRequestItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    total_quantity = serializers.DecimalField(max_digits=10, decimal_places=3, read_only=True)

    class Meta:
        model = StoreRequest
        fields = [
            'id', 'store', 'store_name', 'partner', 'partner_name',
            'status', 'items', 'total_items', 'total_quantity',
            'requested_at', 'processed_at', 'delivered_at',
            'store_notes', 'partner_notes'
        ]
        read_only_fields = ['id', 'requested_at', 'processed_at', 'delivered_at']


class StoreRequestCreateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания запроса товаров"""

    items = StoreRequestItemSerializer(many=True, write_only=True)

    class Meta:
        model = StoreRequest
        fields = ['partner', 'store_notes', 'items']

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Список товаров не может быть пустым")

        # Проверяем уникальность товаров
        product_ids = [item['product'].id for item in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("Товары в запросе должны быть уникальными")

        return value

    # apps/stores/serializers.py - исправляем create метод
    def create(self, validated_data):
        items_data = validated_data.pop('items')

        store = self.context['request'].user.store_profile
        validated_data['store'] = store

        request = StoreRequest.objects.create(**validated_data)

        # Создаём позиции
        for item_data in items_data:
            AdminInventory.objects.create(request=request, **item_data)

        return request


class StoreRequestUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для обновления запроса (только для партнёров)"""

    class Meta:
        model = StoreRequest
        fields = ['status', 'partner_notes']

    def validate_status(self, value):
        current_status = self.instance.status

        # Проверяем допустимые переходы статуса
        allowed_transitions = {
            'pending': ['approved', 'rejected'],
            'approved': ['delivered', 'cancelled'],
            'rejected': [],
            'delivered': [],
            'cancelled': []
        }

        if value not in allowed_transitions.get(current_status, []):
            raise serializers.ValidationError(
                f"Недопустимый переход статуса с '{current_status}' на '{value}'"
            )

        return value

    def update(self, instance, validated_data):
        # Обновляем статус
        new_status = validated_data.get('status')

        if new_status == 'approved':
            instance.approve(self.context['request'].user)
        elif new_status == 'rejected':
            reason = validated_data.get('partner_notes', '')
            instance.reject(self.context['request'].user, reason)
        else:
            # Обычное обновление
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

        return instance


class StoreProfileSerializer(serializers.ModelSerializer):
    """Сериализатор профиля магазина для текущего пользователя"""

    user_info = serializers.SerializerMethodField()
    region_name = serializers.CharField(source='region.full_name', read_only=True)
    partner_name = serializers.CharField(source='partner.get_full_name', read_only=True)
    partner_phone = serializers.CharField(source='partner.phone', read_only=True)
    total_debt = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    orders_count = serializers.IntegerField(read_only=True)
    coordinates = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'store_name', 'address', 'latitude', 'longitude',
            'region', 'region_name', 'partner_name', 'partner_phone',
            'user_info', 'total_debt', 'orders_count', 'coordinates',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'is_active']

    def get_user_info(self, obj):
        return {
            'name': obj.user.name,
            'second_name': obj.user.second_name,
            'email': obj.user.email,
            'phone': obj.user.phone,
            'role': obj.user.role
        }

    def get_coordinates(self, obj):
        return obj.get_coordinates()


class ProductCatalogSerializer(serializers.ModelSerializer):
    """Сериализатор каталога товаров для магазинов"""

    available_quantity = serializers.SerializerMethodField()
    in_cart = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'unit',
            'category', 'available_quantity', 'in_cart',
            'images', 'is_available'
        ]

    def get_available_quantity(self, obj):
        """Получить доступное количество товара на складе партнёра"""
        # Здесь будет логика получения остатков у партнёра
        return obj.stock_quantity

    def get_in_cart(self, obj):
        """Проверить, есть ли товар в корзине"""
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            # Здесь будет логика проверки корзины
            return False
        return False