# apps/users/permissions.py
from rest_framework.permissions import BasePermission, IsAuthenticated
from typing import Any

class IsAdminUser(BasePermission):
    def has_permission(self, request, view) -> bool:
        return request.user and request.user.is_authenticated and request.user.role == 'admin'

class IsPartnerUser(BasePermission):
    def has_permission(self, request, view) -> bool:
        return request.user and request.user.is_authenticated and request.user.role == 'partner'

class IsStoreUser(BasePermission):
    def has_permission(self, request, view) -> bool:
        return request.user and request.user.is_authenticated and request.user.role == 'store'

class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj) -> bool:
        if request.user.role == 'admin':
            return True
        # Check ownership based on model
        if hasattr(obj, 'partner') and obj.partner == request.user:
            return True
        if hasattr(obj, 'store') and obj.store.created_by == request.user:
            return True
        return False

class CanFulfillStoreOrder(BasePermission):
    def has_object_permission(self, request, view, obj) -> bool:
        return request.user == obj.partner and request.user.role == 'partner'

class CanApproveReturn(BasePermission):
    def has_object_permission(self, request, view, obj) -> bool:
        return request.user == obj.order.partner and request.user.role == 'partner'