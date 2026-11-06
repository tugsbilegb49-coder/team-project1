"""
Unit tests for src/activity_tracker.py — no camera or model required.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.activity_tracker import (
    classify, ActivityTracker,
    STATE_PHONE, STATE_WORKING, STATE_IDLE, STATE_AWAY,
)


def test_classify_phone_takes_priority():
    labels = {"person", "laptop", "cell phone"}
    assert classify(labels) == STATE_PHONE


def test_classify_working():
    labels = {"person", "laptop"}
    assert classify(labels) == STATE_WORKING


def test_classify_idle():
    labels = {"person"}
    assert classify(labels) == STATE_IDLE


def test_classify_away():
    labels = set()
    assert classify(labels) == STATE_AWAY


def test_classify_gaze_override_ignores_phone_on_desk():
    labels = {"person", "laptop", "cell phone"}
    # phone is visible but the person is NOT looking down at it -> treat as WORKING
    assert classify(labels, looking_at_phone=False) == STATE_WORKING


def test_classify_gaze_override_confirms_phone_use():
    labels = {"person", "laptop", "cell phone"}
    assert classify(labels, looking_at_phone=True) == STATE_PHONE


def test_tracker_accumulates_time():
    fake_time = [0.0]

    def clock():
        return fake_time[0]

    transitions = []

    tracker = ActivityTracker(
        initial_state=STATE_AWAY,
        on_transition=lambda state, duration: transitions.append((state, duration)),
        clock=clock,
    )

    fake_time[0] = 5.0
    tracker.update(STATE_WORKING)  # was AWAY for 5s

    fake_time[0] = 15.0
    tracker.update(STATE_PHONE)    # was WORKING for 10s

    fake_time[0] = 20.0
    tracker.finalize()             # was PHONE for 5s

    assert transitions == [
        (STATE_AWAY, 5.0),
        (STATE_WORKING, 10.0),
        (STATE_PHONE, 5.0),
    ]

    summary = tracker.summary()
    assert summary[STATE_AWAY] == 5.0
    assert summary[STATE_WORKING] == 10.0
    assert summary[STATE_PHONE] == 5.0


def test_tracker_no_transition_when_state_unchanged():
    fake_time = [0.0]
    tracker = ActivityTracker(initial_state=STATE_IDLE, clock=lambda: fake_time[0])
    fake_time[0] = 10.0
    tracker.update(STATE_IDLE)  # same state, should not trigger a transition
    assert tracker.state_start == 0.0


def test_camera_sleep_preserves_observed_time_and_skips_gap():
    clock=[0.0]
    rows=[]
    tracker=ActivityTracker(initial_state=STATE_WORKING,clock=lambda:clock[0],max_gap_seconds=10,
        on_segment=lambda state,duration,end:rows.append((state,duration,end)))
    clock[0]=5
    tracker.update(STATE_WORKING)
    clock[0]=100
    tracker.update(STATE_WORKING)
    clock[0]=105
    tracker.finalize()
    tracker.finalize()
    assert rows==[(STATE_WORKING,5,5),(STATE_WORKING,5,105)]
    assert tracker.summary()[STATE_WORKING]==10


def test_camera_shutdown_after_sleep_never_counts_unobserved_time():
    clock=[0.0]
    tracker=ActivityTracker(initial_state=STATE_WORKING,clock=lambda:clock[0],max_gap_seconds=10)
    clock[0]=5
    tracker.update(STATE_WORKING)
    clock[0]=100
    tracker.finalize()
    assert tracker.summary()[STATE_WORKING]==5


def test_camera_multiple_backward_clock_changes_do_not_lower_recorded_watermark():
    clock=[0.0]
    rows=[]
    tracker=ActivityTracker(initial_state=STATE_WORKING,clock=lambda:clock[0],max_gap_seconds=10,
        on_segment=lambda state,duration,end:rows.append((duration,end)))
    for value in (5,10,1,2,.5,3,11):
        clock[0]=value
        tracker.update(STATE_WORKING)
    tracker.finalize()
    assert rows==[(10,10),(1,11)]
