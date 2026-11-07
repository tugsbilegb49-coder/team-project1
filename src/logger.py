"""
logger.py
---------
CSV-based event logging for the activity tracker, plus helpers for
summarizing a log file (used by the dashboard and CLI reports).
"""

import os
from datetime import datetime
from typing import Dict
import pandas as pd


class CSVActivityLogger:
    """CSV logger. Supports an optional `person_id` column so the same log
    format works for both single-person and multi-person (DeepSORT) modes.
    """

    def __init__(self, log_file: str, multi_person: bool = False, **limits):
        self.log_file = log_file
        self.multi_person = multi_person
        self.header = ['timestamp', 'state', 'duration_seconds']
        if multi_person:
            self.header.insert(1, 'person_id')
        from src.presence import PresenceLogger

        self._csv = PresenceLogger(log_file, fields=self.header, **limits)

    def configure(self, settings):
        from src.presence import PresenceLogger

        self._csv.close()
        self._csv = PresenceLogger(
            self.log_file,
            fields=self.header,
            max_bytes=settings['presence_log_max_bytes'],
            backup_count=settings['presence_log_backups'],
            retention_days=settings['presence_log_retention_days'],
        )

    def log(self, state: str, duration_seconds: float, person_id=None, timestamp=None) -> None:
        recorded = timestamp or datetime.now()
        if recorded.tzinfo is not None:
            # Existing local CSV files use naive local timestamps. Keep that
            # format while the HTTP uploader retains its timezone-aware end.
            recorded = recorded.astimezone().replace(tzinfo=None)
        row = [recorded.isoformat(timespec='seconds')]
        if self.multi_person:
            row.append(person_id)
        row += [state, round(duration_seconds, 1)]
        self._csv.write_row(row)

    def close(self) -> None:
        self._csv.close()


def load_log(log_file: str) -> pd.DataFrame:
    if not os.path.exists(log_file):
        return pd.DataFrame(columns=['timestamp', 'state', 'duration_seconds'])
    from pathlib import Path

    path = Path(log_file)
    files = [path]
    for candidate in path.parent.glob(path.name + '.*'):
        suffix = candidate.name[len(path.name) + 1 :]
        if suffix.isdecimal() and str(int(suffix)) == suffix and 1 <= int(suffix) <= 100:
            files.append(candidate)
    df = pd.concat([pd.read_csv(file, parse_dates=['timestamp']) for file in files], ignore_index=True)
    if df.empty:
        df['date'] = pd.Series(dtype=object)
        return df
    df['date'] = df['timestamp'].dt.date
    return df


def summarize(df: pd.DataFrame) -> Dict[str, float]:
    """Total seconds per state across the whole log."""
    if df.empty:
        return {}
    return df.groupby('state')['duration_seconds'].sum().to_dict()


def summarize_by_day(df: pd.DataFrame) -> pd.DataFrame:
    """Seconds per state, per day — handy for the dashboard's daily chart."""
    if df.empty:
        return pd.DataFrame(columns=['date', 'state', 'duration_seconds'])
    return df.groupby(['date', 'state'])['duration_seconds'].sum().reset_index()


def summarize_by_person(df: pd.DataFrame) -> pd.DataFrame:
    """Seconds per state, per person_id — only meaningful for logs recorded
    in multi-person mode (i.e. df has a `person_id` column)."""
    if df.empty or 'person_id' not in df.columns:
        return pd.DataFrame(columns=['person_id', 'state', 'duration_seconds'])
    return df.groupby(['person_id', 'state'])['duration_seconds'].sum().reset_index()


def print_summary(log_file: str) -> None:
    df = load_log(log_file)
    totals = summarize(df)
    total = sum(totals.values())
    print('--- Activity Log Summary ---')
    if total == 0:
        print('No data recorded yet.')
        return
    for state, secs in sorted(totals.items(), key=lambda x: -x[1]):
        pct = secs / total * 100
        print(f'{state:10s}: {secs / 60:6.1f} min ({pct:5.1f}%)')
    print(f'{"TOTAL":10s}: {total / 60:6.1f} min')
