"""Create the first administrator from the browser instead of a terminal command.

Enabled only when the local launcher started this server with WORKTRACK_SETUP_TOKEN, a random
secret it opens in this computer's browser, and only while no active administrator exists. The
token also stops other websites from posting to the local server and claiming the admin account.
Production servers never set the token, so this endpoint stays closed there.
"""

import hmac
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import User
from .operations import StrictSerializer, audit_event


def setup_token():
    return os.environ.get('WORKTRACK_SETUP_TOKEN', '')


def needs_admin():
    # Same check as the launcher's bootstrap.
    return not User.objects.filter(is_active=True, is_superuser=True).exists()


class FirstAdminInput(StrictSerializer):
    token = serializers.CharField(trim_whitespace=False, max_length=200)
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(trim_whitespace=False, max_length=256)
    confirm_password = serializers.CharField(trim_whitespace=False, max_length=256)


class FirstRunThrottle(AnonRateThrottle):
    scope = 'first_run'
    rate = '20/hour'


class FirstRunView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get_throttles(self):
        return [FirstRunThrottle()] if self.request.method == 'POST' else []

    def get(self, request):
        return Response({'needs_admin': needs_admin(), 'setup_available': bool(setup_token())})

    @transaction.atomic
    def post(self, request):
        expected = setup_token()
        if not expected:
            raise PermissionDenied('Анхны тохиргоо зөвхөн WorkTrack-ийг энэ компьютер дээр асаахад нээгдэнэ.')
        serializer = FirstAdminInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not hmac.compare_digest(data['token'].encode(), expected.encode()):
            raise PermissionDenied('Холбоос хүчингүй байна. WorkTrack-ийн нээсэн хуудсыг ашиглана уу.')
        if not needs_admin():
            raise PermissionDenied('Админ аль хэдийн үүссэн байна. Нэвтэрнэ үү.')
        username = data['username'].strip()
        try:
            User.username_validator(username)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {'username': 'Нэрэнд зөвхөн үсэг, тоо болон @ . + - _ тэмдэгт ашиглана уу.'}
            ) from exc
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError({'username': 'Энэ нэр аль хэдийн бүртгэлтэй байна.'})
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Нууц үгүүд ижил байх ёстой.'})
        user = User(username=username, role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        try:
            validate_password(data['password'], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages}) from exc
        user.set_password(data['password'])
        user.save()
        audit_event(user, 'user', user.pk, 'first_admin_created', {}, user)
        return Response({'detail': 'Админ үүслээ.', 'username': user.username}, status=201)
