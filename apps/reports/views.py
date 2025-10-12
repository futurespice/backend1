from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Report
from .serializers import ReportSerializer
from .services import ReportGeneratorService
from users.permissions import IsAdminUser, IsPartnerUser, IsStoreUser
from stores.models import StoreSelection
from django.http import FileResponse
from datetime import date, timedelta
from .filters import ReportFilter
from users.models import User
from stores.models import City, Store
from django.db.models import Q


class ReportViewSet(viewsets.ModelViewSet):
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ReportFilter

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return Report.objects.all()
        elif user.role == 'partner':
            return Report.objects.filter(filter_partner=user)
        elif user.role == 'store':
            try:
                selection = StoreSelection.objects.get(user=user)
                return Report.objects.filter(Q(filter_store=selection.store) | Q(filter_city=selection.store.city))
            except StoreSelection.DoesNotExist:
                return Report.objects.none()
        return Report.objects.none()

    @action(detail=False, methods=['get'])
    def generate(self, request):
        report_type = request.query_params.get('type')
        date_from = request.query_params.get('date_from', date.today() - timedelta(days=30))
        date_to = request.query_params.get('date_to', date.today())
        city_id = request.query_params.get('city')
        partner_id = request.query_params.get('partner')
        store_id = request.query_params.get('store')
        city = City.objects.filter(id=city_id).first() if city_id else None
        partner = User.objects.filter(id=partner_id, role='partner').first() if partner_id else None
        store = Store.objects.filter(id=store_id).first() if store_id else None

        if report_type not in ['sales', 'debts', 'costs', 'bonuses', 'brak', 'balance', 'orders', 'products', 'markup']:
            return Response({'error': 'Неверный тип отчета'}, status=status.HTTP_400_BAD_REQUEST)

        data_method = getattr(ReportGeneratorService, f'generate_{report_type}_report')
        data = data_method(date_from, date_to, city=city, partner=partner, store=store)

        report = Report.objects.create(
            type=report_type,
            date_from=date_from,
            date_to=date_to,
            filter_city=city,
            filter_partner=partner,
            filter_store=store,
            data=data
        )
        pdf_file = ReportGeneratorService.export_to_pdf(report)
        report.pdf.save(f'report_{report.id}.pdf', pdf_file)
        return Response(ReportSerializer(report).data)

    @action(detail=True, methods=['get'])
    def diagram(self, request, pk=None):
        report = self.get_object()
        shares = report.data.get('shares', {})
        labels = list(shares.keys())
        values = list(shares.values())
        return Response({'labels': labels, 'values': values, 'type': report.type})

    @action(detail=True, methods=['get'])
    def download_pdf(self, request, pk=None):
        report = self.get_object()
        if not report.pdf:
            return Response({'error': 'PDF не найден'}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(report.pdf, as_attachment=True, filename=f'report_{report.id}.pdf')