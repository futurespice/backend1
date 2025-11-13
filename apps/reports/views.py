from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
from django_filters.rest_framework import DjangoFilterBackend

from .models import Report
from .serializers import ReportSerializer
from .services import ReportGeneratorService
from .filters import ReportFilter

class ReportViewSet(viewsets.ModelViewSet):
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ReportFilter

    def get_queryset(self):
        user = self.request.user
        queryset = Report.objects.all()
        if user.role == 'admin':
            return queryset
        elif user.role == 'partner':
            return queryset.filter(generated_by=user)  # Или по filter_partner
        elif user.role == 'store':
            return queryset.filter(data__store__selections__user=user)  # По магазину/городу
        return queryset.none()

    @action(detail=False, methods=['get'])
    def generate(self, request):
        report_type = request.query_params.get('type')
        if report_type not in [choice[0] for choice in Report.REPORT_TYPES]:  # Из ТЗ
            return Response({"error": "Неверный тип"}, status=400)

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        city = request.query_params.get('city')
        partner = request.user if request.user.role == 'partner' else request.query_params.get('partner')
        store = request.query_params.get('store')  # Для store роли взять из selection

        service_method = f"generate_{report_type}_report"
        data = getattr(ReportGeneratorService, service_method)(date_from, date_to, city, partner, store)

        pdf_buffer = ReportGeneratorService.export_to_pdf(data)

        report = Report.objects.create(
            type=report_type,
            generated_by=request.user,
            data=data,
            pdf_file=pdf_buffer  # Сохраните как файл
        )

        return Response(ReportSerializer(report).data)

    @action(detail=True, methods=['get'])
    def diagram(self, request, pk=None):
        report = self.get_object()
        return Response({
            'labels': report.data.get('shares', {}).get('labels', []),
            'values': report.data.get('shares', {}).get('values', []),
            'type': report.type
        })

    @action(detail=True, methods=['get'])
    def download_pdf(self, request, pk=None):
        report = self.get_object()
        if not report.pdf_file:
            return Response(status=404)
        return FileResponse(report.pdf_file.open(), as_attachment=True, filename=f"report_{report.id}.pdf")