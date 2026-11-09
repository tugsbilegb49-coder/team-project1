"""The WorkTrack program version, shown to the admin per device and compared with the server's latest."""

VERSION = '1.0.0'


def parse(value):
    """'1.2.10' -> (1, 2, 10); None for anything else."""
    try:
        parts = tuple(int(part) for part in str(value).split('.'))
    except ValueError:
        return None
    return parts if 1 <= len(parts) <= 4 and all(part >= 0 for part in parts) else None


def is_newer(candidate, current=VERSION):
    new, old = parse(candidate), parse(current)
    if not new or not old:
        return False
    width = max(len(new), len(old))
    return new + (0,) * (width - len(new)) > old + (0,) * (width - len(old))
