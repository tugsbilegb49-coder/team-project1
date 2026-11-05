"""
Unit tests for src/gaze.py's pure math: the rotation-matrix-to-Euler-angle
conversion and the solvePnP-based head pose estimate, using synthetic
landmark data (no camera or MediaPipe model inference required).
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from src.gaze import _rotation_matrix_to_euler, estimate_head_pose, _MODEL_POINTS_3D, _LANDMARK_IDS
import cv2


class FakeLandmark:
    def __init__(self, x, y, z=0.0):
        self.x = x
        self.y = y
        self.z = z


def _project_model_points_to_landmarks(frame_shape, rvec, tvec, focal_length=None):
    """Helper: project the same 3D model points used by gaze.py through a
    known rotation/translation to synthesize a consistent set of 2D
    landmarks, so we can check that estimate_head_pose recovers the same
    rotation we put in."""
    h, w = frame_shape[:2]
    focal_length = focal_length or w
    center = (w / 2, h / 2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1],
    ], dtype=np.float64)
    dist_coeffs = np.zeros((4, 1))

    image_points, _ = cv2.projectPoints(_MODEL_POINTS_3D, rvec, tvec, camera_matrix, dist_coeffs)
    image_points = image_points.reshape(-1, 2)

    # Build a 468-ish landmark list with just the 6 indices gaze.py reads,
    # normalized to [0, 1] as MediaPipe landmarks are.
    max_index = max(_LANDMARK_IDS.values())
    landmarks = [FakeLandmark(0.5, 0.5) for _ in range(max_index + 1)]
    order = ["nose_tip", "chin", "left_eye_corner", "right_eye_corner",
             "left_mouth_corner", "right_mouth_corner"]
    for name, (px, py) in zip(order, image_points):
        landmarks[_LANDMARK_IDS[name]] = FakeLandmark(px / w, py / h)
    return landmarks


def test_identity_rotation_gives_near_zero_angles():
    rmat = np.eye(3)
    pitch, yaw, roll = _rotation_matrix_to_euler(rmat)
    assert abs(pitch) < 1e-6
    assert abs(yaw) < 1e-6
    assert abs(roll) < 1e-6


def test_estimate_head_pose_recovers_frontal_pose():
    frame_shape = (480, 640)
    tvec = np.array([[0.0], [0.0], [500.0]])  # face 500mm in front of camera
    rvec = np.array([[0.0], [0.0], [0.0]])    # no rotation -> looking straight ahead

    landmarks = _project_model_points_to_landmarks(frame_shape, rvec, tvec)
    pose = estimate_head_pose(landmarks, frame_shape)

    assert pose is not None
    assert abs(pose.pitch) < 5.0
    assert abs(pose.yaw) < 5.0


def test_estimate_head_pose_detects_downward_pitch():
    frame_shape = (480, 640)
    tvec = np.array([[0.0], [0.0], [500.0]])
    # Rotate ~30 degrees around the X axis -> head pitched down
    rvec = np.array([[np.radians(30)], [0.0], [0.0]])

    landmarks = _project_model_points_to_landmarks(frame_shape, rvec, tvec)
    pose = estimate_head_pose(landmarks, frame_shape)

    assert pose is not None
    assert pose.pitch > 15.0  # clearly pitched down, well above our 15-deg threshold
