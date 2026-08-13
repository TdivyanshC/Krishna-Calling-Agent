# -*- coding: utf-8 -*-
"""
checks.py — runs every check against the local SQLite mirror (audit.db) and
writes results to the findings table, one row per (call_uuid, turn, check).

Each check function returns a list of finding dicts:
    {"call_uuid": ..., "turn": ..., "check": ..., "severity": ..., "summary": ..., "evidence": {...}}
severity is one of: critical, high, medium, low, info.

IMPORTANT data-availability caveat: audit_log.py (logs/audit.jsonl) is new as
of today -- there is no historical audit-event data for calls before it
started. Checks that read audit_events (reply_play_failures,
intents_tracking_gap, empty_stt_ratio, latency_stats, long_clip_no_bargein)
can therefore only ever find something in TODAY's traffic; a 0 on a 30-day
run for one of those means "no audit-log data existed to check", not
"nothing wrong happened in the last 30 days". Checks built on call_summaries/
call_logs/outbound_leads (dnc_phrase_missed, date_mentioned_no_capture,
turn_count_anomalies, calling_window, retry_ladder, cross_funnel_duplicate)
don't have this limitation -- those tables go back the full window.

Usage: python3 checks.py
"""
import json
import os
import statistics
import sys
import wave
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, "/home/voiceagent/voice-ai")
from knowledge_react_abc import REACT_ABC_INTENTS  # noqa: E402
from webhook_reactivation import _is_explicit_optout, _phrase_in_tokens, _tokenize  # noqa: E402

from config import CALL_START_HOUR_IST, CALL_END_HOUR_BY_FUNNEL_IST, CALL_END_HOUR_DEFAULT_IST
from db import connect

IST = ZoneInfo("Asia/Kolkata")
STATIC_DIR = "/home/voiceagent/voice-ai/tts-cache/static"

_DNC_PHRASES = REACT_ABC_INTENTS.get("dnc", [])
_DATE_PHRASES = REACT_ABC_INTENTS.get("appointment_confirm", [])


def _row_matches_dnc(text: str) -> bool:
    t = text.lower().strip()
    if not t:
        return False
    tokens = _tokenize(t)
    boundary_text = f" {' '.join(tokens)} "
    return any(_phrase_in_tokens(kw, boundary_text) for kw in _DNC_PHRASES) or _is_explicit_optout(t)


def _row_matches_date(text: str) -> bool:
    t = text.lower().strip()
    if not t:
        return False
    return any(p in t for p in _DATE_PHRASES) or any(ch.isdigit() for ch in t)


def _wav_duration(key: str) -> float:
    path = os.path.join(STATIC_DIR, f"{key}_hi.wav")
    try:
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


def _user_turns(full_transcript_json: str) -> list[str]:
    try:
        transcript = json.loads(full_transcript_json or "[]")
    except json.JSONDecodeError:
        return []
    return [text for role, text in transcript if role == "user"]


# ─────────────────────────────────────────────────────────────────────────
# 1. reply play failures — customer heard nothing
# ─────────────────────────────────────────────────────────────────────────
def check_reply_play_failures(conn) -> list[dict]:
    findings = []
    for row in conn.execute("SELECT raw FROM audit_events WHERE event IN ('play_timeout','play_result')"):
        rec = json.loads(row["raw"])
        if rec.get("kind") != "reply":
            continue
        if rec["event"] == "play_timeout":
            findings.append({
                "call_uuid": rec.get("call_uuid"), "turn": rec.get("turn"),
                "check": "reply_play_failure", "severity": "high",
                "summary": "Reply play timed out — customer likely heard nothing this turn",
                "evidence": rec,
            })
        elif rec.get("status_code") not in (200, 202):
            findings.append({
                "call_uuid": rec.get("call_uuid"), "turn": rec.get("turn"),
                "check": "reply_play_failure", "severity": "high",
                "summary": f"Reply play returned {rec.get('status_code')} (not 202) — customer likely heard nothing this turn",
                "evidence": rec,
            })
    return findings


# ─────────────────────────────────────────────────────────────────────────
# 2. route intents detected but never reached call_summaries.intents_fired
# ─────────────────────────────────────────────────────────────────────────
def check_intents_tracking_gap(conn) -> list[dict]:
    findings = []
    summaries = {r["call_uuid"]: json.loads(r["intents_fired"] or "[]") for r in conn.execute("SELECT call_uuid, intents_fired FROM call_summaries")}
    for row in conn.execute("SELECT raw FROM audit_events WHERE event = 'route'"):
        rec = json.loads(row["raw"])
        intents = rec.get("intents") or []
        call_uuid = rec.get("call_uuid")
        if intents and call_uuid in summaries and not summaries[call_uuid]:
            findings.append({
                "call_uuid": call_uuid, "turn": rec.get("turn"),
                "check": "intents_tracking_gap", "severity": "medium",
                "summary": f"Turn detected intents {intents} but call_summaries.intents_fired is empty",
                "evidence": rec,
            })
    return findings


# ─────────────────────────────────────────────────────────────────────────
# 3. DNC phrase in transcript but outbound_leads.dnc is false
# ─────────────────────────────────────────────────────────────────────────
def check_dnc_phrase_missed(conn) -> list[dict]:
    findings = []
    leads = {r["phone_norm"]: r["dnc"] for r in conn.execute("SELECT phone_norm, dnc FROM outbound_leads") if r["phone_norm"]}
    for row in conn.execute("SELECT call_uuid, phone_norm, full_transcript FROM call_summaries"):
        user_turns = _user_turns(row["full_transcript"])
        matched_text = next((t for t in user_turns if _row_matches_dnc(t)), None)
        if not matched_text:
            continue
        phone_norm = row["phone_norm"]
        dnc_value = leads.get(phone_norm)
        if dnc_value in (1, True):
            continue  # correctly marked
        findings.append({
            "call_uuid": row["call_uuid"], "turn": None,
            "check": "dnc_phrase_missed", "severity": "critical",
            "summary": (
                "Transcript contains a DNC phrase but outbound_leads.dnc is not true"
                if phone_norm in leads else
                "Transcript contains a DNC phrase but no matching outbound_leads row exists to check"
            ),
            "evidence": {"phone_norm": phone_norm, "matched_text": matched_text, "dnc_in_leads": dnc_value},
        })
    return findings


# ─────────────────────────────────────────────────────────────────────────
# 4. date mentioned in transcript but never captured anywhere
# ─────────────────────────────────────────────────────────────────────────
def check_date_mentioned_no_capture(conn) -> list[dict]:
    findings = []
    leads = {r["phone_norm"]: r["visit_date"] for r in conn.execute("SELECT phone_norm, visit_date FROM outbound_leads") if r["phone_norm"]}
    for row in conn.execute("SELECT call_uuid, phone_norm, slots, full_transcript FROM call_summaries"):
        user_turns = _user_turns(row["full_transcript"])
        matched_text = next((t for t in user_turns if _row_matches_date(t)), None)
        if not matched_text:
            continue
        try:
            slots = json.loads(row["slots"] or "{}")
        except json.JSONDecodeError:
            slots = {}
        has_slot_date = any("date" in str(k).lower() for k in slots.keys())
        has_lead_date = bool(leads.get(row["phone_norm"]))
        if has_slot_date or has_lead_date:
            continue
        findings.append({
            "call_uuid": row["call_uuid"], "turn": None,
            "check": "date_mentioned_no_capture", "severity": "medium",
            "summary": "Transcript mentions a date/day but neither call_summaries.slots nor outbound_leads.visit_date has one",
            "evidence": {"matched_text": matched_text},
        })
    return findings


# ─────────────────────────────────────────────────────────────────────────
# 5. turn-count anomalies
# ─────────────────────────────────────────────────────────────────────────
def check_turn_count_anomalies(conn) -> list[dict]:
    """
    _resolve_call_state()'s default ("QUALIFY_PRODUCT", or "" for react
    flows before react_state exists) means EVERY zero-turn call already has
    a non-null final_state -- that's the normal shape for an unanswered/
    no-engagement call, not a contradiction. Only a REAL state name (the
    call progressed somewhere) alongside turn_count=0 is actually anomalous.
    """
    NO_PROGRESS_STATES = {"QUALIFY_PRODUCT", "GREETING", "", None}
    findings = []
    for row in conn.execute("SELECT call_uuid, turn_count, final_state FROM call_summaries"):
        if (row["turn_count"] or 0) >= 25:
            findings.append({
                "call_uuid": row["call_uuid"], "turn": None,
                "check": "turn_count_cap_hit", "severity": "medium",
                "summary": f"turn_count={row['turn_count']} — likely hit a conversation cap or loop",
                "evidence": dict(row),
            })
        if (row["turn_count"] or 0) == 0 and row["final_state"] not in NO_PROGRESS_STATES:
            findings.append({
                "call_uuid": row["call_uuid"], "turn": None,
                "check": "final_state_with_zero_turns", "severity": "medium",
                "summary": f"final_state={row['final_state']!r} recorded despite turn_count=0",
                "evidence": dict(row),
            })
    return findings


# ─────────────────────────────────────────────────────────────────────────
# 6. empty-STT ratio per call
# ─────────────────────────────────────────────────────────────────────────
def check_empty_stt_ratio(conn, threshold: float = 0.5, min_turns: int = 3) -> list[dict]:
    findings = []
    per_call = defaultdict(lambda: [0, 0])  # call_uuid -> [empty, total]
    for row in conn.execute("SELECT raw FROM audit_events WHERE event = 'stt'"):
        rec = json.loads(row["raw"])
        call_uuid = rec.get("call_uuid")
        per_call[call_uuid][1] += 1
        if rec.get("empty"):
            per_call[call_uuid][0] += 1
    for call_uuid, (empty, total) in per_call.items():
        if total >= min_turns and empty / total > threshold:
            findings.append({
                "call_uuid": call_uuid, "turn": None,
                "check": "high_empty_stt_ratio", "severity": "low",
                "summary": f"{empty}/{total} STT turns returned empty ({empty/total:.0%})",
                "evidence": {"empty": empty, "total": total},
            })
    return findings


# ─────────────────────────────────────────────────────────────────────────
# 7. turn_end latency percentiles (run-level, not per-call)
# ─────────────────────────────────────────────────────────────────────────
def check_latency_stats(conn) -> list[dict]:
    # Exclude turns whose stt was empty (same "substantive turns only" rule
    # webhook.py/webhook_reactivation.py already apply to their own
    # first_response_latency/avg_response_latency).
    empty_turns = set()
    for row in conn.execute("SELECT raw FROM audit_events WHERE event = 'stt'"):
        rec = json.loads(row["raw"])
        if rec.get("empty"):
            empty_turns.add((rec.get("call_uuid"), rec.get("turn")))

    latencies = []
    for row in conn.execute("SELECT raw FROM audit_events WHERE event = 'turn_end'"):
        rec = json.loads(row["raw"])
        if (rec.get("call_uuid"), rec.get("turn")) in empty_turns:
            continue
        if rec.get("latency_ms") is not None:
            latencies.append(rec["latency_ms"])

    if not latencies:
        return []
    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    return [{
        "call_uuid": None, "turn": None,
        "check": "latency_stats", "severity": "info",
        "summary": f"turn_end latency (substantive turns only): p50={p50:.0f}ms p95={p95:.0f}ms n={len(latencies)}",
        "evidence": {"p50_ms": p50, "p95_ms": p95, "n": len(latencies)},
    }]


# ─────────────────────────────────────────────────────────────────────────
# 8. calls outside the 10am-8pm IST window
# ─────────────────────────────────────────────────────────────────────────
# webhook.py's /trigger-call window guard went live 2026-07-19 11:43 UTC (see
# project_trigger_call_window_guard_fix memory) -- calls dispatched via
# /trigger-call before this should have had NO server-side window enforcement
# at all (only outbound_orchestrator.py's own tick() gate, client-side).
TRIGGER_CALL_WINDOW_FIX_DEPLOYED_AT = datetime(2026, 7, 19, 11, 43, 0, tzinfo=timezone.utc)


def check_calling_window(conn) -> list[dict]:
    """
    Bound is per-funnel: fresh_cta 10-22 IST, everything else (reactivation/
    react_a/b/c, fresh_lead, etc.) 10-20 IST -- matches what webhook.py's
    is_calling_window(campaign) and outbound_orchestrator.py's tick() now
    enforce per-lane. campaign_type comes from call_summaries (call_logs has
    no campaign_type of its own), joined by call_uuid.
    """
    findings = []
    campaign_by_call = {r["call_uuid"]: r["campaign_type"] for r in conn.execute("SELECT call_uuid, campaign_type FROM call_summaries")}
    after_fix_violations = 0
    for row in conn.execute("SELECT call_uuid, started_at FROM call_logs WHERE direction = 'outbound' AND started_at IS NOT NULL"):
        try:
            ts = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
        except ValueError:
            continue
        ist = ts.astimezone(IST)
        campaign = campaign_by_call.get(row["call_uuid"])
        end_hour = CALL_END_HOUR_BY_FUNNEL_IST.get(campaign, CALL_END_HOUR_DEFAULT_IST)
        if not (CALL_START_HOUR_IST <= ist.hour < end_hour):
            after_fix = ts > TRIGGER_CALL_WINDOW_FIX_DEPLOYED_AT
            if after_fix:
                after_fix_violations += 1
            findings.append({
                "call_uuid": row["call_uuid"], "turn": None,
                "check": "outside_calling_window", "severity": "critical" if after_fix else "medium",
                "summary": (
                    f"Outbound call ({campaign or 'unknown'}) started at {ist.strftime('%Y-%m-%d %H:%M')} IST, outside {CALL_START_HOUR_IST}:00-{end_hour}:00"
                    + (" — AFTER the /trigger-call window fix was deployed (2026-07-19 11:43 UTC)" if after_fix else "")
                ),
                "evidence": {"started_at_ist": ist.isoformat(), "campaign_type": campaign, "end_hour": end_hour, "after_window_fix_deploy": after_fix},
            })
    if after_fix_violations:
        findings.append({
            "call_uuid": None, "turn": None,
            "check": "calling_window_fix_ineffective", "severity": "critical",
            "summary": f"{after_fix_violations} outside-window call(s) happened AFTER the /trigger-call window fix deployed — the fix may not be working",
            "evidence": {"count": after_fix_violations},
        })
    return findings


# ─────────────────────────────────────────────────────────────────────────
# 9. retry ladder / dial-after-dnc
# ─────────────────────────────────────────────────────────────────────────
def check_retry_ladder(conn) -> list[dict]:
    """
    Two sub-checks:
      - call_number sequence per phone should be spaced out -- two calls
        < 30 min apart is almost certainly a double-dial, not a deliberate
        retry cadence.
      - a call placed AFTER the call where a "dnc" intent was actually
        detected (call_summaries.intents_fired, available for the full
        history) for the same phone. outbound_leads.dnc is deliberately NOT
        used for this (a first-check version did) -- outbound_leads has no
        dnc-set-at timestamp, so "dnc is currently true AND this phone has
        >0 calls" is true for nearly every opted-out lead by construction
        (they had to be called at least once to opt out) and isn't evidence
        of anything wrong. Anchoring on the actual call where "dnc" fired
        gives a real before/after to check.
    """
    findings = []
    by_phone = defaultdict(list)
    for row in conn.execute("SELECT call_uuid, to_number_norm, started_at, call_number FROM call_logs WHERE direction='outbound' AND to_number_norm IS NOT NULL ORDER BY started_at ASC"):
        by_phone[row["to_number_norm"]].append(row)

    for phone, calls in by_phone.items():
        for i in range(1, len(calls)):
            prev, cur = calls[i - 1], calls[i]
            try:
                t_prev = datetime.fromisoformat(prev["started_at"].replace("Z", "+00:00"))
                t_cur = datetime.fromisoformat(cur["started_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            gap_min = (t_cur - t_prev).total_seconds() / 60
            if gap_min < 30:
                findings.append({
                    "call_uuid": cur["call_uuid"], "turn": None,
                    "check": "retry_spacing_violation", "severity": "medium",
                    "summary": f"Call to {phone} only {gap_min:.0f} min after the previous call (call_number {prev['call_number']}->{cur['call_number']})",
                    "evidence": {"phone_norm": phone, "prev_call": prev["call_uuid"], "gap_minutes": round(gap_min, 1)},
                })

    dnc_call_by_phone = {}  # phone_norm -> (started_at, call_uuid) of the earliest call where "dnc" fired
    for row in conn.execute("SELECT call_uuid, phone_norm, started_at, intents_fired FROM call_summaries WHERE phone_norm IS NOT NULL ORDER BY started_at ASC"):
        try:
            intents = json.loads(row["intents_fired"] or "[]")
        except json.JSONDecodeError:
            intents = []
        if "dnc" in intents and row["phone_norm"] not in dnc_call_by_phone:
            dnc_call_by_phone[row["phone_norm"]] = (row["started_at"], row["call_uuid"])

    for phone, (dnc_started_at, dnc_call_uuid) in dnc_call_by_phone.items():
        try:
            t_dnc = datetime.fromisoformat(dnc_started_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        for cur in by_phone.get(phone, []):
            if cur["call_uuid"] == dnc_call_uuid:
                continue
            try:
                t_cur = datetime.fromisoformat(cur["started_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            if t_cur > t_dnc:
                findings.append({
                    "call_uuid": cur["call_uuid"], "turn": None,
                    "check": "dial_after_dnc_detected", "severity": "critical",
                    "summary": f"{phone} dialed again at {t_cur.isoformat()}, after call {dnc_call_uuid[:8]} where a 'dnc' intent fired at {t_dnc.isoformat()}",
                    "evidence": {"phone_norm": phone, "dnc_call_uuid": dnc_call_uuid, "dnc_at": dnc_started_at, "later_call_at": cur["started_at"]},
                })
    return findings


# ─────────────────────────────────────────────────────────────────────────
# 10. same phone dialed in both react and fresh_cta campaigns
# ─────────────────────────────────────────────────────────────────────────
def check_cross_funnel_duplicate(conn) -> list[dict]:
    findings = []
    campaigns_by_phone = defaultdict(set)
    calls_by_phone = defaultdict(list)
    for row in conn.execute("SELECT call_uuid, phone_norm, campaign_type FROM call_summaries WHERE phone_norm IS NOT NULL"):
        campaigns_by_phone[row["phone_norm"]].add(row["campaign_type"])
        calls_by_phone[row["phone_norm"]].append(row["call_uuid"])
    react_set = {"react_a", "react_b", "react_c", "reactivation"}
    for phone, campaigns in campaigns_by_phone.items():
        if campaigns & react_set and "fresh_cta" in campaigns:
            findings.append({
                "call_uuid": calls_by_phone[phone][-1], "turn": None,
                "check": "cross_funnel_duplicate", "severity": "medium",
                "summary": f"{phone} was dialed under both a reactivation campaign and fresh_cta",
                "evidence": {"phone_norm": phone, "campaigns": sorted(campaigns), "call_uuids": calls_by_phone[phone]},
            })
    return findings


# ─────────────────────────────────────────────────────────────────────────
# 11. long clip played with no barge-in — possible missed barge-in
# ─────────────────────────────────────────────────────────────────────────
def check_long_clip_no_bargein(conn, min_duration_s: float = 8.0) -> list[dict]:
    findings = []
    bargein_turns = set()
    for row in conn.execute("SELECT raw FROM audit_events WHERE event = 'barge_in'"):
        rec = json.loads(row["raw"])
        bargein_turns.add((rec.get("call_uuid"), rec.get("turn")))

    # Next substantive (non-empty) STT per (call_uuid, turn) that immediately
    # follows, with its timestamp -- used to check whether the customer's
    # next utterance started while the clip should still have been playing.
    stt_by_call = defaultdict(list)
    for row in conn.execute("SELECT raw FROM audit_events WHERE event = 'stt' AND raw NOT LIKE '%\"empty\": true%'"):
        rec = json.loads(row["raw"])
        stt_by_call[rec.get("call_uuid")].append(rec)

    for row in conn.execute("SELECT raw FROM audit_events WHERE event = 'tts' AND raw LIKE '%\"cached\": true%'"):
        rec = json.loads(row["raw"])
        key = rec.get("key")
        duration = _wav_duration(key)
        if duration < min_duration_s:
            continue
        call_uuid, turn = rec.get("call_uuid"), rec.get("turn")
        if (call_uuid, turn) in bargein_turns:
            continue  # barge-in correctly fired
        try:
            play_ts = datetime.fromisoformat(rec["ts"])
        except (ValueError, KeyError):
            continue
        next_turns = [s for s in stt_by_call.get(call_uuid, []) if (s.get("turn") or 0) > (turn or 0)]
        overlapping = None
        for s in next_turns:
            try:
                s_ts = datetime.fromisoformat(s["ts"])
            except ValueError:
                continue
            if (s_ts - play_ts).total_seconds() < duration:
                overlapping = s
                break
        if overlapping:
            findings.append({
                "call_uuid": call_uuid, "turn": turn,
                "check": "long_clip_possible_missed_bargein", "severity": "medium",
                "summary": f"'{key}' ({duration:.1f}s) — next customer turn started {(datetime.fromisoformat(overlapping['ts']) - play_ts).total_seconds():.1f}s later, before the clip should have finished, with no barge_in event",
                "evidence": {"key": key, "duration_s": round(duration, 1), "next_stt_ts": overlapping["ts"], "next_stt_text": overlapping.get("text")},
            })
    return findings


# ─────────────────────────────────────────────────────────────────────────
# 12. leads stuck at status='in_progress' — see
# project_silent_status_write_failure_pattern memory: the ivr_detected and
# no_date_stalled outbound_leads.status writes violate the DB check
# constraint and fail silently (httpx doesn't raise on 4xx, and the guard
# PATCH's error handling only checks the empty-200 no-match case, not a real
# error status). Both failures happen while status is still 'in_progress'
# (set by lock_lead()/mark_in_progress() before dial) and never advance it,
# so a lead can fall out of the normal cadence permanently and silently.
# Not a re-dial-safety risk (in_progress is excluded from selection), but a
# lead sitting here past cleanup_stuck_leads()'s own ~5-minute sweep window
# means something is wrong and isn't self-healing.
# ─────────────────────────────────────────────────────────────────────────
def check_stuck_in_progress(conn, stale_minutes: int = 15) -> list[dict]:
    findings = []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    for row in conn.execute("SELECT id, phone_norm, last_called_at, campaign_type, batch_id FROM outbound_leads WHERE status = 'in_progress'"):
        if not row["last_called_at"]:
            continue
        try:
            last_called = datetime.fromisoformat(row["last_called_at"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if last_called.tzinfo is None:
            last_called = last_called.replace(tzinfo=timezone.utc)
        if last_called < cutoff:
            age_min = (datetime.now(timezone.utc) - last_called).total_seconds() / 60
            findings.append({
                "call_uuid": None, "turn": None,
                "check": "stuck_in_progress", "severity": "high",
                "summary": f"{row['phone_norm']} stuck at status='in_progress' for {age_min:.0f} min (last_called_at={row['last_called_at']}) — cleanup_stuck_leads() should have processed this by now",
                "evidence": {"lead_id": row["id"], "phone_norm": row["phone_norm"], "campaign_type": row["campaign_type"], "batch_id": row["batch_id"], "age_minutes": round(age_min, 1)},
            })
    return findings


ALL_CHECKS = [
    check_reply_play_failures,
    check_intents_tracking_gap,
    check_dnc_phrase_missed,
    check_date_mentioned_no_capture,
    check_turn_count_anomalies,
    check_empty_stt_ratio,
    check_latency_stats,
    check_calling_window,
    check_retry_ladder,
    check_cross_funnel_duplicate,
    check_long_clip_no_bargein,
    check_stuck_in_progress,
]


def run() -> str:
    conn = connect()
    run_id = datetime.now(timezone.utc).isoformat()
    started_at = run_id
    all_findings = []
    for fn in ALL_CHECKS:
        try:
            findings = fn(conn)
        except Exception as exc:
            print(f"check {fn.__name__} raised {type(exc).__name__}: {exc}")
            continue
        all_findings.extend(findings)
        print(f"{fn.__name__}: {len(findings)} findings")

    for f in all_findings:
        conn.execute(
            """INSERT INTO findings (run_id, call_uuid, turn, check_name, severity, summary, evidence, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (run_id, f["call_uuid"], f["turn"], f["check"], f["severity"], f["summary"], json.dumps(f["evidence"], ensure_ascii=False, default=str), datetime.now(timezone.utc).isoformat()),
        )
    calls_checked = conn.execute("SELECT COUNT(*) FROM call_summaries").fetchone()[0]
    conn.execute(
        "INSERT INTO runs (run_id, started_at, finished_at, calls_checked, findings_count) VALUES (?,?,?,?,?)",
        (run_id, started_at, datetime.now(timezone.utc).isoformat(), calls_checked, len(all_findings)),
    )
    conn.commit()
    conn.close()
    print(f"\nrun {run_id}: {len(all_findings)} findings across {calls_checked} calls")
    return run_id


if __name__ == "__main__":
    run()
