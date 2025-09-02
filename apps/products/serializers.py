from decimal import Decimal, ROUND_FLOOR
from typing import Tuple

from rest_framework import serializers

from .models import (
    ProductCategory, Product, ProductImage, ProductBOM,
    Expense, ExpenseValue, ExpenseBinding, CostRegister,
    Unit, ExpenseKind, ExpenseScope
)

# ---------- helpers ----------

DEC_STEP_01 = Decimal("0.1")


def is_step_ok(val: Decimal, step: Decimal) -> bool:
    # Проверка кратности шага без плавающих ошибок
    q = (val / step).quantize(Decimal("1"), rounding=ROUND_FLOOR)
    return (q * step) == val


def split_bonus(product: Product, qty: int) -> Tuple[int, int]:
    return product.split_bonus(qty)


# ---------- Images ----------

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image", "is_primary", "order", "created_at")
        read_only_fields = ("id", "created_at")


# ---------- Categories ----------

class ProductCategorySerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = ("id", "name", "category_type", "description", "is_active", "products_count", "created_at")

    def get_products_count(self, obj):
        return obj.products.filter(is_active=True).count()


# ---------- BOM (product -> ingredients) ----------

class ProductBOMItemSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    ingredient_type = serializers.CharField(source="ingredient.category_type", read_only=True)

    class Meta:
        model = ProductBOM
        fields = ("id", "ingredient", "ingredient_name", "ingredient_type", "qty_per_unit")


class ProductBOMItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductBOM
        fields = ("id", "ingredient", "qty_per_unit")

    def validate(self, attrs):
        product: Product = self.context["product"]
        if attrs["ingredient"].pk == product.pk:
            raise serializers.ValidationError("Продукт не может быть ингредиентом самого себя.")
        return attrs


# ---------- Products (list/detail/create/update) ----------

class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    primary_image = serializers.SerializerMethodField()
    price_per_100g = serializers.ReadOnlyField()
    is_in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "category_type", "category_name", "price", "price_per_100g",
            "stock_quantity", "min_order_quantity", "is_bonus_eligible", "is_active",
            "is_available", "is_in_stock", "primary_image", "created_at"
        ]

    def get_primary_image(self, obj: Product):
        im = obj.images.filter(is_primary=True).first()
        return im.image.url if im else None

    def get_is_in_stock(self, obj: Product):
        return obj.is_in_stock()


class ProductDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    price_per_100g = serializers.ReadOnlyField()
    is_in_stock = serializers.SerializerMethodField()
    bom_items = ProductBOMItemSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "description", "category", "category_name", "category_type",
            "price", "price_per_100g", "stock_quantity", "min_order_quantity",
            "is_bonus_eligible", "bonus_every_n",
            "is_active", "is_available", "is_in_stock",
            "images", "bom_items",
            "created_at", "updated_at",
        ]

    def get_is_in_stock(self, obj):
        return obj.is_in_stock()


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "name", "description", "category", "category_type", "price",
            "stock_quantity", "min_order_quantity", "is_bonus_eligible", "bonus_every_n",
            "is_active", "is_available",
        ]

    def validate(self, attrs):
        ctype = attrs.get("category_type", getattr(self.instance, "category_type", None))
        is_bonus = attrs.get("is_bonus_eligible", getattr(self.instance, "is_bonus_eligible", False))
        min_order = attrs.get("min_order_quantity", getattr(self.instance, "min_order_quantity", Decimal("1.0")))
        stock = attrs.get("stock_quantity", getattr(self.instance, "stock_quantity", Decimal("0")))
        price = attrs.get("price", getattr(self.instance, "price", None))

        if price is None or price <= 0:
            raise serializers.ValidationError("Цена должна быть больше 0.")

        if stock < 0:
            raise serializers.ValidationError("Остаток не может быть отрицательным.")

        # Весовые правила
        if ctype == Unit.WEIGHT:
            if is_bonus:
                raise serializers.ValidationError("Весовые товары не могут участвовать в бонусной программе.")
            if min_order < Decimal("0.1"):
                raise serializers.ValidationError("Для весовых минималка не ниже 0.1 кг.")
            if not is_step_ok(min_order, DEC_STEP_01):
                raise serializers.ValidationError("Для весовых шаг заказа 0.1 кг.")

        else:
            # штучные
            if min_order < 1:
                raise serializers.ValidationError("Для штучных минималка 1 шт.")
            if not is_step_ok(min_order, Decimal("1")):
                raise serializers.ValidationError("Для штучных шаг 1.")

        return attrs


# ---------- Операции с ценой/остатком/запросом ----------

class ProductPriceCalculationSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=Decimal("0.001"))

    def validate(self, attrs):
        product: Product = self.context["product"]
        q = attrs["quantity"]

        # валидируем порог и шаг
        if product.is_weight:
            if q < product.min_order_quantity:
                raise serializers.ValidationError(f"Минимум для заказа: {product.min_order_quantity} кг.")
            if not is_step_ok(q, DEC_STEP_01):
                raise serializers.ValidationError("Шаг для весовых — 0.1 кг.")
        else:
            if q < Decimal("1"):
                raise serializers.ValidationError("Минимум для штучных — 1 шт.")
            if not is_step_ok(q, Decimal("1")):
                raise serializers.ValidationError("Шаг для штучных — 1.")

        # наличие
        if not product.is_in_stock(q):
            raise serializers.ValidationError(f"Недостаточно на складе. Доступно: {product.stock_quantity}.")
        return attrs

    def to_representation(self, instance):
        # не используется
        return super().to_representation(instance)


class ProductStockUpdateSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    operation = serializers.ChoiceField(choices=["add", "subtract", "set"])
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate(self, attrs):
        product: Product = self.context["product"]
        q = attrs["quantity"]
        op = attrs["operation"]

        if op in ["add", "set"] and q < 0:
            raise serializers.ValidationError("Количество не может быть отрицательным.")

        # Для веса — шаг 0.1
        if product.is_weight and not is_step_ok(abs(q), DEC_STEP_01):
            raise serializers.ValidationError("Для весовых операций шаг 0.1 кг.")

        # Для вычитания проверяем остаток
        if op == "subtract" and not product.is_in_stock(q):
            raise serializers.ValidationError(f"Недостаточно остатка. Доступно: {product.stock_quantity}.")

        return attrs


class ProductRequestSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=Decimal("0.001"))

    def validate(self, attrs):
        try:
            product = Product.objects.get(id=attrs["product_id"], is_active=True, is_available=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Товар не найден или недоступен.")

        q = attrs["quantity"]

        # правила шага/минимума
        if product.is_weight:
            if q < product.min_order_quantity:
                raise serializers.ValidationError(f"Минимальное количество: {product.min_order_quantity} кг.")
            if not is_step_ok(q, DEC_STEP_01):
                raise serializers.ValidationError("Шаг для весовых — 0.1 кг.")
        else:
            if q < 1:
                raise serializers.ValidationError("Минимальное количество: 1 шт.")
            if not is_step_ok(q, Decimal("1")):
                raise serializers.ValidationError("Шаг для штучных — 1.")

        if not product.is_in_stock(q):
            raise serializers.ValidationError(f"Недостаточно на складе. Доступно: {product.stock_quantity}.")

        # сохраняем объект в контекст, чтобы не делать второй get() во view
        self.context["product"] = product
        return attrs


# ---------- Expenses ----------

class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = "__all__"


class ExpenseValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseValue
        fields = "__all__"

    def validate(self, attrs):
        exp: Expense = attrs.get("expense") or self.instance.expense  # type: ignore
        is_physical = exp.kind == ExpenseKind.PHYSICAL
        pp = attrs.get("price_per_unit", getattr(self.instance, "price_per_unit", None))
        pa = attrs.get("period_amount", getattr(self.instance, "period_amount", None))

        if is_physical:
            if pp is None:
                raise serializers.ValidationError("Для физического расхода укажите price_per_unit.")
            if pa:
                raise serializers.ValidationError("Для физического period_amount не заполняется.")
        else:
            if pa is None:
                raise serializers.ValidationError("Для накладного расхода укажите period_amount.")
            if pp:
                raise serializers.ValidationError("Для накладного price_per_unit не заполняется.")
        return attrs


class ExpenseBindingSerializer(serializers.ModelSerializer):
    expense_name = serializers.CharField(source="expense.name", read_only=True)

    class Meta:
        model = ExpenseBinding
        fields = ("id", "expense", "expense_name", "product", "qty_per_unit", "weight_factor")

    def validate(self, attrs):
        exp: Expense = attrs.get("expense") or self.instance.expense  # type: ignore
        product: Product = attrs.get("product") or self.instance.product  # type: ignore

        if exp.scope == ExpenseScope.PER_PRODUCT:
            # Для PHYSICAL нужна норма на единицу
            if exp.kind == ExpenseKind.PHYSICAL and (attrs.get("qty_per_unit") or Decimal("0")) <= 0:
                raise serializers.ValidationError("Для физического расхода укажите qty_per_unit > 0.")
        else:
            # UNIVERSAL: не должен иметь привязок, но оставим мягкую проверку
            pass

        # Запрет нелепых связей: весовой расход «за шт» и т.д. — оставляем бизнес-проверки на сервис расчёта
        return attrs


# ---------- Cost register (read-only в API) ----------

class CostRegisterSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = CostRegister
        fields = ("date", "product", "product_name", "cost_per_unit", "breakdown")
        read_only_fields = ("date", "product", "cost_per_unit", "breakdown")
