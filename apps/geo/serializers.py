from rest_framework import serializers
from .models import GeoDevice, GeoPing

class GeoDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeoDevice
        fields = ["id", "user", "device_id", "platform", "last_seen", "is_active"]
        read_only_fields = ["id", "last_seen", "user"]

class GeoPingCreateSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = GeoPing
        fields = [
            "id", "lat", "lng", "accuracy_m", "speed_mps", "bearing_deg",
            "recorded_at", "provider", "battery", "is_mock",
            "device_id", "received_at"
        ]
        read_only_fields = ["id", "received_at"]

    def create(self, validated):
        request = self.context["request"]
        user = request.user  # игнорируем user из тела — берём из токена

        device = None
        device_id = validated.pop("device_id", None)
        if device_id:
            device, _ = GeoDevice.objects.get_or_create(
                user=user, device_id=device_id,
                defaults={"platform": "android"}
            )
            device.last_seen = validated.get("recorded_at")
            device.save(update_fields=["last_seen"])

        return GeoPing.objects.create(user=user, device=device, **validated)
