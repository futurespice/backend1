from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """Разрешение только для администраторов"""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == 'admin'
        )


class IsPartnerUser(BasePermission):
    """Разрешение только для партнёров"""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == 'partner'
        )


class IsStoreUser(BasePermission):
    """Разрешение только для магазинов"""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == 'store'
        )


class IsPartnerOrAdmin(BasePermission):
    """Разрешение для партнёров и администраторов"""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ['partner', 'admin']
        )


class IsStoreOrPartner(BasePermission):
    """Разрешение для магазинов и партнёров"""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ['store', 'partner']
        )


class IsApprovedUser(BasePermission):
    """Разрешение только для одобренных пользователей"""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_approved
        )


class IsOwnerOrAdmin(BasePermission):
    """Разрешение для владельца объекта или администратора"""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated
        )

    def has_object_permission(self, request, view, obj):
        # Администраторы имеют доступ ко всему
        if request.user.role == 'admin':
            return True

        # Проверяем владельца в зависимости от типа объекта
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'store') and hasattr(obj.store, 'user'):
            return obj.store.user == request.user
        elif hasattr(obj, 'partner'):
            return obj.partner == request.user

        return False


class CanManageStore(BasePermission):
    """Разрешение на управление магазином"""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ['admin', 'partner', 'store']
        )

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True

        # Партнёр может управлять своими магазинами
        if request.user.role == 'partner':
            return obj.partner == request.user

        # Магазин может управлять только собой
        if request.user.role == 'store':
            return obj.user == request.user

        return False


class CanViewOrder(BasePermission):
    """Разрешение на просмотр заказа"""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated
        )

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True

        # Партнёр видит заказы своих магазинов
        if request.user.role == 'partner':
            return hasattr(obj, 'store') and obj.store.partner == request.user

        # Магазин видит только свои заказы
        if request.user.role == 'store':
            return hasattr(obj, 'store') and obj.store.user == request.user

        return False


class CanManageDebt(BasePermission):
    """Разрешение на управление долгами"""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ['admin', 'partner']
        )

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True

        # Партнёр может управлять долгами своих магазинов
        if request.user.role == 'partner':
            return obj.store.partner == request.user

        return False


class ReadOnlyOrAdmin(BasePermission):
    """Только чтение для обычных пользователей, полный доступ для админов"""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        # Админы имеют полный доступ
        if request.user.role == 'admin':
            return True

        # Остальные только читать
        return request.method in ['GET', 'HEAD', 'OPTIONS']