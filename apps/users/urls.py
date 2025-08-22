from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.routers import DefaultRouter
from . import views

# Создаем роутер для ViewSets
router = DefaultRouter()
router.register(r'admin/users', views.AdminUserViewSet, basename='admin-users')

urlpatterns = [
    # Регистрация
    path('register/', views.UserRegistrationView.as_view(), name='register'),

    # Аутентификация (JWT)
    path('token/', views.CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', views.logout_view, name='logout'),

    # Профиль
    path('me/', views.UserProfileView.as_view(), name='user_profile'),

    # Сброс пароля
    path('password-reset/', views.PasswordResetRequestView.as_view(), name='password_reset'),
    path('password-reset-confirm/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    # Подключаем роутер (админские API)
    path('', include(router.urls)),
]