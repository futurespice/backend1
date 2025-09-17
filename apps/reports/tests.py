from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from regions.models import Region
from reports.models import (
    Report,
    InventoryReport,
    BonusReport,
)
from reports.waste_models import WasteLog, WasteReport
from reports import services
from products.models import Category, Product
from stores.models import Store

User = get_user_model()


def uniq_digits(n=12):
    ts = str(int(timezone.now().timestamp() * 1_000_000))
    return ts[-n:].rjust(n, "0")

def ensure_region():
    """
    Создаём один Region (город Алматы) — без City, т.к. Его нет в твоих моделях.
    Поле code уникально, поэтому используем стабильный код.
    """
    region, _ = Region.objects.get_or_create(
        name="Алматы",
        defaults={"code": "ALM", "region_type": "city", "is_active": True},
    )
    # если уже был с другим code — обновим, чтобы не падало на unique
    if not region.code:
        region.code = "ALM"
        region.save(update_fields=["code"])
    return region

def make_user(role: str, **kwargs):
    """Твой User без username; email — логин, phone уникальный."""
    ts = uniq_digits(12)
    defaults = {
        "email": f"{role}.{ts}@test.local",
        "password": "pass123456",
        "role": role,
        "name": role.capitalize(),
        "second_name": "Testov",
        "phone": f"+77{uniq_digits(9)}",
        "is_active": True,
    }
    defaults.update(kwargs)
    pwd = defaults.pop("password")
    email = defaults.pop("email")
    return User.objects.create_user(email=email, password=pwd, **defaults)

def _store_field_names():
    return {f.name for f in Store._meta.get_fields() if hasattr(f, "attname")}

def make_store(user_store: User):
    """
    Создаём Store и привязываем к пользователю с ролью 'store'.
    Поля выставляем условно — под твой фактический Store.
    """
    fields = _store_field_names()
    region = ensure_region()
    owner = make_user("partner")

    data = {}
    # имя магазина
    if "store_name" in fields:
        data["store_name"] = "Магазин №1"
    elif "name" in fields:
        data["name"] = "Магазин №1"

    # привязки
    if "user" in fields:
        data["user"] = user_store
    if "owner" in fields:
        data["owner"] = owner
    if "region" in fields:
        data["region"] = region

    # прочие возможные поля
    if "inn" in fields:
        data["inn"] = uniq_digits(12)
    if "phone" in fields:
        data["phone"] = f"+77{uniq_digits(9)}"
    if "address" in fields:
        data["address"] = "ул. Абая, 1"
    if "contact_name" in fields:
        data["contact_name"] = "Иван Иванов"
    if "is_active" in fields:
        data["is_active"] = True

    return Store.objects.create(**data)


# ---------------------- FIXTURES ----------------------

@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
@pytest.mark.django_db
def admin_user():
    return make_user("admin", is_staff=True, is_superuser=True)


@pytest.fixture
@pytest.mark.django_db
def partner_user():
    return make_user("partner")


@pytest.fixture
@pytest.mark.django_db
def store_user():
    """
    Пользователь с ролью 'store'. make_store(u) внутри создаст связанный Store.
    """
    u = make_user("store")
    make_store(u)  # гарантирует наличие Store, привязанного к этому пользователю
    return u

@pytest.fixture
@pytest.mark.django_db
def store(store_user):
    """
    Возвращаем сам объект Store (а не пользователя).
    Если вдруг его ещё нет — создадим.
    """
    st = Store.objects.filter(user=store_user).first()
    if st:
        return st
    return make_store(store_user)

@pytest.fixture
@pytest.mark.django_db
def category_root():
    return Category.objects.create(name="Еда")

@pytest.fixture
@pytest.mark.django_db
def category_piece(category_root):
    return Category.objects.create(name="Готовая еда (штучные)", parent=category_root)

@pytest.fixture
@pytest.mark.django_db
def category_weight(category_root):
    return Category.objects.create(name="Мясо (весовые)", parent=category_root)

@pytest.fixture
@pytest.mark.django_db
def product_piece(category_piece):
    # unit = 'pcs' (шт), как в твоём ENUM
    return Product.objects.create(
        name="Pelmeni",
        category=category_piece,
        unit="pcs",
        price=100
    )

@pytest.fixture
@pytest.mark.django_db
def product_weight(category_weight):
    # unit = 'kg'
    return Product.objects.create(
        name="Chicken Breast",
        category=category_weight,
        unit="kg",
        price=1200
    )

@pytest.fixture
def d0():
    return date(2025, 9, 1)

@pytest.fixture
def d1():
    return date(2025, 9, 2)


# -------------------------- WASTE: API + services --------------------------

@pytest.mark.django_db
def test_waste_log_create_and_list_filters(api, partner_user, admin_user, store, product_piece, d0, d1):
    # Авторизация
    api.force_authenticate(user=admin_user)

    # Создаём две записи брака через API (POST /api/reports/waste-logs/)
    url_create = reverse("reports:waste-log-list")
    payload_1 = {
        "date": str(d0),
        "partner": partner_user.id,
        "store": store.id,
        "product": product_piece.id,
        "quantity": "1.300",
        "amount": "450.00",
        "reason": "Damaged pack",
        "notes": "Box broken"
    }
    resp = api.post(url_create, data=payload_1, format="json")
    assert resp.status_code == 201, resp.content

    payload_2 = {
        "date": str(d1),
        "partner": partner_user.id,
        "store": store.id,
        "product": product_piece.id,
        "quantity": "0.100",
        "amount": "30.00",
        "reason": "Minor defect",
        "notes": ""
    }
    resp = api.post(url_create, data=payload_2, format="json")
    assert resp.status_code == 201, resp.content

    # Листинг с фильтрами по диапазону дат
    url_list = reverse("reports:waste-log-list")
    resp = api.get(url_list, {"date_from": str(d0), "date_to": str(d1), "store": store.id})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2  # обе записи попадают

    # Проверим фильтр по product
    resp = api.get(url_list, {"date_from": str(d0), "date_to": str(d1), "product": product_piece.id})
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.django_db
def test_rebuild_waste_daily_and_report_viewset(api, partner_user, store, product_piece, d0):
    # Создадим несколько WasteLog на один день
    WasteLog.objects.create(date=d0, partner_id=partner_user.id, store=store,
                            product=product_piece, quantity="1.000", amount="100.00")
    WasteLog.objects.create(date=d0, partner_id=partner_user.id, store=store,
                            product=product_piece, quantity="0.500", amount="50.00")

    # Перестроим дневную витрину
    updated = services.rebuild_waste_daily(d0, partner_id=partner_user.id, store_id=store.id, product_id=product_piece.id)
    assert updated == 1  # одна агрегированная строка

    wr = WasteReport.objects.get(date=d0, partner_id=partner_user.id, store_id=store.id, product_id=product_piece.id)
    assert str(wr.waste_quantity) == "1.500"
    assert str(wr.waste_amount) == "150.00"

    # Доступность витрины через API
    api.force_authenticate(user=partner_user)
    url = reverse("reports:waste-report-list")
    resp = api.get(url, {"date_from": str(d0), "date_to": str(d0), "store": store.id, "product": product_piece.id})
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list) and len(items) == 1
    assert items[0]["waste_quantity"] == "1.500"
    assert items[0]["waste_amount"] == "150.00"


@pytest.mark.django_db
def test_collect_waste_period_totals_service(partner_user, store, product_piece, d0):
    # Подготовка агрегатов (витрина)
    WasteReport.objects.create(
        date=d0, partner_id=partner_user.id, store=store, product=product_piece,
        waste_quantity="1.300", waste_amount="450.00"
    )
    WasteReport.objects.create(
        date=d0 + timedelta(days=1), partner_id=partner_user.id, store=store, product=product_piece,
        waste_quantity="0.100", waste_amount="30.00"
    )

    totals = services.collect_waste_period_totals(d0, d0 + timedelta(days=1),
                                                  partner_id=partner_user.id, store_id=store.id, product_id=product_piece.id)
    assert str(totals["total_waste_quantity"]) == "1.400"
    assert str(totals["total_waste_amount"]) == "480.00"


@pytest.mark.django_db
def test_generate_and_save_report_waste_endpoint(api, partner_user, store, product_piece, d0, admin_user):
    # Исходная первичка (WasteLog)
    WasteLog.objects.create(date=d0, partner_id=partner_user.id, store=store,
                            product=product_piece, quantity="1.300", amount="450.00")
    WasteLog.objects.create(date=d0, partner_id=partner_user.id, store=store,
                            product=product_piece, quantity="0.100", amount="30.00")

    # Авторизация любым валидным пользователем
    api.force_authenticate(user=admin_user)


    # Вызов POST /api/reports/generate/ с типом "waste"
    url_gen = reverse("reports:report-generate")
    payload = {
        "name": "Waste report d0",
        "report_type": "waste",
        "period": "daily",
        "date_from": str(d0),
        "date_to": str(d0),
        "partner": partner_user.id,
        "store": store.id,
        "product": product_piece.id,
        "is_automated": False
    }
    resp = api.post(url_gen, data=payload, format="json")
    assert resp.status_code == 201, resp.content

    body = resp.json()
    assert body["name"] == "Waste report d0"
    assert body["report_type"] == "waste"
    assert body["period"] == "daily"
    assert body["data"]["rebuilt_rows"] >= 1
    assert body["data"]["totals"]["total_waste_quantity"] == "1.400"
    assert body["data"]["totals"]["total_waste_amount"] == "480.00"

    # Проверим, что запись в Report действительно создана
    rid = body["id"]
    rpt = Report.objects.get(id=rid)
    assert rpt.report_type == "waste"
    assert rpt.data["totals"]["total_waste_amount"] == "480.00"


# -------------------------- VALIDATIONS --------------------------

@pytest.mark.django_db
def test_bonus_report_clean_weight_product_invalid(partner_user, store, product_weight, d0):
    # Весовой товар не может иметь бонусное количество > 0
    br = BonusReport(
        date=d0, partner_id=partner_user.id, store=store, product=product_weight,
        sold_quantity=10, bonus_quantity=1, bonus_discount="100.00", net_revenue="0.00"
    )
    with pytest.raises(ValidationError):
        br.clean()  # весовой unit -> бонусы запрещены


@pytest.mark.django_db
def test_inventory_report_balance_invariant_validation(partner_user, store, product_piece, d0):
    # opening + received - sold должно равняться closing
    inv = InventoryReport(
        date=d0, store=store, partner_id=partner_user.id, product=product_piece,
        opening_balance="10.000", received_quantity="5.000", sold_quantity="12.000",
        closing_balance="4.000",  # должно быть 3.000 — специально ошибочно
        opening_value="1000.00", closing_value="0.00"
    )
    with pytest.raises(ValidationError):
        inv.clean()


@pytest.mark.django_db
def test_report_model_clean_validations(partner_user, product_piece, store):
    # date_from > date_to — ошибка
    r = Report(
        name="Bad dates",
        report_type="waste",
        period="daily",
        date_from=date(2025, 9, 10),
        date_to=date(2025, 9, 1),
        partner_id=partner_user.id,
        store_id=store.id,
        product_id=product_piece.id,
        data={}
    )
    with pytest.raises(ValidationError):
        r.clean()

    # period=custom без обеих дат — ошибка
    r2 = Report(
        name="Custom bad",
        report_type="waste",
        period="custom",
        date_from=None,
        date_to=None,
        partner_id=partner_user.id,
        store_id=store.id,
        product_id=product_piece.id,
        data={}
    )
    with pytest.raises(ValidationError):
        r2.clean()

    # Валидный вариант
    r3 = Report(
        name="OK",
        report_type="waste",
        period="custom",
        date_from=date(2025, 9, 1),
        date_to=date(2025, 9, 5),
        partner_id=partner_user.id,
        store_id=store.id,
        product_id=product_piece.id,
        data={}
    )
    # не должно кидать
    r3.clean()
