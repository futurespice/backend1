from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from .models import Chat, ChatMember, Message, MessageAttachment, MessageReceipt, HiddenMessage
from .serializers import ChatSerializer, MessageSerializer, MessageCreateSerializer
from .permissions import (
    IsChatParticipantOrGlobalAdmin,
    KindRoleGuard,
    CanEditOrDeleteMessage,
    _ALLOWED_ROLES_BY_KIND
)

class ChatViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Список/детали чатов текущего пользователя.
    Фильтры из ТЗ: ?kind=admin_partner|partner_store|admin_store, ?city=, ?region=
    """
    serializer_class = ChatSerializer
    permission_classes = [IsChatParticipantOrGlobalAdmin, KindRoleGuard]

    def get_queryset(self):
        user = self.request.user
        qs = (
            Chat.objects.filter(members__user=user)
            .distinct()
            .select_related()
            .prefetch_related("messages")
            .order_by("-updated_at")
        )
        kind = self.request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)

        city = self.request.query_params.get("city")
        if city:
            qs = qs.filter(metadata__city__iexact=city)

        region = self.request.query_params.get("region")
        if region:
            qs = qs.filter(metadata__region__iexact=region)

        return qs


class MessageViewSet(mixins.ListModelMixin,
                     mixins.CreateModelMixin,
                     viewsets.GenericViewSet):
    """
    Лента сообщений чата и отправка новых.
    Роут nested: /api/chats/<chat_pk>/messages/
    """
    serializer_class = MessageSerializer
    permission_classes = [IsChatParticipantOrGlobalAdmin, KindRoleGuard]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        chat_id = self.kwargs["chat_pk"]
        user = self.request.user
        qs = (
            Message.objects.filter(chat_id=chat_id)
            .exclude(hidden_for__user=user)
            .select_related("sender", "reply_to")
            .prefetch_related("attachments")
            .order_by("-created_at")
        )
        before = self.request.query_params.get("before")
        after = self.request.query_params.get("after")
        if before:
            qs = qs.filter(id__lt=before)
        if after:
            qs = qs.filter(id__gt=after)
        return qs

    def create(self, request, *args, **kwargs):
        chat_id = kwargs["chat_pk"]
        s = MessageCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        # 1) проверка соответствия роли типу чата
        chat = get_object_or_404(Chat, pk=chat_id)
        allowed = _ALLOWED_ROLES_BY_KIND.get(chat.kind, set())
        user_role = getattr(request.user, "role", None)
        if user_role not in allowed:
            return Response({"detail": "Forbidden by chat kind/role"}, status=status.HTTP_403_FORBIDDEN)

        client_msg_id = data.get("client_msg_id", "") or ""

        # 2) дедупликация по (chat, client_msg_id)
        if client_msg_id:
            existing = Message.objects.filter(chat=chat, client_msg_id=client_msg_id).first()
            if existing:
                return Response(
                    MessageSerializer(existing, context={"request": request}).data,
                    status=status.HTTP_200_OK
                )

        with transaction.atomic():
            msg = Message.objects.create(
                chat=chat,
                sender=request.user,
                type=Message.Type.TEXT if not data.get("files") else Message.Type.FILE,
                text=data.get("text", "")[:4000],
                reply_to_id=data.get("reply_to"),
                client_msg_id=client_msg_id,
            )
            for f in data.get("files", []):
                MessageAttachment.objects.create(
                    message=msg,
                    file=f,
                    mime=getattr(f, "content_type", ""),
                    size=getattr(f, "size", 0) or 0,
                )

            # авто-квитанция для автора
            MessageReceipt.objects.update_or_create(
                message=msg,
                user=request.user,
                defaults={"status": MessageReceipt.Status.READ},
            )

            # last_read для участника
            ChatMember.objects.filter(chat=chat, user=request.user) \
                .update(last_read_message=msg)

            # обновим updated_at у чата
            Chat.objects.filter(id=chat.id).update(updated_at=msg.created_at)

        return Response(
            MessageSerializer(msg, context={"request": request}).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def read(self, request, chat_pk=None, pk=None):
        """
        Пометить одно сообщение прочитанным и сдвинуть last_read_message.
        """
        message = get_object_or_404(Message, pk=pk, chat_id=chat_pk)
        MessageReceipt.objects.update_or_create(
            message=message,
            user=request.user,
            defaults={"status": MessageReceipt.Status.READ},
        )
        ChatMember.objects.filter(chat_id=chat_pk, user=request.user)\
            .update(last_read_message=message)
        return Response({"ok": True})

    @action(detail=False, methods=["post"])
    def read_bulk(self, request, chat_pk=None):
        """
        Принять список message_ids и отметить их прочитанными.
        Тело: {"ids":[1,2,3]}
        """
        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "ids required"}, status=400)
        qs = Message.objects.filter(chat_id=chat_pk, id__in=ids)
        for m in qs:
            MessageReceipt.objects.update_or_create(
                message=m, user=request.user,
                defaults={"status": MessageReceipt.Status.READ},
            )
        # сдвигаем last_read до максимального из переданных
        last = qs.order_by("-id").first()
        if last:
            ChatMember.objects.filter(chat_id=chat_pk, user=request.user)\
                .update(last_read_message=last)
        return Response({"ok": True})

    @action(detail=True, methods=["delete"])
    def delete_for_me(self, request, chat_pk=None, pk=None):
        """Удаление сообщения 'у себя'."""
        message = get_object_or_404(Message, pk=pk, chat_id=chat_pk)
        HiddenMessage.objects.get_or_create(message=message, user=request.user)
        return Response(status=204)


class MessageModerationViewSet(mixins.UpdateModelMixin,
                               mixins.DestroyModelMixin,
                               viewsets.GenericViewSet):
    """
    Редактирование и удаление сообщений по правам.
    Роут: /api/messages/<id>/?scope=me|everyone
    """
    queryset = Message.objects.all().select_related("chat", "sender")
    serializer_class = MessageSerializer
    permission_classes = [IsChatParticipantOrGlobalAdmin, KindRoleGuard, CanEditOrDeleteMessage]

    def destroy(self, request, *args, **kwargs):
        msg = self.get_object()
        scope = (request.query_params.get("scope") or "everyone").lower()
        if scope == "me":
            HiddenMessage.objects.get_or_create(message=msg, user=request.user)
            return Response(status=204)

        # everyone — автор, админ чата или глобальный админ (проверено в пермишене)
        msg.is_deleted_for_everyone = True
        msg.deleted_by = request.user
        msg.save(update_fields=["is_deleted_for_everyone", "deleted_by"])
        return Response(status=204)

    def partial_update(self, request, *args, **kwargs):
        """Редактирование текста (только автор)."""
        msg = self.get_object()
        text = (request.data.get("text") or "")[:4000]
        msg.text = text
        msg.mark_edited()
        msg.save(update_fields=["text", "edited_at"])
        return Response(MessageSerializer(msg, context={"request": request}).data)
