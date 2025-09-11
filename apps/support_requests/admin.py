from django.contrib import admin
from .models import SupportTicket, SupportMessage, FAQ, SupportCategory

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ['ticket_number', 'title', 'category', 'priority', 'status', 'requester', 'created_at']
    list_filter = ['category', 'priority', 'status', 'created_at']
    search_fields = ['ticket_number', 'title', 'requester__name']

@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'sender', 'message_type', 'is_internal', 'created_at']
    list_filter = ['message_type', 'is_internal', 'created_at']

@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ['question', 'category', 'view_count', 'helpful_count', 'is_published']
    list_filter = ['category', 'is_published']
    search_fields = ['question', 'answer']

@admin.register(SupportCategory)
class SupportCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'ticket_count', 'is_active', 'order']
    list_filter = ['is_active']