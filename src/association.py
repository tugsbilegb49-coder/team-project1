"""
association.py
---------------
Pure geometry helpers to decide which tracked person a given "laptop" or
"cell phone" detection belongs to. Used in multi-person mode where several
people (and their objects) share one camera frame.

Strategy: assign each object to the person whose bounding box is nearest
(by center-point distance), but only if within a reasonable distance
relative to that person's box size — otherwise the object is considered
unassigned (e.g. a laptop on an empty desk with nobody sitting there).
"""

from typing import Dict, List, Optional, Tuple

BBox = Tuple[float, float, float, float]  # x1, y1, x2, y2


def _center(box: BBox) -> Tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2, (y1 + y2) / 2


def _diagonal(box: BBox) -> float:
    x1, y1, x2, y2 = box
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5


def _distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


def assign_objects_to_people(
    person_boxes: Dict[int, BBox],
    object_boxes: List[BBox],
    max_distance_ratio: float = 1.5,
) -> Dict[int, List[BBox]]:
    """
    person_boxes: {track_id: bbox}
    object_boxes: list of bboxes for a single object class (e.g. all phones)
    max_distance_ratio: an object can be assigned to a person only if the
        distance between their box centers is <= max_distance_ratio times
        that person's bounding-box diagonal. Prevents assigning a phone on
        the far side of the room to someone just because they're the
        "closest" of a distant set.

    Returns: {track_id: [assigned object boxes]}
    """
    assignments: Dict[int, List[BBox]] = {tid: [] for tid in person_boxes}
    if not person_boxes or not object_boxes:
        return assignments

    for obj_box in object_boxes:
        obj_center = _center(obj_box)
        best_id: Optional[int] = None
        best_dist = float("inf")

        for track_id, person_box in person_boxes.items():
            person_center = _center(person_box)
            dist = _distance(obj_center, person_center)
            limit = _diagonal(person_box) * max_distance_ratio
            if dist <= limit and dist < best_dist:
                best_dist = dist
                best_id = track_id

        if best_id is not None:
            assignments[best_id].append(obj_box)

    return assignments


def crop_box(frame, box: BBox, padding_ratio: float = 0.15):
    """Crop a (padded) region of `frame` corresponding to `box`. Used to run
    gaze estimation on just one person's region in multi-person mode."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    pad_x, pad_y = bw * padding_ratio, bh * padding_ratio

    x1 = max(0, int(x1 - pad_x))
    y1 = max(0, int(y1 - pad_y))
    x2 = min(w, int(x2 + pad_x))
    y2 = min(h, int(y2 + pad_y))

    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]
