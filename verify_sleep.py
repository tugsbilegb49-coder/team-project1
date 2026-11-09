#!/usr/bin/env python3
"""Observe manual Mac sleep/resume with the real agent, without API writes."""

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import time
from unittest.mock import patch

import agent.main as agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=int, default=300, help='Maximum observation seconds, 30–600.')
    args = parser.parse_args()
    if not 30 <= args.duration <= 600:
        parser.error('--duration must be between 30 and 600 seconds.')
    started = time.time()
    observations, rows = [], []
    resume_deadline = [None]

    class ProbeUploader:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def append(self, row):
            rows.append(row)

        def request_flush(self):
            pass

        def stop(self):
            pass

    def observe():
        now = datetime.now().astimezone()
        if observations and (now - observations[-1]).total_seconds() > 10:
            resume_deadline[0] = time.time() + 8
        observations.append(now)
        return now

    actual_sleep = time.sleep

    def sleep(seconds):
        actual_sleep(seconds)
        if time.time() - started > args.duration or (
            resume_deadline[0] is not None and time.time() >= resume_deadline[0]
        ):
            raise KeyboardInterrupt

    print('READY: Apple menu → Sleep for 20 seconds, then wake the Mac. No database writes.', flush=True)
    config = {
        'interval_seconds': 30,
        'poll_interval_seconds': 1,
        'max_sample_gap_seconds': 10,
        'idle_threshold_seconds': 300,
        'productive_apps': ['Code', 'Visual Studio Code'],
    }
    with (
        patch.object(agent, 'PendingUploader', ProbeUploader),
        patch.object(agent, '_now', side_effect=observe),
        patch.object(agent.time, 'sleep', side_effect=sleep),
    ):
        agent.run_agent(config, None)
    gaps = [(a, b) for a, b in zip(observations, observations[1:]) if (b - a).total_seconds() > 10]
    crossing = False
    for row in rows:
        begin = datetime.fromisoformat(row['started_at'])
        end = begin + timedelta(seconds=row['duration_seconds'])
        if any(begin < b and a < end for a, b in gaps):
            crossing = True
    report = {
        'wall_seconds': round(time.time() - started, 2),
        'largest_sample_gap_seconds': round(
            max(((b - a).total_seconds() for a, b in zip(observations, observations[1:])), default=0), 2
        ),
        'recorded_seconds': round(sum(row['duration_seconds'] for row in rows), 2),
        'sleep_gap_detected': bool(gaps),
        'gap_included_in_app_time': crossing,
        'result': 'passed' if gaps and not crossing else 'inconclusive' if not gaps else 'failed',
    }
    runtime = Path(__file__).resolve().parent / '.runtime'
    runtime.mkdir(exist_ok=True)
    (runtime / 'sleep-resume-test.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    return 0 if report['result'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
