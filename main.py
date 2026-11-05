"""
Entry point: loads config.yaml and starts the Worker Activity Monitor.

Usage:
    python main.py
    python main.py --config custom_config.yaml
"""

import argparse
from src.monitor import WorkerActivityMonitor, load_config
from src.multi_monitor import MultiPersonMonitor


def main():
    parser = argparse.ArgumentParser(description="Worker Activity Monitor")
    parser.add_argument("--config", default="config.yaml",
                         help="Path to config YAML file (default: config.yaml)")
    args = parser.parse_args()

    config = load_config(args.config)

    if config.get("multi_person"):
        monitor = MultiPersonMonitor(config)
    else:
        monitor = WorkerActivityMonitor(config)

    monitor.run()


if __name__ == "__main__":
    main()
