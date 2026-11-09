"""The employee's own end-of-day rating (Бага / Дунд / Өндөр), the label for the AI experiment."""

from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DailySelfRating
from .operations import StrictSerializer


class RatingInput(StrictSerializer):
    label = serializers.ChoiceField(choices=DailySelfRating.Label.choices)


class SelfRatingView(APIView):
    """Today's rating of the signed-in person; it can be changed until the day ends."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        row = DailySelfRating.objects.filter(employee=request.user, date=today).first()
        return Response({'date': today, 'label': row.label if row else None})

    def put(self, request):
        serializer = RatingInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        today = timezone.localdate()
        DailySelfRating.objects.update_or_create(
            employee=request.user, date=today, defaults={'label': serializer.validated_data['label']}
        )
        return Response({'date': today, 'label': serializer.validated_data['label']})
