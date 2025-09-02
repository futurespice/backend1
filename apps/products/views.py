from decimal import Decimal

from django.db import models
from django.db.models import Count, Q, F, ExpressionWrapper, DecimalField, Case, When
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Product, ProductCategory, ProductImage, ProductBOM,
    Expense, ExpenseValue, ExpenseBinding, Unit
)
from .serializers import (
    # products
    ProductListSerializer, ProductDetailSerializer, ProductCreateUpdateSerializer,
    ProductCategorySerializer, ProductPriceCalculationSerializer,
    ProductStockUpdateSerializer, ProductRequestSerializer,
    # bom
    ProductBOMItemSerializer, ProductBOMItemWriteSerializer,
    # expenses (если понадобятся публичные CRUD)
    ExpenseSerializer, ExpenseValueSerializer, ExpenseBindingSerializer,
)
from .filters import ProductFilter
from users.permissions import IsPartnerUser, IsAdminUser, IsStoreUser


# ---------- Категории ----------
class ProductCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProductCategory.objects.filter(is_active=True)
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering = ["name"]


# ---------- Товары ----------
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category").prefetch_related("images")
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ["name", "description"]
    ordering_fields = ["name", "price", "created_at", "stock_quantity"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        elif self.action in ["create", "update", "partial_update"]:
            return ProductCreateUpdateSerializer
        return ProductDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Партнёрам/магазинам — только активные и доступные
        if getattr(self.request.user, "role", None) in ("partner", "store"):
            qs = qs.filter(is_active=True, is_available=True)
        return qs

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy", "update_stock",
                           "bom_add", "bom_update", "bom_delete"]:
            classes = [IsAdminUser]
        elif self.action in ["calculate_price", "request_products"]:
            classes = [IsPartnerUser | IsStoreUser]
        else:
            classes = [permissions.IsAuthenticated]
        return [c() for c in classes]

    # --- Цены/бонусы/остатки ---

    @action(detail=True, methods=["post"])
    def calculate_price(self, request, pk=None):
        product = self.get_object()
        ser = ProductPriceCalculationSerializer(data=request.data, context={"product": product})
        if not ser.is_valid():
            return Response(ser.errors, status=400)

        q = ser.validated_data["quantity"]
        total = product.calc_line_total(q)

        # Для штучных сразу отдадим инфо по бонусу
        bonus_info = None
        if not product.is_weight and product.is_bonus_eligible:
            payable, bonus = product.split_bonus(int(q))
            bonus_info = {"requested_qty": int(q), "payable_qty": payable, "bonus_qty": bonus}

        return Response({
            "product_id": product.id,
            "product_name": product.name,
            "quantity": q,
            "unit_price": product.price,
            "price_per_100g": product.price_per_100g,
            "total_price": total,
            "category_type": product.category_type,
            "bonus": bonus_info,
        })

    @action(detail=True, methods=["post"])
    def split_bonus(self, request, pk=None):
        """Вернёт (payable_qty, bonus_qty) для штучных; для весовых — пусто."""
        product = self.get_object()
        if product.is_weight or not product.is_bonus_eligible:
            return Response({"payable_qty": int(request.data.get("quantity", 0)), "bonus_qty": 0})

        try:
            qty = int(Decimal(str(request.data.get("quantity", 0))))
        except Exception:
            return Response({"detail": "quantity должен быть целым числом"}, status=400)

        payable, bonus = product.split_bonus(qty)
        return Response({"payable_qty": payable, "bonus_qty": bonus})

    @action(detail=True, methods=["post"])
    def update_stock(self, request, pk=None):
        """Изменение остатка (с валидацией шага 0.1 для весовых). Только админ в get_permissions()."""
        product = self.get_object()
        ser = ProductStockUpdateSerializer(data=request.data, context={"product": product})
        if not ser.is_valid():
            return Response(ser.errors, status=400)

        qty = ser.validated_data["quantity"]
        op = ser.validated_data["operation"]
        reason = ser.validated_data.get("reason", "")

        old = product.stock_quantity
        if op == "add":
            product.increase_stock(qty)
        elif op == "subtract":
            if not product.reduce_stock(qty):
                return Response({"error": "Недостаточно товара на складе"}, status=400)
        else:  # set
            product.stock_quantity = qty
            product.save()

        # TODO: если у вас есть аудит/лог — сюда интегрируйте

        return Response({
            "product_id": product.id,
            "old_quantity": old,
            "new_quantity": product.stock_quantity,
            "operation": op,
            "reason": reason,
        })

    # --- Подборки/категории ---

    @action(detail=False, methods=["get"])
    def categories(self, request):
        cats = ProductCategory.objects.filter(is_active=True, products__is_active=True).distinct() \
            .annotate(products_count=Count("products"))
        return Response(ProductCategorySerializer(cats, many=True).data)

    @action(detail=False, methods=["get"])
    def bonus_eligible(self, request):
        qs = self.get_queryset().filter(is_bonus_eligible=True, category_type=Unit.PIECE)
        page = self.paginate_queryset(qs)
        ser = ProductListSerializer(page or qs, many=True, context={"request": request})
        return self.get_paginated_response(ser.data) if page else Response(ser.data)

    @action(detail=False, methods=["get"])
    def weight_products(self, request):
        qs = self.get_queryset().filter(category_type=Unit.WEIGHT)
        page = self.paginate_queryset(qs)
        ser = ProductListSerializer(page or qs, many=True, context={"request": request})
        return self.get_paginated_response(ser.data) if page else Response(ser.data)

    @action(detail=False, methods=["get"])
    def low_stock(self, request):
        """
        Низкий остаток:
        - штучные: < 10
        - весовые: < 1.0 кг
        """
        qs = self.get_queryset().annotate(
            is_low_piece=Case(
                When(category_type=Unit.PIECE, then=Q(stock_quantity__lt=Decimal("10"))),
                default=False, output_field=models.BooleanField()
            ),
            is_low_weight=Case(
                When(category_type=Unit.WEIGHT, then=Q(stock_quantity__lt=Decimal("1.0"))),
                default=False, output_field=models.BooleanField()
            ),
        ).filter(Q(is_low_piece=True) | Q(is_low_weight=True))

        page = self.paginate_queryset(qs)
        ser = ProductListSerializer(page or qs, many=True, context={"request": request})
        return self.get_paginated_response(ser.data) if page else Response(ser.data)

    # --- BOM (ингредиенты товара) ---

    @action(detail=True, methods=["get"])
    def bom(self, request, pk=None):
        """Список ингредиентов продукта."""
        product = self.get_object()
        ser = ProductBOMItemSerializer(product.bom_items.all(), many=True)
        return Response(ser.data)

    @action(detail=True, methods=["post"])
    def bom_add(self, request, pk=None):
        """Добавить ингредиент продукту (админ)."""
        product = self.get_object()
        ser = ProductBOMItemWriteSerializer(data=request.data, context={"product": product})
        if not ser.is_valid():
            return Response(ser.errors, status=400)
        ProductBOM.objects.create(product=product, **ser.validated_data)
        return Response({"detail": "Ингредиент добавлен"}, status=201)

    @action(detail=True, methods=["put", "patch"])
    def bom_update(self, request, pk=None):
        """Обновить qty существующего ингредиента (админ). body: {ingredient, qty_per_unit}"""
        product = self.get_object()
        try:
            item = ProductBOM.objects.get(product=product, ingredient_id=request.data.get("ingredient"))
        except ProductBOM.DoesNotExist:
            return Response({"detail": "Связь product-ingredient не найдена"}, status=404)

        ser = ProductBOMItemWriteSerializer(item, data=request.data, partial=True, context={"product": product})
        if not ser.is_valid():
            return Response(ser.errors, status=400)
        ser.save()
        return Response(ProductBOMItemSerializer(item).data)

    @action(detail=True, methods=["delete"])
    def bom_delete(self, request, pk=None):
        """Удалить ингредиент (админ). query: ?ingredient=<id>"""
        product = self.get_object()
        ing_id = request.query_params.get("ingredient")
        if not ing_id:
            return Response({"detail": "Не передан ingredient"}, status=400)
        deleted, _ = ProductBOM.objects.filter(product=product, ingredient_id=ing_id).delete()
        return Response(status=204 if deleted else 404)


# ---------- (опционально) CRUD расходов ----------
class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAdminUser]


class ExpenseValueViewSet(viewsets.ModelViewSet):
    queryset = ExpenseValue.objects.select_related("expense")
    serializer_class = ExpenseValueSerializer
    permission_classes = [IsAdminUser]


class ExpenseBindingViewSet(viewsets.ModelViewSet):
    queryset = ExpenseBinding.objects.select_related("expense", "product")
    serializer_class = ExpenseBindingSerializer
    permission_classes = [IsAdminUser]
