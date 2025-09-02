import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='full_name',
        ),
        migrations.AddField(
            model_name='user',
            name='name',
            field=models.CharField(
                max_length=100,
                validators=[
                    django.core.validators.RegexValidator(
                        r'^[a-zA-Zа-яА-Я\s]+$',
                        'Имя должно содержать только буквы'
                    )
                ],
                default='',  # временно для миграции существующих строк
            ),
            preserve_default=False,  # после миграции дефолт уберётся
        ),
        migrations.AddField(
            model_name='user',
            name='second_name',
            field=models.CharField(
                max_length=100,
                validators=[
                    django.core.validators.RegexValidator(
                        r'^[a-zA-Zа-яА-Я\s]+$',
                        'Фамилия должна содержать только буквы'
                    )
                ],
                default='',
            ),
            preserve_default=False,
        ),
    ]
