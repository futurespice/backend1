# apps/messaging/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ChatViewSet, MessageViewSet, MessageModerationViewSet

router = DefaultRouter()
router.register(r"chats", ChatViewSet, basename="chat")
router.register(r"messages", MessageModerationViewSet, basename="message")  # редакт/удаление по id

# ручные маршруты для nested: /chats/<chat_pk>/messages/...
# маппим методы viewset'а вручную
chat_messages_list = MessageViewSet.as_view({"get": "list", "post": "create"})
chat_message_read = MessageViewSet.as_view({"post": "read"})               # /.../messages/<pk>/read/
chat_messages_read_bulk = MessageViewSet.as_view({"post": "read_bulk"})    # /.../messages/read-bulk/
chat_message_delete_for_me = MessageViewSet.as_view({"delete": "delete_for_me"})  # /.../messages/<pk>/delete-for-me/

urlpatterns = [
    path("", include(router.urls)),

    # nested endpoints
    path("chats/<int:chat_pk>/messages/", chat_messages_list, name="chat-messages-list"),
    path("chats/<int:chat_pk>/messages/read-bulk/", chat_messages_read_bulk, name="chat-messages-read-bulk"),
    path("chats/<int:chat_pk>/messages/<int:pk>/read/", chat_message_read, name="chat-message-read"),
    path("chats/<int:chat_pk>/messages/<int:pk>/delete-for-me/", chat_message_delete_for_me, name="chat-message-delete-for-me"),
]
