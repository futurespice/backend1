# apps/messaging/permissions.py
from __future__ import annotations

from typing import Optional

from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import Chat, ChatMember, Message


# -----------------------------
#       helpers (role/membership)
# -----------------------------
def _user_role(user) -> Optional[str]:
    return getattr(user, "role", None)

def _is_global_admin(user) -> bool:
    return bool(user and user.is_authenticated and _user_role(user) == "admin")

def _is_member(user_id: int, chat_id: int) -> bool:
    return ChatMember.objects.filter(chat_id=chat_id, user_id=user_id).exists()

def _is_admin_in_chat(user_id: int, chat_id: int) -> bool:
    return ChatMember.objects.filter(
        chat_id=chat_id,
        user_id=user_id,
        role_in_chat__in=["owner", "admin"],
    ).exists()

# соответствие ролей типу чата (из ТЗ)
_ALLOWED_ROLES_BY_KIND = {
    Chat.Kind.ADMIN_PARTNER: {"admin", "partner"},
    Chat.Kind.PARTNER_STORE: {"partner", "store"},
    Chat.Kind.ADMIN_STORE:   {"admin", "store"},
}


# -----------------------------
#        base permissions
# -----------------------------
class IsChatParticipantOrGlobalAdmin(BasePermission):
    """
    Доступ к объектам чата: пропускаем глобального админа ИЛИ участника чата.
    Подходит для Chat / Message / Attachment.
    """

    def has_permission(self, request, view):
        if _is_global_admin(request.user):
            return True
        chat_id = view.kwargs.get("chat_pk") or view.kwargs.get("pk")
        if not chat_id:
            # список / создание — проверим дальше объектными пермишенами
            return True
        return _is_member(request.user.id, int(chat_id))

    def has_object_permission(self, request, view, obj):
        if _is_global_admin(request.user):
            return True
        chat_id = getattr(obj, "chat_id", None)
        if chat_id is None and hasattr(obj, "chat"):
            chat_id = getattr(obj.chat, "id", None)
        if chat_id is None and isinstance(obj, Message):
            chat_id = obj.chat_id
        if chat_id is None:
            return True
        return _is_member(request.user.id, int(chat_id))


class KindRoleGuard(BasePermission):
    """
    Страховка: роль пользователя должна соответствовать типу чата (Chat.kind).
    - Для POST создания чата проверяем request.data['kind'].
    - Для операций над объектом проверяем obj.chat.kind / obj.kind.
    Глобальный админ проходит всегда.
    """

    def has_permission(self, request, view):
        if _is_global_admin(request.user):
            return True
        # проверим только создание, где 'kind' приходит в теле
        if request.method in ("POST", "PUT", "PATCH"):
            kind = (request.data or {}).get("kind")
            if not kind:
                return True  # не мы контролируем
            allowed = _ALLOWED_ROLES_BY_KIND.get(kind)
            if not allowed:
                return False
            return _user_role(request.user) in allowed
        return True

    def has_object_permission(self, request, view, obj):
        if _is_global_admin(request.user):
            return True
        # достанем kind из объекта (Chat или Message → Chat)
        if isinstance(obj, Chat):
            kind = obj.kind
        elif isinstance(obj, Message):
            kind = obj.chat.kind
        else:
            kind = getattr(getattr(obj, "chat", None), "kind", None)
        if not kind:
            return True
        allowed = _ALLOWED_ROLES_BY_KIND.get(kind)
        if not allowed:
            return False
        return _user_role(request.user) in allowed


class CanEditOrDeleteMessage(BasePermission):
    """
    Редактировать сообщение может только автор (PATCH/PUT).
    Удалять:
      - scope=me      → любой участник чата;
      - scope=everyone→ автор, админ чата, ИЛИ глобальный админ.
    """

    def has_object_permission(self, request, view, obj):
        if not isinstance(obj, Message):
            return True

        user = request.user
        user_id = user.id

        # глобальный админ — всегда можно удалять/редактировать
        if _is_global_admin(user):
            return True

        # только участник чата в принципе
        if not _is_member(user_id, obj.chat_id):
            return False

        if request.method in SAFE_METHODS:
            return True

        if request.method in ("PUT", "PATCH"):
            # редактировать — только автор
            return obj.sender_id == user_id

        if request.method == "DELETE":
            scope = (request.query_params.get("scope") or "everyone").lower()
            if scope == "me":
                return True
            # everyone → автор или админ чата
            return (obj.sender_id == user_id) or _is_admin_in_chat(user_id, obj.chat_id)

        return False
