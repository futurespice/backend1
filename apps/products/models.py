from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


# =========================
#  Справочники и утилиты
# =========================

class Unit:
    PIECE = "piece"
    WEIGHT = "weight"
    CHOICES = [(PIECE, "Штучный"), (WEIGHT, "Весовой")]


class ExpenseKind:
    PHYSICAL = "physical"   # ингредиенты/упаковка (осязаемое)
    OVERHEAD = "overhead"   # аренда/свет/вода/зарплаты (накладные)
    CHOICES = [(PHYSICAL, "Физический"), (OVERHEAD, "Накладной")]


class ExpenseStatus:
    SUZERAIN = "suzerain"   # главный драйвер
    VASSAL = "vassal"       # рассчитывается от механики
    COMMONER = "commoner"   # базовый/ручной
    CHOICES = [
        (SUZERAIN, "Сюзерен"),
        (VASSAL, "Вассал"),
        (COMMONER, "Обыватель"),
    ]


class ExpenseState:
    MECHANIC = "mechanic"   # механический учёт (ручной ввод суммы/объёма)
    AUTO = "auto"           # автоматический (от драйверов/объёма)
    CHOICES = [(MECHANIC, "Механический"), (AUTO, "Автоматический")]


class ExpenseScope:
    UNIVERSAL = "universal"     # применяется ко всем товарам
    PER_PRODUCT = "per_product" # назначается на конкретные товары
    CHOICES = [(UNIVERSAL, "Универсальный"), (PER_PRODUCT, "По товарам")]


# =========================
#  Категории и товары
# =========================

class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название категории")
    category_type = models.CharField(max_length=10, choices=Unit.CHOICES, default=Unit.PIECE, verbose_name="Тип категории")
    description = models.TextField(blank=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_categories"
        ordering = ["name"]
        verbose_name = "Категория товаров"
        verbose_name_plural = "Категории товаров"

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"


class Product(models.Model):
    # Базовое
    name = models.CharField(max_length=200, unique=True, verbose_name="Название товара")
    description = models.TextField(max_length=250, blank=True, verbose_name="Описание")
    category = models.ForeignKey(
        ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="products", verbose_name="Категория"
    )

    category_type = models.CharField(max_length=10, choices=Unit.CHOICES, default=Unit.PIECE, verbose_name="Тип товара")

    # Цена: для штучных — за штуку, для весовых — за кг
    price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))], verbose_name="Цена (шт/кг)"
    )

    # Остаток: для штучных — шт, для весовых — кг
    stock_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Остаток на складе"
    )

    # Минимум к заказу (пересчитывается для весовых)
    min_order_quantity = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("1.000"),
        validators=[MinValueValidator(Decimal("0.1"))], verbose_name="Минимальное количество к заказу"
    )

    # Бонусы
    is_bonus_eligible = models.BooleanField(
        default=True, verbose_name="Участвует в бонусной программе",
        help_text="Весовые товары не могут быть бонусными"
    )
    bonus_every_n = models.PositiveIntegerField(default=21, verbose_name="Каждый N-й бесплатно (штучные)")

    # Статусы
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    is_available = models.BooleanField(default=True, verbose_name="Доступен к заказу")

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")

    # Техническое — фиксация исходного типа (запрет менять вес/шт задним числом)
    _initial_type = None

    class Meta:
        db_table = "products"
        ordering = ["-created_at"]
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

    def __str__(self):
        return f"{self.name} ({self.price} за {'кг' if self.is_weight else 'шт'})"

    # --------- helpers ---------
    @property
    def is_weight(self) -> bool:
        return self.category_type == Unit.WEIGHT

    @property
    def price_per_100g(self):
        return (self.price / Decimal("10")) if self.is_weight else None

    def clean(self):
        # Весовые не могут быть бонусными
        if self.is_weight and self.is_bonus_eligible:
            self.is_bonus_eligible = False

        # Запрет на смену типа товара после создания
        if self.pk:
            if self._initial_type and self._initial_type != self.category_type:
                raise ValueError("Нельзя менять тип товара (весовой ↔ штучный) после создания.")

    def save(self, *args, **kwargs):
        # Инициализируем исходный тип
        if self.pk and self._initial_type is None:
            self._initial_type = Product.objects.only("category_type").get(pk=self.pk).category_type

        # Весовые: порог min зависит от остатка
        if self.is_weight:
            self.is_bonus_eligible = False
            self.min_order_quantity = Decimal("0.1") if self.stock_quantity < Decimal("1.0") else Decimal("1.0")
        else:
            self.min_order_quantity = Decimal("1.0")

        self.clean()
        super().save(*args, **kwargs)

    # ---------- доменная логика ----------
    def calc_line_total(self, quantity: Decimal) -> Decimal:
        """Итоговая стоимость строки без учёта бонусов (штучные) или с шагом 0.1 кг (весовые)."""
        if self.is_weight:
            # цена за 100г * (вес / 0.1)
            steps = (quantity / Decimal("0.1"))
            return (self.price / Decimal("10")) * steps.quantize(Decimal("1"))
        return (self.price * quantity).quantize(Decimal("0.01"))

    def split_bonus(self, quantity: int):
        """Для штучных: возвращает (payable_qty, bonus_qty) с правилом 'каждый N-й бесплатно'."""
        if self.is_weight or not self.is_bonus_eligible or self.bonus_every_n < 2:
            return quantity, 0
        bonus_qty = quantity // self.bonus_every_n
        return quantity - bonus_qty, bonus_qty


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/", verbose_name="Изображение")
    is_primary = models.BooleanField(default=False, verbose_name="Основное")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_images"
        ordering = ["order", "created_at"]
        verbose_name = "Изображение товара"
        verbose_name_plural = "Изображения товаров"

    def save(self, *args, **kwargs):
        if not self.product.images.exists():
            self.is_primary = True
        elif self.is_primary:
            self.product.images.update(is_primary=False)
        super().save(*args, **kwargs)


# =========================
#  Продукт как ингредиент (BOM)
# =========================

class ProductBOM(models.Model):
    """Состав: продукт -> ингредиент (которым может быть другой продукт). qty_per_unit — сколько ингредиента на 1 ед. выпуска."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="bom_items", verbose_name="Продукт")
    ingredient = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="used_in", verbose_name="Ингредиент")
    qty_per_unit = models.DecimalField(max_digits=12, decimal_places=4, validators=[MinValueValidator(Decimal("0.0001"))])

    class Meta:
        db_table = "product_bom"
        unique_together = [("product", "ingredient")]
        verbose_name = "Ингредиент продукта"
        verbose_name_plural = "Ингредиенты продуктов"

    def clean(self):
        if self.product_id == self.ingredient_id:
            raise ValueError("Продукт не может быть ингредиентом самого себя.")


# =========================
#  Расходы и их значения
# =========================

class Expense(models.Model):
    name = models.CharField(max_length=120, unique=True, verbose_name="Статья расхода")
    kind = models.CharField(max_length=16, choices=ExpenseKind.CHOICES, default=ExpenseKind.PHYSICAL, verbose_name="Вид")
    status = models.CharField(max_length=16, choices=ExpenseStatus.CHOICES, default=ExpenseStatus.COMMONER, verbose_name="Статус")
    state = models.CharField(max_length=16, choices=ExpenseState.CHOICES, default=ExpenseState.AUTO, verbose_name="Состояние")
    scope = models.CharField(max_length=16, choices=ExpenseScope.CHOICES, default=ExpenseScope.UNIVERSAL, verbose_name="Область применения")
    unit = models.CharField(max_length=16, blank=True, verbose_name="Ед. изм. (для физ.)")  # например: kg, piece, pack
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "expenses"
        ordering = ["name"]
        verbose_name = "Расход"
        verbose_name_plural = "Расходы"

    def __str__(self):
        return self.name


class ExpenseValue(models.Model):
    """
    Значения расходов по датам/периодам.
    - Для PHYSICAL: price_per_unit (напр., цена 1 кг упаковки).
    - Для OVERHEAD: period_amount (сумма за месяц/неделю).
    Ровно одно из полей должно быть заполнено.
    """
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="values")
    date_from = models.DateField(default=timezone.now)
    date_to = models.DateField(null=True, blank=True)

    price_per_unit = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    period_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "expense_values"
        ordering = ["-date_from"]
        verbose_name = "Значение расхода"
        verbose_name_plural = "Значения расходов"

    def clean(self):
        is_physical = self.expense.kind == ExpenseKind.PHYSICAL
        if is_physical and not self.price_per_unit:
            raise ValueError("Для физического расхода требуется price_per_unit.")
        if (not is_physical) and not self.period_amount:
            raise ValueError("Для накладного расхода требуется period_amount.")
        if is_physical and self.period_amount:
            raise ValueError("Для физического расхода period_amount не заполняется.")
        if (not is_physical) and self.price_per_unit:
            raise ValueError("Для накладного расхода price_per_unit не заполняется.")


class ExpenseBinding(models.Model):
    """
    Привязка расходов к конкретным товарам (для scope=per_product).
    Для PHYSICAL qty_per_unit означает, сколько расхода требуется на единицу продукта.
    Для OVERHEAD weight_factor — коэффициент распределения накладных (если не UNIVERSAL).
    """
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="bindings")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="expense_bindings")

    qty_per_unit = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal("0"))  # только для PHYSICAL
    weight_factor = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal("1"))  # для OVERHEAD

    class Meta:
        db_table = "expense_bindings"
        unique_together = [("expense", "product")]
        verbose_name = "Привязка расхода к товару"
        verbose_name_plural = "Привязки расходов к товарам"


# =========================
#  Себестоимость (снапшоты)
# =========================

class CostRegister(models.Model):
    """Зафиксированная себестоимость на дату (для аналитики и отчётов)."""
    date = models.DateField()
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cost_snapshots")
    cost_per_unit = models.DecimalField(max_digits=14, decimal_places=4)
    breakdown = models.JSONField(default=dict, blank=True)  # разложение: ингредиенты/накладные/прочее

    class Meta:
        db_table = "cost_register"
        unique_together = [("date", "product")]
        ordering = ["-date", "product_id"]
        verbose_name = "Себестоимость (дата)"
        verbose_name_plural = "Себестоимость по датам"
