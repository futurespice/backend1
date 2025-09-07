# apps/messaging/consumers.py
from __future__ import annotations

from typing import Iterable, Optional

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from .models import (
    Chat,
    ChatMember,
    Message,
    MessageAttachment,
    MessageReceipt,
    HiddenMessage,
)

# -----------------------------
#            helpers
# -----------------------------
@database_sync_to_async
def _is_member(user_id: int, chat_id: int) -> bool:
    return ChatMember.objects.filter(chat_id=chat_id, user_id=user_id).exists()

@database_sync_to_async
def _is_admin_in_chat(user_id: int, chat_id: int) -> bool:
    return ChatMember.objects.filter(
        chat_id=chat_id,
        user_id=user_id,
        role_in_chat__in=["owner", "admin"],
    ).exists()

def _is_global_admin(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "role", None) == "admin")

@database_sync_to_async
def _serialize_message(msg: Message) -> dict:
    # Минимальный полезный слепок для фронта
    atts = list(
        msg.attachments.values("id", "mime", "size", "file", "image_w", "image_h")
    )
    return {
        "id": msg.id,
        "chat": msg.chat_id,
        "sender_id": msg.sender_id,
        "type": msg.type,
        "text": "" if msg.is_deleted_for_everyone else (msg.text or ""),
        "reply_to": ({"id": msg.reply_to_id, "sender_id": msg.reply_to.sender_id, "type": msg.reply_to.type,
                      "text": (msg.reply_to.text or "")[:120]} if msg.reply_to_id else None),
        "created_at": msg.created_at.isoformat(),
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
        "is_deleted_for_everyone": msg.is_deleted_for_everyone,
        "attachments": [] if msg.is_deleted_for_everyone else atts,
    }

@database_sync_to_async
def _create_text_message(chat_id: int, user_id: int, text: str, reply_to: Optional[int], client_msg_id: str) -> Message:
    # дедуп по (chat_id, client_msg_id)
    if client_msg_id:
        existing = Message.objects.filter(chat_id=chat_id, client_msg_id=client_msg_id).first()
        if existing:
            return existing

    msg = Message.objects.create(
        chat_id=chat_id,
        sender_id=user_id,
        type=Message.Type.TEXT,
        text=(text or "")[:4000],
        reply_to_id=reply_to,
        client_msg_id=client_msg_id or "",
    )
    # обновим время чата + квитанцию автора как READ
    Chat.objects.filter(pk=chat_id).update(updated_at=msg.created_at)
    MessageReceipt.objects.update_or_create(
        message=msg, user_id=user_id, defaults={"status": MessageReceipt.Status.READ}
    )
    # last_read автора — на это сообщение
    ChatMember.objects.filter(chat_id=chat_id, user_id=user_id).update(last_read_message=msg)
    return msg


@database_sync_to_async
def _edit_message_text(message_id: int, user_id: int, new_text: str) -> Optional[Message]:
    msg = Message.objects.select_related("chat").filter(pk=message_id).first()
    if not msg:
        return None
    if msg.sender_id != user_id:
        return None
    msg.text = (new_text or "")[:4000]
    msg.mark_edited()
    msg.save(update_fields=["text", "edited_at"])
    return msg

@database_sync_to_async
def _delete_message_scope_me(message_id: int, user_id: int) -> bool:
    msg = Message.objects.filter(pk=message_id).first()
    if not msg:
        return False
    HiddenMessage.objects.get_or_create(message=msg, user_id=user_id)
    return True

@database_sync_to_async
def _delete_message_scope_everyone(message_id: int, user_id: int, chat_id: int, global_admin: bool) -> Optional[Message]:
    msg = Message.objects.select_related("chat").filter(pk=message_id, chat_id=chat_id).first()
    if not msg:
        return None
    # автор, админ чата или глобальный админ
    is_chat_admin = ChatMember.objects.filter(
        chat_id=chat_id, user_id=user_id, role_in_chat__in=["owner", "admin"]
    ).exists()
    if msg.sender_id != user_id and not is_chat_admin and not global_admin:
        return None
    msg.is_deleted_for_everyone = True
    msg.deleted_by_id = user_id
    msg.save(update_fields=["is_deleted_for_everyone", "deleted_by"])
    return msg

@database_sync_to_async
def _mark_read(chat_id: int, user_id: int, message_ids: Iterable[int]) -> Optional[int]:
    """
    Отмечает сообщения как прочитанные, возвращает max(message_ids) если есть.
    """
    ids = list(message_ids or [])
    if not ids:
        return None
    qs = Message.objects.filter(chat_id=chat_id, id__in=ids).only("id")
    max_id = None
    for m in qs:
        MessageReceipt.objects.update_or_create(
            message=m, user_id=user_id, defaults={"status": MessageReceipt.Status.READ}
        )
        max_id = max(m.id, max_id or m.id)
    if max_id:
        # сдвинем last_read_message
        last = Message.objects.filter(chat_id=chat_id, id__lte=max_id).order_by("-id").first()
        if last:
            ChatMember.objects.filter(chat_id=chat_id, user_id=user_id).update(last_read_message=last)
    return max_id


# -----------------------------
#           Consumers
# -----------------------------
class MeConsumer(AsyncJsonWebsocketConsumer):
    """
    Персональная шина (на будущее) — сюда можно слать уведомления по всем чатам пользователя.
    """
    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4401); return
        self.user_id = user.id
        self.group = f"user_{self.user_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    WS по конкретному чату: события message.created/edited/deleted, receipt.updated, typing.
    """
    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4401); return
        self.user = user
        try:
            self.chat_id = int(self.scope["url_route"]["kwargs"]["chat_id"])
        except Exception:
            await self.close(code=4400); return

        if not await _is_member(self.user.id, self.chat_id):
            await self.close(code=4403); return

        self.group = f"chat_{self.chat_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    # -------- inbound actions from client --------
    async def receive_json(self, content, **kwargs):
        """
        Поддерживаемые действия:
        - {"action":"typing", "is_typing":true}
        - {"action":"send_message", "text":"...", "reply_to":123, "client_msg_id":"uuid"}
        - {"action":"edit_message", "message_id":1, "text":"..."}
        - {"action":"delete_message", "message_id":1, "scope":"me|everyone"}
        - {"action":"read", "ids":[1,2,3]}   # batch read
        - {"action":"ping"} → {"type":"pong"}
        """
        action = (content or {}).get("action")

        if action == "ping":
            await self.send_json({"type": "pong", "ts": timezone.now().isoformat()})
            return

        if action == "typing":
            await self._broadcast_typing(bool(content.get("is_typing", True)))
            return

        if action == "send_message":
            text = content.get("text", "")
            reply_to = content.get("reply_to")
            client_msg_id = content.get("client_msg_id", "")
            if not isinstance(text, str):
                await self._error("invalid_payload", "text must be string"); return
            msg = await _create_text_message(self.chat_id, self.user.id, text, reply_to, client_msg_id)
            payload = await _serialize_message(msg)
            await self.channel_layer.group_send(self.group, {"type": "message.created", "payload": payload})
            return

        if action == "edit_message":
            mid = content.get("message_id")
            new_text = content.get("text", "")
            if not isinstance(mid, int):
                await self._error("invalid_payload", "message_id must be int"); return
            msg = await _edit_message_text(mid, self.user.id, new_text)
            if not msg:
                await self._error("forbidden_or_not_found", "cannot edit message"); return
            payload = await _serialize_message(msg)
            await self.channel_layer.group_send(self.group, {"type": "message.edited", "payload": payload})
            return

        if action == "delete_message":
            mid = content.get("message_id")
            scope = (content.get("scope") or "everyone").lower()
            if not isinstance(mid, int):
                await self._error("invalid_payload", "message_id must be int"); return
            if scope == "me":
                ok = await _delete_message_scope_me(mid, self.user.id)
                if not ok:
                    await self._error("not_found", "message not found"); return
                # локально клиент сам скроет; рассылка группе не нужна
                await self.send_json({"type": "message.deleted", "message_id": mid, "scope": "me"})
                return
            # everyone
            msg = await _delete_message_scope_everyone(
                message_id=mid, user_id=self.user.id, chat_id=self.chat_id, global_admin=_is_global_admin(self.user)
            )
            if not msg:
                await self._error("forbidden_or_not_found", "cannot delete for everyone"); return
            await self.channel_layer.group_send(
                self.group, {"type": "message.deleted", "payload": {"message_id": mid, "scope": "everyone"}}
            )
            return

        if action == "read":
            ids = content.get("ids") or []
            if not isinstance(ids, list):
                await self._error("invalid_payload", "ids must be list[int]"); return
            max_id = await _mark_read(self.chat_id, self.user.id, ids)
            await self.channel_layer.group_send(
                self.group, {
                    "type": "receipt.updated",
                    "payload": {"user_id": self.user.id, "ids": ids, "max_id": max_id}
                }
            )
            return

        await self._error("unknown_action", f"Unsupported action: {action}")

    # -------- outbound events to clients --------
    async def message_created(self, event):
        await self.send_json({"type": "message.created", **event["payload"]})

    async def message_edited(self, event):
        await self.send_json({"type": "message.edited", **event["payload"]})

    async def message_deleted(self, event):
        await self.send_json({"type": "message.deleted", **event["payload"]})

    async def receipt_updated(self, event):
        await self.send_json({"type": "receipt.updated", **event["payload"]})

    async def typing_event(self, event):
        await self.send_json({"type": "typing", "user_id": event["user_id"], "is_typing": event["is_typing"], "ts": event["ts"]})

    # -------- internals --------
    async def _broadcast_typing(self, is_typing: bool):
        await self.channel_layer.group_send(
            self.group,
            {
                "type": "typing.event",
                "user_id": self.user.id,
                "is_typing": bool(is_typing),
                "ts": timezone.now().isoformat(),
            },
        )

    async def _error(self, code: str, detail: str):
        await self.send_json({"type": "error", "code": code, "detail": detail})
