from django.db import connection, transaction, IntegrityError
from django.db.models import Avg, Count, Q
from django.db.models.deletion import ProtectedError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import extend_schema
from .models import Department, Employee, Workstation, ConsentRecord, Task, ComputerActivity, CameraObservation, ProductivityScore
from .serializers import (UserSerializer, UserCreateSerializer, DepartmentSerializer, EmployeeSerializer,
    WorkstationSerializer, ConsentSerializer, TaskSerializer, ActivitySerializer, ActivityBatchSerializer,
    ObservationSerializer, ScoreSerializer, ScoreCalculateSerializer, ReportQuerySerializer)
from .access import AdminOnly, AdminWrite, is_admin, visible_employees
from .services import calculate_score

class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    @extend_schema(responses={200: {'type': 'object', 'properties': {'status': {'type': 'string'}}}})
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        except Exception:
            return Response({'status': 'unavailable'}, status=503)
        return Response({'status': 'ok'})

class UserViewSet(viewsets.GenericViewSet):
    serializer_class = UserCreateSerializer
    permission_classes = [AdminOnly]
    @extend_schema(responses=UserSerializer)
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=201)
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], serializer_class=UserSerializer)
    def me(self, request):
        return Response(UserSerializer(request.user).data)

class SafeModelViewSet(viewsets.ModelViewSet):
    permission_classes = [AdminWrite]
    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            raise ValidationError('Record is referenced by other records; deactivate its user instead.')

class DepartmentViewSet(SafeModelViewSet):
    queryset = Department.objects.none()
    serializer_class = DepartmentSerializer
    def get_queryset(self):
        qs = Department.objects.order_by('id')
        return qs if is_admin(self.request.user) else qs.filter(id__in=visible_employees(self.request.user).values('department_id'))

class EmployeeViewSet(SafeModelViewSet):
    queryset = Employee.objects.none()
    serializer_class = EmployeeSerializer
    def get_queryset(self):
        return visible_employees(self.request.user).order_by('id')

class WorkstationViewSet(SafeModelViewSet):
    queryset = Workstation.objects.none()
    serializer_class = WorkstationSerializer
    def get_queryset(self):
        return Workstation.objects.filter(employee__in=visible_employees(self.request.user)).order_by('id')
    def perform_update(self, serializer):
        if serializer.validated_data.get('employee', serializer.instance.employee) != serializer.instance.employee:
            raise ValidationError('Create a new workstation record to reassign an employee; preserve historical ownership.')
        serializer.save()

class TaskViewSet(SafeModelViewSet):
    queryset = Task.objects.none()
    serializer_class = TaskSerializer
    def get_queryset(self):
        return Task.objects.filter(employee__in=visible_employees(self.request.user)).select_related('employee')

class ConsentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ConsentRecord.objects.none()
    serializer_class = ConsentSerializer
    def get_queryset(self):
        # Managers can see department reports, but not grant employees consent.
        return ConsentRecord.objects.filter(employee__in=visible_employees(self.request.user))
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data['employee'].user_id != request.user.id:
            raise PermissionDenied('Only the employee can grant or revoke their consent.')
        with transaction.atomic():
            Employee.objects.select_for_update().get(pk=serializer.validated_data['employee'].pk)
            serializer.save()
        return Response(serializer.data, status=201)

class ActivityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ComputerActivity.objects.none()
    serializer_class = ActivitySerializer
    def get_queryset(self):
        return ComputerActivity.objects.filter(employee__in=visible_employees(self.request.user))
    @extend_schema(request=ActivityBatchSerializer, responses={201: ActivitySerializer(many=True)})
    @action(detail=False, methods=['post'], url_path='batch')
    def batch(self, request):
        try:
            with transaction.atomic():
                # Serialize submissions per employee, including validation of overlapping intervals.
                list(Employee.objects.select_for_update().filter(pk__in=visible_employees(request.user).values('pk')).order_by('pk'))
                serializer = ActivityBatchSerializer(data=request.data, context={'request': request})
                serializer.is_valid(raise_exception=True)
                saved = ComputerActivity.objects.bulk_create([ComputerActivity(**item) for item in serializer.validated_data['events']])
        except IntegrityError:
            raise ValidationError('Duplicate event_id or invalid relationship; no events were saved.')
        return Response(ActivitySerializer(saved, many=True).data, status=201)

class ObservationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CameraObservation.objects.none()
    serializer_class = ObservationSerializer
    def get_permissions(self):
        return [AdminOnly()] if self.action == 'create' else super().get_permissions()
    def get_queryset(self):
        return CameraObservation.objects.filter(employee__in=visible_employees(self.request.user))
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise ValidationError('Duplicate event_id or invalid relationship.')
        return Response(serializer.data, status=201)

class ScoreViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProductivityScore.objects.none()
    serializer_class = ScoreSerializer
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ProductivityScore.objects.none()
        qs = ProductivityScore.objects.filter(employee__in=visible_employees(self.request.user))
        params = ReportQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        for field in ('start', 'end'):
            if field in self.request.query_params:
                qs = qs.filter(**{'date__gte' if field == 'start' else 'date__lte': params.validated_data[field]})
        return qs
    @extend_schema(request=ScoreCalculateSerializer, responses=ScoreSerializer)
    @action(detail=False, methods=['post'], permission_classes=[AdminOnly])
    def calculate(self, request):
        serializer = ScoreCalculateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        score = calculate_score(**serializer.validated_data)
        return Response(ScoreSerializer(score).data)

class ReportView(APIView):
    @extend_schema(parameters=[ReportQuerySerializer], responses={200: {'type': 'object', 'additionalProperties': True}})
    def get(self, request):
        params = ReportQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        employees = visible_employees(request.user)
        if 'department' in data:
            employees = employees.filter(department_id=data['department'])
        scores = ProductivityScore.objects.filter(employee__in=employees, date__range=(data['start'], data['end']))
        tasks = Task.objects.filter(employee__in=employees, due_at__date__range=(data['start'], data['end']))
        completed = tasks.filter(status='done', completed_at__date__lte=data['end']).count()
        total = tasks.count()
        from django.db.models.functions import TruncWeek, TruncMonth
        return Response({
            'start': data['start'], 'end': data['end'], 'employee_count': employees.count(),
            'score_count': scores.count(), 'average_score': scores.aggregate(value=Avg('p'))['value'],
            'task_count': total, 'completed_tasks': completed, 'task_completion_percent': round(100*completed/total, 2) if total else 0,
            'daily': list(scores.values('date').annotate(average_score=Avg('p'), count=Count('id')).order_by('date')),
            'weekly': list(scores.annotate(period=TruncWeek('date')).values('period').annotate(average_score=Avg('p')).order_by('period')),
            'monthly': list(scores.annotate(period=TruncMonth('date')).values('period').annotate(average_score=Avg('p')).order_by('period')),
            'departments': list(scores.values('employee__department_id', 'employee__department__name').annotate(average_score=Avg('p'), count=Count('id')).order_by('employee__department_id')),
            'workload': list(tasks.values('employee_id').annotate(total=Count('id'), done=Count('id', filter=Q(status='done', completed_at__date__lte=data['end']))).order_by('employee_id')),
        })
