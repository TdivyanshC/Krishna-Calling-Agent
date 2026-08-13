"""
audit_log.py — JSONL audit event sink.

Additive-only: emits one JSON object per line to logs/audit.jsonl for
call-flow observability. Fully isolated from the app's normal logging —
its own logger does not propagate to root, so audit records never reach
journald. Writes happen on a background thread (via QueueHandler /
QueueListener) so a slow or failing disk can't stall the asyncio event
loop mid-call. Every failure is swallowed; a single warning is emitted
(through the normal app logger, once per process) and the sink then goes
quiet rather than risk breaking a live call.
"""

import json
import logging
import logging.handlers
import os
import queue
from datetime import datetime, timezone

_LOG_DIR  = "/home/voiceagent/voice-ai/logs"
_LOG_PATH = os.path.join(_LOG_DIR, "audit.jsonl")

_warn_logger = logging.getLogger(__name__)  # normal logger — DOES propagate

_sink_logger = logging.getLogger("audit_sink")
_sink_logger.propagate = False
_sink_logger.setLevel(logging.INFO)

_queue_listener = None
_sink_ready = False
_warned = False


def _init_sink() -> None:
    global _queue_listener, _sink_ready
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        file_handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(message)s"))

        q = queue.Queue(-1)
        queue_handler = logging.handlers.QueueHandler(q)
        _sink_logger.addHandler(queue_handler)

        _queue_listener = logging.handlers.QueueListener(q, file_handler, respect_handler_level=True)
        _queue_listener.start()
        _sink_ready = True
    except Exception:
        _sink_ready = False


_init_sink()


def audit_event(call_uuid: str, event: str, turn: int = 0, **fields) -> None:
    """Append one audit record. Never raises; never blocks the caller on disk I/O."""
    global _warned
    try:
        if not _sink_ready:
            return
        record = {
            "ts":        datetime.now(timezone.utc).isoformat(),
            "call_uuid": call_uuid,
            "turn":      turn,
            "event":     event,
            **fields,
        }
        _sink_logger.info(json.dumps(record, ensure_ascii=False, default=str))
    except Exception:
        if not _warned:
            _warned = True
            _warn_logger.warning("audit_log: sink failed, suppressing further warnings", exc_info=True)
