from celery import shared_task
from .services import ReportGeneratorService
from .models import Report
from django.core.files import File
from datetime import date, timedelta


@shared_task
def generate_reports(period='monthly'):
    today = date.today()
    if period == 'daily':
        date_from = date_to = today - timedelta(days=1)
    elif period == 'weekly':
        date_from = today - timedelta(days=7)
        date_to = today - timedelta(days=1)
    else:  # monthly
        date_from = today.replace(day=1)
        date_to = today

    types = ['sales', 'debts', 'costs', 'bonuses', 'brak', 'balance', 'orders', 'products', 'markup']
    for report_type in types:
        data_method = getattr(ReportGeneratorService, f'generate_{report_type}_report')
        data = data_method(date_from, date_to)
        report = Report.objects.create(
            type=report_type,
            date_from=date_from,
            date_to=date_to,
            data=data
        )
        pdf_file = ReportGeneratorService.export_to_pdf(report)
        report.pdf.save(f'report_{report.id}.pdf', File(pdf_file))