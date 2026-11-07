"""macOS authorization is checked by our bundled host before OpenCV capture."""

import sys

WINDOWS_CAMERA_HELP = (
    'Camera нээгдсэнгүй. Windows Settings → Privacy & security → Camera дээр "Camera access" болон '
    '"Let desktop apps access your camera"-г асаана уу. Өөр програм camera ашиглаж байвал хаана уу.'
)


class CameraPermissionError(RuntimeError):
    pass


class CameraSessionCancelled(RuntimeError):
    pass


def check_session():
    try:
        import _worktrack_camera_host as host
    except ImportError:
        return
    if not host.session_active():
        raise CameraSessionCancelled('Camera session cancelled.')


def unopened_camera_error():
    """Windows reports a privacy block only as a camera that does not open; say how to allow it."""
    if sys.platform == 'win32':
        return CameraPermissionError(WINDOWS_CAMERA_HELP)
    return RuntimeError('Could not open webcam. Check camera permission and camera_index.')


def open_camera(index, permitted=None):
    check_session()
    if permitted is not None and not permitted():
        return None
    if sys.platform == 'darwin':
        try:
            import _worktrack_camera_host as host
        except ImportError as exc:
            raise CameraPermissionError('Camera-г main.py эсвэл WorkTrack-ийн Camera асаах товчоор нээнэ үү.') from exc
        status = host.permission_status()
        if status == 'not_determined':
            status = host.request_permission()
        if status != 'authorized':
            raise CameraPermissionError(
                'Camera зөвшөөрөгдөөгүй. System Settings → Privacy & Security → Camera → WorkTrack Camera-ийг зөвшөөрнө үү. ('
                + status
                + ')'
            )
    # The user may pause/revoke server consent while the OS prompt is pending.
    check_session()
    if permitted is not None and not permitted():
        return None
    import cv2

    return cv2.VideoCapture(index)
