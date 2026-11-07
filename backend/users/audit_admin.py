"""Bridge Django admin changes into the same append-only operational history."""
from django.db import transaction


class AuditedAdminMixin:
    audit_fields = ()
    audit_resource = ''

    def _subject(self, obj):
        return obj if obj._meta.model_name == 'user' else getattr(obj, 'employee', None)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        from .operations import audit_update, snapshot
        previous = self.model.objects.filter(pk=obj.pk).first() if change else None
        before = snapshot(previous, self.audit_fields) if previous else {}
        super().save_model(request, obj, form, change)
        audit_update(request.user, self.audit_resource, obj, before, self.audit_fields,
                     self._subject(obj), action='update' if change else 'create')
        request._worktrack_admin_saved = (self.audit_resource, obj.pk)

    def log_change(self, request, obj, message):
        result = super().log_change(request, obj, message)
        if getattr(request, '_worktrack_admin_saved', None) != (self.audit_resource, obj.pk):
            from .operations import audit_event
            # Password forms bypass save_model. Never copy messages or submitted values.
            audit_event(request.user, self.audit_resource, obj.pk, 'admin_change', {}, self._subject(obj))
        return result

    @transaction.atomic
    def delete_model(self, request, obj):
        from .operations import audit_event
        audit_event(request.user, self.audit_resource, obj.pk, 'delete', {}, self._subject(obj))
        super().delete_model(request, obj)

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        from .operations import audit_event
        for obj in queryset.iterator():
            audit_event(request.user, self.audit_resource, obj.pk, 'delete', {}, self._subject(obj))
        super().delete_queryset(request, queryset)
