# -*- coding: utf-8 -*-
"""
enrich.py — pulls call_logs, call_summaries, outbound_leads, and
whatsapp_conversations and mirrors them into the local SQLite audit.db,
joined to audit_events by call_uuid, and to each other by a normalized phone
(outbound_leads.phone carries a '+' prefix; call_logs.to_number,
call_summaries.phone, and whatsapp_conversations.phone are all bare digits —
normalize_phone() from supabase_calling.py, already the project's own
established fix for this exact inconsistency, is reused here rather than
reinvented).

Connects via AUDIT_HARNESS_DB_URL — a direct Postgres connection for the
audit_readonly role (GRANT SELECT only; INSERT/UPDATE/DELETE are not granted
and a live write attempt against this role correctly raised
InsufficientPrivilege). This is a structural guarantee enforced by Postgres
itself: unlike hitting the REST API with a key and simply not calling POST/
PATCH/DELETE, this module could try to write and it would still fail.

Usage: python3 enrich.py [--since-days 30]
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/home/voiceagent/voice-ai")
from supabase_calling import normalize_phone  # noqa: E402

from config import AUDIT_HARNESS_DB_URL, TENANT_ID
from db import connect


def _pg_connect():
    conn = psycopg2.connect(AUDIT_HARNESS_DB_URL, connect_timeout=15)
    conn.set_session(readonly=True, autocommit=True)
    return conn


def enrich_call_logs(pg, sqlite_conn, since_dt) -> int:
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT * FROM public.call_logs
           WHERE tenant_id = %s AND started_at >= %s
           ORDER BY started_at ASC""",
        (TENANT_ID, since_dt),
    )
    rows = cur.fetchall()
    for r in rows:
        sqlite_conn.execute(
            """INSERT INTO call_logs (call_uuid, lead_id, from_number, to_number, to_number_norm,
                   direction, caller_name, status, duration_seconds, started_at, ended_at,
                   hangup_cause, recording_url, tenant_id, recording_duration, call_number)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(call_uuid) DO UPDATE SET
                   status=excluded.status, duration_seconds=excluded.duration_seconds,
                   ended_at=excluded.ended_at, hangup_cause=excluded.hangup_cause,
                   recording_url=excluded.recording_url, recording_duration=excluded.recording_duration,
                   call_number=excluded.call_number""",
            (
                r.get("call_uuid"), r.get("lead_id"), r.get("from_number"), r.get("to_number"),
                normalize_phone(r.get("to_number")), r.get("direction"), r.get("caller_name"),
                r.get("status"), r.get("duration_seconds"), str(r.get("started_at")), str(r.get("ended_at")) if r.get("ended_at") else None,
                r.get("hangup_cause"), r.get("recording_url"), r.get("tenant_id"),
                r.get("recording_duration"), r.get("call_number"),
            ),
        )
    sqlite_conn.commit()
    return len(rows)


def enrich_call_summaries(pg, sqlite_conn, since_dt) -> int:
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT * FROM public.call_summaries
           WHERE tenant_id = %s AND created_at >= %s
           ORDER BY created_at ASC""",
        (TENANT_ID, since_dt),
    )
    rows = cur.fetchall()
    for r in rows:
        sqlite_conn.execute(
            """INSERT INTO call_summaries (call_uuid, lead_id, product_interest, budget_mentioned,
                   urgency_mentioned, final_state, deepest_state, turn_count, intents_fired, slots,
                   full_transcript, lead_score, lead_tier, summary_text, created_at, tenant_id,
                   budget_numeric, phone, phone_norm, campaign_type, offer_explained, wa_triggered,
                   customer_response, recording_url, first_response_latency, avg_response_latency,
                   interest_signals, rejection_signals, cta_accepted, duration_seconds, caller_name,
                   started_at, call_number)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(call_uuid) DO UPDATE SET
                   final_state=excluded.final_state, deepest_state=excluded.deepest_state,
                   turn_count=excluded.turn_count, intents_fired=excluded.intents_fired,
                   slots=excluded.slots, full_transcript=excluded.full_transcript,
                   lead_score=excluded.lead_score, lead_tier=excluded.lead_tier,
                   offer_explained=excluded.offer_explained, wa_triggered=excluded.wa_triggered,
                   customer_response=excluded.customer_response, cta_accepted=excluded.cta_accepted""",
            (
                r.get("call_uuid"), r.get("lead_id"), r.get("product_interest"), r.get("budget_mentioned"),
                r.get("urgency_mentioned"), r.get("final_state"), r.get("deepest_state"), r.get("turn_count"),
                json.dumps(r.get("intents_fired") or []), json.dumps(r.get("slots") or {}),
                json.dumps(r.get("full_transcript") or []), r.get("lead_score"), r.get("lead_tier"),
                r.get("summary_text"), str(r.get("created_at")), r.get("tenant_id"), r.get("budget_numeric"),
                r.get("phone"), normalize_phone(r.get("phone")), r.get("campaign_type"),
                r.get("offer_explained"), r.get("wa_triggered"), r.get("customer_response"),
                r.get("recording_url"), r.get("first_response_latency"), r.get("avg_response_latency"),
                r.get("interest_signals"), r.get("rejection_signals"), r.get("cta_accepted"),
                r.get("duration_seconds"), r.get("caller_name"), str(r.get("started_at")) if r.get("started_at") else None,
                r.get("call_number"),
            ),
        )
    sqlite_conn.commit()
    return len(rows)


def enrich_outbound_leads(pg, sqlite_conn) -> int:
    # No created_at window here on purpose — a lead created long ago can still
    # be the target of a call inside the report window, and dnc/status is
    # always current-state, not historical, so the full table is small enough
    # (thousands of rows, not millions) to just mirror in full every run.
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM public.outbound_leads WHERE tenant_id = %s", (TENANT_ID,))
    rows = cur.fetchall()
    for r in rows:
        sqlite_conn.execute(
            """INSERT INTO outbound_leads (id, tenant_id, name, phone, phone_norm, source, notes,
                   status, retry_count, next_call_at, last_called_at, campaign_id, created_at,
                   campaign_type, wa_sent, wa_sent_at, funnel_type, lead_stage, prior_purchase_id,
                   visit_date, visit_date_status, walked_in_at, converted_at, pickup_attempt_count,
                   answered_no_date_count, objection_type, ad_campaign_id, cooldown_until, dnc,
                   contact_id, confirm_call_attempted, product_interest, batch_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   status=excluded.status, dnc=excluded.dnc, cooldown_until=excluded.cooldown_until,
                   answered_no_date_count=excluded.answered_no_date_count, visit_date=excluded.visit_date,
                   visit_date_status=excluded.visit_date_status, wa_sent=excluded.wa_sent,
                   last_called_at=excluded.last_called_at, retry_count=excluded.retry_count""",
            (
                r.get("id"), r.get("tenant_id"), r.get("name"), r.get("phone"), normalize_phone(r.get("phone")),
                r.get("source"), r.get("notes"), r.get("status"), r.get("retry_count"),
                str(r.get("next_call_at")) if r.get("next_call_at") else None,
                str(r.get("last_called_at")) if r.get("last_called_at") else None,
                r.get("campaign_id"), str(r.get("created_at")), r.get("campaign_type"),
                r.get("wa_sent"), str(r.get("wa_sent_at")) if r.get("wa_sent_at") else None,
                r.get("funnel_type"), r.get("lead_stage"),
                r.get("prior_purchase_id"), r.get("visit_date"), r.get("visit_date_status"),
                str(r.get("walked_in_at")) if r.get("walked_in_at") else None,
                str(r.get("converted_at")) if r.get("converted_at") else None,
                r.get("pickup_attempt_count"),
                r.get("answered_no_date_count"), r.get("objection_type"), r.get("ad_campaign_id"),
                str(r.get("cooldown_until")) if r.get("cooldown_until") else None,
                r.get("dnc"), r.get("contact_id"), r.get("confirm_call_attempted"),
                r.get("product_interest"), r.get("batch_id"),
            ),
        )
    sqlite_conn.commit()
    return len(rows)


def enrich_whatsapp(pg, sqlite_conn, since_dt) -> int:
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT * FROM public.whatsapp_conversations
           WHERE created_at >= %s
           ORDER BY created_at ASC""",
        (since_dt,),
    )
    rows = cur.fetchall()
    for r in rows:
        sqlite_conn.execute(
            """INSERT INTO whatsapp_conversations (id, lead_id, phone, phone_norm, message_type,
                   direction, content, media_url, context, created_at, message_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET message_status=excluded.message_status""",
            (
                str(r.get("id")), r.get("lead_id"), r.get("phone"), normalize_phone(r.get("phone")),
                r.get("message_type"), r.get("direction"), r.get("content"), r.get("media_url"),
                json.dumps(r.get("context")) if r.get("context") is not None else None,
                str(r.get("created_at")), r.get("message_status"),
            ),
        )
    sqlite_conn.commit()
    return len(rows)


def run(since_days: int = 30) -> None:
    if not AUDIT_HARNESS_DB_URL:
        print("AUDIT_HARNESS_DB_URL not set — nothing to enrich")
        return
    since_dt = datetime.now(timezone.utc) - timedelta(days=since_days)
    pg = _pg_connect()
    sqlite_conn = connect()
    n1 = enrich_call_logs(pg, sqlite_conn, since_dt)
    n2 = enrich_call_summaries(pg, sqlite_conn, since_dt)
    n3 = enrich_outbound_leads(pg, sqlite_conn)
    n4 = enrich_whatsapp(pg, sqlite_conn, since_dt)
    pg.close()
    sqlite_conn.close()
    print(f"enrich: call_logs={n1} call_summaries={n2} outbound_leads={n3} whatsapp_conversations={n4} (since {since_dt.isoformat()})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-days", type=int, default=30)
    args = ap.parse_args()
    run(args.since_days)
