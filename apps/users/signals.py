from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import User
from .services import EmailService
import logging
from bonuses.models import BonusBalance

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def user_post_save_handler(sender, instance, created, **kwargs):
    """Обработчик создания/обновления пользователя"""

    if created:
        # Новый пользователь создан
        logger.info(f"Создан новый пользователь: {instance.email} ({instance.role})")

        # Отправляем приветственное письмо
        try:
            EmailService.send_welcome_email(instance)
        except Exception as e:
            logger.error(f"Ошибка отправки приветственного письма: {e}")

        # Создаём профиль магазина для пользователей роли 'store'
        if instance.role == 'store':
            _create_store_profile(instance)

        # Создаём баланс бонусов для магазинов
        if instance.role == 'store':
            _create_bonus_balance(instance)

    else:
        # Пользователь обновлён
        # Проверяем изменение статуса одобрения
        if hasattr(instance, '_original_is_approved'):
            old_approved = instance._original_is_approved
            new_approved = instance.is_approved

            if old_approved != new_approved:
                logger.info(f"Изменён статус одобрения пользователя {instance.email}: {old_approved} -> {new_approved}")

                # Отправляем уведомление
                try:
                    EmailService.send_approval_notification(instance, new_approved)
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления об одобрении: {e}")


def _create_store_profile(user):
    """Создание профиля магазина"""
    try:
        from apps.stores.models import Store

        # Проверяем, что профиль ещё не создан
        if not hasattr(user, 'store_profile'):
            store = Store.objects.create(
                user=user,
                store_name=f"Магазин {user.get_full_name()}",
                address="Адрес не указан",
                is_active=user.is_approved
            )
            logger.info(f"Создан профиль магазина для пользователя {user.email}")

    except Exception as e:
        logger.error(f"Ошибка создания профиля магазина: {e}")


def _create_bonus_balance(user):
    """Создание баланса бонусов для магазина"""
    try:
        # Импортируем здесь, чтобы избежать циклических импортов
        from apps.bonuses.models import BonusBalance

        if hasattr(user, 'store_profile'):
            store = user.store_profile

            # Проверяем, что баланс ещё не создан
            if not hasattr(store, 'bonus_balance'):
                BonusBalance.objects.create(store=store)
                logger.info(f"Создан баланс бонусов для магазина {store.store_name}")

    except Exception as e:
        logger.error(f"Ошибка создания баланса бонусов: {e}")


@receiver(post_delete, sender=User)
def user_post_delete_handler(sender, instance, **kwargs):
    """Обработчик удаления пользователя"""
    logger.info(f"Удалён пользователь: {instance.email} ({instance.role})")


# Сигнал для отслеживания изменений в поле is_approved
@receiver(post_save, sender=User)
def track_approval_changes(sender, instance, **kwargs):
    """Отслеживание изменений статуса одобрения"""
    try:
        # Получаем оригинальное значение из базы
        if instance.pk:
            original = User.objects.get(pk=instance.pk)
            instance._original_is_approved = original.is_approved
    except User.DoesNotExist:
        instance._original_is_approved = None


# Автоматическое создание корзины для магазинов
@receiver(post_save, sender='stores.Store')
def create_store_cart(sender, instance, created, **kwargs):
    """Создание корзины для нового магазина"""
    if created:
        try:
            from apps.orders.models import Cart
            Cart.objects.get_or_create(store=instance)
            logger.info(f"Создана корзина для магазина {instance.store_name}")
        except Exception as e:
            logger.error(f"Ошибка создания корзины: {e}")


# Автоматическое создание сводки долгов для магазинов
@receiver(post_save, sender='stores.Store')
def create_debt_summary(sender, instance, created, **kwargs):
    """Создание сводки долгов для нового магазина"""
    if created:
        try:
            from apps.debts.models import DebtSummary
            DebtSummary.objects.get_or_create(store=instance)
            logger.info(f"Создана сводка долгов для магазина {instance.store_name}")
        except Exception as e:
            logger.error(f"Ошибка создания сводки долгов: {e}")


# Автоматический пересчёт сумм при изменении позиций заказа
@receiver(post_save, sender='orders.OrderItem')
@receiver(post_delete, sender='orders.OrderItem')
def recalculate_order_totals(sender, instance, **kwargs):
    """Пересчёт сумм заказа при изменении позиций"""
    try:
        instance.order.calculate_totals()
        logger.debug(f"Пересчитаны суммы заказа #{instance.order.id}")
    except Exception as e:
        logger.error(f"Ошибка пересчёта сумм заказа: {e}")


# Автоматический пересчёт сумм запроса товаров
@receiver(post_save, sender='orders.ProductRequestItem')
@receiver(post_delete, sender='orders.ProductRequestItem')
def recalculate_request_totals(sender, instance, **kwargs):
    """Пересчёт сумм запроса товаров при изменении позиций"""
    try:
        instance.request.calculate_totals()
        logger.debug(f"Пересчитаны суммы запроса #{instance.request.id}")
    except Exception as e:
        logger.error(f"Ошибка пересчёта сумм запроса: {e}")


# Автоматическое обновление баланса бонусов
@receiver(post_save, sender='bonuses.BonusHistory')
def update_bonus_balance(sender, instance, created, **kwargs):
    """Обновление баланса бонусов при добавлении истории"""
    if created:
        try:
            balance, created = BonusBalance.objects.get_or_create(
                store=instance.store
            )

            # Обновляем баланс
            balance.add_points(instance.points_earned)
            balance.add_bonus_items(
                items_count=instance.total_items_purchased,
                bonus_count=instance.bonus_items,
                saved_amount=instance.discount_amount
            )

            logger.debug(f"Обновлён баланс бонусов для {instance.store.store_name}")

        except Exception as e:
            logger.error(f"Ошибка обновления баланса бонусов: {e}")


# Автоматическое обновление сводки долгов
@receiver(post_save, sender='debts.Debt')
@receiver(post_delete, sender='debts.Debt')
def update_debt_summary(sender, instance, **kwargs):
    """Обновление сводки долгов при изменении долга"""
    try:
        from apps.debts.services import DebtService
        DebtService.update_store_debt_summary(instance.store)
        logger.debug(f"Обновлена сводка долгов для {instance.store.store_name}")
    except Exception as e:
        logger.error(f"Ошибка обновления сводки долгов: {e}")


# Автоматическая запись истории изменения цен
@receiver(post_save, sender='products.Product')
def track_price_changes(sender, instance, created, **kwargs):
    """Отслеживание изменений цен товаров"""
    if not created and hasattr(instance, '_original_price'):
        old_price = instance._original_price
        new_price = instance.price

        if old_price != new_price:
            try:
                from apps.products.models import ProductPriceHistory
                ProductPriceHistory.objects.create(
                    product=instance,
                    old_price=old_price,
                    new_price=new_price,
                    reason='Автоматическое изменение'
                )
                logger.info(f"Записано изменение цены товара {instance.name}: {old_price} -> {new_price}")
            except Exception as e:
                logger.error(f"Ошибка записи истории цен: {e}")


# Сигнал для получения оригинальной цены перед сохранением
@receiver(post_save, sender='products.Product')
def get_original_price(sender, instance, **kwargs):
    """Получение оригинальной цены товара"""
    try:
        if instance.pk:
            original = sender.objects.get(pk=instance.pk)
            instance._original_price = original.price
    except sender.DoesNotExist:
        instance._original_price = None