from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AuditLog, ConsentRecord, Device
from .serializers import AuditLogSerializer, ConsentRecordSerializer, DeviceSerializer, UserSerializer
from .permissions import IsSystemAdmin
from .audit import audit_value, write_audit


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

    def perform_create(self, serializer):
        with transaction.atomic():
            user = serializer.save()
            write_audit(self.request, entity_type="user", instance=user, action="create",
                         fields=("username", "email", "first_name", "last_name", "role", "department_id", "is_active"))

    def perform_update(self, serializer):
        instance = serializer.instance
        next_active = serializer.validated_data.get("is_active", instance.is_active)
        next_role = serializer.validated_data.get("role", instance.role)
        remains_admin = instance.is_superuser or next_role == User.Role.ADMIN
        if instance.is_active and instance.is_admin_role and (not next_active or not remains_admin):
            other_admins = User.objects.filter(is_active=True).exclude(pk=instance.pk).filter(
                models.Q(role=User.Role.ADMIN) | models.Q(is_superuser=True)
            )
            if not other_admins.exists():
                raise ValidationError("The last active administrator cannot be deactivated or demoted.")
        fields = ("username", "email", "first_name", "last_name", "role", "department_id", "is_active")
        before = {field: audit_value(getattr(instance, field, None)) for field in fields}
        with transaction.atomic():
            user = serializer.save()
            write_audit(self.request, entity_type="user", instance=user, action="update", before=before, fields=fields)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise PermissionDenied("You cannot delete your own account.")
        if instance.is_active and instance.is_admin_role and not User.objects.filter(
            is_active=True, role=User.Role.ADMIN
        ).exclude(pk=instance.pk).exists() and not User.objects.filter(
            is_active=True, is_superuser=True
        ).exclude(pk=instance.pk).exists():
            raise ValidationError("The last active administrator cannot be deleted.")
        with transaction.atomic():
            write_audit(self.request, entity_type="user", instance=instance, action="delete",
                         fields=("username", "email", "role", "department_id", "is_active"))
            instance.delete()

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

    @transaction.atomic
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
        AuditLog.objects.create(
            actor=request.user, actor_label=request.user.get_username(),
            target_user=request.user, target_label=request.user.get_username(),
            entity_type="consent", entity_id=str(record.pk), action="grant",
            changes={"policy_version": {"new": record.policy_version}},
        )
        return Response(self.get_serializer(record).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    @action(detail=False, methods=["post"])
    def revoke(self, request):
        active_records = ConsentRecord.objects.filter(employee=request.user, granted=True, revoked_at__isnull=True)
        revoked = active_records.update(revoked_at=timezone.now())
        if revoked:
            AuditLog.objects.create(
                actor=request.user, actor_label=request.user.get_username(),
                target_user=request.user, target_label=request.user.get_username(),
                entity_type="consent", entity_id="self", action="revoke",
                changes={"revoked_records": {"new": revoked}},
            )
        return Response({"revoked": revoked})

    @action(detail=False, methods=["get"])
    def status(self, request):
        record = ConsentRecord.objects.filter(employee=request.user).first()
        return Response({
            "active": bool(record and record.is_active),
            "latest": self.get_serializer(record).data if record else None,
            "retention_days": settings.ACTIVITY_RETENTION_DAYS,
            "backup_retention_days": settings.BACKUP_KEEP,
            "retention_automatic": settings.ACTIVITY_RETENTION_AUTO,
        })


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Administrative audit history; never exposes write endpoints."""
    serializer_class = AuditLogSerializer
    permission_classes = [IsSystemAdmin]
    queryset = AuditLog.objects.select_related("actor", "target_user").all()


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

