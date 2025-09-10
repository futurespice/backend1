from rest_framework import serializers
from .models import Category, Product, ProductImage


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор категории"""

    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'parent', 'image', 'is_active']


class ProductImageSerializer(serializers.ModelSerializer):
    """Сериализатор изображений товара"""

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary']


class ProductSerializer(serializers.ModelSerializer):
    """Сериализатор товара"""

    images = ProductImageSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'category', 'category_name',
            'sku', 'price', 'unit', 'min_order_quantity',
            'stock_quantity', 'low_stock_threshold',
            'is_available', 'is_active', 'images',
            'created_at', 'updated_at'
        ]