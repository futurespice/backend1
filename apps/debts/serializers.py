from rest_framework import serializers
from decimal import Decimal
from .models import Debt, DebtPayment, DebtSummary
from drf_spectacular.utils import extend_schema_field

class DebtPaymentSerializer(serializers.ModelSerializer):
    """Сериализатор платежей по долгам"""

    class Meta:
        model = DebtPayment
        fields = [
            'id', 'debt', 'amount', 'payment_method',
            'created_at', 'processed_by', 'notes', 'transaction_id'
        ]
        read_only_fields = ['created_at', 'processed_by']


class DebtSerializer(serializers.ModelSerializer):
    """Сериализатор долгов"""

    store_name = serializers.CharField(source='store.store_name', read_only=True)
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    remaining_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    is_overdue = serializers.BooleanField(read_only=True)
    payments = DebtPaymentSerializer(many=True, read_only=True)
    payments_count = serializers.SerializerMethodField()

    class Meta:
        model = Debt
        fields = [
            'id', 'store', 'store_name', 'order', 'order_id',
            'amount', 'is_paid', 'paid_amount', 'remaining_amount',
            'created_at', 'due_date', 'paid_at', 'is_overdue',
            'description', 'notes', 'payments', 'payments_count'
        ]
        read_only_fields = ['created_at', 'paid_at', 'is_paid']

    @extend_schema_field({"type": "integer"})
    def get_payments_count(self, obj) -> int:
        """Количество платежей"""
        return obj.payments.count()


class DebtCreateSerializer(serializers.ModelSerializer):
    """Сериализатор создания долга"""

    class Meta:
        model = Debt
        fields = ['store', 'order', 'amount', 'due_date', 'description', 'notes']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Сумма долга должна быть положительной")
        return value


class DebtSummarySerializer(serializers.ModelSerializer):
    """Сериализатор сводки долгов"""

    store_name = serializers.CharField(source='store.store_name', read_only=True)
    store_owner = serializers.CharField(source='store.user.get_full_name', read_only=True)

    class Meta:
        model = DebtSummary
        fields = [
            'id', 'store', 'store_name', 'store_owner',
            'total_debt', 'overdue_debt',
            'active_debts_count', 'overdue_debts_count',
            'last_payment_date', 'updated_at'
        ]
        read_only_fields = ['updated_at']


class PaymentCreateSerializer(serializers.Serializer):
    """Сериализатор создания платежа"""

    debt_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    payment_method = serializers.ChoiceField(choices=DebtPayment.PAYMENT_METHODS)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    transaction_id = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_debt_id(self, value):
        try:
            debt = Debt.objects.get(id=value)
            if debt.is_paid:
                raise serializers.ValidationError("Долг уже погашен")
            return value
        except Debt.DoesNotExist:
            raise serializers.ValidationError("Долг не найден")

    def validate(self, data):
        try:
            debt = Debt.objects.get(id=data['debt_id'])
            if data['amount'] > debt.remaining_amount:
                raise serializers.ValidationError({
                    'amount': f'Сумма платежа не может превышать остаток долга ({debt.remaining_amount} сом)'
                })
        except Debt.DoesNotExist:
            pass

        return data

    def create(self, validated_data):
        debt = Debt.objects.get(id=validated_data['debt_id'])
        amount = validated_data['amount']
        payment_method = validated_data['payment_method']
        notes = validated_data.get('notes', '')

        # Создаём платёж
        payment = debt.make_payment(amount, payment_method, notes)

        # Устанавливаем дополнительные поля
        if validated_data.get('transaction_id'):
            payment.transaction_id = validated_data['transaction_id']
            payment.save()

        return payment


class DebtAnalyticsSerializer(serializers.Serializer):
    """Сериализатор аналитики долгов"""

    store_id = serializers.IntegerField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    include_paid = serializers.BooleanField(default=False)