from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from .models import GeoPing, GeoDevice
from .serializers import GeoPingCreateSerializer, GeoDeviceSerializer
from users.permissions import IsAdminUser, IsPartnerUser  # твои классы
from datetime import date, timedelta
from django.utils.dateparse import parse_date
from calendar import monthrange

class IsAdminOrPartner(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and (
            IsAdminUser().has_permission(request, view) or
            IsPartnerUser().has_permission(request, view)
        )

def _period_range(anchor: date, period: str):
    if period == "day":
        start = anchor
        end = anchor
    elif period == "week":
        # неделя: пн-вс
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
    elif period == "month":
        start = anchor.replace(day=1)
        end = start.replace(day=monthrange(start.year, start.month)[1])
    elif period == "halfyear":
        # 1 полугодие: Jan–Jun, 2 полугодие: Jul–Dec
        if anchor.month <= 6:
            start = date(anchor.year, 1, 1)
            end = date(anchor.year, 6, 30)
        else:
            start = date(anchor.year, 7, 1)
            end = date(anchor.year, 12, 31)
    elif period == "year":
        start = date(anchor.year, 1, 1)
        end = date(anchor.year, 12, 31)
    else:
        return None, None
    # вернём как datetime границы включительно
    return (start, end)


class GeoPingViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet,mixins.RetrieveModelMixin,):
    """
    POST /api/geo/pings/        — партнёр шлёт точку
    GET  /api/geo/pings/?date=YYYY-MM-DD
    GET  /api/geo/pings/?user_id=...&start=ISO&end=ISO  — только админ
    """
    queryset = GeoPing.objects.all().select_related("device", "user")
    serializer_class = GeoPingCreateSerializer
    permission_classes = [IsAdminOrPartner]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        p = self.request.query_params

        # доступ: партнёр — только себя; админ — по user_id (если задан)
        if u.role == "admin":
            user_id = p.get("user_id")
            if user_id:
                qs = qs.filter(user_id=user_id)
        else:
            qs = qs.filter(user=u)

        # фильтрация по календарному периоду
        period = p.get("period")  # day|week|month|halfyear|year
        anchor_str = p.get("anchor")
        if period and anchor_str:
            anchor = parse_date(anchor_str)
            if anchor:
                start_d, end_d = _period_range(anchor, period)
                if start_d and end_d:
                    qs = qs.filter(recorded_at__date__gte=start_d,
                                   recorded_at__date__lte=end_d)
                    return qs.order_by("recorded_at")

        # fallback: date | start/end как было
        date_str = p.get("date")
        start = p.get("start")
        end = p.get("end")
        if date_str:
            d = parse_date(date_str)
            if d:
                qs = qs.filter(recorded_at__date=d)
        else:
            if start:
                qs = qs.filter(recorded_at__gte=start)
            if end:
                qs = qs.filter(recorded_at__lte=end)

        return qs.order_by("recorded_at")

class GeoDeviceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = GeoDevice.objects.all().select_related("user")
    serializer_class = GeoDeviceSerializer
    permission_classes = [IsAdminOrPartner]

    def get_queryset(self):
        u = self.request.user
        if u.role == "admin":
            return super().get_queryset()
        return super().get_queryset().filter(user=u)
