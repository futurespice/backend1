from rest_framework import permissions


class IsAdminUser(permissions.BasePermission):
    """
    Разрешение только для администраторов
    """

    def has_permission(self, request, view):
        return (
                request.user and
                request.user.is_authenticated and
                request.user.role == 'admin'
        )


class IsPartnerUser(permissions.BasePermission):
    """
    Разрешение только для партнёров
    """

    def has_permission(self, request, view):
        return (
                request.user and
                request.user.is_authenticated and
                request.user.role == 'partner' and
                request.user.is_approved
        )


class IsStoreUser(permissions.BasePermission):
    """
    Разрешение только для магазинов
    """

    def has_permission(self, request, view):
        return (
                request.user and
                request.user.is_authenticated and
                request.user.role == 'store' and
                request.user.is_approved
        )


class IsPartnerOrStoreUser(permissions.BasePermission):
    """
    Разрешение для партнёров или магазинов
    """

    def has_permission(self, request, view):
        return (
                request.user and
                request.user.is_authenticated and
                request.user.role in ['partner', 'store'] and
                request.user.is_approved
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Разрешение для владельца объекта или администратора
    """

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True

        # Проверяем есть ли у объекта поле user или owner
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'owner'):
            return obj.owner == request.user

        return False


class IsApprovedUser(permissions.BasePermission):
    """
    Разрешение только для одобренных пользователей
    """

    def has_permission(self, request, view):
        return (
                request.user and
                request.user.is_authenticated and
                request.user.is_approved and
                request.user.is_active
        )