# apps/messaging/permissions.py

from rest_framework import permissions

from .models import ChatThread


class IsThreadParticipant(permissions.BasePermission):
    """
    Доступ к чату только участникам,
    admin может видеть всё.
    """

    def has_object_permission(self, request, view, obj: ChatThread):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "role", None) == "admin" or user.is_superuser:
            return True
        return obj.participants.filter(id=user.id).exists()

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
