from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from .models import Department, Employee, Task, Workstation, ConsentRecord, ComputerActivity, CameraObservation, ProductivityScore

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'role']

class UserCreateSerializer(UserSerializer):
    password = serializers.CharField(write_only=True)
    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['password']
    def validate(self, attrs):
        try:
            validate_password(attrs['password'], get_user_model()(**{k:v for k,v in attrs.items() if k != 'password'}))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages})
        return attrs
    def create(self, validated_data):
        return get_user_model().objects.create_user(**validated_data)

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name']

class EmployeeSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    class Meta:
        model = Employee
        fields = ['id', 'user', 'user_details', 'department', 'position', 'expected_daily_minutes']

class WorkstationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workstation
        fields = ['id', 'code', 'employee', 'camera_id']

class ConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsentRecord
        fields = ['id', 'employee', 'activity_allowed', 'camera_allowed', 'recorded_at']
        read_only_fields = ['recorded_at']

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ['id', 'employee', 'title', 'description', 'started_at', 'due_at', 'completed_at', 'status', 'quality_score']
    def validate(self, attrs):
        def value(key):
            return attrs.get(key, getattr(self.instance, key, None))
        start, due, completed = value('started_at'), value('due_at'), value('completed_at')
        if start and due and due < start:
            raise serializers.ValidationError({'due_at': 'Must be on or after started_at.'})
        if completed and (completed < start or completed > timezone.now()):
            raise serializers.ValidationError({'completed_at': 'Must be between started_at and now.'})
        if (value('status') == Task.Status.DONE) != bool(completed):
            raise serializers.ValidationError('Done tasks require completed_at; unfinished tasks must omit it.')
        return attrs

class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ComputerActivity
        fields = ['id', 'event_id', 'employee', 'workstation', 'started_at', 'ended_at', 'application', 'category', 'active_seconds']
        extra_kwargs = {'event_id': {'required': True}}
    def validate(self, attrs):
        start, end = attrs['started_at'], attrs['ended_at']
        if end <= start or end > timezone.now():
            raise serializers.ValidationError('Activity interval must end after start and cannot be in the future.')
        if timezone.localdate(start) != timezone.localdate(end):
            raise serializers.ValidationError('Split activity at local midnight.')
        if attrs['active_seconds'] > (end-start).total_seconds():
            raise serializers.ValidationError({'active_seconds': 'Cannot exceed interval duration.'})
        return validate_collection(self, attrs, 'activity_allowed', start)

class ActivityBatchSerializer(serializers.Serializer):
    events = ActivitySerializer(many=True, allow_empty=False, max_length=500)
    def validate_events(self, events):
        ids = [event['event_id'] for event in events]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError('Duplicate event_id in batch.')
        # Avoid counting the same employee time twice, including multiple workstations.
        for index, event in enumerate(events):
            if ComputerActivity.objects.filter(employee=event['employee'], started_at__lt=event['ended_at'], ended_at__gt=event['started_at']).exists():
                raise serializers.ValidationError('Activity interval overlaps an existing event.')
            for prior in events[:index]:
                if prior['employee'] == event['employee'] and prior['started_at'] < event['ended_at'] and prior['ended_at'] > event['started_at']:
                    raise serializers.ValidationError('Activity intervals overlap within batch.')
        return events

class ObservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CameraObservation
        fields = ['id', 'event_id', 'employee', 'workstation', 'observed_at', 'person_count', 'confidence']
        extra_kwargs = {'event_id': {'required': True}}
    def validate(self, attrs):
        if attrs['observed_at'] > timezone.now():
            raise serializers.ValidationError({'observed_at': 'Cannot be in the future.'})
        return validate_collection(self, attrs, 'camera_allowed', attrs['observed_at'])

def validate_collection(serializer, attrs, consent_field, event_time):
    from .access import is_admin
    employee = attrs['employee']
    user = serializer.context['request'].user
    if not is_admin(user) and employee.user_id != user.id:
        raise serializers.ValidationError({'employee': 'You can only submit your own activity.'})
    if attrs['workstation'].employee_id != employee.pk:
        raise serializers.ValidationError({'workstation': 'Workstation belongs to a different employee.'})
    latest = employee.consents.first()
    at_event = employee.consents.filter(recorded_at__lte=event_time).first()
    if not latest or not getattr(latest, consent_field) or not at_event or not getattr(at_event, consent_field):
        raise serializers.ValidationError('Consent is required both at event time and at submission time.')
    return attrs

class ScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductivityScore
        fields = ['id', 'employee', 'date', 't', 'q', 'd', 'w', 'p', 'level', 'calculated_at']
        read_only_fields = fields

class ScoreCalculateSerializer(serializers.Serializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    date = serializers.DateField()
    def validate_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError('Cannot calculate a future date.')
        return value

class ReportQuerySerializer(serializers.Serializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    department = serializers.IntegerField(required=False, min_value=1)
    def validate(self, attrs):
        end = attrs.setdefault('end', timezone.localdate())
        attrs.setdefault('start', end.replace(day=1))
        if attrs['start'] > end or (end-attrs['start']).days > 366:
            raise serializers.ValidationError('Date range must be ordered and at most 366 days.')
        return attrs
