from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    UserRegistrationView, CustomTokenObtainPairView, UserProfileView,
    UserListViewSet, PasswordResetRequestView, PasswordResetCodeView,
    PasswordResetConfirmView, logout_view
)

router = DefaultRouter()
router.register(r'users', UserListViewSet, basename='users')

app_name = 'users'

urlpatterns = [
    # Аутентификация
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('logout/', logout_view, name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    # Профиль пользователя
    path('profile/', UserProfileView.as_view(), name='profile'),

    # Сброс пароля
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset/verify/', PasswordResetCodeView.as_view(), name='password-reset-verify'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),

    # Управление пользователями (админ)
    path('', include(router.urls)),
]