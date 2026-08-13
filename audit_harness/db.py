# -*- coding: utf-8 -*-
"""db.py — SQLite schema + connection helper for the audit harness."""
import sqlite3

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingest_state (
    path   TEXT PRIMARY KEY,
    inode  INTEGER,
    offset INTEGER
);

CREATE TABLE IF NOT EXISTS audit_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    call_uuid TEXT,
    turn      INTEGER,
    event     TEXT,
    ts        TEXT,
    raw       TEXT,
    UNIQUE(call_uuid, turn, event, ts, raw) ON CONFLICT IGNORE
);
CREATE INDEX IF NOT EXISTS idx_audit_events_call ON audit_events(call_uuid);
CREATE INDEX IF NOT EXISTS idx_audit_events_event ON audit_events(event);

CREATE TABLE IF NOT EXISTS call_logs (
    call_uuid          TEXT PRIMARY KEY,
    lead_id            TEXT,
    from_number        TEXT,
    to_number          TEXT,
    to_number_norm     TEXT,
    direction          TEXT,
    caller_name        TEXT,
    status             TEXT,
    duration_seconds   INTEGER,
    started_at         TEXT,
    ended_at           TEXT,
    hangup_cause       TEXT,
    recording_url      TEXT,
    tenant_id          TEXT,
    recording_duration REAL,
    call_number        INTEGER
);
CREATE INDEX IF NOT EXISTS idx_call_logs_phone ON call_logs(to_number_norm);

CREATE TABLE IF NOT EXISTS call_summaries (
    call_uuid              TEXT PRIMARY KEY,
    lead_id                TEXT,
    product_interest       TEXT,
    budget_mentioned       TEXT,
    urgency_mentioned      TEXT,
    final_state            TEXT,
    deepest_state          TEXT,
    turn_count             INTEGER,
    intents_fired          TEXT,
    slots                  TEXT,
    full_transcript        TEXT,
    lead_score             INTEGER,
    lead_tier              TEXT,
    summary_text           TEXT,
    created_at             TEXT,
    tenant_id              TEXT,
    budget_numeric         REAL,
    phone                  TEXT,
    phone_norm             TEXT,
    campaign_type          TEXT,
    offer_explained        INTEGER,
    wa_triggered           INTEGER,
    customer_response      TEXT,
    recording_url          TEXT,
    first_response_latency REAL,
    avg_response_latency   REAL,
    interest_signals       INTEGER,
    rejection_signals      INTEGER,
    cta_accepted           INTEGER,
    duration_seconds       INTEGER,
    caller_name            TEXT,
    started_at             TEXT,
    call_number            INTEGER
);
CREATE INDEX IF NOT EXISTS idx_call_summaries_phone ON call_summaries(phone_norm);

CREATE TABLE IF NOT EXISTS outbound_leads (
    id                      TEXT PRIMARY KEY,
    tenant_id               TEXT,
    name                    TEXT,
    phone                   TEXT,
    phone_norm              TEXT,
    source                  TEXT,
    notes                   TEXT,
    status                  TEXT,
    retry_count             INTEGER,
    next_call_at            TEXT,
    last_called_at          TEXT,
    campaign_id             TEXT,
    created_at              TEXT,
    campaign_type           TEXT,
    wa_sent                 INTEGER,
    wa_sent_at              TEXT,
    funnel_type             TEXT,
    lead_stage              TEXT,
    prior_purchase_id       TEXT,
    visit_date              TEXT,
    visit_date_status       TEXT,
    walked_in_at            TEXT,
    converted_at            TEXT,
    pickup_attempt_count    INTEGER,
    answered_no_date_count  INTEGER,
    objection_type          TEXT,
    ad_campaign_id          TEXT,
    cooldown_until          TEXT,
    dnc                     INTEGER,
    contact_id              TEXT,
    confirm_call_attempted  INTEGER,
    product_interest        TEXT,
    batch_id                TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbound_leads_phone ON outbound_leads(phone_norm);
CREATE INDEX IF NOT EXISTS idx_outbound_leads_batch ON outbound_leads(batch_id);

CREATE TABLE IF NOT EXISTS whatsapp_conversations (
    id             TEXT PRIMARY KEY,
    lead_id        TEXT,
    phone          TEXT,
    phone_norm     TEXT,
    message_type   TEXT,
    direction      TEXT,
    content        TEXT,
    media_url      TEXT,
    context        TEXT,
    created_at     TEXT,
    message_status TEXT
);
CREATE INDEX IF NOT EXISTS idx_whatsapp_phone ON whatsapp_conversations(phone_norm);

CREATE TABLE IF NOT EXISTS findings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT,
    call_uuid  TEXT,
    turn       INTEGER,
    check_name TEXT,
    severity   TEXT,
    summary    TEXT,
    evidence   TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_call ON findings(call_uuid);

CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    started_at TEXT,
    finished_at TEXT,
    calls_checked INTEGER,
    findings_count INTEGER
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
