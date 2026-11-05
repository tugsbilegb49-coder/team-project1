from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ActivityEvent, ComputerActivity
from .serializers import (
    ActivityEventIngestSerializer,
    ActivityEventSerializer,
    ComputerActivityIngestSerializer,
    ComputerActivitySerializer,
)
from users.permissions import IsSystemAdmin
from users.models import ConsentRecord, Device


def _resolve_device(request, validated_data):
    device_id = validated_data.pop("device_id", None)
    if not device_id:
        return None
    try:
        device = Device.objects.get(pk=device_id, employee=request.user, enabled=True)
    except Device.DoesNotExist as exc:
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("This device is not enrolled for the current user.") from exc
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])
    return device


def _require_consent(request):
    if not getattr(settings, "REQUIRE_MONITORING_CONSENT", False):
        return
    if not ConsentRecord.objects.filter(employee=request.user, granted=True, revoked_at__isnull=True).exists():
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("Active monitoring consent is required before data can be uploaded.")


class ActivityEventViewSet(viewsets.ModelViewSet):
    serializer_class = ActivityEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = ActivityEvent.objects.select_related("employee", "employee__department")
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
    def ingest(self, request):
        """Accept a camera segment for the authenticated user's own account."""
        _require_consent(request)
        serializer = ActivityEventIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        device = _resolve_device(request, data)
        activity, created = ActivityEvent.objects.get_or_create(
            employee=request.user,
            source_person_id="",
            device=device,
            **data,
        )
        return Response(
            ActivityEventSerializer(activity).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ComputerActivityViewSet(viewsets.ModelViewSet):
    serializer_class = ComputerActivitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = ComputerActivity.objects.select_related("employee", "employee__department")
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
    def ingest(self, request):
        """Accept one segment from the authenticated user's own desktop agent."""
        _require_consent(request)
        serializer = ComputerActivityIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        device = _resolve_device(request, data)
        activity, created = ComputerActivity.objects.get_or_create(
            employee=request.user,
            device=device,
            **data,
        )
        return Response(
            ComputerActivitySerializer(activity).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

