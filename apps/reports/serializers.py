from rest_framework import serializers
from .models import Report
from stores.serializers import CitySerializer


class ReportSerializer(serializers.ModelSerializer):
    filter_city = CitySerializer(read_only=True)
    filter_partner_name = serializers.CharField(source='filter_partner.name', read_only=True)
    filter_store_name = serializers.CharField(source='filter_store.name', read_only=True)

    class Meta:
        model = Report
        fields = ['id', 'type', 'date_from', 'date_to', 'filter_city', 'filter_partner', 'filter_partner_name', 'filter_store', 'filter_store_name', 'data', 'pdf', 'generated_at']