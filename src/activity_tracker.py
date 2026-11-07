"""
activity_tracker.py
--------------------
Pure state-machine logic for turning a set of detected labels into an
activity state, and for accumulating time spent in each state.

Kept free of any camera/IO code so it's trivial to unit test.
"""

import time
import math
from collections import defaultdict
from typing import Set, Dict, Optional, Callable

STATE_PHONE = 'PHONE'
STATE_WORKING = 'WORKING'
STATE_IDLE = 'IDLE'
STATE_AWAY = 'AWAY'


def classify(
    labels: Set[str],
    person_label: str = 'person',
    laptop_label: str = 'laptop',
    phone_label: str = 'cell phone',
    looking_at_phone: Optional[bool] = None,
) -> str:
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

    def __init__(
        self,
        initial_state: str = STATE_AWAY,
        on_transition: Optional[Callable[[str, float], None]] = None,
        clock: Callable[[], float] = time.time,
        max_gap_seconds: Optional[float] = None,
        on_segment: Optional[Callable[[str, float, float], None]] = None,
    ):
        if max_gap_seconds is not None and (
            isinstance(max_gap_seconds, bool)
            or not isinstance(max_gap_seconds, (int, float))
            or not math.isfinite(max_gap_seconds)
            or max_gap_seconds <= 0
        ):
            raise ValueError('max_gap_seconds must be a finite positive number.')
        self.state = initial_state
        self._clock = clock
        self.state_start = self._clock()
        self.last_observed = self.state_start
        self.max_gap_seconds = max_gap_seconds
        self.on_segment = on_segment
        self.totals: Dict[str, float] = defaultdict(float)
        self.on_transition = on_transition

    def _emit(self, end):
        if end <= self.state_start:
            return
        duration = end - self.state_start
        if duration:
            self.totals[self.state] += duration
            if self.on_segment:
                self.on_segment(self.state, duration, end)
            elif self.on_transition:
                self.on_transition(self.state, duration)
        self.state_start = end

    def update(self, new_state: str) -> None:
        now = self._clock()
        gap = now - self.last_observed
        if self.max_gap_seconds is not None and (gap < 0 or gap > self.max_gap_seconds):
            self._emit(self.last_observed)
            self.state_start = max(now, self.last_observed, self.state_start)
        elif new_state != self.state:
            self._emit(now)
        self.state = new_state
        self.last_observed = now

    def current_elapsed(self) -> float:
        return max(0, self._clock() - self.state_start)

    def reset_timer(self) -> None:
        """Discard the elapsed period without logging it, e.g. while monitoring is paused."""
        self.state_start = self._clock()
        self.last_observed = self.state_start

    def finalize(self) -> None:
        """Call at shutdown to flush the time spent in the current state."""
        now = self._clock()
        if self.max_gap_seconds is not None and (
            now < self.last_observed or now - self.last_observed > self.max_gap_seconds
        ):
            now = self.last_observed
        self._emit(now)
        self.last_observed = now

    def summary(self) -> Dict[str, float]:
        return dict(self.totals)
