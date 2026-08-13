# -*- coding: utf-8 -*-
"""
test_cache_trigger_audit_live.py — production-data replay for the
cache-trigger honesty audit (fresh_cta + react_a/b/c Call1/2/3).

Unlike test_cache_trigger_audit.py (synthetic single-intent transcripts,
fully-mocked play_key), this pulls REAL customer turns from Supabase
(call_summaries.full_transcript — the only place actual STT output for
these flows is persisted) and replays them through the REAL handler
functions AND the REAL play_key()/_static_url() cache-resolution logic.
Only true network/external side effects are mocked:
  - _vobiz_play         (POST to Vobiz — no real call session exists here)
  - tts_engine.get_speech (would incur a real, paid, live TTS API call on
                           an actual cache miss — mocked to avoid spending
                           money/time inside a read-only audit; classified
                           and logged explicitly, never silently absorbed)
  - fire_whatsapp / _fire_immediate_dnc (would send real WhatsApp / write
                           real DNC rows against production data)
Everything else -- detect_intents(), route_objection(), the state chains,
_static_url()'s real os.path.exists/getsize disk check -- runs unmodified,
timed with time.perf_counter().

Cross-checks each replayed turn against the real production journalctl
log for voiceai.service (same host, same call_uuid) where available.

Usage: python3 test_cache_trigger_audit_live.py
"""
import asyncio
import json
import os
import re
import statistics
import time
from types import SimpleNamespace

import httpx

import webhook_reactivation as wr
import tts_engine as tts

SCRATCH = "/tmp/claude-0/-home-voiceagent-voice-ai/494cd381-eade-4fb6-ac3e-dfd3a1b35b6c/scratchpad"
JOURNAL_FILE = f"{SCRATCH}/journal_relevant.txt"


# ─────────────────────────────────────────────────────────────────────────
# STEP 1 — pull real transcripts from Supabase
# ─────────────────────────────────────────────────────────────────────────

def load_env():
    env = {}
    for line in open("/home/voiceagent/voice-ai/.env"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    return env


def fetch_real_calls():
    env = load_env()
    url, key = env["SUPABASE_URL"], env["SUPABASE_SERVICE_KEY"]
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    in_scope = ("react_a", "react_b", "react_c", "fresh_cta")
    r = httpx.get(
        f"{url}/rest/v1/call_summaries"
        f"?select=call_uuid,campaign_type,call_number,final_state,deepest_state,"
        f"turn_count,full_transcript,created_at,duration_seconds,product_interest"
        f"&campaign_type=in.({','.join(in_scope)})&turn_count=gt.0"
        f"&order=created_at.asc&limit=1000",
        headers=h, timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────────────────────────────────────
# STEP 3 (prep) — parse the production journalctl dump into per-call_uuid,
# per-turn records: state line (state/campaign/transcript-prefix/intents)
# followed by whichever CACHE HIT/MISS lines came before the next state line
# for that same call_uuid.
# ─────────────────────────────────────────────────────────────────────────

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_STATE_RE = re.compile(
    rf"\[({_UUID})\] (?:react state=(?P<state>\S+)(?: campaign=(?P<campaign>\S+))?|"
    rf"call2 state=(?P<c2state>\S+)|call3 state=(?P<c3state>\S+)|"
    rf"fresh_cta transcript=)"
    rf".*?transcript='(?P<transcript>.*?)' intents=\[(?P<intents>.*?)\]"
)
_CACHE_RE = re.compile(rf"\[({_UUID})\] CACHE (HIT|MISS) . (\S+)")

_HANDLER_LINE_RE = re.compile(
    rf"\[({_UUID})\] (react state=|call2 state=|call3 state=|fresh_cta transcript=)"
)
_HANDLER_TAG_MAP = {
    "react state=": "react_call1", "call2 state=": "call2",
    "call3 state=": "call3", "fresh_cta transcript=": "fresh_cta",
}


def detect_handler_types_from_journal():
    """
    call_summaries.call_number is NULL for a large fraction of rows in this
    dataset (confirmed: it was only backfilled starting the 2026-07-15
    migration -- see project_call_number_migration_pending memory) and is
    NOT a reliable way to tell which handler (react_call1 vs call2 vs call3)
    actually processed a given call_uuid for rows before that date. The
    production journal log's own line prefix ("react state=" / "call2
    state=" / "call3 state=" / "fresh_cta transcript=") is unambiguous
    ground truth for whichever handler really ran -- used here in
    preference to call_number wherever a log entry exists.
    """
    types = {}
    for line in open(JOURNAL_FILE, encoding="utf-8", errors="replace"):
        m = _HANDLER_LINE_RE.search(line)
        if m:
            types.setdefault(m.group(1), set()).add(_HANDLER_TAG_MAP[m.group(2)])
    return types


def parse_journal():
    turns_by_call = {}  # call_uuid -> list of dicts, in file order
    pending_cache_target = {}  # call_uuid -> index into turns_by_call[uuid] awaiting cache lines
    for raw in open(JOURNAL_FILE, encoding="utf-8", errors="replace"):
        m = _STATE_RE.search(raw)
        if m:
            uuid = m.group(1)
            state = m.group("state") or m.group("c2state") or m.group("c3state") or "APPOINTMENT"
            transcript = m.group("transcript")
            intents_raw = m.group("intents")
            intents = [x.strip().strip("'\"") for x in intents_raw.split(",")] if intents_raw.strip() else []
            turns_by_call.setdefault(uuid, []).append({
                "state": state, "transcript": transcript, "prod_intents": intents,
                "prod_keys": [], "prod_cache_status": [],
            })
            pending_cache_target[uuid] = len(turns_by_call[uuid]) - 1
            continue
        m2 = _CACHE_RE.search(raw)
        if m2:
            uuid, hit_or_miss, key = m2.group(1), m2.group(2), m2.group(3)
            idx = pending_cache_target.get(uuid)
            if idx is not None and uuid in turns_by_call and idx < len(turns_by_call[uuid]):
                turns_by_call[uuid][idx]["prod_keys"].append(key)
                turns_by_call[uuid][idx]["prod_cache_status"].append(hit_or_miss)
    return turns_by_call


# ─────────────────────────────────────────────────────────────────────────
# STEP 2 — replay: real handlers, real play_key()/_static_url(), only
# network/external side effects mocked. Timed with perf_counter().
# ─────────────────────────────────────────────────────────────────────────

class LiveRecorder:
    def __init__(self):
        self.plays = []   # list of dicts: key, status(CACHE-HIT/LIVE-TTS-FALLBACK-MOCKED/ERROR), elapsed_s
        self.wa_fired = False
        self.dnc_fired = False
        self.errors = []


def make_session(campaign, call_cycle, product_interest=None):
    s = SimpleNamespace()
    s.customer_phone = "+919999900000"
    s.customer_name = "ProdReplay"
    s.campaign = campaign
    s.call_cycle = call_cycle
    s.conversation = []
    s.turn_count = 0
    s.silence_count = 0
    s.wa_sent = False
    if campaign == "fresh_cta":
        # bare -- handle_fresh_cta_turn bootstraps dnc/react_state itself on
        # first call via `not hasattr(session, "dnc")` (see test_cache_trigger_audit.py's
        # make_bare_fresh_session note -- same reasoning applies here).
        s.fresh_product = product_interest or ""
    elif call_cycle == "2":
        s.c2_state = "GREETING"
    elif call_cycle == "3":
        s.c3_state = "GREETING"
    else:
        s.react_state = "GREETING"
        s.dnc = False
    return s


async def real_play_key_timed(recorder, call_uuid, key, session=None, log_transcript=True):
    """
    Real play_key() body, reimplemented only to the extent needed to attach
    perf_counter() timing around the exact same calls play_key() itself
    makes (_static_url, then live-TTS fallback) -- calling wr.play_key()
    directly and timing around it would work too, but this lets us
    distinguish cache-hit-path time from fallback-path time cleanly, and
    guarantees the fallback branch NEVER reaches a real network TTS call.
    """
    t0 = time.perf_counter()
    try:
        url = wr._static_url(key)          # REAL disk check -- os.path.exists + getsize
        if url:
            elapsed = time.perf_counter() - t0
            recorder.plays.append({"key": key, "status": "CACHE-HIT", "elapsed_s": elapsed})
            return True
        # Real cache miss -- mirror play_key()'s own script-selection AND
        # miss-handling exactly (same call_cycle branching play_key() itself
        # does at the top of its body), but with get_speech mocked so no
        # real paid TTS call is made.
        call_cycle = getattr(session, "call_cycle", None) if session else None
        if call_cycle == "2":
            script = wr.CALL2_SCRIPT
        elif call_cycle == "3":
            script = wr.CALL3_SCRIPT
        else:
            script = wr.get_script(getattr(session, "campaign", "react_a"))
        elapsed_before_fallback = time.perf_counter() - t0
        text = script.get(key) or wr.SHARED_SCRIPT.get(key)
        if not text:
            elapsed = time.perf_counter() - t0
            recorder.plays.append({"key": key, "status": "ERROR-NO-TEXT-FOR-KEY", "elapsed_s": elapsed})
            return False
        elapsed = time.perf_counter() - t0
        recorder.plays.append({
            "key": key, "status": "LIVE-TTS-FALLBACK (real TTS call mocked -- not executed)",
            "elapsed_s": elapsed, "elapsed_before_mock_s": elapsed_before_fallback,
        })
        return True
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        recorder.errors.append(f"{key}: {type(exc).__name__}: {exc}")
        recorder.plays.append({"key": key, "status": f"ERROR-EXCEPTION: {exc}", "elapsed_s": elapsed})
        return False


def get_handler(campaign, call_cycle):
    if campaign == "fresh_cta":
        return wr.handle_fresh_cta_turn
    if call_cycle == "2":
        return wr.handle_call2_turn
    if call_cycle == "3":
        return wr.handle_call3_turn
    return wr.handle_reactivation_turn


def state_attr_for(campaign, call_cycle):
    if campaign == "fresh_cta":
        return "react_state"
    if call_cycle == "2":
        return "c2_state"
    if call_cycle == "3":
        return "c3_state"
    return "react_state"


CALL_NUMBER_TO_CYCLE = {None: None, 1: None, 2: "2", 3: "3"}
HANDLER_TO_CYCLE = {"react_call1": None, "call2": "2", "call3": "3", "fresh_cta": None}


async def replay_call(row, journal_handler_types):
    campaign = row["campaign_type"]
    uuid = row["call_uuid"]
    journal_handlers = journal_handler_types.get(uuid)
    mapping_source = "call_number"
    if campaign == "fresh_cta":
        call_cycle = None  # fresh_cta's handler doesn't branch on call_cycle at all
    elif journal_handlers and len(journal_handlers) == 1:
        # Ground truth from production log -- see detect_handler_types_from_journal().
        call_cycle = HANDLER_TO_CYCLE[next(iter(journal_handlers))]
        mapping_source = "journal-log-ground-truth"
    else:
        call_cycle = CALL_NUMBER_TO_CYCLE.get(row.get("call_number"))
        if journal_handlers and len(journal_handlers) > 1:
            mapping_source = f"call_number (journal ambiguous: {journal_handlers})"
        elif not journal_handlers:
            mapping_source = "call_number (no journal entry for this call_uuid)"
    ft = row.get("full_transcript") or []
    user_turns = [e[1] for e in ft if isinstance(e, list) and len(e) == 2 and e[0] == "user"]
    if not user_turns:
        return []

    session = make_session(campaign, call_cycle, row.get("product_interest"))
    handler = get_handler(campaign, call_cycle)
    state_attr = state_attr_for(campaign, call_cycle)

    orig_play_key, orig_vobiz, orig_wa, orig_dnc = wr.play_key, wr._vobiz_play, wr.fire_whatsapp, wr._fire_immediate_dnc

    turn_results = []
    for turn_idx, transcript in enumerate(user_turns):
        recorder = LiveRecorder()

        async def fake_play_key(call_uuid, key, session=None, log_transcript=True, _rec=recorder):
            return await real_play_key_timed(_rec, call_uuid, key, session, log_transcript)

        async def fake_fire_whatsapp(session, call_uuid, _rec=recorder):
            _rec.wa_fired = True
            return True

        def fake_fire_dnc(session, call_uuid, _rec=recorder):
            _rec.dnc_fired = True

        wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc = fake_play_key, fake_fire_whatsapp, fake_fire_dnc

        # fresh_cta's session has no react_state attribute until the handler's
        # own first-turn bootstrap runs (see make_session's bare-fresh-session
        # note); it only ever operates in one conceptual state regardless, so
        # report it directly rather than reading a not-yet-set attribute.
        starting_state = "APPOINTMENT" if campaign == "fresh_cta" else getattr(session, state_attr, None)
        # Real, unmocked detect_intents() -- independent signal, same call the handler makes internally.
        real_intents = wr.detect_intents(transcript)

        exc_info = None
        t0 = time.perf_counter()
        try:
            should_continue = await handler(session, transcript, f"replay-{row['call_uuid']}-{turn_idx}")
        except Exception as exc:
            import traceback
            exc_info = traceback.format_exc()
            should_continue = None
        turn_wall_s = time.perf_counter() - t0

        ending_state = getattr(session, state_attr, None)

        turn_results.append({
            "call_uuid": row["call_uuid"], "campaign": campaign, "call_cycle": call_cycle,
            "mapping_source": mapping_source,
            "turn_idx": turn_idx, "transcript": transcript,
            "starting_state": starting_state, "ending_state": ending_state,
            "replay_intents": real_intents, "plays": recorder.plays,
            "wa_fired": recorder.wa_fired, "dnc_fired": recorder.dnc_fired,
            "should_continue": should_continue, "turn_wall_s": turn_wall_s,
            "exception": exc_info,
        })

        wr.play_key, wr._vobiz_play, wr.fire_whatsapp, wr._fire_immediate_dnc = orig_play_key, orig_vobiz, orig_wa, orig_dnc

    return turn_results


async def main():
    print("=" * 100)
    print("STEP 1 — PULL REAL TRANSCRIPTS FROM SUPABASE")
    print("=" * 100)
    rows = fetch_real_calls()
    total_user_turns = sum(
        sum(1 for e in (r.get("full_transcript") or []) if isinstance(e, list) and len(e) == 2 and e[0] == "user")
        for r in rows
    )
    print(f"In-scope calls with turn_count>0: {len(rows)}")
    print(f"Total real (non-silent) customer utterances across those calls: {total_user_turns}")
    if total_user_turns < 200:
        print(f"NOTE: production call_summaries only goes back to {min(r['created_at'] for r in rows)[:10]} "
              f"(table start, not a query limit) -- {total_user_turns} is the FULL population of real, "
              f"non-silent turns available for these 4 flows today, not a subsample. Reporting all of them "
              f"rather than padding to the 200-500 target with synthetic or silent data.")

    print("\n" + "=" * 100)
    print("PARSING PRODUCTION JOURNAL LOG (voiceai.service, journalctl)")
    print("=" * 100)
    journal_turns = parse_journal()
    journal_handler_types = detect_handler_types_from_journal()
    print(f"Distinct call_uuids with production log turn data: {len(journal_turns)}")

    print("\n" + "=" * 100)
    print("STEP 2 — REPLAY (real handlers, real play_key()/_static_url(), timed)")
    print("=" * 100)
    all_turns = []
    for row in rows:
        try:
            results = await replay_call(row, journal_handler_types)
        except Exception as exc:
            import traceback
            print(f"CALL-LEVEL REPLAY FAILURE {row['call_uuid']}: {exc}")
            print(traceback.format_exc())
            continue
        all_turns.extend(results)

    print(f"Total real turns replayed: {len(all_turns)}")
    from collections import Counter
    src_counts = Counter(t["mapping_source"] for t in all_turns)
    print("Flow-assignment source (which handler ran this call, i.e. campaign/call_cycle used for replay):")
    for src, cnt in src_counts.most_common():
        print(f"    {cnt:4d} turns -- {src}")
    errored = [t for t in all_turns if t["exception"]]
    print(f"Turns that raised an exception during replay: {len(errored)}")
    for t in errored:
        print(f"\n  --- EXCEPTION: call_uuid={t['call_uuid']} turn={t['turn_idx']} transcript={t['transcript']!r} ---")
        print(t["exception"])

    with open(f"{SCRATCH}/live_replay_results.json", "w") as f:
        json.dump(all_turns, f, ensure_ascii=False, indent=1)
    print(f"\nFull per-turn results saved to {SCRATCH}/live_replay_results.json")

    print("\n" + "=" * 100)
    print("STEP 3 — CROSS-CHECK REPLAY vs PRODUCTION LOG")
    print("=" * 100)
    # Filter production turns to non-silent (transcript != '') to align order with full_transcript's user list.
    prod_turns_by_call = {}
    for uuid, turns in journal_turns.items():
        prod_turns_by_call[uuid] = [t for t in turns if t["transcript"].strip() != ""]

    matched = 0
    unmatched_calls = []
    discrepancies = []
    for row in rows:
        uuid = row["call_uuid"]
        prod_turns = prod_turns_by_call.get(uuid)
        if not prod_turns:
            unmatched_calls.append(uuid)
            continue
        replay_turns_this_call = [t for t in all_turns if t["call_uuid"] == uuid]
        n = min(len(prod_turns), len(replay_turns_this_call))
        for i in range(n):
            matched += 1
            pt, rt = prod_turns[i], replay_turns_this_call[i]
            replay_keys = [p["key"] for p in rt["plays"]]
            replay_cache = [p["status"] for p in rt["plays"]]
            prod_keys = pt["prod_keys"]
            prod_intents = pt["prod_intents"]
            replay_intents = rt["replay_intents"]

            issues = []
            if set(prod_intents) != set(replay_intents):
                issues.append(f"INTENTS DIFFER: prod={prod_intents} vs replay={replay_intents}")
            if prod_keys != replay_keys:
                issues.append(f"KEYS DIFFER: prod={prod_keys} vs replay={replay_keys}")
            prod_cache_norm = ["CACHE-HIT" if s == "HIT" else "CACHE-MISS" for s in pt["prod_cache_status"]]
            replay_cache_norm = ["CACHE-HIT" if s == "CACHE-HIT" else "CACHE-MISS" for s in replay_cache]
            if prod_cache_norm != replay_cache_norm and prod_keys == replay_keys:
                issues.append(f"CACHE STATUS DIFFERS for same key(s): prod={prod_cache_norm} vs replay={replay_cache_norm}")

            if issues:
                discrepancies.append({
                    "call_uuid": uuid, "turn_idx": i,
                    "prod_state": pt["state"], "replay_starting_state": rt["starting_state"],
                    "transcript_prod_truncated": pt["transcript"], "transcript_replay_full": rt["transcript"],
                    "issues": issues,
                })

    print(f"Calls with a matching production log entry: {len(rows) - len(unmatched_calls)} / {len(rows)}")
    print(f"Calls with NO production log entry found (outside retention or never logged): {len(unmatched_calls)}")
    for u in unmatched_calls:
        print(f"    NO-PROD-LOG: {u}")
    print(f"\nTurns cross-checked against production log: {matched}")
    print(f"Discrepancies found: {len(discrepancies)}")
    for d in discrepancies:
        print(f"\n  --- DISCREPANCY: call_uuid={d['call_uuid']} turn={d['turn_idx']} ---")
        print(f"      prod_state={d['prod_state']!r}  replay_starting_state={d['replay_starting_state']!r}")
        print(f"      prod transcript (truncated, as logged): {d['transcript_prod_truncated']!r}")
        print(f"      replay transcript (full, from Supabase): {d['transcript_replay_full']!r}")
        for issue in d["issues"]:
            print(f"      {issue}")

    with open(f"{SCRATCH}/live_discrepancies.json", "w") as f:
        json.dump(discrepancies, f, ensure_ascii=False, indent=1)

    print("\n" + "=" * 100)
    print("STEP 4 — HONEST AGGREGATE REPORT")
    print("=" * 100)
    total = len(all_turns)
    no_error = sum(1 for t in all_turns if not t["exception"])
    print(f"Total turns tested: {total}")
    print(f"Completed with no error: {no_error} ({100*no_error/total:.1f}%)" if total else "no turns")

    all_plays = [p for t in all_turns for p in t["plays"]]
    cache_hits = [p for p in all_plays if p["status"] == "CACHE-HIT"]
    fallbacks = [p for p in all_plays if p["status"].startswith("LIVE-TTS-FALLBACK")]
    errors_plays = [p for p in all_plays if p["status"].startswith("ERROR")]
    print(f"\nTotal play_key() resolutions across all replayed turns: {len(all_plays)}")
    print(f"  CACHE-HIT: {len(cache_hits)} ({100*len(cache_hits)/len(all_plays):.1f}%)" if all_plays else "")
    print(f"  LIVE-TTS-FALLBACK: {len(fallbacks)} ({100*len(fallbacks)/len(all_plays):.1f}%)" if all_plays else "")
    print(f"  ERROR: {len(errors_plays)}")
    for p in fallbacks:
        print(f"    FALLBACK KEY: {p['key']}")
    for p in errors_plays:
        print(f"    ERROR KEY: {p}")

    # breakdown by flow/state
    print("\n--- cache-hit rate by (flow, state) ---")
    from collections import defaultdict
    by_flow_state = defaultdict(lambda: {"hit": 0, "fallback": 0, "error": 0})
    for t in all_turns:
        flow = f"{t['campaign']}#{t['call_cycle'] or '1'}"
        for p in t["plays"]:
            k = (flow, t["starting_state"])
            if p["status"] == "CACHE-HIT":
                by_flow_state[k]["hit"] += 1
            elif p["status"].startswith("LIVE-TTS-FALLBACK"):
                by_flow_state[k]["fallback"] += 1
            else:
                by_flow_state[k]["error"] += 1
    for (flow, state), counts in sorted(by_flow_state.items()):
        tot = sum(counts.values())
        fb_rate = 100 * counts["fallback"] / tot if tot else 0
        flag = "  <-- FALLBACK/ERROR PRESENT" if (counts["fallback"] or counts["error"]) else ""
        print(f"  {flow:<16} {str(state):<14} hit={counts['hit']:<4} fallback={counts['fallback']:<3} "
              f"error={counts['error']:<3} fallback_rate={fb_rate:.1f}%{flag}")

    # latency distribution
    def pctl(data, p):
        if not data:
            return None
        s = sorted(data)
        idx = min(len(s) - 1, int(len(s) * p))
        return s[idx]

    hit_lat = [p["elapsed_s"] for p in cache_hits]
    fb_lat = [p["elapsed_s"] for p in fallbacks]
    turn_wall = [t["turn_wall_s"] for t in all_turns]
    print("\n--- latency distribution ---")
    if hit_lat:
        print(f"  CACHE-HIT play_key() call: min={min(hit_lat)*1000:.2f}ms median={statistics.median(hit_lat)*1000:.2f}ms "
              f"p95={pctl(hit_lat,0.95)*1000:.2f}ms max={max(hit_lat)*1000:.2f}ms  (n={len(hit_lat)})")
    if fb_lat:
        print(f"  LIVE-TTS-FALLBACK path (up to the mocked TTS call, i.e. cost of discovering the miss): "
              f"min={min(fb_lat)*1000:.2f}ms median={statistics.median(fb_lat)*1000:.2f}ms max={max(fb_lat)*1000:.2f}ms "
              f"(n={len(fb_lat)}) -- NOTE: real TTS generation time NOT measured, mocked to avoid a real paid API call")
    else:
        print("  LIVE-TTS-FALLBACK: 0 occurrences in this replay -- no fallback latency to report")
    if turn_wall:
        print(f"  Full handler turn (detect_intents + routing + all play_key calls, network mocked): "
              f"min={min(turn_wall)*1000:.2f}ms median={statistics.median(turn_wall)*1000:.2f}ms "
              f"p95={pctl(turn_wall,0.95)*1000:.2f}ms max={max(turn_wall)*1000:.2f}ms")

    # intent-detection surprises: flag turns where replay intents are empty
    # despite a non-trivial transcript, or where prod vs replay disagree
    # (already in discrepancies) -- listed separately here for readability.
    print("\n--- turns where detect_intents() returned NOTHING despite real customer speech ---")
    zero_intent_turns = [t for t in all_turns if not t["replay_intents"] and len(t["transcript"].strip()) > 0]
    print(f"count: {len(zero_intent_turns)} / {total}")
    for t in zero_intent_turns:
        print(f"    call={t['call_uuid']} turn={t['turn_idx']} state={t['starting_state']} "
              f"transcript={t['transcript']!r} -> played={[p['key'] for p in t['plays']]}")


if __name__ == "__main__":
    asyncio.run(main())
