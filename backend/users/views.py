from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ConsentRecord, Device
from .serializers import ConsentRecordSerializer, DeviceSerializer, UserSerializer
from .permissions import IsSystemAdmin


User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = User.objects.select_related("department").order_by("username")
        if user.is_admin_role:
            return queryset
        if user.is_manager and user.department_id:
            return queryset.filter(department=user.department)
        return queryset.filter(pk=user.pk)

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsSystemAdmin()]
        return [IsAuthenticated()]

    @action(detail=False, methods=["get"])
    def me(self, request):
        return Response(self.get_serializer(request.user).data)


class ConsentRecordViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ConsentRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = ConsentRecord.objects.select_related("employee", "employee__department")
        if user.is_admin_role:
            return queryset
        if user.is_manager and user.department_id:
            return queryset.filter(employee__department_id=user.department_id)
        return queryset.filter(employee=user)

    @action(detail=False, methods=["post"])
    def grant(self, request):
        policy_version = request.data.get("policy_version")
        if not isinstance(policy_version, str) or not policy_version.strip():
            raise ValidationError({"policy_version": "A policy version is required."})
        record = ConsentRecord.objects.create(
            employee=request.user,
            granted=True,
            policy_version=policy_version.strip(),
        )
        return Response(self.get_serializer(record).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def revoke(self, request):
        active_records = ConsentRecord.objects.filter(employee=request.user, granted=True, revoked_at__isnull=True)
        revoked = active_records.update(revoked_at=timezone.now())
        return Response({"revoked": revoked})

    @action(detail=False, methods=["get"])
    def status(self, request):
        record = ConsentRecord.objects.filter(employee=request.user).first()
        return Response({
            "active": bool(record and record.is_active),
            "latest": self.get_serializer(record).data if record else None,
        })


class DeviceViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Device.objects.select_related("employee", "employee__department")
        if user.is_admin_role:
            return queryset
        if user.is_manager and user.department_id:
            return queryset.filter(employee__department_id=user.department_id)
        return queryset.filter(employee=user)

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsSystemAdmin()]
        return [IsAuthenticated()]

    @action(detail=False, methods=["post"])
    def enroll(self, request):
        name = request.data.get("name")
        platform = request.data.get("platform")
        if not isinstance(name, str) or not name.strip():
            raise ValidationError({"name": "A device name is required."})
        if not isinstance(platform, str) or not platform.strip():
            raise ValidationError({"platform": "A platform is required."})
        device, _ = Device.objects.update_or_create(
            employee=request.user,
            name=name.strip()[:120],
            defaults={"platform": platform.strip()[:40], "enabled": True, "last_seen_at": timezone.now()},
        )
        return Response(self.get_serializer(device).data, status=status.HTTP_201_CREATED)

