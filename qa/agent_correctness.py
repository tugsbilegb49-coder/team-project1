"""Run the real sampling loop against deterministic fake OS observations."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import Mock, patch

from agent import main as agent


def run_case(case):
    tick = [0]
    rows = []
    uploader = Mock()
    uploader.append.side_effect = rows.append
    beginning = datetime(2026, 11, 6, tzinfo=timezone.utc)

    def sleep(interval):
        tick[0] += interval
        if tick[0] >= case['seconds']:
            raise KeyboardInterrupt

    def foreground():
        return next(name for start, name in reversed(case['apps']) if tick[0] >= start)

    def wall():
        gap = case.get('sleep_seconds', 0) if tick[0] >= case.get('sleep_at', float('inf')) else 0
        return beginning + timedelta(seconds=tick[0] + gap)

    config = {'interval_seconds': 30, 'poll_interval_seconds': 1, 'idle_threshold_seconds': 300,
              'productive_apps': ['Code'], 'device_id': 'synthetic-device'}
    with patch.object(agent, 'PendingUploader', return_value=uploader), \
         patch.object(agent.time, 'sleep', side_effect=sleep), \
         patch.object(agent.time, 'monotonic', side_effect=lambda: tick[0]), \
         patch.object(agent, '_now', side_effect=wall), \
         patch.object(agent, 'foreground_application', side_effect=foreground), \
         patch.object(agent, 'idle_seconds', side_effect=lambda: 301 if tick[0] >= case.get('idle_at', float('inf')) else 0), \
         patch.object(agent, 'is_paused', side_effect=lambda: case.get('pause', [0, 0])[0] <= tick[0] < case.get('pause', [0, 0])[1]):
        agent.run_agent(config, Mock())
    actual = [[row['application'], row['category'], row['duration_seconds']] for row in rows]
    return {'id': case['id'], 'expected': case['expected'], 'actual': actual, 'passed': actual == case['expected'], 'events': rows}


def report():
    cases = json.loads((Path(__file__).parent / 'fixtures/agent_cases.json').read_text())
    results = [run_case(case) for case in cases]
    return {'data_kind': 'synthetic OS observations; actual sampler code', 'cases': results,
            'passed': all(case['passed'] for case in results)}
