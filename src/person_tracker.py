"""
person_tracker.py
------------------
Wraps DeepSORT (via the `deep-sort-realtime` package) to assign a stable
track ID to each person across frames — needed for open-office / multi-desk
setups where several people are visible in the same camera feed.

Without this, YOLO alone gives you a fresh, unlabeled bounding box for each
person every frame, with no way to know "this is the same person as last
frame" — so you can't accumulate per-person time.
"""

from typing import List, Tuple, Dict
import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort


class PersonTracker:
    def __init__(self, max_age: int = 30):
        """
        max_age: number of consecutive missed frames before a track is
        dropped (handles brief occlusions without losing the person's ID).
        """
        self.tracker = DeepSort(max_age=max_age)

    def update(self, frame: np.ndarray, person_boxes: List[dict]) -> Dict[int, Tuple[float, float, float, float]]:
        """
        person_boxes: list of {"xyxy": [x1,y1,x2,y2], "confidence": float}
                      (only `person`-class detections — filter before calling)
        frame: the current BGR frame (used internally for appearance embedding)

        Returns: {track_id: (x1, y1, x2, y2)} for all currently confirmed tracks.
        """
        # deep_sort_realtime expects ([x, y, w, h], confidence, class_name)
        formatted = []
        for box in person_boxes:
            x1, y1, x2, y2 = box["xyxy"]
            formatted.append(([x1, y1, x2 - x1, y2 - y1], box["confidence"], "person"))

        tracks = self.tracker.update_tracks(formatted, frame=frame)

        result = {}
        for track in tracks:
            if not track.is_confirmed():
                continue
            x1, y1, x2, y2 = track.to_ltrb()
            result[track.track_id] = (x1, y1, x2, y2)
        return result
