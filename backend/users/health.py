import logging
from django.core.cache import cache
from django.conf import settings
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

log = logging.getLogger(__name__)


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            cache.set('worktrack-health', True, 30)
            if cache.get('worktrack-health') is not True:
                raise RuntimeError('Cache round trip failed.')
            from .operations import current_settings

            policy = current_settings()
        except Exception:
            log.exception('Readiness check failed')
            return Response({'status': 'unavailable'}, status=503)
        data = {
            'status': 'ok',
            'service': 'worktrack-api',
            'protocol': 1,
            'source_digest': settings.BACKEND_SOURCE_DIGEST,
            'workspace_id': settings.BACKEND_WORKSPACE_ID,
        }
        if settings.WORKTRACK_DEMO:
            # Only in the separate demo database: the example accounts, for one-click sign-in.
            from activity.management.commands.seed_demo import PASSWORD

            data['demo'] = {
                'password': PASSWORD,
                'accounts': [
                    {'username': 'demo-admin', 'label': 'Админ', 'name': 'Болд'},
                    {'username': 'demo-manager', 'label': 'Менежер', 'name': 'Ганаа'},
                    {'username': 'bat', 'label': 'Ажилтан', 'name': 'Бат'},
                ],
            }
        if policy.client_version and policy.client_download_url:
            # Employee apps read this to offer an update (desktop/updates.py).
            data['client'] = {'version': policy.client_version, 'download_url': policy.client_download_url}
        return Response(data)
