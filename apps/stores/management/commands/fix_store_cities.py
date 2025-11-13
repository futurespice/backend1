"""
Management команда для исправления неправильных регион/город в магазинах
"""
from django.core.management.base import BaseCommand
from apps.stores.models import Store


class Command(BaseCommand):
    help = 'Находит и исправляет магазины с неправильным регионом/городом'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Исправить неправильные записи (по умолчанию только показывает)',
        )

    def handle(self, *args, **options):
        fix_mode = options['fix']

        # Найти все магазины где город не принадлежит региону
        invalid_stores = []
        for store in Store.objects.select_related('region', 'city', 'city__region'):
            if store.city.region_id != store.region.id:
                invalid_stores.append(store)

        if not invalid_stores:
            self.stdout.write(self.style.SUCCESS('✓ Все записи корректны!'))
            return

        self.stdout.write(
            self.style.WARNING(f'\nНайдено {len(invalid_stores)} неправильных записей:\n')
        )
        self.stdout.write('=' * 80)

        for store in invalid_stores:
            self.stdout.write(f'\nID: {store.id}, Магазин: {store.name}')
            self.stdout.write(f'  Указанный регион: {store.region.name} (ID={store.region.id})')
            self.stdout.write(
                f'  Город: {store.city.name}, который на самом деле в регионе: '
                f'{store.city.region.name} (ID={store.city.region.id})'
            )

            if fix_mode:
                # Исправляем: устанавливаем правильный регион
                old_region = store.region.name
                store.region = store.city.region
                store.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  → ИСПРАВЛЕНО: регион изменен с "{old_region}" на "{store.region.name}"'
                    )
                )

            self.stdout.write('-' * 80)

        if not fix_mode:
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠ Запустите с флагом --fix чтобы автоматически исправить записи:'
                )
            )
            self.stdout.write(
                self.style.WARNING('  python manage.py fix_store_cities --fix\n')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'\n✓ Исправлено {len(invalid_stores)} записей\n')
            )
