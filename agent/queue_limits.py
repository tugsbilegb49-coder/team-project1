"""Bound JSON offline queues by both event count and encoded file size."""
import json


def bounded_queue(items, max_events=10000, max_bytes=10 * 1024 * 1024):
    if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 1:
        raise ValueError('max_queue_events must be a positive integer.')
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1024:
        raise ValueError('max_queue_bytes must be an integer of at least 1024.')
    kept = []
    size = 2  # JSON array brackets; separators match json.dumps defaults.
    for item in reversed(items):
        length = len(json.dumps(item, ensure_ascii=False).encode('utf-8'))
        if length + 2 > max_bytes:
            continue
        additional = length + (2 if kept else 0)
        if len(kept) >= max_events or size + additional > max_bytes:
            break
        kept.append(item)
        size += additional
    kept.reverse()
    return kept, len(items) - len(kept)
