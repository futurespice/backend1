from django.db import models


class Region(models.Model):
    """Область/регион"""
    name = models.CharField(max_length=100, unique=True, verbose_name='Название области')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'regions'
        verbose_name = 'Область'
        verbose_name_plural = 'Области'
        ordering = ['name']

    def __str__(self):
        return self.name


class City(models.Model):
    """Город"""
    name = models.CharField(max_length=100, verbose_name='Название города')
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='cities', verbose_name='Область')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cities'
        verbose_name = 'Город'
        verbose_name_plural = 'Города'
        unique_together = ['name', 'region']
        ordering = ['name']

    def __str__(self):
        return f"{self.name}, {self.region.name}"