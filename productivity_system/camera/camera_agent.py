"""
Camera presence (suudald baigaa esehiig) shalgah.
Zurag HADGALAHGUI, zuvhun is_at_desk + confidence hadgalna.

Heregtei: pip install opencv-python mediapipe
Ajilluulah: python -m camera.camera_agent <employee_id>
"""
import os
import sys
import time

import cv2
import django
import mediapipe as mp
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.consent import has_consent  # noqa: E402
from core.models import CameraAnalytics  # noqa: E402

INTERVAL = 30  # sekund buriin shalgalt


def main(employee_id):
    if not has_consent(employee_id, "camera"):
        print("Camera zuvshuurul baihgui. Zogsloo.")
        return

    pose = mp.solutions.pose.Pose(min_detection_confidence=0.5)
    cap = cv2.VideoCapture(0)
    print("Camera ehelle. Ctrl+C = zogsoh.")
    try:
        while True:
            ok, frame = cap.read()
            if ok:
                result = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                if result.pose_landmarks:
                    vis = [lm.visibility for lm in result.pose_landmarks.landmark]
                    conf, at_desk = sum(vis) / len(vis), True
                else:
                    conf, at_desk = 0.0, False
                CameraAnalytics.objects.create(
                    employee_id=employee_id,
                    observed_at=timezone.now(),
                    is_at_desk=at_desk,
                    confidence=round(min(max(conf, 0), 1), 3),
                )
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Ashiglalt: python -m camera.camera_agent <employee_id>")
        sys.exit(1)
    main(int(sys.argv[1]))
