# -*- coding: utf-8 -*-
"""
ingest.py — tails logs/audit.jsonl into SQLite (audit_events table).

Idempotent via a (path, inode, offset) watermark in ingest_state: each run
only reads bytes appended since the last run. If the file's inode changes
(rotated/truncated by audit_log.py's FileHandler, or manually replaced), the
watermark resets to 0 so nothing after the rotation gets silently skipped.

Usage: python3 ingest.py
"""
import json
import os

from config import AUDIT_LOG_PATH
from db import connect


def run() -> int:
    conn = connect()
    if not os.path.exists(AUDIT_LOG_PATH):
        print(f"no audit log at {AUDIT_LOG_PATH} — nothing to ingest")
        return 0

    st = os.stat(AUDIT_LOG_PATH)
    row = conn.execute(
        "SELECT inode, offset FROM ingest_state WHERE path = ?", (AUDIT_LOG_PATH,)
    ).fetchone()

    if row is not None and row["inode"] == st.st_ino:
        offset = row["offset"]
    else:
        offset = 0  # new file, or rotated — start from the beginning

    inserted = 0
    skipped = 0
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        f.seek(offset)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            cur = conn.execute(
                """INSERT OR IGNORE INTO audit_events (call_uuid, turn, event, ts, raw)
                   VALUES (?, ?, ?, ?, ?)""",
                (rec.get("call_uuid"), rec.get("turn"), rec.get("event"), rec.get("ts"), json.dumps(rec, ensure_ascii=False)),
            )
            if cur.rowcount:
                inserted += 1
        new_offset = f.tell()

    conn.execute(
        """INSERT INTO ingest_state (path, inode, offset) VALUES (?, ?, ?)
           ON CONFLICT(path) DO UPDATE SET inode = excluded.inode, offset = excluded.offset""",
        (AUDIT_LOG_PATH, st.st_ino, new_offset),
    )
    conn.commit()
    conn.close()
    print(f"ingest: +{inserted} events (skipped {skipped} malformed lines), watermark now at byte {new_offset}")
    return inserted


if __name__ == "__main__":
    run()
