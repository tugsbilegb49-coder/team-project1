from .models import ConsentRecord


def has_consent(employee_id, consent_type):
    """Return the latest consent decision; a revocation overrides older grants."""
    latest_decision = (
        ConsentRecord.objects.filter(
            employee_id=employee_id,
            consent_type=consent_type,
        )
        .order_by("-pk")
        .values_list("is_granted", flat=True)
        .first()
    )
    return latest_decision is True
