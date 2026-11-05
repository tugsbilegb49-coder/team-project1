from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import ConsentRecord, Device


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "password", "first_name", "last_name", "email",
            "role", "department", "department_name", "is_active",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class ConsentRecordSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = ConsentRecord
        fields = ["id", "employee", "granted", "policy_version", "recorded_at", "revoked_at", "is_active"]
        read_only_fields = ["id", "employee", "recorded_at", "revoked_at", "is_active"]


class DeviceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.username", read_only=True)

    class Meta:
        model = Device
        fields = ["id", "employee", "employee_name", "name", "platform", "enabled", "created_at", "last_seen_at"]
        read_only_fields = ["id", "employee", "employee_name", "created_at", "last_seen_at"]

