from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from regions.models import Region, City


class Store(models.Model):
    """Магазин"""
    # Владелец (партнер)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_stores',
        limit_choices_to={'role': 'partner'},
        verbose_name='Владелец (партнер)'
    )

    # Пользователь магазина (может быть None если магазин еще не привязан к пользователю)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='store',
        limit_choices_to={'role': 'store'},
        verbose_name='Пользователь магазина'
    )

    # Основная информация
    name = models.CharField(max_length=200, verbose_name='Название магазина')
    inn = models.CharField(
        max_length=14,
        unique=True,
        validators=[RegexValidator(r'^\d{12,14}$', 'ИНН должен содержать 12-14 цифр')],
        verbose_name='ИНН'
    )
    phone = models.CharField(
        max_length=20,
        unique=True,
        validators=[RegexValidator(r'^\+?[0-9]{10,15}$', 'Неверный формат телефона')],
        verbose_name='Номер телефона'
    )

    # Местоположение
    region = models.ForeignKey(Region, on_delete=models.CASCADE, verbose_name='Область')
    city = models.ForeignKey(City, on_delete=models.CASCADE, verbose_name='Город')
    address = models.TextField(verbose_name='Адрес')

    # Контактное лицо
    contact_name = models.CharField(max_length=200, verbose_name='ФИО контактного лица')

    # Статус
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'stores'
        verbose_name = 'Магазин'
        verbose_name_plural = 'Магазины'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} (ИНН: {self.inn})"

    @property
    def full_address(self):
        return f"{self.region.name}, {self.city.name}, {self.address}"

    def get_debt_amount(self):
        """Получить общую сумму долга магазина"""
        from debts.models import Debt
        return Debt.objects.filter(store=self, is_paid=False).aggregate(
            total=models.Sum('amount')
        )['total'] or 0

    def get_total_orders_count(self):
        """Получить общее количество заказов"""
        return self.orders.count()

    def get_total_orders_amount(self):
        """Получить общую сумму заказов"""
        return self.orders.aggregate(
            total=models.Sum('total_amount')
        )['total'] or 0