"""
activity_tracker.py
--------------------
Pure state-machine logic for turning a set of detected labels into an
activity state, and for accumulating time spent in each state.

Kept free of any camera/IO code so it's trivial to unit test.
"""

import time
from collections import defaultdict
from typing import Set, Dict, Optional, Callable

STATE_PHONE = "PHONE"
STATE_WORKING = "WORKING"
STATE_IDLE = "IDLE"
STATE_AWAY = "AWAY"


def classify(labels: Set[str], person_label: str = "person",
             laptop_label: str = "laptop", phone_label: str = "cell phone",
             looking_at_phone: Optional[bool] = None) -> str:
    """Turn a set of detected object labels into an activity state.

    If `looking_at_phone` is provided (True/False) it overrides the naive
    "any phone in frame counts" behaviour — used by the optional gaze
    heuristic to avoid false positives from a phone just sitting on the desk.
    """
    has_phone = phone_label in labels
    has_person = person_label in labels
    has_laptop = laptop_label in labels

    if has_phone and looking_at_phone is not None:
        has_phone = looking_at_phone

    if has_phone:
        return STATE_PHONE
    elif has_person and has_laptop:
        return STATE_WORKING
    elif has_person:
        return STATE_IDLE
    else:
        return STATE_AWAY


class ActivityTracker:
    """Tracks state transitions over time and accumulates totals per state.

    `on_transition` is an optional callback invoked as
    on_transition(old_state, duration_seconds) every time the state changes,
    e.g. to write a log line.
    """

    def __init__(self, initial_state: str = STATE_AWAY,
                 on_transition: Optional[Callable[[str, float], None]] = None,
                 clock: Callable[[], float] = time.time):
        self.state = initial_state
        self._clock = clock
        self.state_start = self._clock()
        self.totals: Dict[str, float] = defaultdict(float)
        self.on_transition = on_transition

    def update(self, new_state: str) -> None:
        if new_state == self.state:
            return
        now = self._clock()
        duration = now - self.state_start
        self.totals[self.state] += duration
        if self.on_transition:
            self.on_transition(self.state, duration)
        self.state = new_state
        self.state_start = now

    def current_elapsed(self) -> float:
        return self._clock() - self.state_start

    def reset_timer(self) -> None:
        """Discard the elapsed period without logging it, e.g. while monitoring is paused."""
        self.state_start = self._clock()

    def finalize(self) -> None:
        """Call at shutdown to flush the time spent in the current state."""
        now = self._clock()
        duration = now - self.state_start
        self.totals[self.state] += duration
        if self.on_transition:
            self.on_transition(self.state, duration)

    def summary(self) -> Dict[str, float]:
        return dict(self.totals)
