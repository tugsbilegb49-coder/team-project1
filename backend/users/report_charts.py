"""Month comparisons for the «Тайлан» charts, within what the signed-in person may see."""

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.charts import month_comparison
from .monthly import ZONE, month_bounds
from .operations import visible_users


class ReportChartsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        month = request.query_params.get('month', timezone.now().astimezone(ZONE).strftime('%Y-%m'))
        start, end = month_bounds(month)
        people = list(
            visible_users(request.user).filter(is_active=True).select_related('department').order_by('username')
        )
        return Response({'month': month, **month_comparison(people, start, end)})
