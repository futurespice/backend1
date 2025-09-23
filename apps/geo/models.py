from django.db import models
from django.conf import settings

class GeoDevice(models.Model):
    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"
        WEB = "web", "Web"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="geo_devices")
    device_id = models.CharField(max_length=128)
    platform = models.CharField(max_length=16, choices=Platform.choices, default=Platform.ANDROID)
    last_seen = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("user", "device_id")]

class GeoPing(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="geo_pings")
    device = models.ForeignKey(GeoDevice, on_delete=models.SET_NULL, null=True, blank=True, related_name="pings")

    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_m = models.IntegerField(null=True, blank=True)
    speed_mps = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    bearing_deg = models.IntegerField(null=True, blank=True)

    recorded_at = models.DateTimeField()            # время на устройстве
    received_at = models.DateTimeField(auto_now_add=True)

    provider = models.CharField(max_length=32, null=True, blank=True)  # gps/network
    battery = models.PositiveSmallIntegerField(null=True, blank=True)
    is_mock = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["user", "recorded_at"]),
            models.Index(fields=["recorded_at"]),
        ]
        ordering = ["recorded_at"]
