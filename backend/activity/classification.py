"""Server-controlled application classification for aggregate agent batches."""


def normalized_name(name):
    value = name.strip().replace('\\', '/').rsplit('/', 1)[-1].casefold()
    for suffix in ('.exe', '.app'):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return value


def category_for_application(name, productive_apps=None):
    key = normalized_name(name)
    if productive_apps is None:
        from users.operations import current_settings

        productive_apps = current_settings().productive_apps
    if key in {normalized_name(item) for item in productive_apps}:
        return 'WORK'
    if key in {'safari', 'chrome', 'google chrome', 'chromium', 'firefox', 'arc', 'msedge', 'microsoft edge'}:
        return 'BROWSER'
    if key in {'slack', 'teams', 'microsoft teams', 'zoom', 'discord'}:
        return 'COMMUNICATION'
    return 'OTHER'
