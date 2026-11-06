"""Login throttling and authenticated refresh-token revocation."""
import hashlib

from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView


class LoginIPThrottle(SimpleRateThrottle):
    scope = 'login_ip'

    def get_cache_key(self, request, view):
        # Do not trust a user-supplied X-Forwarded-For header. Configure a trusted
        # reverse proxy before adapting this for deployment behind one.
        identity = request.META.get('REMOTE_ADDR', 'unknown')
        return self.cache_format % {'scope': self.scope, 'ident': identity}


class LoginAccountThrottle(SimpleRateThrottle):
    scope = 'login_account'

    def get_cache_key(self, request, view):
        username = request.data.get('username') if isinstance(request.data, dict) else None
        if not isinstance(username, str) or not username.strip():
            return None
        identity = hashlib.sha256(username.strip().casefold().encode()).hexdigest()
        return self.cache_format % {'scope': self.scope, 'ident': identity}


class LoginView(TokenObtainPairView):
    throttle_classes = [LoginIPThrottle, LoginAccountThrottle]


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(trim_whitespace=False)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data['refresh'])
        except TokenError as exc:
            raise serializers.ValidationError({'refresh': 'Invalid, expired or revoked refresh token.'}) from exc
        user_id = getattr(request.user, api_settings.USER_ID_FIELD)
        if str(token.get(api_settings.USER_ID_CLAIM)) != str(user_id):
            raise PermissionDenied('You may only revoke your own refresh token.')
        token.blacklist()
        return Response(status=status.HTTP_204_NO_CONTENT)
