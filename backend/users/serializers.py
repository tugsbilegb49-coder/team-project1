from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import ConsentRecord, Device


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    is_admin = serializers.BooleanField(source='is_admin_role', read_only=True)
    password = serializers.CharField(
        write_only=True, required=False, min_length=8, max_length=256, trim_whitespace=False
    )
    department_name = serializers.CharField(source='department.name', read_only=True)

    def validate_email(self, value):
        email = (value or '').strip().casefold()
        if not email:
            return ''
        duplicates = User.objects.filter(email__iexact=email)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError('This email is already used by another account.')
        return email

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'password',
            'first_name',
            'last_name',
            'email',
            'role',
            'is_admin',
            'department',
            'department_name',
            'is_active',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'A password is required.'})
        if attrs.get('password'):
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError

            try:
                validate_password(attrs['password'], self.instance or User(username=attrs.get('username', '')))
            except ValidationError as exc:
                raise serializers.ValidationError({'password': exc.messages})
        role = attrs.get('role', getattr(self.instance, 'role', User.Role.EMPLOYEE))
        department = attrs.get('department', getattr(self.instance, 'department', None))
        active = attrs.get('is_active', getattr(self.instance, 'is_active', True))
        if active and role == User.Role.MANAGER and department is None:
            raise serializers.ValidationError({'department': 'An active manager must belong to a department.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class ConsentRecordSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = ConsentRecord
        fields = ['id', 'employee', 'granted', 'policy_version', 'recorded_at', 'revoked_at', 'is_active']
        read_only_fields = ['id', 'employee', 'recorded_at', 'revoked_at', 'is_active']


class DeviceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.username', read_only=True)

    class Meta:
        model = Device
        fields = ['id', 'employee', 'employee_name', 'name', 'platform', 'enabled', 'created_at', 'last_seen_at']
        read_only_fields = ['id', 'employee', 'employee_name', 'created_at', 'last_seen_at']
