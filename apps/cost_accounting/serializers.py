from decimal import Decimal
from datetime import date
from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import (
    Expense, ProductExpense, DailyExpenseLog,
    ProductionBatch, MonthlyOverheadBudget
)
from products.models import Product


class ExpenseSerializer(serializers.ModelSerializer):
    """Сериализатор расходов"""

    type_display = serializers.CharField(source='get_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    state_display = serializers.CharField(source='get_state_display', read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id', 'type', 'name', 'unit', 'price_per_unit',
            'status', 'state', 'is_universal', 'is_active',
            'type_display', 'status_display', 'state_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        # Валидация на уровне сериализатора дублирует модель для API
        expense_type = attrs.get('type')
        unit = attrs.get('unit')
        price_per_unit = attrs.get('price_per_unit')

        if expense_type == Expense.ExpenseType.PHYSICAL:
            if not unit:
                raise serializers.ValidationError({
                    "unit": "Физическому расходу нужна единица измерения"
                })
            if price_per_unit is None:
                raise serializers.ValidationError({
                    "price_per_unit": "Физическому расходу нужна цена за единицу"
                })
        elif expense_type == Expense.ExpenseType.OVERHEAD:
            if unit or price_per_unit is not None:
                raise serializers.ValidationError(
                    "Накладным расходам не нужны unit/price_per_unit"
                )

        return attrs

    def create(self, validated_data):
        try:
            return Expense.objects.create(**validated_data)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict or str(e))

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        try:
            instance.save()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict or str(e))
        return instance


class ProductExpenseSerializer(serializers.ModelSerializer):
    """Сериализатор связи товар-расход"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    expense_name = serializers.CharField(source='expense.name', read_only=True)
    expense_type = serializers.CharField(source='expense.type', read_only=True)
    expense_unit = serializers.CharField(source='expense.unit', read_only=True)

    class Meta:
        model = ProductExpense
        fields = [
            'id', 'product', 'expense', 'ratio_per_product_unit', 'is_active',
            'product_name', 'expense_name', 'expense_type', 'expense_unit',
            'created_at'
        ]
        read_only_fields = ['created_at']

    def validate(self, attrs):
        expense = attrs.get('expense')
        if expense and not expense.is_active:
            raise serializers.ValidationError({
                "expense": "Нельзя привязывать неактивный расход"
            })
        return attrs


class DailyExpenseLogSerializer(serializers.ModelSerializer):
    """Сериализатор дневных расходов"""

    expense_name = serializers.CharField(source='expense.name', read_only=True)
    expense_type = serializers.CharField(source='expense.type', read_only=True)
    expense_unit = serializers.CharField(source='expense.unit', read_only=True)

    class Meta:
        model = DailyExpenseLog
        fields = [
            'id', 'expense', 'date', 'quantity_used', 'actual_price_per_unit',
            'daily_amount', 'total_cost', 'notes',
            'expense_name', 'expense_type', 'expense_unit',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['total_cost', 'created_at', 'updated_at']

    def validate(self, attrs):
        expense = attrs.get('expense') or getattr(self.instance, 'expense', None)

        if not expense:
            raise serializers.ValidationError({"expense": "Нужно указать расход"})

        if expense.type == Expense.ExpenseType.PHYSICAL:
            if attrs.get('quantity_used') is None:
                raise serializers.ValidationError({
                    "quantity_used": "Для физического расхода нужно количество"
                })
            if attrs.get('actual_price_per_unit') is None:
                raise serializers.ValidationError({
                    "actual_price_per_unit": "Для физического расхода нужна цена"
                })
            if attrs.get('daily_amount') is not None:
                raise serializers.ValidationError({
                    "daily_amount": "Для физического расхода не нужна daily_amount"
                })
        else:  # OVERHEAD
            if attrs.get('daily_amount') is None:
                raise serializers.ValidationError({
                    "daily_amount": "Для накладного расхода нужна сумма за день"
                })
            if attrs.get('quantity_used') or attrs.get('actual_price_per_unit'):
                raise serializers.ValidationError(
                    "Для накладного расхода не нужны quantity/price"
                )

        return attrs


class ProductionBatchSerializer(serializers.ModelSerializer):
    """Сериализатор производственной смены"""

    product_name = serializers.CharField(source='product.name', read_only=True)
    product_type = serializers.CharField(source='product.category_type', read_only=True)
    profit_margin = serializers.SerializerMethodField()

    class Meta:
        model = ProductionBatch
        fields = [
            'id', 'date', 'product', 'produced_quantity', 'suzerain_input_amount',
            'physical_cost', 'overhead_cost', 'total_cost', 'cost_per_unit',
            'revenue', 'net_profit', 'cost_breakdown',
            'product_name', 'product_type', 'profit_margin',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'physical_cost', 'overhead_cost', 'total_cost', 'cost_per_unit',
            'net_profit', 'cost_breakdown', 'created_at', 'updated_at'
        ]

    def get_profit_margin(self, obj):
        """Рентабельность в процентах"""
        if obj.revenue > 0:
            return round(float(obj.net_profit / obj.revenue * 100), 2)
        return 0


class MonthlyOverheadBudgetSerializer(serializers.ModelSerializer):
    """Сериализатор месячного бюджета накладных"""

    expense_name = serializers.CharField(source='expense.name', read_only=True)
    daily_average = serializers.SerializerMethodField()
    execution_percent = serializers.SerializerMethodField()

    class Meta:
        model = MonthlyOverheadBudget
        fields = [
            'id', 'year', 'month', 'expense', 'planned_amount', 'actual_amount',
            'expense_name', 'daily_average', 'execution_percent',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['actual_amount', 'created_at', 'updated_at']

    def get_daily_average(self, obj):
        """Средняя сумма в день"""
        return round(float(obj.planned_amount / 30), 2)

    def get_execution_percent(self, obj):
        """Процент исполнения бюджета"""
        if obj.planned_amount > 0:
            return round(float(obj.actual_amount / obj.planned_amount * 100), 2)
        return 0

    def validate(self, attrs):
        expense = attrs.get('expense')
        if expense and expense.type != Expense.ExpenseType.OVERHEAD:
            raise serializers.ValidationError({
                "expense": "Можно добавлять только накладные расходы"
            })
        return attrs


# ---------- Сериализаторы для API расчетов ----------

class CostCalculationRequestSerializer(serializers.Serializer):
    """Запрос на расчет себестоимости"""

    date = serializers.DateField(required=False)
    production_data = serializers.DictField(
        child=serializers.DictField(),
        help_text="Данные производства: {product_id: {'quantity': ..., 'suzerain_input': ...}}"
    )

    def validate_date(self, value):
        if value is None:
            return date.today()
        return value

    def validate_production_data(self, value):
        """Валидация данных производства"""
        if not value:
            raise serializers.ValidationError("Нужны данные производства")

        for product_id, prod_data in value.items():
            try:
                int(product_id)
            except (ValueError, TypeError):
                raise serializers.ValidationError(f"Некорректный product_id: {product_id}")

            if not isinstance(prod_data, dict):
                raise serializers.ValidationError(f"prod_data должен быть объектом для product_id {product_id}")

            quantity = prod_data.get('quantity')
            suzerain_input = prod_data.get('suzerain_input')

            if quantity is None and suzerain_input is None:
                raise serializers.ValidationError(
                    f"Для product_id {product_id} нужно quantity или suzerain_input"
                )

            if quantity is not None:
                try:
                    Decimal(str(quantity))
                except:
                    raise serializers.ValidationError(
                        f"Некорректное quantity для product_id {product_id}"
                    )

            if suzerain_input is not None:
                try:
                    Decimal(str(suzerain_input))
                except:
                    raise serializers.ValidationError(
                        f"Некорректное suzerain_input для product_id {product_id}"
                    )
        return value


class CostBreakdownSerializer(serializers.Serializer):
    """Детальная разбивка себестоимости"""

    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    date = serializers.DateField()
    produced_quantity = serializers.DecimalField(max_digits=12, decimal_places=3)

    physical_costs = serializers.ListField(
        child=serializers.DictField(),
        read_only=True
    )
    overhead_costs = serializers.ListField(
        child=serializers.DictField(),
        read_only=True
    )

    total_physical = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_overhead = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    cost_per_unit = serializers.DecimalField(max_digits=12, decimal_places=4)


class BulkDailyExpenseSerializer(serializers.Serializer):
    """Массовое обновление дневных расходов"""

    date = serializers.DateField()
    expenses = serializers.ListField(
        child=serializers.DictField(),
        help_text="Список расходов: [{'expense_id': .., 'quantity_used': .., 'actual_price_per_unit': ..}]"
    )

    def validate_expenses(self, value):
        """Валидация списка расходов"""
        if not value:
            raise serializers.ValidationError("Список расходов не может быть пустым")

        for i, expense_data in enumerate(value):
            expense_id = expense_data.get('expense_id')
            if not expense_id:
                raise serializers.ValidationError(f"Нужен expense_id для элемента {i}")

            try:
                expense = Expense.objects.get(id=expense_id, is_active=True)
            except Expense.DoesNotExist:
                raise serializers.ValidationError(f"Расход {expense_id} не найден")

            # Валидация в зависимости от типа расхода
            if expense.type == Expense.ExpenseType.PHYSICAL:
                if 'quantity_used' not in expense_data or 'actual_price_per_unit' not in expense_data:
                    raise serializers.ValidationError(
                        f"Для физического расхода {expense_id} нужны quantity_used и actual_price_per_unit"
                    )
            else:  # OVERHEAD
                if 'daily_amount' not in expense_data:
                    raise serializers.ValidationError(
                        f"Для накладного расхода {expense_id} нужна daily_amount"
                    )

        return value


class MonthlyOverheadBulkSerializer(serializers.Serializer):
    """Массовое создание месячного бюджета накладных"""

    year = serializers.IntegerField()
    month = serializers.IntegerField(min_value=1, max_value=12)
    overheads = serializers.DictField(
        child=serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0),
        help_text="Накладные расходы: {expense_id: planned_amount, ...}"
    )

    def validate_overheads(self, value):
        """Валидация накладных расходов"""
        if not value:
            raise serializers.ValidationError("Список накладных не может быть пустым")

        for expense_id, amount in value.items():
            try:
                expense_id = int(expense_id)
                expense = Expense.objects.get(
                    id=expense_id,
                    type=Expense.ExpenseType.OVERHEAD,
                    is_active=True
                )
            except (ValueError, Expense.DoesNotExist):
                raise serializers.ValidationError(f"Накладной расход {expense_id} не найден")

        return value


# ---------- Вспомогательные сериализаторы ----------

class ExpenseShortSerializer(serializers.ModelSerializer):
    """Краткая информация о расходе"""

    class Meta:
        model = Expense
        fields = ['id', 'name', 'type', 'status', 'unit', 'is_active']


class ProductCostSummarySerializer(serializers.Serializer):
    """Сводка по себестоимости товара"""

    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    cost_per_unit = serializers.DecimalField(max_digits=12, decimal_places=4)
    last_calculation_date = serializers.DateField()

    # Средние показатели за период
    avg_physical_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    avg_overhead_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    avg_total_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    avg_profit_margin = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)


class DailyCostSummarySerializer(serializers.Serializer):
    """Общая сводка по всем товарам за день"""

    date = serializers.DateField()
    total_production_units = serializers.DecimalField(max_digits=12, decimal_places=3)
    total_costs = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_profit = serializers.DecimalField(max_digits=12, decimal_places=2)

    products = serializers.ListField(
        child=serializers.DictField(),
        help_text="Детали по каждому товару"
    )


class ExpensePriceUpdateSerializer(serializers.Serializer):
    """Обновление цены расхода"""

    expense_id = serializers.IntegerField()
    new_price = serializers.DecimalField(
        max_digits=12, decimal_places=2,
        min_value=Decimal('0.01')
    )
    effective_date = serializers.DateField(required=False)

    def validate_expense_id(self, value):
        try:
            expense = Expense.objects.get(
                id=value,
                type=Expense.ExpenseType.PHYSICAL,
                is_active=True
            )
        except Expense.DoesNotExist:
            raise serializers.ValidationError("Физический расход не найден")
        return value

    def validate_effective_date(self, value):
        if value is None:
            return date.today()
        return value


class SuzerainProductSetupSerializer(serializers.Serializer):
    """Настройка товара с расходом-Сюзереном"""

    product_id = serializers.IntegerField()
    suzerain_expense_id = serializers.IntegerField()
    ratio_per_unit = serializers.DecimalField(
        max_digits=14, decimal_places=6,
        min_value=Decimal('0.000001'),
        help_text="Единиц Сюзерена на 1 единицу товара"
    )

    def validate(self, attrs):
        product_id = attrs['product_id']
        suzerain_expense_id = attrs['suzerain_expense_id']

        # Проверка товара
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError({"product_id": "Товар не найден"})

        # Проверка расхода-Сюзерена
        try:
            expense = Expense.objects.get(
                id=suzerain_expense_id,
                type=Expense.ExpenseType.PHYSICAL,
                status=Expense.ExpenseStatus.SUZERAIN,
                is_active=True
            )
        except Expense.DoesNotExist:
            raise serializers.ValidationError({
                "suzerain_expense_id": "Расход-Сюзерен не найден"
            })

        # Проверка, что уже нет другого Сюзерена у этого товара
        existing_suzerain = ProductExpense.objects.filter(
            product=product,
            expense__status=Expense.ExpenseStatus.SUZERAIN,
            is_active=True
        ).exclude(expense_id=suzerain_expense_id).first()

        if existing_suzerain:
            raise serializers.ValidationError({
                "product_id": f"У товара уже есть Сюзерен: {existing_suzerain.expense.name}"
            })

        attrs['product'] = product
        attrs['expense'] = expense
        return attrs