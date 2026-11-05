"""
gaze.py
-------
Head-pose estimation used to decide whether a person is actually looking at
a phone (head tilted down toward their hands) versus at a laptop screen
(head roughly level, facing forward) — even when a phone is visible
somewhere in the frame.

Unlike a crude "vertical landmark offset" trick, this uses the standard
6-point 3D face model + cv2.solvePnP approach to recover real yaw/pitch/roll
angles in degrees:

    1. Take 6 canonical 3D points on a generic face (nose tip, chin,
       left/right eye corners, left/right mouth corners) in an arbitrary
       head-centered coordinate system.
    2. Take the corresponding 2D pixel locations of those points from
       MediaPipe Face Mesh.
    3. Solve the Perspective-n-Point problem to recover the rotation
       (and translation) of the head relative to the camera.
    4. Convert the rotation matrix to Euler angles (pitch/yaw/roll).

This is a well-established technique and is dramatically more reliable than
2D landmark-offset heuristics, though it's still an approximation (it
assumes a generic face model and an approximate camera focal length, since
no calibration is performed at runtime).

Requires: mediapipe, opencv-python, numpy
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
import cv2

try:
    import mediapipe as mp
    _HAS_MEDIAPIPE = True
except ImportError:
    _HAS_MEDIAPIPE = False


# Generic 3D face model points (in mm, arbitrary head-centered frame).
# Order must match the MediaPipe landmark indices below.
_MODEL_POINTS_3D = np.array([
    (0.0, 0.0, 0.0),        # Nose tip
    (0.0, -63.6, -12.5),    # Chin
    (-43.3, 32.7, -26.0),   # Left eye, left corner
    (43.3, 32.7, -26.0),    # Right eye, right corner
    (-28.9, -28.9, -24.1),  # Left mouth corner
    (28.9, -28.9, -24.1),   # Right mouth corner
], dtype=np.float64)

# Corresponding MediaPipe Face Mesh landmark indices (468-point model).
_LANDMARK_IDS = {
    "nose_tip": 1,
    "chin": 152,
    "left_eye_corner": 33,
    "right_eye_corner": 263,
    "left_mouth_corner": 61,
    "right_mouth_corner": 291,
}


@dataclass
class HeadPose:
    pitch: float  # degrees, positive = looking down
    yaw: float    # degrees, positive = turned right
    roll: float   # degrees, positive = tilted right


def _rotation_matrix_to_euler(rmat: np.ndarray) -> Tuple[float, float, float]:
    """Convert a rotation matrix to pitch/yaw/roll in degrees."""
    sy = np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
    singular = sy < 1e-6

    # Note: given our face-model axis convention (Y-up, Z depth) combined
    # with OpenCV's Y-down image convention, the head "nod" (pitch) shows up
    # in the R[2,1]/R[2,2] term and the head "tilt" (roll) shows up in the
    # R[2,0] term — verified against a synthetic rotation in tests/test_gaze.py.
    if not singular:
        pitch = np.arctan2(rmat[2, 1], rmat[2, 2])
        yaw = np.arctan2(rmat[1, 0], rmat[0, 0])
        roll = np.arctan2(-rmat[2, 0], sy)
    else:
        pitch = np.arctan2(-rmat[1, 2], rmat[1, 1])
        yaw = 0.0
        roll = np.arctan2(-rmat[2, 0], sy)

    return np.degrees(pitch), np.degrees(yaw), np.degrees(roll)


def estimate_head_pose(landmarks, frame_shape: Tuple[int, int]) -> Optional[HeadPose]:
    """
    landmarks: MediaPipe FaceMesh landmark list for one face
               (result.multi_face_landmarks[i].landmark)
    frame_shape: (height, width) of the source frame

    Returns a HeadPose, or None if the pose couldn't be solved.
    """
    h, w = frame_shape[:2]

    image_points = np.array([
        (landmarks[_LANDMARK_IDS["nose_tip"]].x * w, landmarks[_LANDMARK_IDS["nose_tip"]].y * h),
        (landmarks[_LANDMARK_IDS["chin"]].x * w, landmarks[_LANDMARK_IDS["chin"]].y * h),
        (landmarks[_LANDMARK_IDS["left_eye_corner"]].x * w, landmarks[_LANDMARK_IDS["left_eye_corner"]].y * h),
        (landmarks[_LANDMARK_IDS["right_eye_corner"]].x * w, landmarks[_LANDMARK_IDS["right_eye_corner"]].y * h),
        (landmarks[_LANDMARK_IDS["left_mouth_corner"]].x * w, landmarks[_LANDMARK_IDS["left_mouth_corner"]].y * h),
        (landmarks[_LANDMARK_IDS["right_mouth_corner"]].x * w, landmarks[_LANDMARK_IDS["right_mouth_corner"]].y * h),
    ], dtype=np.float64)

    # Approximate camera intrinsics (no calibration available at runtime).
    focal_length = w
    center = (w / 2, h / 2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1],
    ], dtype=np.float64)
    dist_coeffs = np.zeros((4, 1))  # assume no lens distortion

    success, rotation_vec, _translation_vec = cv2.solvePnP(
        _MODEL_POINTS_3D, image_points, camera_matrix, dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        return None

    rmat, _ = cv2.Rodrigues(rotation_vec)
    pitch, yaw, roll = _rotation_matrix_to_euler(rmat)
    return HeadPose(pitch=pitch, yaw=yaw, roll=roll)


class GazeEstimator:
    """Runs MediaPipe Face Mesh + solvePnP head-pose estimation on frames
    or on cropped person regions (for multi-person mode)."""

    def __init__(self, downward_pitch_threshold: float = 15.0,
                 max_yaw_for_screen: float = 35.0):
        if not _HAS_MEDIAPIPE:
            raise ImportError(
                "mediapipe is required for gaze estimation. "
                "Install it with `pip install mediapipe`."
            )
        self.downward_pitch_threshold = downward_pitch_threshold
        self.max_yaw_for_screen = max_yaw_for_screen
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
        )

    def estimate(self, frame_bgr: np.ndarray) -> Optional[HeadPose]:
        results = self.face_mesh.process(frame_bgr[:, :, ::-1])  # BGR -> RGB
        if not results.multi_face_landmarks:
            return None
        return estimate_head_pose(results.multi_face_landmarks[0].landmark, frame_bgr.shape)

    def is_looking_down(self, frame_bgr: np.ndarray) -> Optional[bool]:
        """True if head is pitched down enough to suggest looking at
        something in the hands (e.g. a phone). None if no face found."""
        pose = self.estimate(frame_bgr)
        if pose is None:
            return None
        return pose.pitch > self.downward_pitch_threshold

    def is_facing_screen(self, frame_bgr: np.ndarray) -> Optional[bool]:
        """True if head is roughly level and forward-facing (consistent
        with looking at a laptop screen). None if no face found."""
        pose = self.estimate(frame_bgr)
        if pose is None:
            return None
        return (abs(pose.pitch) < self.downward_pitch_threshold and
                abs(pose.yaw) < self.max_yaw_for_screen)

    def close(self):
        self.face_mesh.close()


# Backwards-compatible alias used by earlier versions of this project.
GazeHeuristic = GazeEstimator
