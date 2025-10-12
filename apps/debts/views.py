# from rest_framework import viewsets, permissions, status, generics
# from rest_framework.response import Response
# from rest_framework.decorators import action
# from django_filters.rest_framework import DjangoFilterBackend
# from rest_framework import filters
# from django.db.models import Sum, Count, Q, Avg
# from datetime import datetime
#
# from .models import Debt, DebtPayment, DebtSummary
# from .serializers import (
#     DebtSerializer, DebtCreateSerializer, DebtPaymentSerializer,
#     DebtSummarySerializer, PaymentCreateSerializer, DebtAnalyticsSerializer
# )
# from users.permissions import IsAdminUser, IsPartnerUser
#
#
# class DebtViewSet(viewsets.ModelViewSet):
#     """ViewSet для долгов"""
#
#     queryset = Debt.objects.select_related('store', 'store__user', 'order')
#     permission_classes = [permissions.IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
#     filterset_fields = ['is_paid', 'store', 'order']
#     search_fields = ['description', 'notes', 'store__store_name']
#     ordering_fields = ['created_at', 'amount', 'due_date']
#     ordering = ['-created_at']
#
#     def get_serializer_class(self):
#         if self.action == 'create':
#             return DebtCreateSerializer
#         return DebtSerializer
#
#     def get_permissions(self):
#         if self.action in ['create', 'update', 'partial_update', 'destroy']:
#             return [IsAdminUser()]
#         return [permissions.IsAuthenticated()]
#
#     def get_queryset(self):
#         qs = super().get_queryset()
#         user = self.request.user
#
#         if user.role == 'store':
#             # Магазин видит только свои долги
#             qs = qs.filter(store__user=user)
#         elif user.role == 'partner':
#             # Партнёр видит долги своих магазинов
#             qs = qs.filter(store__partner=user)
#
#         return qs
#
#     @action(detail=False, methods=['get'])
#     def active(self, request):
#         """Активные долги"""
#         qs = self.get_queryset().filter(is_paid=False)
#
#         page = self.paginate_queryset(qs)
#         if page is not None:
#             serializer = self.get_serializer(page, many=True)
#             return self.get_paginated_response(serializer.data)
#
#         serializer = self.get_serializer(qs, many=True)
#         return Response(serializer.data)
#
#     @action(detail=False, methods=['get'])
#     def overdue(self, request):
#         """Просроченные долги"""
#         from django.utils import timezone
#
#         qs = self.get_queryset().filter(
#             is_paid=False,
#             due_date__lt=timezone.now().date()
#         )
#
#         page = self.paginate_queryset(qs)
#         if page is not None:
#             serializer = self.get_serializer(page, many=True)
#             return self.get_paginated_response(serializer.data)
#
#         serializer = self.get_serializer(qs, many=True)
#         return Response(serializer.data)
#
#     @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
#     def mark_paid(self, request, pk=None):
#         """Отметить долг как погашенный"""
#         debt = self.get_object()
#
#         if debt.is_paid:
#             return Response(
#                 {'error': 'Долг уже погашен'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#
#         remaining = debt.remaining_amount
#         notes = request.data.get('notes', 'Отмечен как погашенный через админку')
#
#         payment = debt.make_payment(remaining, 'other', notes)
#         payment.processed_by = request.user
#         payment.save()
#
#         serializer = self.get_serializer(debt)
#         return Response(serializer.data)
#
#
# class DebtPaymentViewSet(viewsets.ModelViewSet):
#     """ViewSet для платежей по долгам"""
#
#     queryset = DebtPayment.objects.select_related('debt', 'debt__store', 'processed_by')
#     serializer_class = DebtPaymentSerializer
#     permission_classes = [permissions.IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
#     filterset_fields = ['debt', 'payment_method', 'processed_by']
#     search_fields = ['notes', 'transaction_id', 'debt__description']
#     ordering_fields = ['created_at', 'amount']
#     ordering = ['-created_at']
#
#     def get_permissions(self):
#         if self.action in ['create', 'update', 'partial_update', 'destroy']:
#             return [IsAdminUser()]
#         return [permissions.IsAuthenticated()]
#
#     def get_queryset(self):
#         qs = super().get_queryset()
#         user = self.request.user
#
#         if user.role == 'store':
#             qs = qs.filter(debt__store__user=user)
#         elif user.role == 'partner':
#             qs = qs.filter(debt__store__partner=user)
#
#         return qs
#
#     def perform_create(self, serializer):
#         serializer.save(processed_by=self.request.user)
#
#
# class DebtSummaryViewSet(viewsets.ReadOnlyModelViewSet):
#     """ViewSet для сводок долгов (только чтение)"""
#
#     queryset = DebtSummary.objects.select_related('store', 'store__user')
#     serializer_class = DebtSummarySerializer
#     permission_classes = [permissions.IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
#     filterset_fields = ['store']
#     ordering_fields = ['total_debt', 'overdue_debt', 'last_payment_date']
#     ordering = ['-total_debt']
#
#     def get_queryset(self):
#         qs = super().get_queryset()
#         user = self.request.user
#
#         if user.role == 'store':
#             qs = qs.filter(store__user=user)
#         elif user.role == 'partner':
#             qs = qs.filter(store__partner=user)
#
#         return qs
#
#     @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
#     def recalculate_all(self, request):
#         """Пересчитать все сводки"""
#         count = 0
#         for summary in DebtSummary.objects.all():
#             summary.recalculate()
#             count += 1
#
#         return Response({
#             'message': f'Пересчитано {count} сводок'
#         })
#
#
# class PaymentCreateView(generics.CreateAPIView):
#     """Создание платежа по долгу"""
#
#     serializer_class = PaymentCreateSerializer
#     permission_classes = [IsAdminUser]
#
#     def create(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#
#         payment = serializer.save()
#         payment.processed_by = request.user
#         payment.save()
#
#         # Возвращаем данные платежа
#         response_serializer = DebtPaymentSerializer(payment)
#         return Response(response_serializer.data, status=status.HTTP_201_CREATED)
#
#
# class DebtAnalyticsView(generics.GenericAPIView):
#     """Аналитика по долгам"""
#
#     serializer_class = DebtAnalyticsSerializer
#     permission_classes = [permissions.IsAuthenticated]
#
#     def get(self, request):
#         """
#         Получить аналитику по долгам
#
#         Query params:
#         - store_id: ID магазина
#         - date_from: Дата начала (YYYY-MM-DD)
#         - date_to: Дата окончания (YYYY-MM-DD)
#         - include_paid: Включать погашенные долги (default: false)
#         """
#         serializer = self.get_serializer(data=request.query_params)
#         serializer.is_valid(raise_exception=True)
#
#         qs = Debt.objects.all()
#         user = request.user
#
#         # Фильтрация по правам доступа
#         if user.role == 'store':
#             qs = qs.filter(store__user=user)
#         elif user.role == 'partner':
#             qs = qs.filter(store__partner=user)
#
#         # Применяем фильтры
#         filters = serializer.validated_data
#
#         if filters.get('store_id'):
#             qs = qs.filter(store_id=filters['store_id'])
#
#         if filters.get('date_from'):
#             qs = qs.filter(created_at__date__gte=filters['date_from'])
#
#         if filters.get('date_to'):
#             qs = qs.filter(created_at__date__lte=filters['date_to'])
#
#         if not filters.get('include_paid', False):
#             qs = qs.filter(is_paid=False)
#
#         # Общая статистика
#         total_stats = qs.aggregate(
#             total_amount=Sum('amount'),
#             total_paid=Sum('paid_amount'),
#             total_remaining=Sum('amount') - Sum('paid_amount'),
#             total_count=Count('id'),
#             avg_debt=Avg('amount')
#         )
#
#         # Просроченные долги
#         from django.utils import timezone
#         overdue_stats = qs.filter(
#             is_paid=False,
#             due_date__lt=timezone.now().date()
#         ).aggregate(
#             overdue_amount=Sum('amount') - Sum('paid_amount'),
#             overdue_count=Count('id')
#         )
#
#         # Статистика по магазинам (для админов и партнёров)
#         store_stats = []
#         if user.role in ['admin', 'partner']:
#             store_stats = qs.values(
#                 'store__store_name', 'store_id'
#             ).annotate(
#                 total_debt=Sum('amount') - Sum('paid_amount'),
#                 debt_count=Count('id'),
#                 avg_debt=Avg('amount')
#             ).filter(total_debt__gt=0).order_by('-total_debt')[:10]
#
#         # Статистика платежей
#         payment_qs = DebtPayment.objects.filter(debt__in=qs)
#         if filters.get('date_from'):
#             payment_qs = payment_qs.filter(created_at__date__gte=filters['date_from'])
#         if filters.get('date_to'):
#             payment_qs = payment_qs.filter(created_at__date__lte=filters['date_to'])
#
#         payment_stats = payment_qs.aggregate(
#             total_payments=Sum('amount'),
#             payment_count=Count('id'),
#             avg_payment=Avg('amount')
#         )
#
#         return Response({
#             'total_stats': {
#                 'total_amount': total_stats['total_amount'] or 0,
#                 'total_paid': total_stats['total_paid'] or 0,
#                 'total_remaining': total_stats['total_remaining'] or 0,
#                 'total_count': total_stats['total_count'] or 0,
#                 'avg_debt': total_stats['avg_debt'] or 0
#             },
#             'overdue_stats': {
#                 'overdue_amount': overdue_stats['overdue_amount'] or 0,
#                 'overdue_count': overdue_stats['overdue_count'] or 0
#             },
#             'payment_stats': {
#                 'total_payments': payment_stats['total_payments'] or 0,
#                 'payment_count': payment_stats['payment_count'] or 0,
#                 'avg_payment': payment_stats['avg_payment'] or 0
#             },
#             'top_debtors': list(store_stats)
#         })