#!/usr/bin/env python3
"""Run final QA without recording a camera or modifying the real database."""

import argparse
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent


def source_revision():
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    digest = hashlib.sha256()
    # Includes untracked implementation files while excluding private runtime data.
    candidates = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, text=True
    ).splitlines()
    for name in sorted(set(candidates)):
        if name.startswith('qa/evidence/') or not name.endswith(
            ('.py', '.js', '.jsx', '.json', '.yml', '.yaml', '.txt', '.md', '.csv', '.m')
        ):
            continue
        path = ROOT / name
        if path.is_file():
            digest.update(name.encode())
            digest.update(b'\0')
            digest.update(path.read_bytes())
            digest.update(b'\0')
    return {'git_head': revision, 'working_tree_dirty': dirty, 'source_sha256': digest.hexdigest()}


def run_stage(name, command, log_dir, timeout=240):
    started = time.monotonic()
    log_path = log_dir / (name + '.log')
    with log_path.open('w', encoding='utf-8') as stream:
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                env={**os.environ, 'PYTHONUNBUFFERED': '1'},
            )
            code = result.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            stream.write(f'\nStage failed: {type(exc).__name__}: {exc}\n')
            code = -1
    output = log_path.read_text(encoding='utf-8', errors='replace')
    counts = re.findall(r'Ran (\d+) tests?|(?<!\d)(\d+) passed', output)
    count = sum(int(a or b) for a, b in counts)
    skipped = re.findall(r'skipped=(\d+)|(?<!\d)(\d+) skipped', output)
    stage = {
        'name': name,
        'command': command,
        'status': 'passed' if code == 0 else 'failed',
        'exit_code': code,
        'seconds': round(time.monotonic() - started, 3),
        'tests_reported': count or None,
        'tests_skipped': sum(int(a or b) for a, b in skipped),
        'log': str(log_path.relative_to(ROOT)),
    }
    print(f'{stage["status"].upper()}: {name} ({stage["seconds"]}s)', flush=True)
    if code:
        print(output[-2500:], flush=True)
    return stage


def camera_smoke(path):
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['timestamp', 'present', 'confidence']:
            raise ValueError('Camera smoke input must contain only timestamp,present,confidence.')
        rows = list(reader)
    if not rows:
        raise ValueError('Camera smoke log is empty.')
    from src.presence import validate_presence

    for row in rows:
        if row['present'] not in {'0', '1'}:
            raise ValueError('Invalid presence boolean in smoke log.')
        validate_presence(row['present'] == '1', float(row['confidence']))
    return {
        'status': 'observed',
        'data_kind': 'real camera; unlabeled',
        'samples': len(rows),
        'present_predictions': sum(r['present'] == '1' for r in rows),
        'absent_predictions': sum(r['present'] == '0' for r in rows),
        'first_sample': rows[0]['timestamp'],
        'last_sample': rows[-1]['timestamp'],
        'images_or_video_recorded': False,
        'accuracy': None,
        'limitation': 'No independent human labels; prediction counts are not precision/recall.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.runtime/qa/final-qa.json'))
    parser.add_argument(
        '--skip-browser', action='store_true', help='Explicitly mark real browser integration as skipped.'
    )
    parser.add_argument('--native', action='store_true', help='Also run the interactive macOS native lifecycle check.')
    parser.add_argument(
        '--camera-log', type=Path, help='Summarize a previously consented metadata-only live smoke log.'
    )
    args = parser.parse_args()
    npm = shutil.which('npm')
    if not npm:
        parser.error('npm is required for final system QA.')
    now = datetime.now(ZoneInfo('Asia/Ulaanbaatar'))
    log_dir = ROOT / '.runtime/qa' / now.strftime('%Y%m%dT%H%M%S%f')
    log_dir.mkdir(parents=True, exist_ok=True)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        'performed_at': now.isoformat(),
        'source': source_revision(),
        'status': 'running',
        'scope': 'Disposable test databases, synthetic OS observations and synthetic AI data; no webcam capture.',
        'stages': [],
        'manual_remaining': [
            'Independent real camera precision/recall validation',
            'Human defense rehearsal',
            'Team PR evidence links and remote CI run after code publication',
        ],
    }
    commands = [
        ('django-check', [sys.executable, 'manage.py', 'check']),
        ('migration-check', [sys.executable, 'manage.py', 'makemigrations', '--check', '--dry-run']),
        ('python-camera-ai', [sys.executable, '-m', 'pytest', '-q']),
        ('computer-agent', [sys.executable, '-m', 'unittest', 'discover', '-s', 'agent', '-p', 'test*.py']),
        ('alternative-agent', [sys.executable, '-m', 'unittest', 'discover', '-s', 'activity_agent/tests']),
        ('django-integration', [sys.executable, 'manage.py', 'test', 'users', 'workforce', 'activity', 'scoring']),
        ('frontend-unit', [npm, 'run', 'test']),
        ('frontend-lint', [npm, 'run', 'lint']),
        ('frontend-build', [npm, 'run', 'build']),
        ('frontend-browser', [npm, 'run', 'test:e2e', '--', 'e2e/frontend.spec.js']),
    ]
    if not args.skip_browser:
        commands.append(('browser-django', [sys.executable, 'verify_frontend.py']))
    else:
        report['manual_remaining'].append('Real browser/Django integration was explicitly skipped')
    if args.native and sys.platform == 'darwin':
        commands.append(('native-macos-app', [sys.executable, 'verify_desktop_app.py']))
    else:
        report['manual_remaining'].append('Native macOS app GUI startup/Quit verification; run --native on macOS')
    try:
        for name, command in commands:
            report['stages'].append(run_stage(name, command, log_dir))
        from qa.agent_correctness import report as agent_report
        from ai.experiment import experiment, demo_rows
        from evaluate_camera import evaluate_presence

        report['agent_correctness'] = agent_report()
        report['ai_experiment'] = experiment(demo_rows())
        with (ROOT / 'qa/fixtures/presence_demo.csv').open(newline='', encoding='utf-8') as stream:
            report['camera_metric_fixture'] = {
                'data_kind': 'synthetic evaluator fixture; not real camera accuracy',
                **evaluate_presence(csv.DictReader(stream)),
            }
        report['camera_live_smoke'] = camera_smoke(args.camera_log) if args.camera_log else {'status': 'not_run'}
        success = (
            all(stage['status'] == 'passed' for stage in report['stages']) and report['agent_correctness']['passed']
        )
        report['status'] = 'passed' if success else 'failed'
        report['release_readiness'] = (
            'automated_checks_passed_manual_validation_pending' if success else 'changes_required'
        )
    except KeyboardInterrupt:
        report['status'] = 'interrupted'
        raise
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        report['finished_at'] = datetime.now(ZoneInfo('Asia/Ulaanbaatar')).isoformat()
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(f'QA report: {output}', flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
