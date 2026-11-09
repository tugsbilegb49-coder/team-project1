"""Forgotten passwords without e-mail: the admin hands out a one-time code, the employee sets a new password.

The admin never learns the new password. A code has 60 random bits, is stored only as a hash, works
once within 24 hours, and the reset page shares the login throttles, so it cannot be guessed.
"""

from datetime import timedelta
import hashlib
import hmac
import secrets

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .auth import LoginAccountThrottle, LoginIPThrottle
from .models import PasswordResetCode, User
from .operations import StrictSerializer, audit_event

ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # No 0/O or 1/I to mix up when read aloud.
LENGTH = 12
VALID_FOR = timedelta(hours=24)
WRONG = 'Код буруу эсвэл хугацаа нь дууссан байна. Админаас шинэ код аваарай.'


def normalize(code):
    return ''.join(code.split()).replace('-', '').upper()


def digest(code):
    return hashlib.sha256(normalize(code).encode()).hexdigest()


def revoke_sessions(user):
    for token in OutstandingToken.objects.filter(user=user, expires_at__gt=timezone.now()).iterator():
        BlacklistedToken.objects.get_or_create(token=token)


@transaction.atomic
def issue(user, admin):
    """A new code for `user`; earlier unused codes stop working."""
    code = ''.join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    PasswordResetCode.objects.filter(user=user).delete()
    row = PasswordResetCode.objects.create(
        user=user, code_hash=digest(code), created_by=admin, expires_at=timezone.now() + VALID_FOR
    )
    audit_event(admin, 'user', user.pk, 'password_reset_code', {}, user)
    return '-'.join(code[i : i + 4] for i in range(0, LENGTH, 4)), row.expires_at


class ResetInput(StrictSerializer):
    username = serializers.CharField(max_length=150)
    code = serializers.CharField(max_length=40)
    new_password = serializers.CharField(trim_whitespace=False, max_length=256)
    confirm_password = serializers.CharField(trim_whitespace=False, max_length=256)


class PasswordResetWithCodeView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginIPThrottle, LoginAccountThrottle]

    @transaction.atomic
    def post(self, request):
        serializer = ResetInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.select_for_update().filter(username=data['username'].strip(), is_active=True).first()
        expected = digest(data['code'])
        rows = PasswordResetCode.objects.filter(user=user, expires_at__gt=timezone.now()) if user else []
        row = next((row for row in rows if hmac.compare_digest(row.code_hash, expected)), None)
        if row is None:
            raise serializers.ValidationError({'code': WRONG})
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Шинэ нууц үгүүд ижил байх ёстой.'})
        try:
            validate_password(data['new_password'], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': exc.messages}) from exc
        user.set_password(data['new_password'])
        user.save(update_fields=['password'])
        PasswordResetCode.objects.filter(user=user).delete()
        revoke_sessions(user)
        audit_event(user, 'user', user.pk, 'password_reset', {}, user)
        return Response({'detail': 'Нууц үг шинэчлэгдлээ. Шинэ нууц үгээрээ нэвтэрнэ үү.'})
