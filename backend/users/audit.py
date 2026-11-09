from django.contrib.auth import get_user_model

from .models import AuditLog


User = get_user_model()


def audit_value(value):
    if hasattr(value, "pk"):
        return value.pk
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def write_audit(request, *, entity_type, instance, action, before=None, fields=()):
    changes = {}
    for field in fields:
        old = before.get(field) if before is not None else None
        value = audit_value(getattr(instance, field, None))
        if before is None or old != value:
            changes[field] = {"old": old, "new": value} if before is not None else {"new": value}
    actor = request.user
    is_user = isinstance(instance, User)
    AuditLog.objects.create(
        actor=actor if actor.is_authenticated else None,
        actor_label=actor.get_username() if actor.is_authenticated else "system",
        target_user=instance if is_user else None,
        target_label=(instance.get_username() if is_user else str(instance))[:200],
        entity_type=entity_type,
        entity_id=str(instance.pk),
        action=action,
        changes=changes,
    )
