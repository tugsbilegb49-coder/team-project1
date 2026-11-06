"""Server-controlled application classification for aggregate agent batches."""
from django.conf import settings


def normalized_name(name):
    value = name.strip().replace('\\', '/').rsplit('/', 1)[-1].casefold()
    for suffix in ('.exe', '.app'):
        if value.endswith(suffix):
            value = value[:-len(suffix)]
    return value


def category_for_application(name):
    key = normalized_name(name)
    if key in {normalized_name(item) for item in settings.PRODUCTIVE_APPLICATIONS}:
        return 'WORK'
    if key in {'safari','chrome','google chrome','chromium','firefox','arc','msedge','microsoft edge'}:
        return 'BROWSER'
    if key in {'slack','teams','microsoft teams','zoom','discord'}:
        return 'COMMUNICATION'
    return 'OTHER'
