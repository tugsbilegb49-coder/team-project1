"""Computer activity agent.

Ашиглах:
    python agent.py check      # OS permission болон тохиргоо шалгах (Өдөр 1)
    python agent.py mock       # Нэг mock batch API руу илгээх (Өдөр 2)
    python agent.py run        # Agent ажиллуулах (Өдөр 3)
    python agent.py run --config other.json
"""

import argparse
import hashlib
import json
import logging
import os
import platform
import signal
import sys
import time
import uuid

from collector import ActivityCollector
from contract import build_batch, validate_batch
from sender import BatchSender

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("agent")


def load_config(path):
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    for key in ("spool_file", "log_file"):
        if not os.path.isabs(config[key]):
            config[key] = os.path.join(BASE_DIR, config[key])
    return config


def setup_logging(log_file):
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


def device_id():
    """Hostname + MAC-аас гаргасан hash. Жинхэнэ hostname сервер рүү явахгүй."""
    raw = f"{platform.node()}-{uuid.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def make_sender(config):
    return BatchSender(
        config["api_url"], config["api_token"], config["spool_file"],
        timeout=config["request_timeout_seconds"], max_spool_batches=config["max_spool_batches"],
    )


# --- commands ---

def cmd_check(config):
    from check_permissions import run_checks
    return 0 if run_checks(config) else 1


def cmd_mock(config):
    now = time.time()
    stats = {"active_seconds": 45, "idle_seconds": 15, "keyboard_events": 80, "mouse_events": 12,
             "apps": {"chrome.exe": 30, "code.exe": 15}}
    batch = build_batch(config["employee_id"], device_id(), now - 60, now, stats)
    errors = validate_batch(batch)
    if errors:
        print("Contract алдаа:", errors)
        return 1
    print(json.dumps(batch, indent=2, ensure_ascii=False))
    sent, waiting = make_sender(config).send(batch)
    print(f"Илгээсэн: {sent}, spool-д үлдсэн: {waiting}")
    return 0 if waiting == 0 else 1


def cmd_run(config):
    collector = ActivityCollector(config["idle_threshold_seconds"])
    sender = make_sender(config)
    dev_id = device_id()
    stopping = {"flag": False}

    def stop(*_):
        stopping["flag"] = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    collector.start_listeners()
    log.info("Agent started: employee=%s device=%s idle_threshold=%ss batch=%ss",
             config["employee_id"], dev_id, config["idle_threshold_seconds"], config["batch_interval_seconds"])

    period_start = time.time()
    while not stopping["flag"]:
        time.sleep(config["tick_seconds"])
        try:
            collector.tick()
            if not collector.listeners_alive():
                log.warning("Input listener stopped, restarting")
                collector.stop_listeners()
                collector.start_listeners()

            now = time.time()
            if now - period_start >= config["batch_interval_seconds"]:
                batch = build_batch(config["employee_id"], dev_id, period_start, now, collector.flush())
                period_start = now
                sender.send(batch)
        except Exception:
            # Нэг алдаанаас болж agent бүхэлдээ зогсох ёсгүй.
            log.exception("Unexpected error in main loop")

    # Унтрахаас өмнө сүүлийн дутуу batch-ийг spool-д хадгална.
    now = time.time()
    batch = build_batch(config["employee_id"], dev_id, period_start, now, collector.flush())
    if batch["active_seconds"] + batch["idle_seconds"] > 0:
        sender.spool_only(batch)
    collector.stop_listeners()
    log.info("Agent stopped")
    return 0


def main(argv=None):
    # Windows console (cp1252) кирилл үсэг хэвлэж чадахгүй тул UTF-8 болгоно.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Computer activity agent")
    parser.add_argument("command", choices=["run", "check", "mock"])
    parser.add_argument("--config", default=os.path.join(BASE_DIR, "config.json"))
    args = parser.parse_args(argv)

    config = load_config(args.config)
    setup_logging(config["log_file"])
    commands = {"run": cmd_run, "check": cmd_check, "mock": cmd_mock}
    return commands[args.command](config)


if __name__ == "__main__":
    sys.exit(main())
