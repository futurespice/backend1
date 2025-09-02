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
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='user',
            name='second_name',
            preserve_default=False,
        ),
    ]
