from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_email_task(self, subject, message, recipient_list, from_email=None):
    """Асинхронная отправка email"""
    try:
        if not from_email:
            from_email = settings.DEFAULT_FROM_EMAIL

        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False,
        )

        logger.info(f"Email отправлен: {subject} -> {recipient_list}")
        return f"Email успешно отправлен на {len(recipient_list)} адресов"

    except Exception as exc:
        logger.error(f"Ошибка отправки email: {exc}")

        # Повторная попытка через 60 секунд
        if self.request.retries < self.max_retries:
            logger.info(f"Повторная попытка отправки email через 60 сек (попытка {self.request.retries + 1})")
            raise self.retry(countdown=60, exc=exc)

        raise exc


@shared_task
def send_password_reset_code_task(user_id, code):
    """Отправка кода сброса пароля"""
    try:
        from .models import User
        user = User.objects.get(id=user_id)

        subject = 'Код для сброса пароля - B2B Система'
        message = f"""
Здравствуйте, {user.name}!

Вы запросили сброс пароля для вашего аккаунта в B2B системе.

Ваш код для сброса пароля: {code}

Код действителен в течение 15 минут.

Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо.
        """

        send_email_task.delay(
            subject=subject,
            message=message,
            recipient_list=[user.email]
        )

        return f"Код сброса пароля отправлен на {user.email}"

    except Exception as exc:
        logger.error(f"Ошибка отправки кода сброса пароля: {exc}")
        raise exc


@shared_task
def send_approval_notification_task(user_id, is_approved):
    """Уведомление об одобрении/отклонении заявки"""
    try:
        from .models import User
        user = User.objects.get(id=user_id)

        if is_approved:
            subject = 'Ваша заявка одобрена - B2B Система'
            message = f"""
Здравствуйте, {user.name}!

Ваша заявка на регистрацию в B2B системе была одобрена.

Теперь вы можете войти в систему и начать работу.

Добро пожаловать!
            """
        else:
            subject = 'Ваша заявка отклонена - B2B Система'
            message = f"""
Здравствуйте, {user.name}!

К сожалению, ваша заявка на регистрацию в B2B системе была отклонена.

Для получения дополнительной информации обратитесь к администратору.
            """

        send_email_task.delay(
            subject=subject,
            message=message,
            recipient_list=[user.email]
        )

        return f"Уведомление отправлено на {user.email}"

    except Exception as exc:
        logger.error(f"Ошибка отправки уведомления: {exc}")
        raise exc


@shared_task
def cleanup_expired_password_resets():
    """Очистка просроченных запросов сброса пароля"""
    try:
        from .models import PasswordResetRequest

        expired_requests = PasswordResetRequest.objects.filter(
            expires_at__lt=timezone.now(),
            is_used=False
        )

        count = expired_requests.count()
        expired_requests.update(is_used=True)

        logger.info(f"Очищено {count} просроченных запросов сброса пароля")
        return f"Очищено {count} запросов"

    except Exception as exc:
        logger.error(f"Ошибка очистки просроченных запросов: {exc}")
        raise exc


@shared_task
def daily_reports_task():
    """Ежедневные отчёты системы"""
    try:
        from .models import User
        from apps.orders.models import Order
        from apps.debts.models import Debt

        # Получаем статистику за вчера
        yesterday = timezone.now().date() - timedelta(days=1)

        # Новые пользователи
        new_users = User.objects.filter(created_at__date=yesterday).count()

        # Новые заказы
        new_orders = Order.objects.filter(order_date__date=yesterday).count()

        # Новые долги
        new_debts = Debt.objects.filter(created_at__date=yesterday).count()

        # Формируем отчёт
        report = f"""
Ежедневный отчёт B2B системы за {yesterday}

📊 Статистика:
- Новых пользователей: {new_users}
- Новых заказов: {new_orders}  
- Новых долгов: {new_debts}

📈 Общая статистика:
- Всего пользователей: {User.objects.count()}
- Всего заказов: {Order.objects.count()}
- Активных долгов: {Debt.objects.filter(is_paid=False).count()}
        """

        # Отправляем отчёт администраторам
        admin_emails = list(User.objects.filter(
            role='admin',
            is_active=True
        ).values_list('email', flat=True))

        if admin_emails:
            send_email_task.delay(
                subject=f'Ежедневный отчёт B2B системы - {yesterday}',
                message=report,
                recipient_list=admin_emails
            )

        logger.info(f"Ежедневный отчёт отправлен {len(admin_emails)} администраторам")
        return f"Отчёт отправлен {len(admin_emails)} администраторам"

    except Exception as exc:
        logger.error(f"Ошибка формирования ежедневного отчёта: {exc}")
        raise exc


@shared_task
def check_overdue_debts():
    """Проверка просроченных долгов"""
    try:
        from apps.debts.models import Debt

        # Находим просроченные долги
        overdue_debts = Debt.objects.filter(
            is_paid=False,
            due_date__lt=timezone.now().date()
        ).select_related('store', 'store__user')

        notifications_sent = 0

        for debt in overdue_debts:
            try:
                days_overdue = (timezone.now().date() - debt.due_date).days

                subject = f'Просроченная задолженность #{debt.id}'
                message = f"""
Уважаемый {debt.store.user.get_full_name()}!

У вас имеется просроченная задолженность:

💰 Сумма: {debt.remaining_amount} сом
📅 Срок оплаты: {debt.due_date}
⏰ Просрочка: {days_overdue} дней

Описание: {debt.description}

Пожалуйста, погасите задолженность в ближайшее время.

Для вопросов обращайтесь к администратору.
                """

                send_email_task.delay(
                    subject=subject,
                    message=message,
                    recipient_list=[debt.store.user.email]
                )

                notifications_sent += 1

            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о долге {debt.id}: {e}")

        logger.info(f"Отправлено {notifications_sent} уведомлений о просроченных долгах")
        return f"Отправлено {notifications_sent} уведомлений"

    except Exception as exc:
        logger.error(f"Ошибка проверки просроченных долгов: {exc}")
        raise exc


@shared_task
def update_product_costs():
    """Обновление себестоимости товаров"""
    try:
        from apps.cost_accounting.services import CostCalculationService
        from apps.products.models import Product

        updated_count = 0

        # Обновляем себестоимость для всех активных товаров
        products = Product.objects.filter(is_active=True)

        for product in products:
            try:
                new_cost = CostCalculationService.calculate_product_cost(product)

                if new_cost != product.cost_price:
                    product.cost_price = new_cost
                    product.save(update_fields=['cost_price'])
                    updated_count += 1

            except Exception as e:
                logger.error(f"Ошибка обновления себестоимости товара {product.id}: {e}")

        logger.info(f"Обновлена себестоимость {updated_count} товаров")
        return f"Обновлено {updated_count} товаров"

    except Exception as exc:
        logger.error(f"Ошибка обновления себестоимости: {exc}")
        raise exc


@shared_task
def backup_database():
    """Резервное копирование базы данных"""
    try:
        import os
        import subprocess
        from django.conf import settings

        # Получаем параметры подключения к БД
        db_config = settings.DATABASES['default']

        if db_config['ENGINE'] == 'django.db.backends.postgresql':
            # Создаём дамп PostgreSQL
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"/app/backups/backup_{timestamp}.sql"

            # Создаём директорию для бэкапов
            os.makedirs('/app/backups', exist_ok=True)

            # Выполняем pg_dump
            cmd = [
                'pg_dump',
                f"--host={db_config['HOST']}",
                f"--port={db_config['PORT']}",
                f"--username={db_config['USER']}",
                f"--dbname={db_config['NAME']}",
                f"--file={backup_file}",
                '--verbose'
            ]

            # Устанавливаем пароль через переменную окружения
            env = os.environ.copy()
            env['PGPASSWORD'] = db_config['PASSWORD']

            result = subprocess.run(cmd, env=env, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info(f"Резервная копия создана: {backup_file}")

                # Удаляем старые бэкапы (старше 7 дней)
                cleanup_old_backups.delay()

                return f"Бэкап создан: {backup_file}"
            else:
                logger.error(f"Ошибка создания бэкапа: {result.stderr}")
                raise Exception(f"Ошибка pg_dump: {result.stderr}")

        else:
            logger.warning("Бэкап поддерживается только для PostgreSQL")
            return "Бэкап не поддерживается для данной БД"

    except Exception as exc:
        logger.error(f"Ошибка создания резервной копии: {exc}")
        raise exc


@shared_task
def cleanup_old_backups():
    """Очистка старых резервных копий"""
    try:
        import os
        import glob

        backup_dir = '/app/backups'
        if not os.path.exists(backup_dir):
            return "Директория бэкапов не существует"

        # Находим файлы старше 7 дней
        cutoff_time = timezone.now() - timedelta(days=7)
        cutoff_timestamp = cutoff_time.timestamp()

        backup_files = glob.glob(os.path.join(backup_dir, 'backup_*.sql'))
        deleted_count = 0

        for backup_file in backup_files:
            file_time = os.path.getctime(backup_file)

            if file_time < cutoff_timestamp:
                try:
                    os.remove(backup_file)
                    deleted_count += 1
                    logger.info(f"Удалён старый бэкап: {backup_file}")
                except Exception as e:
                    logger.error(f"Ошибка удаления бэкапа {backup_file}: {e}")

        logger.info(f"Удалено {deleted_count} старых бэкапов")
        return f"Удалено {deleted_count} файлов"

    except Exception as exc:
        logger.error(f"Ошибка очистки старых бэкапов: {exc}")
        raise exc


@shared_task
def generate_monthly_reports():
    """Генерация месячных отчётов"""
    try:
        from apps.reports.services import ReportGeneratorService

        # Получаем прошлый месяц
        today = timezone.now().date()
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)

        # Генерируем отчёты
        reports_generated = []

        # Отчёт по продажам
        sales_report = ReportGeneratorService.generate_sales_report(
            date_from=first_day_last_month,
            date_to=last_day_last_month
        )
        reports_generated.append('sales')

        # Отчёт по долгам
        debt_report = ReportGeneratorService.generate_debt_report(
            date_from=first_day_last_month,
            date_to=last_day_last_month
        )
        reports_generated.append('debts')

        # Отчёт по себестоимости
        cost_report = ReportGeneratorService.generate_cost_report(
            date_from=first_day_last_month,
            date_to=last_day_last_month
        )
        reports_generated.append('costs')

        logger.info(f"Сгенерированы месячные отчёты: {reports_generated}")
        return f"Сгенерировано отчётов: {len(reports_generated)}"

    except Exception as exc:
        logger.error(f"Ошибка генерации месячных отчётов: {exc}")
        raise exc


@shared_task
def sync_inventory_balances():
    """Синхронизация остатков товаров"""
    try:
        from apps.stores.models import StoreInventory
        from apps.products.models import Product

        synced_count = 0
        errors_count = 0

        # Проверяем все записи инвентаря
        for inventory in StoreInventory.objects.select_related('product', 'store'):
            try:
                # Здесь может быть логика синхронизации с внешними системами
                # Пока просто проверяем консистентность данных

                if inventory.quantity < 0:
                    inventory.quantity = 0
                    inventory.save()
                    synced_count += 1

            except Exception as e:
                logger.error(f"Ошибка синхронизации инвентаря {inventory.id}: {e}")
                errors_count += 1

        logger.info(f"Синхронизировано {synced_count} записей инвентаря, ошибок: {errors_count}")
        return f"Синхронизировано: {synced_count}, ошибок: {errors_count}"

    except Exception as exc:
        logger.error(f"Ошибка синхронизации инвентаря: {exc}")
        raise exc