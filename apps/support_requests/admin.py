from django.contrib import admin
from .models import SupportRequest, SupportResponse, SupportCategory

@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'subject', 'user', 'category', 'status', 'priority', 'created_at']
    list_filter = ['status', 'priority', 'category', 'created_at']
    search_fields = ['subject', 'description', 'user__name']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at', 'closed_at']

@admin.register(SupportResponse)
class SupportResponseAdmin(admin.ModelAdmin):
    list_display = ['request', 'author', 'is_internal', 'created_at']
    list_filter = ['is_internal', 'created_at']
    search_fields = ['message', 'request__subject']
    readonly_fields = ['created_at']

@admin.register(SupportCategory)
class SupportCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'sort_order']  # Убрали parent, ticket_count, order
    list_filter = ['is_active']
    search_fields = ['name', 'description']