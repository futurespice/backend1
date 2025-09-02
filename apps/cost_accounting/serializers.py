from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .models import (
    Expense,
    ProductExpense,
    MechanicalExpenseLog,
    CostSnapshot, BillOfMaterial, BOMLine,
)
from products.models import Product


# -------------------------
# Expense
# -------------------------

class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = [
            "id",
            "type",
            "name",
            "unit",
            "price_per_unit",
            "status",
            "state",
            "is_universal",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        t = attrs.get("type", getattr(self.instance, "type", None))
        unit = attrs.get("unit", getattr(self.instance, "unit", None))
        ppu = attrs.get("price_per_unit", getattr(self.instance, "price_per_unit", None))

        if t == Expense.ExpenseType.PHYSICAL:
            if not unit:
                raise serializers.ValidationError({"unit": "Для физического расхода требуется единица измерения (кг/шт)."})
            if ppu is None:
                raise serializers.ValidationError({"price_per_unit": "Для физического расхода требуется цена за единицу."})
        elif t == Expense.ExpenseType.OVERHEAD:
            # у накладных не должно быть unit/price_per_unit
            if unit or ppu is not None:
                raise serializers.ValidationError("У накладных расходов нельзя задавать unit/price_per_unit.")

        # автопереход статуса при механическом учёте (логика ТЗ)
        state = attrs.get("state", getattr(self.instance, "state", Expense.ExpenseState.AUTOMATIC))
        status = attrs.get("status", getattr(self.instance, "status", Expense.ExpenseStatus.COMMONER))
        if state == Expense.ExpenseState.MECHANICAL and status == Expense.ExpenseStatus.COMMONER:
            attrs["status"] = Expense.ExpenseStatus.VASSAL

        return attrs

    def create(self, validated_data):
        obj = Expense(**validated_data)
        # запустить model.clean, чтобы бизнес-валидация не разъезжалась
        try:
            obj.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict or e.messages)
        obj.save()
        return obj

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        try:
            instance.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict or e.messages)
        instance.save()
        return instance


# -------------------------
# ProductExpense (BOM link)
# -------------------------

class ProductExpenseSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source="product", write_only=True
    )
    expense_id = serializers.PrimaryKeyRelatedField(
        queryset=Expense.objects.all(), source="expense", write_only=True
    )

    product = serializers.StringRelatedField(read_only=True)
    expense = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = ProductExpense
        fields = [
            "id",
            "product_id",
            "expense_id",
            "product",
            "expense",
            "ratio_per_product_unit",
            "is_active",
        ]

    def validate(self, attrs):
        exp: Expense = attrs.get("expense") or getattr(self.instance, "expense", None)
        if exp and not exp.is_active:
            raise serializers.ValidationError("Нельзя привязывать неактивный расход.")
        return attrs


# -------------------------
# Mechanical logs
# -------------------------

class MechanicalExpenseLogSerializer(serializers.ModelSerializer):
    expense_id = serializers.PrimaryKeyRelatedField(
        queryset=Expense.objects.all(), source="expense", write_only=True
    )
    expense = serializers.StringRelatedField(read_only=True)
    date = serializers.DateField(required=False)

    class Meta:
        model = MechanicalExpenseLog
        fields = [
            "id",
            "expense_id",
            "expense",
            "date",
            "quantity",
            "amount",
            "note",
        ]

    def validate(self, attrs):
        exp: Expense = attrs.get("expense") or getattr(self.instance, "expense", None)
        if not exp:
            return attrs
        if exp.type == Expense.ExpenseType.OVERHEAD:
            # для накладных требуем сумму
            amount = attrs.get("amount", getattr(self.instance, "amount", Decimal("0")))
            if amount is None or amount <= 0:
                raise serializers.ValidationError({"amount": "Для накладного расхода требуется положительная сумма."})
        else:
            # для физического разрешаем quantity (сумму можно посчитать)
            qty = attrs.get("quantity", getattr(self.instance, "quantity", Decimal("0")))
            if qty is None or qty < 0:
                raise serializers.ValidationError({"quantity": "Количество не может быть отрицательным."})
        return attrs

    def create(self, validated_data):
        if "date" not in validated_data:
            validated_data["date"] = timezone.localdate()
        return super().create(validated_data)


# -------------------------
# CostSnapshot (read-only основное)
# -------------------------

class CostSnapshotSerializer(serializers.ModelSerializer):
    product = serializers.StringRelatedField()
    breakdown = serializers.JSONField()

    class Meta:
        model = CostSnapshot
        fields = [
            "id",
            "product",
            "date",
            "produced_qty",
            "suzerain_input_amount",
            "physical_cost",
            "overhead_cost",
            "total_cost",
            "cost_per_unit",
            "revenue",
            "net_profit",
            "breakdown",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields  # снапшот пишется калькулятором


# -----------------------------------------
# Запрос на пересчёт (service input)
# -----------------------------------------

class RecalculateRequestSerializer(serializers.Serializer):
    """
    Вход: один из сценариев
      - produced_qty
      - suzerain_input_amount
    Можно передать оба — приоритет у produced_qty.
    Для честного распределения накладных рекомендуется передавать production_totals_by_product
      {product_id: produced_qty, ...} по всем товарам за дату.
    """
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), source="product")
    date = serializers.DateField(required=False)
    produced_qty = serializers.DecimalField(max_digits=14, decimal_places=6, required=False)
    suzerain_input_amount = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=Decimal("0.00"))
    production_totals_by_product = serializers.DictField(
        child=serializers.DecimalField(max_digits=14, decimal_places=6),
        required=False,
        help_text="Карта выпуска за день по всем товарам для распределения накладных."
    )

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        produced = attrs.get("produced_qty")
        suz = attrs.get("suzerain_input_amount")

        if produced is None and (suz is None or suz == ""):
            raise serializers.ValidationError("Укажите produced_qty или suzerain_input_amount.")
        if produced is not None and produced < 0:
            raise serializers.ValidationError({"produced_qty": "Не может быть отрицательным."})
        if suz is not None and suz < 0:
            raise serializers.ValidationError({"suzerain_input_amount": "Не может быть отрицательным."})

        # нормализуем дату
        if "date" not in attrs or attrs["date"] is None:
            attrs["date"] = timezone.localdate()

        # привести ключи production_totals_by_product к int (они приходят строками из JSON)
        totals = attrs.get("production_totals_by_product")
        if totals:
            norm: Dict[int, Decimal] = {}
            for k, v in totals.items():
                try:
                    norm[int(k)] = Decimal(v)
                except Exception:
                    raise serializers.ValidationError({"production_totals_by_product": f"Некорректный ключ '{k}' или значение '{v}'."})
            attrs["production_totals_by_product"] = norm

        return attrs


# Удобный компактный сериализатор для списков расходов/привязок
class ExpenseShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ["id", "name", "type", "status", "state", "is_universal", "is_active"]


class BOMLineSerializer(serializers.ModelSerializer):
    """
    Одна строка состава: либо expense (сырьё), либо component_product (полуфабрикат).
    Ровно одно из полей должно быть заполнено.
    """
    expense_id = serializers.PrimaryKeyRelatedField(
        queryset=Expense.objects.all(),
        source="expense",
        required=False,
        allow_null=True,
        write_only=True,
    )
    component_product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source="component_product",
        required=False,
        allow_null=True,
        write_only=True,
    )

    # Read-only удобства
    expense = serializers.StringRelatedField(read_only=True)
    component_product = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = BOMLine
        fields = [
            "id",
            "expense_id",
            "component_product_id",
            "expense",
            "component_product",
            "quantity",
            "unit",
            "is_primary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        expense = attrs.get("expense", getattr(self.instance, "expense", None))
        comp    = attrs.get("component_product", getattr(self.instance, "component_product", None))
        qty     = attrs.get("quantity", getattr(self.instance, "quantity", None))
        unit    = attrs.get("unit", getattr(self.instance, "unit", None))

        # one-of
        if bool(expense) == bool(comp):
            raise serializers.ValidationError(
                {"expense_id": "Укажите либо expense, либо component_product.",
                 "component_product_id": "Укажите либо expense, либо component_product."}
            )

        # количество > 0
        if qty is None or qty <= 0:
            raise serializers.ValidationError({"quantity": "Количество должно быть > 0."})

        # единица измерения
        units = dict(BOMLine.Unit.choices)
        if unit not in units:
            raise serializers.ValidationError({"unit": f"Недопустимая единица. Разрешено: {', '.join(units.keys())}."})

        # запрет прямого самоссылания product == component_product
        bom = self.context.get("bom") or getattr(self.instance, "bom", None)
        if bom and comp and bom.product_id == getattr(comp, "id", None):
            raise serializers.ValidationError({"component_product_id": "Компонент-продукт совпадает с целевым продуктом BOM."})

        return attrs


class BillOfMaterialSerializer(serializers.ModelSerializer):
    """
    Полный BOM с линиями. Поддерживает idempotent обновление состава:
    - передаёшь список lines → мы синхронизируем (update/create/delete) под этот список
    - ровно один is_primary допускается (валидируется здесь)
    """
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source="product", write_only=True, required=False
    )
    product = serializers.StringRelatedField(read_only=True)

    lines = BOMLineSerializer(many=True)

    class Meta:
        model = BillOfMaterial
        fields = [
            "id",
            "product_id",
            "product",
            "version",
            "is_active",
            "created_at",
            "updated_at",
            "lines",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        lines = self.initial_data.get("lines", [])
        # единственный сюзерен
        primary_count = sum(1 for l in lines if l.get("is_primary"))
        if primary_count > 1:
            raise serializers.ValidationError({"lines": "В BOM может быть только один «сюзерен» (is_primary=true)."})
        return attrs

    def _upsert_lines(self, bom: BillOfMaterial, lines_payload: list[dict]) -> None:
        """
        Идемпотентная синхронизация строк:
        - если передан id → обновляем строку
        - без id → создаём
        - строки, не попавшие в payload → удаляем
        """
        existing = {l.id: l for l in bom.lines.all()}
        seen_ids: set[int] = set()

        for row in lines_payload:
            row_serializer = BOMLineSerializer(
                instance=existing.get(row.get("id")),
                data=row,
                context={"bom": bom},
                partial=False,
            )
            row_serializer.is_valid(raise_exception=True)
            line: BOMLine = row_serializer.save(bom=bom)
            if line.id:
                seen_ids.add(line.id)

        # удалить "лишние" строки
        to_delete = [obj_id for obj_id in existing.keys() if obj_id not in seen_ids]
        if to_delete:
            BOMLine.objects.filter(id__in=to_delete).delete()

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        # product может прийти только при create
        bom = BillOfMaterial.objects.create(**validated_data)
        # префетчим для консистентности валидаций
        bom.refresh_from_db()
        self._upsert_lines(bom, lines_data)
        return bom

    def update(self, instance: BillOfMaterial, validated_data):
        lines_data = validated_data.pop("lines", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        if lines_data is not None:
            # подгружаем связанные, чтобы валидации знали текущий product
            instance.refresh_from_db()
            instance.lines.all()  # prefetch cache fill
            self._upsert_lines(instance, lines_data)

        return instance


# -----------------------------------------
# Превью себестоимости по BOM (service input)
# -----------------------------------------

class BomCostPreviewRequestSerializer(serializers.Serializer):
    """
    Вход для эндпоинта превью расчёта себестоимости по BOM на дату.
    Пример тела:
      { "product_id": 123, "date": "2025-09-02" }
    """
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), source="product")
    date = serializers.DateField(required=False)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        if "date" not in attrs or attrs["date"] is None:
            attrs["date"] = timezone.localdate()
        return attrs