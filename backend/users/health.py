import logging
from django.core.cache import cache
from django.conf import settings
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

log=logging.getLogger(__name__)


class HealthView(APIView):
    permission_classes=[AllowAny]
    authentication_classes=[]

    def get(self,request):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            cache.set('worktrack-health',True,30)
            if cache.get('worktrack-health') is not True:
                raise RuntimeError('Cache round trip failed.')
        except Exception:
            log.exception('Readiness check failed')
            return Response({'status':'unavailable'},status=503)
        return Response({'status':'ok','service':'worktrack-api','protocol':1,'source_digest':settings.BACKEND_SOURCE_DIGEST,'workspace_id':settings.BACKEND_WORKSPACE_ID})
