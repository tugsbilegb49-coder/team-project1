"""
Entry point: loads config.yaml and starts the Worker Activity Monitor.

Usage:
    python main.py
    python main.py --config custom_config.yaml
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description='Worker Activity Monitor')
    parser.add_argument('--config', default='config.yaml', help='Path to config YAML file (default: config.yaml)')
    parser.add_argument(
        '--mode',
        choices=('presence', 'activity', 'measure'),
        help='Default: presence; measure = guided accuracy test (src/camera_accuracy.py); activity is the legacy experiment.',
    )
    parser.add_argument(
        '--consent',
        action='store_true',
        help='Explicit permission for this local camera session (no images/video saved).',
    )
    parser.add_argument('--seconds', type=float, help='Stop the demo after this many seconds.')
    args = parser.parse_args()
    import signal

    if hasattr(signal, 'SIGBREAK'):  # Windows: the launcher stops children with Ctrl+Break.
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    import math
    import yaml

    with open(args.config, encoding='utf-8') as source:
        config = yaml.safe_load(source)
    if args.seconds is not None and (not math.isfinite(args.seconds) or args.seconds <= 0):
        parser.error('--seconds must be finite and positive.')
    if not args.consent and input(
        'Camera uses frames in RAM only. Save presence/confidence locally? [y/N]: '
    ).strip().lower() not in {'y', 'yes', 'тийм'}:
        print('Camera consent was not granted; camera not opened.')
        return
    import sys
    from desktop.camera_runtime import ensure_host

    arguments = sys.argv[1:]
    if '--consent' not in arguments:
        arguments = [*arguments, '--consent']
    ensure_host(arguments)
    mode = args.mode or config.get('camera_mode', 'presence')
    if mode not in {'presence', 'activity', 'measure'}:
        parser.error('camera_mode must be presence or activity.')
    from agent.process_lock import collector_lock, AlreadyRunningError
    from src.camera_capture import CameraPermissionError, CameraSessionCancelled

    try:
        with collector_lock('camera'):
            run_monitor(config, mode, args.seconds)
    except AlreadyRunningError as exc:
        raise SystemExit(str(exc)) from exc
    except CameraPermissionError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(77) from exc
    except CameraSessionCancelled:
        raise SystemExit(130)


def run_monitor(config, mode, seconds):
    if mode == 'measure':
        from src.camera_accuracy import AccuracySession

        AccuracySession(config).run(seconds=seconds)
        return
    if mode == 'presence':
        from src.presence import PresenceMonitor

        PresenceMonitor(config).run(seconds=seconds)
        return
    from src.monitor import WorkerActivityMonitor

    if config.get('multi_person'):
        from src.multi_monitor import MultiPersonMonitor

        monitor = MultiPersonMonitor(config)
    else:
        monitor = WorkerActivityMonitor(config)

    monitor.run(seconds=seconds)


if __name__ == '__main__':
    main()
