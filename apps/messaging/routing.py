from django.urls import re_path
from .consumers import ChatConsumer, MeConsumer

websocket_urlpatterns = [
    re_path(r"^ws/me/$", MeConsumer.as_asgi()),
    re_path(r"^ws/chats/(?P<chat_id>\d+)/$", ChatConsumer.as_asgi()),
]

__all__ = ["websocket_urlpatterns"]
