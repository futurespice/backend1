# from django.contrib import admin
# from .models import ChatRoom, Message, MessageRead
#
# @admin.register(ChatRoom)
# class ChatRoomAdmin(admin.ModelAdmin):
#     list_display = ['name', 'room_type', 'is_active', 'created_at']
#     list_filter = ['room_type', 'is_active', 'created_at']
#     search_fields = ['name']
#     filter_horizontal = ['participants']
#
# @admin.register(Message)
# class MessageAdmin(admin.ModelAdmin):
#     list_display = ['chat_room', 'sender', 'message_type', 'created_at']  # Убрали is_read
#     list_filter = ['message_type', 'created_at']  # Убрали is_read
#     search_fields = ['content', 'sender__name']
#     readonly_fields = ['created_at', 'edited_at']
#
# @admin.register(MessageRead)
# class MessageReadAdmin(admin.ModelAdmin):
#     list_display = ['message', 'user', 'read_at']
#     list_filter = ['read_at']
#     readonly_fields = ['read_at']