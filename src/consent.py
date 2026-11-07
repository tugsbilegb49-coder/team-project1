"""Background consent checks with a short, fail-closed authorization lease."""

import math
import threading
import time


class ConsentGuard:
    def __init__(self, check, interval=1, ttl=3, clock=time.monotonic):
        if (
            any(
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
                for value in (interval, ttl)
            )
            or ttl < interval
        ):
            raise ValueError('Consent interval/TTL must be positive and TTL must cover the interval.')
        self.check, self.interval, self.ttl, self.clock = check, interval, ttl, clock
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread = None
        self.verified_at = None
        self.granted = False
        self.generation = 0

    def allowed(self):
        with self.lock:
            return bool(
                not self.stopping.is_set()
                and self.granted
                and self.verified_at is not None
                and 0 <= self.clock() - self.verified_at <= self.ttl
            )

    def invalidate(self):
        with self.lock:
            self.generation += 1
            self.granted = False
            self.verified_at = None

    def refresh(self):
        with self.lock:
            generation = self.generation
        try:
            granted = self.check() is True
        except (OSError, RuntimeError, ValueError):
            granted = False
        with self.lock:
            # A late status response cannot undo a newer upload denial.
            if generation == self.generation and not self.stopping.is_set():
                self.granted = granted
                self.verified_at = self.clock() if granted else None

    def _run(self):
        while not self.stopping.is_set():
            self.refresh()
            self.stopping.wait(self.interval)

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name='camera-consent', daemon=True)
            self.thread.start()

    def stop(self):
        self.stopping.set()
        self.invalidate()
        if self.thread:
            self.thread.join(timeout=3)
        return self.thread is None or not self.thread.is_alive()
