# apps/reports/tests.py

import json
from datetime import date

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from reports.models import Report, ReportType
from reports.serializers import ReportGenerateSerializer
from reports.services import ReportContext, ReportGeneratorService


@pytest.mark.django_db
def test_report_model_diagram_fallback():
    r = Report.objects.create(
        type=ReportType.SALES,
        date_from=date(2025, 1, 1),
        date_to=date(2025, 1, 31),
        data={},
    )
    assert r.diagram == {"labels": [], "values": []}


@pytest.mark.django_db
def test_report_generate_serializer_validation_ok():
    payload = {
        "type": ReportType.SALES,
        "date_from": "2025-01-01",
        "date_to": "2025-01-31",
    }
    s = ReportGenerateSerializer(data=payload)
    assert s.is_valid(), s.errors


@pytest.mark.django_db
def test_report_generate_serializer_invalid_range():
    payload = {
        "type": ReportType.SALES,
        "date_from": "2025-02-01",
        "date_to": "2025-01-31",
    }
    s = ReportGenerateSerializer(data=payload)
    assert not s.is_valid()
    assert "non_field_errors" in s.errors


@pytest.mark.django_db
def test_report_viewset_generate_smoke(user_factory):
    """
    Smoke-тест: endpoint /reports/generate/ создаёт Report.
    user_factory — обычная фикстура пользователя проекта.
    """
    user = user_factory()
    client = APIClient()
    client.force_authenticate(user=user)

    url = reverse("report-generate")
    payload = {
        "type": ReportType.SALES,
        "date_from": "2025-01-01",
        "date_to": "2025-01-31",
    }
    resp = client.post(url, payload, format="json")
    assert resp.status_code == 201
    assert Report.objects.count() == 1
    r = Report.objects.first()
    assert r.type == ReportType.SALES
    assert "summary" in r.data
    assert "diagram" in r.data
