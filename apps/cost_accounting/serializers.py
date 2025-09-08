# cost_accounting/serializers.py
from rest_framework import serializers
from .models import (
    Expense, ProductExpense, DailyExpenseLog, ProductionBatch,
    MonthlyOverheadBudget, BillOfMaterial, BOMLine
)
from products.models import Product
from decimal import Decimal

# ---------- Basic Model Serializers ----------

class ExpenseSerializer(serializers.ModelSerializer):
    """Сериализатор для расходов"""

    class Meta:
        model = Expense
        fields = '__all__'


class ProductExpenseSerializer(serializers.ModelSerializer):
    """Сериализатор для связей продуктов с расходами"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    expense_name = serializers.CharField(source='expense.name', read_only=True)
    expense_type = serializers.CharField(source='expense.get_type_display', read_only=True)

    class Meta:
        model = ProductExpense
        fields = [
            'id', 'product', 'product_name', 'expense', 'expense_name', 'expense_type',
            'ratio_per_product_unit', 'is_active', 'created_at']



class DailyExpenseLogSerializer(serializers.ModelSerializer):
    """Сериализатор для дневных логов расходов"""

    expense_name = serializers.CharField(source='expense.name', read_only=True)
    expense_type = serializers.CharField(source='expense.get_type_display', read_only=True)

    class Meta:
        model = DailyExpenseLog
        fields = [
            'id', 'expense', 'expense_name', 'expense_type', 'date',
            'quantity_used', 'actual_price_per_unit', 'daily_amount', 'total_cost',
            'created_at', 'updated_at'
        ]

    def validate(self, data):
        """Автоматически рассчитываем total_cost"""
        if data.get('quantity_used') and data.get('actual_price_per_unit'):
            data['total_cost'] = data['quantity_used'] * data['actual_price_per_unit']
        return data


class ProductionBatchSerializer(serializers.ModelSerializer):
    """Сериализатор для производственных смен"""

    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = ProductionBatch
        fields = [
            'id', 'product', 'product_name', 'date', 'produced_quantity',
            'suzerain_input_amount', 'physical_cost', 'overhead_cost', 'total_cost',
            'cost_per_unit', 'revenue', 'net_profit', 'cost_breakdown',
            'created_at', 'updated_at'
        ]


class MonthlyOverheadBudgetSerializer(serializers.ModelSerializer):
    """Сериализатор для месячных бюджетов накладных расходов"""

    expense_name = serializers.CharField(source='expense.name', read_only=True)

    class Meta:
        model = MonthlyOverheadBudget
        fields = [
            'id', 'expense', 'expense_name', 'year', 'month',
            'planned_amount', 'actual_amount', 'created_at', 'updated_at'
        ]


# ---------- BOM Serializers ----------

class BOMLineSerializer(serializers.ModelSerializer):
    """Сериализатор для строки BOM (компонента)"""

    expense_name = serializers.CharField(source='expense.name', read_only=True)
    component_product_name = serializers.CharField(source='component_product.name', read_only=True)

    class Meta:
        model = BOMLine
        fields = [
            'id', 'expense', 'expense_name', 'component_product', 'component_product_name',
            'quantity', 'unit', 'is_primary', 'order'
        ]

    def validate(self, data):
        """Валидация: должен быть указан либо expense, либо component_product"""
        expense = data.get('expense')
        component_product = data.get('component_product')

        if not expense and not component_product:
            raise serializers.ValidationError(
                "Должен быть указан либо расход (expense), либо компонент-продукт (component_product)"
            )

        if expense and component_product:
            raise serializers.ValidationError(
                "Нельзя указывать одновременно расход и продукт"
            )

        return data


class BOMSerializer(serializers.ModelSerializer):
    """Сериализатор для спецификации состава (BOM)"""

    lines = BOMLineSerializer(many=True, read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    components_count = serializers.SerializerMethodField()

    class Meta:
        model = BillOfMaterial
        fields = [
            'id', 'product', 'product_name', 'version', 'is_active',
            'lines', 'components_count', 'created_at', 'updated_at'
        ]

    def get_components_count(self, obj) -> int:
        """Количество компонентов в спецификации"""
        return obj.lines.count()


class BOMCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания/обновления BOM с компонентами"""

    lines = BOMLineSerializer(many=True)

    class Meta:
        model = BillOfMaterial
        fields = ['product', 'version', 'is_active', 'lines']

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        bom = BillOfMaterial.objects.create(**validated_data)

        for line_data in lines_data:
            BOMLine.objects.create(bom=bom, **line_data)

        return bom

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)

        # Обновляем основные поля
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Обновляем компоненты
        if lines_data is not None:
            instance.lines.all().delete()  # Удаляем старые
            for line_data in lines_data:
                BOMLine.objects.create(bom=instance, **line_data)

        return instance


# ---------- Request/Response Serializers ----------

class ProductRecipeTemplateSerializer(serializers.Serializer):
    """Сериализатор для создания рецепта по шаблону"""

    product_id = serializers.IntegerField()
    version = serializers.CharField(max_length=50, default="1.0")
    components = serializers.ListField(
        child=serializers.DictField(),
        help_text="Список компонентов в формате: [{'type': 'product'|'expense', 'id': 1, 'quantity': 1.0, 'unit': 'шт', 'is_primary': false}]"
    )

    def validate_product_id(self, value):
        """Проверяем существование продукта"""
        try:
            Product.objects.get(id=value)
            return value
        except Product.DoesNotExist:
            raise serializers.ValidationError(f"Продукт с ID {value} не найден")

    def validate_components(self, value):
        """Валидация компонентов"""
        if not value:
            raise serializers.ValidationError("Список компонентов не может быть пустым")

        primary_count = 0

        for component in value:
            # Проверяем обязательные поля
            required_fields = ['type', 'id', 'quantity']
            for field in required_fields:
                if field not in component:
                    raise serializers.ValidationError(f"Поле '{field}' обязательно для каждого компонента")

            # Проверяем тип
            if component['type'] not in ['product', 'expense']:
                raise serializers.ValidationError("Тип компонента должен быть 'product' или 'expense'")

            # Проверяем количество
            try:
                quantity = float(component['quantity'])
                if quantity <= 0:
                    raise serializers.ValidationError("Количество должно быть больше 0")
            except (ValueError, TypeError):
                raise serializers.ValidationError("Количество должно быть числом")

            # Считаем основные компоненты
            if component.get('is_primary', False):
                primary_count += 1

            # Проверяем существование компонента
            if component['type'] == 'product':
                try:
                    Product.objects.get(id=component['id'])
                except Product.DoesNotExist:
                    raise serializers.ValidationError(f"Продукт-компонент с ID {component['id']} не найден")
            else:  # expense
                try:
                    Expense.objects.get(id=component['id'])
                except Expense.DoesNotExist:
                    raise serializers.ValidationError(f"Расход с ID {component['id']} не найден")

        # Проверяем количество основных компонентов
        if primary_count > 1:
            raise serializers.ValidationError("Может быть только один основной компонент (Сюзерен)")

        return value


class CostCalculationRequestSerializer(serializers.Serializer):
    """Сериализатор для запроса расчета себестоимости"""

    date = serializers.DateField()
    production_data = serializers.DictField(
        child=serializers.DictField(),
        help_text="Данные производства в формате: {'product_id': {'quantity': 1100, 'suzerain_input': 105}}"
    )

    def validate_production_data(self, value):
        """Валидация данных производства"""
        if not value:
            raise serializers.ValidationError("Данные производства не могут быть пустыми")

        for product_id, prod_data in value.items():
            # Проверяем, что product_id - число
            try:
                int(product_id)
            except ValueError:
                raise serializers.ValidationError(f"ID продукта должен быть числом: {product_id}")

            # Проверяем наличие хотя бы одного из полей
            quantity = prod_data.get('quantity')
            suzerain_input = prod_data.get('suzerain_input')

            if not quantity and not suzerain_input:
                raise serializers.ValidationError(
                    f"Для продукта {product_id} должно быть указано 'quantity' или 'suzerain_input'"
                )

            # Валидируем числовые значения
            if quantity is not None:
                try:
                    float_qty = float(quantity)
                    if float_qty <= 0:
                        raise serializers.ValidationError(f"Количество должно быть больше 0 для продукта {product_id}")
                except (ValueError, TypeError):
                    raise serializers.ValidationError(f"Количество должно быть числом для продукта {product_id}")

            if suzerain_input is not None:
                try:
                    float_input = float(suzerain_input)
                    if float_input <= 0:
                        raise serializers.ValidationError(
                            f"Ввод Сюзерена должен быть больше 0 для продукта {product_id}")
                except (ValueError, TypeError):
                    raise serializers.ValidationError(f"Ввод Сюзерена должен быть числом для продукта {product_id}")

        return value


class CostBreakdownSerializer(serializers.Serializer):
    """Сериализатор для разбивки себестоимости"""

    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    date = serializers.DateField()
    produced_quantity = serializers.DecimalField(max_digits=12, decimal_places=3)

    # Детализация расходов
    physical_costs = serializers.ListField(
        child=serializers.DictField()
    )
    component_costs = serializers.ListField(
        child=serializers.DictField()
    )
    overhead_costs = serializers.ListField(
        child=serializers.DictField()
    )

    # Итоги
    total_physical = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_components = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_overhead = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    cost_per_unit = serializers.DecimalField(max_digits=12, decimal_places=4)


# ---------- Bulk Operations Serializers ----------

class BulkDailyExpenseSerializer(serializers.Serializer):
    """Сериализатор для массового создания дневных расходов"""

    date = serializers.DateField()
    expenses = serializers.ListField(
        child=serializers.DictField(),
        help_text="Список расходов: [{'expense_id': 1, 'quantity_used': 10.5, 'actual_price': 25.0}]"
    )

    def validate_expenses(self, value):
        """Валидация расходов"""
        if not value:
            raise serializers.ValidationError("Список расходов не может быть пустым")

        for expense_data in value:
            required_fields = ['expense_id', 'quantity_used']
            for field in required_fields:
                if field not in expense_data:
                    raise serializers.ValidationError(f"Поле '{field}' обязательно")

            # Проверяем существование расхода
            try:
                Expense.objects.get(id=expense_data['expense_id'])
            except Expense.DoesNotExist:
                raise serializers.ValidationError(f"Расход с ID {expense_data['expense_id']} не найден")

        return value


class MonthlyOverheadBulkSerializer(serializers.Serializer):
    """Сериализатор для массового создания месячных бюджетов"""

    year = serializers.IntegerField()
    month = serializers.IntegerField(min_value=1, max_value=12)
    budgets = serializers.ListField(
        child=serializers.DictField(),
        help_text="Список бюджетов: [{'expense_id': 1, 'planned_amount': 35000}]"
    )

    def validate_budgets(self, value):
        """Валидация бюджетов"""
        if not value:
            raise serializers.ValidationError("Список бюджетов не может быть пустым")

        for budget_data in value:
            if 'expense_id' not in budget_data or 'planned_amount' not in budget_data:
                raise serializers.ValidationError("Поля 'expense_id' и 'planned_amount' обязательны")

            # Проверяем существование расхода
            try:
                expense = Expense.objects.get(id=budget_data['expense_id'])
                if expense.type != Expense.ExpenseType.OVERHEAD:
                    raise serializers.ValidationError(f"Расход {expense.name} не является накладным")
            except Expense.DoesNotExist:
                raise serializers.ValidationError(f"Расход с ID {budget_data['expense_id']} не найден")

        return value


# ---------- Utility Serializers ----------

class DailyCostSummarySerializer(serializers.Serializer):
    """Сериализатор для дневной сводки расходов"""

    date = serializers.DateField()
    physical_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    overhead_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    grand_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    expenses_count = serializers.IntegerField()


class ExpensePriceUpdateSerializer(serializers.Serializer):
    """Сериализатор для массового обновления цен расходов"""

    expense_id = serializers.IntegerField()
    new_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))

    def validate_expense_id(self, value):
        """Проверяем существование расхода"""
        try:
            Expense.objects.get(id=value)
            return value
        except Expense.DoesNotExist:
            raise serializers.ValidationError(f"Расход с ID {value} не найден")


class SuzerainProductSetupSerializer(serializers.Serializer):
    """Сериализатор для настройки продукта с Сюзереном"""

    product_id = serializers.IntegerField()
    suzerain_expense_id = serializers.IntegerField()
    ratio_per_unit = serializers.DecimalField(
        max_digits=12, decimal_places=6, min_value=Decimal('0.000001'),
        help_text="Количество Сюзерена на 1 единицу продукта"
    )

    def validate_product_id(self, value):
        try:
            Product.objects.get(id=value)
            return value
        except Product.DoesNotExist:
            raise serializers.ValidationError(f"Продукт с ID {value} не найден")

    def validate_suzerain_expense_id(self, value):
        try:
            expense = Expense.objects.get(id=value)
            if expense.type != Expense.ExpenseType.PHYSICAL:
                raise serializers.ValidationError("Сюзерен должен быть физическим расходом")
            return value
        except Expense.DoesNotExist:
            raise serializers.ValidationError(f"Расход с ID {value} не найден")