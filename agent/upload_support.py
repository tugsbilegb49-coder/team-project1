"""Bounded quarantine for permanently rejected activity, excluding auth errors."""
from datetime import datetime, timezone
import json
from pathlib import Path
if __package__:
    from .queue_limits import bounded_queue
    from .token_store import atomic_json_write
else:
    from queue_limits import bounded_queue
    from token_store import atomic_json_write

PERMANENT_EVENT_STATUSES={400,409,413,422}


def quarantine_event(queue_path,event,status):
    path=Path(queue_path).with_name(Path(queue_path).stem+'.rejected.json')
    try:
        rows=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows,list): rows=[]
    except FileNotFoundError:
        rows=[]
    rows.append({'rejected_at':datetime.now(timezone.utc).isoformat(),'status':status,'event':event})
    rows,_=bounded_queue(rows,max_events=1000,max_bytes=1024*1024)
    atomic_json_write(path,rows)
    return path
