from .models import ConsentRecord


def has_consent(employee_id, consent_type):
    """Zuvshuurul ugsun esehiig shalgana. Zuvshuurul baihgui bol data tsugluulahgui."""
    return ConsentRecord.objects.filter(
        employee_id=employee_id, consent_type=consent_type, is_granted=True
    ).exists()
