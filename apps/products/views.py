from decimal import Decimal
from django.db import models
from django.db.models import Q, F, Count
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Product, ProductCategory, ProductImage, ProductBOM
from .serializers import (
    ProductListSerializer, ProductDetailSerializer, ProductCreateUpdateSerializer,
    ProductCategorySerializer, ProductImageSerializer,
    ProductStockUpdateSerializer, ProductRequestSerializer
)
from .filters import ProductFilter
from users.permissions import IsPartnerUser, IsAdminUser, IsStoreUser


class ProductCategoryViewSet(viewsets.ModelViewSet):
    """Категории товаров"""
    queryset = ProductCategory.objects.filter(is_active=True)
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [permissions.IsAuthenticated()]


class ProductViewSet(viewsets.ModelViewSet):
    """
    Товары с интеграцией в систему расчета себестоимости.
    Убрана дублирующая логика BOM и расходов - теперь через cost_accounting.
    """
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
        if self.action in ["create", "update", "partial_update", "destroy", "update_stock"]:
            return [IsAdminUser()]
        elif self.action in ["request_products"]:
            return [IsPartnerUser() | IsStoreUser()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=["patch"], permission_classes=[IsAdminUser])
    def update_stock(self, request, pk=None):
        """Обновление остатков на складе"""
        product = self.get_object()
        serializer = ProductStockUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        quantity = serializer.validated_data["quantity"]
        operation = serializer.validated_data["operation"]

        try:
            old_stock = product.stock_quantity
            product.update_stock(quantity, operation)

            return Response({
                "message": f"Остаток обновлен: {old_stock} → {product.stock_quantity}",
                "old_stock": float(old_stock),
                "new_stock": float(product.stock_quantity),
                "operation": operation,
                "quantity": float(quantity)
            })
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"])
    def calculate_price(self, request, pk=None):
        """Расчет цены для конкретного количества"""
        product = self.get_object()
        quantity = request.data.get("quantity")

        if quantity is None:
            return Response(
                {"error": "Нужен параметр quantity"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            quantity = Decimal(str(quantity))
            if quantity <= 0:
                raise ValueError("Количество должно быть больше 0")

            # Проверяем минимальный заказ и шаги
            if product.is_weight:
                if quantity < product.min_order_quantity:
                    return Response({
                        "error": f"Минимальный заказ: {product.min_order_quantity} кг"
                    }, status=status.HTTP_400_BAD_REQUEST)

                if quantity % Decimal('0.1') != 0:
                    return Response({
                        "error": "Для весовых товаров шаг 0.1 кг"
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                if quantity < 1 or quantity % 1 != 0:
                    return Response({
                        "error": "Для штучных товаров минимум 1 шт, только целые числа"
                    }, status=status.HTTP_400_BAD_REQUEST)

            total_price = product.calculate_price(quantity)

            response_data = {
                "product_id": product.id,
                "product_name": product.name,
                "product_type": product.category_type,
                "quantity": float(quantity),
                "unit_price": float(product.price),
                "total_price": float(total_price)
            }

            # Для штучных товаров показываем бонусы
            if not product.is_weight and product.is_bonus_eligible:
                payable_qty, bonus_qty = product.split_bonus(int(quantity))
                bonus_discount = product.price * bonus_qty

                response_data.update({
                    "bonus_info": {
                        "payable_quantity": payable_qty,
                        "bonus_quantity": bonus_qty,
                        "bonus_discount": float(bonus_discount),
                        "final_price": float(total_price - bonus_discount)
                    }
                })

            return Response(response_data)

        except (ValueError, TypeError) as e:
            return Response(
                {"error": f"Некорректное количество: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=["post"], permission_classes=[IsPartnerUser | IsStoreUser])
    def request_products(self, request):
        """Запрос товаров партнером/магазином"""
        serializer = ProductRequestSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        requested_items = []
        total_amount = Decimal("0")

        for item_data in serializer.validated_data:
            product_id = item_data["product_id"]
            quantity = item_data["quantity"]

            try:
                product = Product.objects.get(id=product_id, is_active=True, is_available=True)

                # Проверяем наличие на складе
                if not product.is_in_stock(quantity):
                    return Response({
                        "error": f"Недостаточно товара '{product.name}' на складе. Доступно: {product.stock_quantity}"
                    }, status=status.HTTP_400_BAD_REQUEST)

                item_total = product.calculate_price(quantity)
                total_amount += item_total

                requested_items.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "quantity": float(quantity),
                    "unit_price": float(product.price),
                    "total_price": float(item_total)
                })

            except Product.DoesNotExist:
                return Response({
                    "error": f"Товар с ID {product_id} не найден"
                }, status=status.HTTP_400_BAD_REQUEST)

        # TODO: Интегрировать с системой заказов/долгов
        # Пока возвращаем расчет без создания заказа

        return Response({
            "requested_by": request.user.id,
            "items": requested_items,
            "total_items": len(requested_items),
            "total_amount": float(total_amount),
            "status": "calculated",  # пока только расчет
            "message": "Расчет выполнен. Интеграция с заказами в разработке."
        })

    @action(detail=True, methods=["get"])
    def cost_info(self, request, pk=None):
        """
        Информация о себестоимости товара.
        Интегрируется с cost_accounting модулем.
        """
        product = self.get_object()

        # Импортируем здесь чтобы избежать циклических импортов
        from cost_accounting.models import ProductExpense, ProductionBatch
        from cost_accounting.models import Expense

        # Получаем связанные расходы
        product_expenses = ProductExpense.objects.filter(
            product=product,
            is_active=True
        ).select_related('expense')

        # Группируем по типам
        physical_expenses = product_expenses.filter(expense__type=Expense.ExpenseType.PHYSICAL)
        overhead_expenses = product_expenses.filter(expense__type=Expense.ExpenseType.OVERHEAD)

        # Ищем Сюзерена
        suzerain = physical_expenses.filter(expense__status=Expense.ExpenseStatus.SUZERAIN).first()

        # Последний расчет себестоимости
        latest_batch = ProductionBatch.objects.filter(product=product).order_by('-date').first()

        response_data = {
            "product_id": product.id,
            "product_name": product.name,
            "physical_expenses": [
                {
                    "expense_id": pe.expense.id,
                    "name": pe.expense.name,
                    "unit": pe.expense.unit,
                    "ratio_per_unit": float(pe.ratio_per_product_unit),
                    "current_price": float(pe.expense.price_per_unit or 0),
                    "is_suzerain": pe.expense.status == Expense.ExpenseStatus.SUZERAIN
                }
                for pe in physical_expenses
            ],
            "overhead_expenses": [
                {
                    "expense_id": pe.expense.id,
                    "name": pe.expense.name,
                    "ratio_per_unit": float(pe.ratio_per_product_unit)
                }
                for pe in overhead_expenses
            ],
            "suzerain_expense": {
                "id": suzerain.expense.id,
                "name": suzerain.expense.name,
                "ratio_per_unit": float(suzerain.ratio_per_product_unit)
            } if suzerain else None,
            "latest_cost_calculation": {
                "date": latest_batch.date,
                "cost_per_unit": float(latest_batch.cost_per_unit),
                "physical_cost": float(latest_batch.physical_cost),
                "overhead_cost": float(latest_batch.overhead_cost),
                "total_cost": float(latest_batch.total_cost)
            } if latest_batch else None
        }

        return Response(response_data)

    @action(detail=False, methods=["get"])
    def by_category(self, request):
        """Товары сгруппированные по категориям"""
        categories = ProductCategory.objects.filter(is_active=True).prefetch_related(
            models.Prefetch(
                'products',
                queryset=self.get_queryset().filter(is_active=True)
            )
        )

        result = []
        for category in categories:
            result.append({
                "category_id": category.id,
                "category_name": category.name,
                "category_type": category.category_type,
                "products": ProductListSerializer(category.products.all(), many=True).data
            })

        return Response(result)

    @action(detail=False, methods=["get"])
    def weight_products(self, request):
        """Только весовые товары"""
        weight_products = self.get_queryset().filter(category_type=Product.CategoryType.WEIGHT)
        serializer = ProductListSerializer(weight_products, many=True)
        return Response({
            "count": weight_products.count(),
            "products": serializer.data
        })

    @action(detail=False, methods=["get"])
    def bonus_eligible(self, request):
        """Товары участвующие в бонусной программе"""
        bonus_products = self.get_queryset().filter(
            is_bonus_eligible=True,
            category_type=Product.CategoryType.PIECE  # только штучные
        )
        serializer = ProductListSerializer(bonus_products, many=True)
        return Response({
            "count": bonus_products.count(),
            "products": serializer.data
        })

    @action(detail=False, methods=["get"])
    def low_stock(self, request):
        """Товары с низким остатком"""
        threshold = Decimal(request.query_params.get('threshold', '10'))

        low_stock_products = self.get_queryset().filter(
            stock_quantity__lt=threshold,
            is_active=True
        ).order_by('stock_quantity')

        serializer = ProductListSerializer(low_stock_products, many=True)
        return Response({
            "threshold": float(threshold),
            "count": low_stock_products.count(),
            "products": serializer.data
        })


class ProductImageViewSet(viewsets.ModelViewSet):
    """Управление изображениями товаров"""
    queryset = ProductImage.objects.select_related('product')
    serializer_class = ProductImageSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['product', 'is_primary']
    ordering = ['product', 'order', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=['patch'], permission_classes=[IsAdminUser])
    def set_primary(self, request, pk=None):
        """Установить изображение как основное"""
        image = self.get_object()

        # Убираем флаг у всех изображений этого товара
        ProductImage.objects.filter(product=image.product).update(is_primary=False)

        # Устанавливаем флаг для текущего
        image.is_primary = True
        image.save()

        return Response({
            "message": f"Изображение установлено как основное для товара '{image.product.name}'",
            "image_id": image.id
        })

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def reorder(self, request):
        """Изменение порядка изображений товара"""
        product_id = request.data.get('product_id')
        image_orders = request.data.get('image_orders')  # [{id: 1, order: 0}, {id: 2, order: 1}]

        if not product_id or not image_orders:
            return Response({
                "error": "Нужны параметры product_id и image_orders"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.get(id=product_id)

            for item in image_orders:
                ProductImage.objects.filter(
                    id=item['id'],
                    product=product
                ).update(order=item['order'])

            return Response({
                "message": f"Порядок изображений товара '{product.name}' обновлен",
                "updated_count": len(image_orders)
            })

        except Product.DoesNotExist:
            return Response({
                "error": "Товар не найден"
            }, status=status.HTTP_404_NOT_FOUND)
        except KeyError:
            return Response({
                "error": "Некорректный формат image_orders"
            }, status=status.HTTP_400_BAD_REQUEST)