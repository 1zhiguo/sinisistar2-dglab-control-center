"""Bounded diagnostic sink for the reused V4 protocol implementation."""
from collections import deque
import threading,time

_records=deque(maxlen=2000)
_lock=threading.Lock()

def record(event,**fields):
    with _lock:_records.append(dict(event=event,at=time.monotonic(),**fields))

def snapshot():
    with _lock:return list(_records)

def command_fields(message):
    return dict(command=str(message)[:160])
