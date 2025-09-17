from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import date

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import (
    Report,
    SalesReport, InventoryReport, DebtReport,
    BonusReport, BonusReportMonthly, CostReport
)
from .waste_models import WasteLog, WasteReport
from . import services


# ====== Базовые сериалайзеры витрин ======

class SalesReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesReport
        fields = (
            "id", "date", "partner", "store", "product",
            "orders_count", "total_quantity",
            "total_revenue", "total_bonus_discount",
            "total_cost", "profit", "updated_at",
        )
        read_only_fields = fields


class InventoryReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryReport
        fields = (
            "id", "date", "store", "partner", "product",
            "opening_balance", "received_quantity", "sold_quantity", "closing_balance",
            "opening_value", "closing_value",
            "production_batch",
        )
        read_only_fields = fields


class DebtReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtReport
        fields = (
            "id", "date", "partner", "store",
            "opening_debt", "new_debt", "paid_debt", "closing_debt",
            "updated_at",
        )
        read_only_fields = fields


class BonusReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = BonusReport
        fields = (
            "id", "date", "partner", "store", "product",
            "sold_quantity", "bonus_quantity", "bonus_discount",
            "net_revenue", "bonus_rule_n", "production_batch",
            "updated_at",
        )
        read_only_fields = fields


class BonusReportMonthlySerializer(serializers.ModelSerializer):
    class Meta:
        model = BonusReportMonthly
        fields = (
            "id", "year", "month", "partner", "store",
            "total_bonus_discount", "total_bonus_items",
            "days_with_bonuses", "avg_daily_bonus_discount", "avg_daily_bonus_items",
            "meta", "updated_at",
        )
        read_only_fields = fields


class CostReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostReport
        fields = (
            "id", "date", "product", "production_batch",
            "materials_cost", "overhead_cost", "total_cost", "produced_quantity",
            "meta", "updated_at",
        )
        read_only_fields = fields


class WasteLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WasteLog
        fields = (
            "id", "date", "partner", "store", "product",
            "quantity", "amount", "reason", "notes",
            "created_by", "created_at",
        )
        read_only_fields = ("id", "created_by", "created_at")

    def create(self, validated_data: Dict[str, Any]) -> WasteLog:
        user = self.context.get("request").user if self.context.get("request") else None
        if user and not validated_data.get("created_by"):
            validated_data["created_by"] = user
        return super().create(validated_data)


class WasteReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = WasteReport
        fields = (
            "id", "date", "partner", "store", "product",
            "waste_quantity", "waste_amount",
            "updated_at",
        )
        read_only_fields = fields


# ====== Report (журнал) ======

class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = (
            "id", "name", "report_type", "period",
            "date_from", "date_to",
            "store", "partner", "product",
            "data",
            "created_by", "created_at", "is_automated", "updated_at",
        )
        read_only_fields = ("id", "data", "created_by", "created_at", "updated_at")


# ====== Генерация отчёта через services.generate_and_save_report ======

class GenerateReportSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    report_type = serializers.ChoiceField(choices=Report.REPORT_TYPES)
    period = serializers.ChoiceField(choices=Report.PERIODS)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    partner = serializers.PrimaryKeyRelatedField(queryset=Report._meta.get_field("partner").remote_field.model.objects.all(), required=False, allow_null=True)
    store = serializers.PrimaryKeyRelatedField(queryset=Report._meta.get_field("store").remote_field.model.objects.all(), required=False, allow_null=True)
    product = serializers.PrimaryKeyRelatedField(queryset=Report._meta.get_field("product").remote_field.model.objects.all(), required=False, allow_null=True)
    is_automated = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        d_from: date = attrs["date_from"]
        d_to: date = attrs["date_to"]
        period: str = attrs["period"]
        if d_from > d_to:
            raise serializers.ValidationError(_("date_from must be <= date_to"))
        if period == "custom" and (not d_from or not d_to):
            raise serializers.ValidationError(_("custom period requires both dates"))
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> Report:
        request = self.context.get("request")
        user_id: Optional[int] = request.user.id if request and request.user and request.user.is_authenticated else None

        report = services.generate_and_save_report(
            name=validated_data["name"],
            report_type=validated_data["report_type"],
            period=validated_data["period"],
            date_from=validated_data["date_from"],
            date_to=validated_data["date_to"],
            created_by_id=user_id,
            partner_id=validated_data.get("partner").id if validated_data.get("partner") else None,
            store_id=validated_data.get("store").id if validated_data.get("store") else None,
            product_id=validated_data.get("product").id if validated_data.get("product") else None,
            is_automated=validated_data.get("is_automated", False),
        )
        return report

    def to_representation(self, instance: Report) -> Dict[str, Any]:
        return ReportSerializer(instance).data
