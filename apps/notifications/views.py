# apps/notifications/views.py

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import (
    NotificationCreateSerializer,
    NotificationSerializer,
)
from .services import NotificationService


class NotificationViewSet(viewsets.ModelViewSet):
    """
    CRUD для уведомлений.

    Основной кейс:
    - пользователю: list / mark_read / mark_all_read
    - админ/сервисы используют NotificationService
    """

    queryset = Notification.objects.all().select_related("user")
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Пользователь видит только свои уведомления.
        Admin с ролью 'admin' видит все.
        """
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()

        role = getattr(user, "role", None)
        if role == "admin" or user.is_superuser:
            return qs
        return qs.filter(user=user)

    def get_serializer_class(self):
        if self.action == "create":
            return NotificationCreateSerializer
        return NotificationSerializer

    def perform_create(self, serializer):
        """
        Создание уведомлений из API — опционально.

        Можно ограничить только для админов, если нужно:
        """
        user = self.request.user
        # если хочется жёстко: if getattr(user, "role", None) != "admin": raise PermissionDenied
        serializer.save()

    @action(detail=True, methods=["post"], url_path="mark_read")
    def mark_read(self, request, pk=None):
        """
        POST /notifications/{id}/mark_read/

        Отметить одно уведомление прочитанным.
        """
        notification = self.get_object()
        if notification.user != request.user and not (
            getattr(request.user, "role", None) == "admin"
            or request.user.is_superuser
        ):
            return Response(
                {"detail": "Недостаточно прав"},
                status=status.HTTP_403_FORBIDDEN,
            )

        NotificationService.mark_as_read(notification)
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"], url_path="mark_all_read")
    def mark_all_read(self, request):
        """
        POST /notifications/mark_all_read/

        Отметить ВСЕ уведомления пользователя прочитанными.
        """
        count = NotificationService.mark_all_as_read(request.user)
        return Response({"updated": count})
