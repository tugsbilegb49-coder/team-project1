"""
Entry point: loads config.yaml and starts the Worker Activity Monitor.

Usage:
    python main.py
    python main.py --config custom_config.yaml
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Worker Activity Monitor")
    parser.add_argument("--config", default="config.yaml",
                         help="Path to config YAML file (default: config.yaml)")
    parser.add_argument('--mode', choices=('presence', 'activity'), help='Default: presence; activity is the legacy experiment.')
    parser.add_argument('--consent', action='store_true', help='Explicit permission for this local camera session (no images/video saved).')
    parser.add_argument('--seconds', type=float, help='Stop the demo after this many seconds.')
    args = parser.parse_args()

    import math
    import yaml
    with open(args.config, encoding='utf-8') as source:
        config = yaml.safe_load(source)
    if args.seconds is not None and (not math.isfinite(args.seconds) or args.seconds <= 0):
        parser.error('--seconds must be finite and positive.')
    if not args.consent and input('Camera uses frames in RAM only. Save presence/confidence locally? [y/N]: ').strip().lower() not in {'y', 'yes', 'тийм'}:
        print('Camera consent was not granted; camera not opened.')
        return
    if (args.mode or config.get('camera_mode', 'presence')) == 'presence':
        from src.presence import PresenceMonitor
        PresenceMonitor(config).run(seconds=args.seconds)
        return
    from src.monitor import WorkerActivityMonitor
    from src.multi_monitor import MultiPersonMonitor

    if config.get("multi_person"):
        monitor = MultiPersonMonitor(config)
    else:
        monitor = WorkerActivityMonitor(config)

    monitor.run()


if __name__ == "__main__":
    main()
