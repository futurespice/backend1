from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User, PasswordResetRequest


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
    'id','email', 'full_name', 'role', 'is_approved', 'is_active', 'is_staff', 'created_at', 'avatar_preview')
    list_filter = ('role', 'is_approved', 'is_active', 'is_staff', 'created_at')
    search_fields = ('email', 'full_name', 'phone')
    ordering = ('-created_at',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Персональная информация', {'fields': ('full_name', 'phone', 'avatar')}),
        ('Роль и права', {'fields': ('role', 'is_approved', 'is_active', 'is_staff', 'is_superuser')}),
        ('Группы и права', {'fields': ('groups', 'user_permissions')}),
        ('Важные даты', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'phone', 'role', 'password1', 'password2', 'is_approved'),
        }),
    )

    readonly_fields = ('created_at', 'updated_at', 'last_login')

    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html('<img src="{}" width="50" height="50" style="border-radius: 50%;" />', obj.avatar.url)
        return "Нет фото"

    avatar_preview.short_description = "Аватар"

    actions = ['approve_users', 'reject_users', 'block_users', 'unblock_users']

    def approve_users(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} пользователей одобрено.')

    approve_users.short_description = "Одобрить выбранных пользователей"

    def reject_users(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f'{updated} пользователей отклонено.')

    reject_users.short_description = "Отклонить выбранных пользователей"

    def block_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} пользователей заблокировано.')

    block_users.short_description = "Заблокировать выбранных пользователей"

    def unblock_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} пользователей разблокировано.')

    unblock_users.short_description = "Разблокировать выбранных пользователей"


@admin.register(PasswordResetRequest)
class PasswordResetRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'is_used', 'created_at', 'expires_at')
    list_filter = ('is_used', 'created_at')
    search_fields = ('user__email', 'code')
    readonly_fields = ('user', 'code', 'created_at', 'expires_at')
    ordering = ('-created_at',)