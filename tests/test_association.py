"""
Unit tests for src/association.py — pure geometry, no camera/model needed.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.association import assign_objects_to_people, crop_box
import numpy as np


def test_assigns_laptop_to_nearest_person():
    person_boxes = {
        1: (0, 0, 100, 200),      # person A, left side
        2: (400, 0, 500, 200),    # person B, right side
    }
    laptop_boxes = [(10, 150, 90, 190)]  # close to person A

    result = assign_objects_to_people(person_boxes, laptop_boxes)
    assert result[1] == laptop_boxes
    assert result[2] == []


def test_object_too_far_is_unassigned():
    person_boxes = {1: (0, 0, 50, 50)}
    far_laptop = [(1000, 1000, 1050, 1050)]

    result = assign_objects_to_people(person_boxes, far_laptop)
    assert result[1] == []


def test_no_people_returns_empty_assignments():
    result = assign_objects_to_people({}, [(0, 0, 10, 10)])
    assert result == {}


def test_multiple_objects_split_correctly():
    person_boxes = {
        1: (0, 0, 100, 100),
        2: (500, 0, 600, 100),
    }
    phone_boxes = [
        (20, 20, 40, 40),     # near person 1
        (520, 20, 540, 40),   # near person 2
    ]
    result = assign_objects_to_people(person_boxes, phone_boxes)
    assert result[1] == [(20, 20, 40, 40)]
    assert result[2] == [(520, 20, 540, 40)]


def test_crop_box_returns_padded_region():
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    crop = crop_box(frame, (50, 50, 100, 100), padding_ratio=0.1)
    assert crop is not None
    assert crop.shape[0] > 50  # padded, so taller than the raw 50px box
    assert crop.shape[1] > 50


def test_crop_box_handles_degenerate_box():
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    crop = crop_box(frame, (100, 100, 100, 100))  # zero-area box
    assert crop is None
