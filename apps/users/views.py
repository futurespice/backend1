from rest_framework import status, generics, permissions, viewsets, filters
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django_filters.rest_framework import DjangoFilterBackend
from django.conf import settings
from .models import User
from .serializers import (
    UserRegistrationSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    UserProfileSerializer,
    UserListSerializer,
    UserModerationSerializer
)
from .permissions import IsAdminUser


class UserRegistrationView(generics.CreateAPIView):
    """
    Регистрация пользователей
    UserManager автоматически определит роль по маркеру в пароле
    """
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response({
            'message': 'Регистрация успешна',
            'user': {
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'is_approved': user.is_approved
            },
            'requires_approval': user.role == 'partner'
        }, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Кастомный вход в систему
    Использует стандартный JWT, но возвращает дополнительную информацию о пользователе
    """

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            # Получаем пользователя
            email = request.data.get('email')
            try:
                user = User.objects.get(email=email)

                # Проверяем одобрение
                if not user.is_approved:
                    return Response({
                        'error': 'Аккаунт ожидает одобрения администратора'
                    }, status=status.HTTP_403_FORBIDDEN)

                # Добавляем информацию о пользователе в ответ
                response.data['user'] = {
                    'id': user.id,
                    'email': user.email,
                    'full_name': user.full_name,
                    'role': user.role,
                    'avatar': user.avatar.url if user.avatar else None
                }

            except User.DoesNotExist:
                pass

        return response


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Получение и обновление профиля текущего пользователя
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class AdminUserViewSet(viewsets.ModelViewSet):
    """
    API для администраторов по управлению пользователями
    """
    queryset = User.objects.all()
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_approved', 'is_active']
    search_fields = ['email', 'full_name', 'phone']
    ordering_fields = ['created_at', 'email', 'full_name']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action in ['approve', 'reject', 'block', 'unblock']:
            return UserModerationSerializer
        return UserListSerializer

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Список пользователей ожидающих одобрения"""
        pending_users = self.queryset.filter(is_approved=False, is_active=True)
        serializer = self.get_serializer(pending_users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def approved(self, request):
        """Список одобренных пользователей"""
        approved_users = self.queryset.filter(is_approved=True, is_active=True)
        serializer = self.get_serializer(approved_users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def blocked(self, request):
        """Список заблокированных пользователей"""
        blocked_users = self.queryset.filter(is_active=False)
        serializer = self.get_serializer(blocked_users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def partners(self, request):
        """Список партнёров"""
        partners = self.queryset.filter(role='partner')
        serializer = self.get_serializer(partners, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stores(self, request):
        """Список магазинов"""
        stores = self.queryset.filter(role='store')
        serializer = self.get_serializer(stores, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Одобрить пользователя"""
        user = self.get_object()
        serializer = UserModerationSerializer(user, data={'is_approved': True}, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': f'Пользователь {user.email} одобрен'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Отклонить пользователя"""
        user = self.get_object()
        serializer = UserModerationSerializer(user, data={'is_approved': False}, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': f'Пользователь {user.email} отклонён'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def block(self, request, pk=None):
        """Заблокировать пользователя"""
        user = self.get_object()
        serializer = UserModerationSerializer(user, data={'is_active': False}, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': f'Пользователь {user.email} заблокирован'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def unblock(self, request, pk=None):
        """Разблокировать пользователя"""
        user = self.get_object()
        serializer = UserModerationSerializer(user, data={'is_active': True}, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': f'Пользователь {user.email} разблокирован'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetRequestView(generics.CreateAPIView):
    """Запрос на сброс пароля"""
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset_request = serializer.save()

        return Response({
            'message': 'Код для сброса пароля отправлен на email',
            # В разработке показываем код, в продакшене убрать!
            'code': reset_request.code if settings.DEBUG else None
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(generics.GenericAPIView):
    """Подтверждение сброса пароля"""
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response({
            'message': 'Пароль успешно изменён'
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    Выход из системы
    Добавляем refresh token в чёрный список
    """
    try:
        refresh_token = request.data.get('refresh_token')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()

        return Response({
            'message': 'Выход выполнен успешно'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': 'Ошибка при выходе из системы'
        }, status=status.HTTP_400_BAD_REQUEST)