"""Self-service account setup and the signed-in employee's daily home."""

from datetime import datetime, time, timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from .models import ConsentRecord, Device, User
from .operations import StrictSerializer, audit_event


class PasswordInput(StrictSerializer):
    current_password = serializers.CharField(trim_whitespace=False, max_length=256)
    new_password = serializers.CharField(trim_whitespace=False, max_length=256)
    confirm_password = serializers.CharField(trim_whitespace=False, max_length=256)


class PasswordThrottle(UserRateThrottle):
    rate = '5/minute'


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PasswordThrottle]

    @transaction.atomic
    def post(self, request):
        serializer = PasswordInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.select_for_update().get(pk=request.user.pk)
        if not user.check_password(data['current_password']):
            raise serializers.ValidationError({'current_password': 'Одоогийн нууц үг буруу байна.'})
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Шинэ нууц үгүүд ижил байх ёстой.'})
        if data['new_password'] == data['current_password']:
            raise serializers.ValidationError({'new_password': 'Өмнөхөөс өөр нууц үг сонгоно уу.'})
        try:
            validate_password(data['new_password'], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': exc.messages}) from exc
        user.set_password(data['new_password'])
        user.save(update_fields=['password'])
        for token in OutstandingToken.objects.filter(user=user, expires_at__gt=timezone.now()).iterator():
            BlacklistedToken.objects.get_or_create(token=token)
        audit_event(user, 'user', user.pk, 'password_change', {}, user)
        return Response({'detail': 'Нууц үг солигдлоо. Шинэ нууц үгээр дахин нэвтэрнэ үү.'})


class LinkInput(StrictSerializer):
    name = serializers.CharField(max_length=120)
    platform = serializers.CharField(max_length=40)
    consent = serializers.BooleanField()
    policy_version = serializers.ChoiceField(choices=['2026-11'])


class DesktopLinkView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = LinkInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data['consent']:
            raise serializers.ValidationError({'consent': 'Бүртгэл эхлүүлэхийн өмнө зөвшөөрлөө сонгоно уу.'})
        from activity.validation import lock_employee

        lock_employee(request.user)
        latest = ConsentRecord.objects.filter(employee=request.user).first()
        if not latest or not latest.is_active:
            record = ConsentRecord.objects.create(
                employee=request.user, granted=True, policy_version=data['policy_version']
            )
            audit_event(
                request.user, 'consent', record.pk, 'grant', {'policy_version': record.policy_version}, request.user
            )
        device, _ = Device.objects.update_or_create(
            employee=request.user,
            name=data['name'],
            defaults={'platform': data['platform'], 'enabled': True, 'last_seen_at': timezone.now()},
        )
        refresh = RefreshToken.for_user(request.user)
        audit_event(request.user, 'device', device.pk, 'link', {}, request.user)
        response = Response(
            {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'device_id': str(device.pk),
                'user_id': request.user.pk,
                'username': request.user.username,
            }
        )
        response['Cache-Control'] = 'no-store'
        return response


class MyTodayView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from activity.charts import day_timeline, outside_schedule_seconds, time_split
        from activity.schedule import Schedule

        schedule = Schedule.current()
        from activity.models import ComputerActivity
        from workforce.models import Task

        today = timezone.localdate()
        begin = timezone.make_aware(datetime.combine(today, time.min))
        end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))
        events = ComputerActivity.objects.filter(employee=request.user, started_at__gte=begin, started_at__lt=end)
        apps = list(
            events.values('application').annotate(seconds=Sum('duration_seconds')).order_by('-seconds', 'application')
        )
        total_seconds = sum(row['seconds'] for row in apps)
        idle_seconds = sum(row['seconds'] for row in apps if row['application'].casefold() == 'idle')
        latest = events.order_by('-started_at').values('application', 'started_at').first()
        tasks = Task.objects.filter(employee=request.user).exclude(status=Task.Status.DONE).order_by('due_date', 'id')
        return Response(
            {
                'date': str(today),
                'tracked_seconds': total_seconds,
                'application_seconds': total_seconds - idle_seconds,
                'idle_seconds': idle_seconds,
                'applications': apps[:20],
                'latest_application': latest,
                'open_tasks': tasks.count(),
                'overdue_tasks': tasks.filter(due_date__lt=today).count(),
                'tasks': list(tasks.values('id', 'title', 'status', 'due_date')[:10]),
                'split': time_split(request.user, today),
                'timeline': day_timeline(request.user, today),
                'schedule': schedule.as_dict(),
                'outside_schedule_seconds': outside_schedule_seconds(request.user, today, schedule),
            }
        )
