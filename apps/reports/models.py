from django.db import models
from django.utils import timezone
from django.conf import settings
from stores.models import City


class Report(models.Model):
    type = models.CharField(
        max_length=20,
        choices=[
            ('sales', 'Продажи'), ('debts', 'Долги'), ('costs', 'Себестоимость'),
            ('bonuses', 'Бонусы'), ('brak', 'Брак'), ('balance', 'Баланс'),
            ('orders', 'Заказы'), ('products', 'Товары'), ('markup', 'Наценка')
        ],
        verbose_name='Тип'
    )
    date_from = models.DateField(verbose_name='С даты')
    date_to = models.DateField(verbose_name='По дату')
    filter_city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Фильтр город')
    filter_partner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'role': 'partner'}, verbose_name='Фильтр партнер')
    filter_store = models.ForeignKey('stores.Store', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Фильтр магазин')
    data = models.JSONField(verbose_name='Данные отчета')  # {'total_income': 1000, 'shares': {...}}
    pdf = models.FileField(upload_to='reports/', null=True, blank=True, verbose_name='PDF отчет')
    generated_at = models.DateTimeField(default=timezone.now, verbose_name='Сгенерировано')

    class Meta:
        db_table = 'reports'
        verbose_name = 'Отчет'
        verbose_name_plural = 'Отчеты'
        ordering = ['-generated_at']

    def __str__(self):
        return f"{self.get_type_display()} за {self.date_from} - {self.date_to}"