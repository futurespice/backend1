from rest_framework import status, generics, permissions, viewsets, filters
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django_filters.rest_framework import DjangoFilterBackend
from django.conf import settings
from .models import User
from .serializers import (
    UserRegistrationSerializer,
    CustomTokenObtainSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetCodeSerializer,
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

        # Формируем ответ
        response_data = {
            'message': 'Регистрация успешна',
            'user': {
                'id': user.id,
                'email': user.email,
                'name': user.name,
                'second_name': user.second_name,
                'phone': user.phone,
                'role': user.role,
                'is_approved': user.is_approved
            }
        }

        # Для партнёров добавляем информацию о необходимости одобрения
        if user.role == 'partner':
            response_data['requires_approval'] = True
            response_data['message'] = 'Регистрация успешна. Заявка передана на рассмотрение администратору.'
        else:
            response_data['requires_approval'] = False

        return Response(response_data, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(generics.GenericAPIView):
    """
    Кастомный вход в систему
    Вход только по номеру телефона и паролю
    """
    serializer_class = CustomTokenObtainSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']

        # Генерируем JWT токены
        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token

        return Response({
            'access': str(access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'name': user.name,
                'second_name': user.second_name,
                'phone': user.phone,
                'role': user.role,
                'is_approved': user.is_approved,
                'full_name': user.get_full_name()
            }
        }, status=status.HTTP_200_OK)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Просмотр и редактирование профиля пользователя
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserListViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления пользователями (только для админов)
    """
    queryset = User.objects.all().order_by('-created_at')
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_approved', 'is_active']
    search_fields = ['email', 'name', 'second_name', 'phone']
    ordering_fields = ['created_at', 'name', 'email']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return UserModerationSerializer
        return UserListSerializer

    @action(detail=True, methods=['patch'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        """Одобрить пользователя"""
        user = self.get_object()
        user.is_approved = True
        user.save()

        return Response({
            'message': f'Пользователь {user.get_full_name()} одобрен',
            'user': UserListSerializer(user).data
        })

    @action(detail=True, methods=['patch'], permission_classes=[IsAdminUser])
    def reject(self, request, pk=None):
        """Отклонить пользователя"""
        user = self.get_object()
        user.is_approved = False
        user.save()

        return Response({
            'message': f'Пользователь {user.get_full_name()} отклонён',
            'user': UserListSerializer(user).data
        })

    @action(detail=True, methods=['patch'], permission_classes=[IsAdminUser])
    def block(self, request, pk=None):
        """Заблокировать пользователя"""
        user = self.get_object()
        user.is_active = False
        user.save()

        return Response({
            'message': f'Пользователь {user.get_full_name()} заблокирован',
            'user': UserListSerializer(user).data
        })

    @action(detail=True, methods=['patch'], permission_classes=[IsAdminUser])
    def unblock(self, request, pk=None):
        """Разблокировать пользователя"""
        user = self.get_object()
        user.is_active = True
        user.save()

        return Response({
            'message': f'Пользователь {user.get_full_name()} разблокирован',
            'user': UserListSerializer(user).data
        })


class PasswordResetRequestView(generics.CreateAPIView):
    """
    Запрос на сброс пароля
    Отправляет код на email
    """
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'message': 'Код для сброса пароля отправлен на email'
        }, status=status.HTTP_200_OK)


class PasswordResetCodeView(generics.CreateAPIView):
    """
    Проверка кода сброса пароля
    """
    serializer_class = PasswordResetCodeSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return Response({
            'message': 'Код верен'
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(generics.CreateAPIView):
    """
    Подтверждение сброса пароля с новым паролем
    """
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response({
            'message': 'Пароль успешно изменён',
            'user': {
                'id': user.id,
                'email': user.email,
                'name': user.name
            }
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    Выход из системы (добавление токена в черный список)
    """
    try:
        refresh_token = request.data.get('refresh')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()

        return Response({
            'message': 'Успешный выход из системы'
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'error': 'Ошибка при выходе из системы'
        }, status=status.HTTP_400_BAD_REQUEST)