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
                request.user.role == 'partner'
        )


class IsStoreUser(permissions.BasePermission):
    """
    Разрешение только для магазинов
    """

    def has_permission(self, request, view):
        return (
                request.user and
                request.user.is_authenticated and
                request.user.role == 'store'
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Разрешение для владельца объекта или администратора
    """

    def has_object_permission(self, request, view, obj):
        # Администраторы могут всё
        if request.user.role == 'admin':
            return True

        # Владелец может редактировать свой объект
        if hasattr(obj, 'user'):
            return obj.user == request.user

        return obj == request.user