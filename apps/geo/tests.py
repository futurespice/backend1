# apps/geo/tests.py
import pytest
from django.urls import reverse
from django.utils import timezone

from datetime import datetime, date, time, timedelta, timezone as dt_timezone



from rest_framework.test import APIClient

from reports.tests import uniq_digits
from users.models import User
from geo.models import GeoPing, GeoDevice

@pytest.fixture
def api():
    return APIClient()


def auth(api: APIClient, user: User):
    api.force_authenticate(user=user)
    return api
def make_user(role: str, **kwargs):
    """
    Создаёт пользователя под твою модель (email-логин, phone уникальный).
    Параметр approved (bool) автоматически маппится в approval_status.
    """
    ts = uniq_digits(12)
    # достаём approved и превращаем в approval_status
    approved = kwargs.pop("approved", None)
    if "approval_status" not in kwargs:
        if approved:
            kwargs["approval_status"] = "approved"
        elif not approved:
            kwargs["approval_status"] = "pending"

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


def pings_url():
    # basename='geo-pings' -> маршруты: geo-pings-list / geo-pings-detail
    return reverse("geo-pings-list")


@pytest.mark.django_db
def test_partner_can_create_ping_and_list_own_by_date(api):
    partner = make_user("partner", phone="77001230001", approval_status='approved')
    auth(api, partner)

    recorded_at = timezone.now() - timedelta(minutes=5)

    # CREATE (POST)
    payload = {
        "device_id": "dev-123",
        "lat": 43.238293,
        "lng": 76.945465,
        "accuracy_m": 10,
        "speed_mps": 1.5,
        "bearing_deg": 180,
        "recorded_at": recorded_at.isoformat(),
        "provider": "gps",
        "battery": 88,
        "is_mock": False,
    }
    resp = api.post(pings_url(), payload, format="json")
    assert resp.status_code == 201, resp.content

    # точка создана и привязана к user из токена
    obj = GeoPing.objects.get()
    assert obj.user_id == partner.id
    assert obj.device is not None
    assert obj.device.device_id == "dev-123"
    assert float(obj.lat) == payload["lat"]
    assert float(obj.lng) == payload["lng"]

    # LIST (GET) по дате
    date_str = recorded_at.date().isoformat()
    resp = api.get(pings_url(), {"date": date_str})
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", data)
    assert len(results) == 1
    assert float(results[0]["lat"]) == payload["lat"]
    assert float(results[0]["lng"]) == payload["lng"]


@pytest.mark.django_db
def test_partner_cannot_see_other_users_pings(api):
    partner1 = make_user("partner", phone="77001230002", approved=True)
    partner2 = make_user("partner", phone="77001230003", approved=True)

    # создаём точку от имени partner2
    GeoPing.objects.create(
        user=partner2,
        lat=43.25, lng=76.91,
        recorded_at=timezone.now() - timedelta(minutes=30)
    )

    auth(api, partner1)
    # партнёр не должен видеть чужие точки, даже если подсунуть user_id
    resp = api.get(pings_url(), {"user_id": partner2.id})
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", data)
    assert results == [] or data.get("count", 0) == 0


@pytest.mark.django_db
def test_admin_can_list_any_user_by_range(api):
    admin = make_user("admin", phone="77001230004", approved=True)
    partner = make_user("partner", phone="77001230005", approved=True)

    t0 = timezone.now() - timedelta(hours=2)
    t1 = timezone.now() - timedelta(hours=1)
    t2 = timezone.now() - timedelta(minutes=10)

    GeoPing.objects.bulk_create([
        GeoPing(user=partner, lat=43.20, lng=76.90, recorded_at=t0),
        GeoPing(user=partner, lat=43.21, lng=76.91, recorded_at=t1),
        GeoPing(user=partner, lat=43.22, lng=76.92, recorded_at=t2),
    ])

    auth(api, admin)
    resp = api.get(pings_url(), {
        "user_id": partner.id,
        "start": (t1 - timedelta(minutes=5)).isoformat(),
        "end": (t2 - timedelta(minutes=5)).isoformat(),
    })
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", data)
    assert len(results) == 1
    assert float(results[0]["lat"]) == 43.21
    assert float(results[0]["lng"]) == 76.91


@pytest.mark.django_db
def test_device_autocreate_and_last_seen_update(api):
    partner = make_user("partner", phone="77001230006", approved=True)
    auth(api, partner)

    t1 = timezone.now() - timedelta(minutes=6)
    t2 = timezone.now() - timedelta(minutes=3)

    # первый пинг с device_id -> создаст устройство
    resp = api.post(pings_url(), {
        "device_id": "uuid-xyz",
        "lat": 43.23, "lng": 76.93,
        "recorded_at": t1.isoformat()
    }, format="json")
    assert resp.status_code == 201

    dev = GeoDevice.objects.get(user=partner, device_id="uuid-xyz")
    assert dev.last_seen is not None

    # второй пинг обновит last_seen
    resp = api.post(pings_url(), {
        "device_id": "uuid-xyz",
        "lat": 43.24, "lng": 76.94,
        "recorded_at": t2.isoformat()
    }, format="json")
    assert resp.status_code == 201

    dev.refresh_from_db()
    # last_seen должен быть не раньше t2
    assert dev.last_seen >= t2


@pytest.mark.django_db
def test_ordering_by_recorded_at(api):
    partner = make_user("partner", phone="77001230007", approved=True)
    auth(api, partner)

    t0 = timezone.now() - timedelta(minutes=15)
    t1 = timezone.now() - timedelta(minutes=10)
    t2 = timezone.now() - timedelta(minutes=5)

    GeoPing.objects.bulk_create([
        GeoPing(user=partner, lat=1, lng=1, recorded_at=t1),
        GeoPing(user=partner, lat=2, lng=2, recorded_at=t2),
        GeoPing(user=partner, lat=0, lng=0, recorded_at=t0),
    ])

    # без параметров — вернём по возрастанию recorded_at (как в Meta.ordering)
    resp = api.get(pings_url())
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", data)
    coords = [(float(r["lat"]), float(r["lng"])) for r in results]
    assert coords == [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]


@pytest.mark.django_db
def test_ping_update_and_delete_forbidden(api):
    partner = make_user("partner", approved=True)
    auth(api, partner)
    ping = GeoPing.objects.create(
        user=partner, lat=43.25, lng=76.91, recorded_at=timezone.now()
    )
    url = reverse("geo-pings-detail", args=[ping.id])
    resp = api.patch(url, {"lat": 50.0}, format="json")
    assert resp.status_code in (403, 405)
    resp = api.delete(url)
    assert resp.status_code in (403, 405)


@pytest.mark.django_db
def test_unauthenticated_access_forbidden(api):
    resp = api.get(pings_url())
    assert resp.status_code == 401


@pytest.mark.django_db
def test_list_by_week_period(api):
    partner = make_user("partner", approved=True)
    auth(api, partner)

    # якорь — среда
    anchor = date(2025, 9, 17)  # Wed
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)

    # точки: до недели, в неделе, после недели
    GeoPing.objects.bulk_create([
        GeoPing(user=partner, lat=0, lng=0, recorded_at=datetime.combine(monday - timedelta(days=1), time(9, 0), tzinfo=dt_timezone.utc)),
        GeoPing(user=partner, lat=1, lng=1, recorded_at=datetime.combine(monday, time(9, 0), tzinfo=dt_timezone.utc)),
        GeoPing(user=partner, lat=2, lng=2, recorded_at=datetime.combine(sunday, time(9, 0), tzinfo=dt_timezone.utc)),
        GeoPing(user=partner, lat=3, lng=3, recorded_at=datetime.combine(sunday + timedelta(days=1), time(9, 0), tzinfo=dt_timezone.utc)),
    ])

    resp = api.get(pings_url(), {"period": "week", "anchor": anchor.isoformat()})
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", data)
    coords = [(float(r["lat"]), float(r["lng"])) for r in results]
    assert coords == [(1.0, 1.0), (2.0, 2.0)]
