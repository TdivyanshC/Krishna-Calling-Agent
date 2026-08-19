# no_match_report.py — periodic review tool for detect_intents() blind spots.
#
# Reads logs/audit.jsonl (already-live "route" events emitted by every turn
# handler in webhook_reactivation.py -- react_a/b/c, call2, call3, fresh_cta
# all write one per turn) and surfaces the two shapes of turn a human should
# spot-check: turns where NO keyword matched at all (transcript fell through
# to the generic "didn't catch that" reprompt or an LLM fallback), and turns
# where 2+ intents matched simultaneously (route_objection()'s priority chain
# picked a winner -- worth confirming it picked the right one).
#
# This is the "real customers keep inventing new phrasings" feedback loop
# flagged during the 2026-08-19 keyword-matching audit: every fix shipped
# this session (callback_later's polite question form, wa_ok's "sakte ho"
# variant, etc.) was found by manually reading one real call's transcript
# after a complaint. This script turns that into something reviewable in
# bulk, without waiting for the next complaint.
#
# Usage:
#   python3 no_match_report.py                       # last 7 days, both reports
#   python3 no_match_report.py --days 1
#   python3 no_match_report.py --only no_match
#   python3 no_match_report.py --only tied
#   python3 no_match_report.py --log-path /path/to/audit.jsonl
#
# KNOWN CAVEAT (found running this against production data 2026-08-19):
# audit_event() is not mocked out by test_objection_routing.py or manual
# testing sessions that call the real handle_*_turn() functions directly
# (only play_key/play_keys/fire_whatsapp/_fire_immediate_dnc are patched) --
# so logs/audit.jsonl mixes real customer turns with synthetic test-harness
# transcripts. Round, suspiciously-repeated counts (e.g. an exact test-file
# constant like "nahi chahiye kya bola" appearing dozens of times) are almost
# certainly test-suite runs, not real customer patterns -- treat those with
# suspicion rather than as organic recurring customer phrasing. Not fixed
# here (would need a dedicated test-mode flag threaded through audit_log.py,
# a separate decision); flagging so reports are read correctly in the
# meantime.

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

DEFAULT_LOG_PATH = "/home/voiceagent/voice-ai/logs/audit.jsonl"

# Turns shorter than this are near-always filler/acks ("haan", "hmm") already
# handled by _is_filler_continuer()/_is_bare_negative() upstream of
# detect_intents() being meaningful here -- excluded from the no-match report
# so it isn't dominated by noise that isn't a real keyword-coverage gap.
_MIN_TRANSCRIPT_CHARS = 4


def _load_route_events(log_path: str, since: datetime):
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") != "route":
                continue
            ts = rec.get("ts")
            if ts:
                try:
                    rec_dt = datetime.fromisoformat(ts)
                except ValueError:
                    rec_dt = None
                if rec_dt and rec_dt < since:
                    continue
            yield rec


def report_no_match(events):
    rows = [
        e for e in events
        if e.get("transcript") and len(e["transcript"].strip()) >= _MIN_TRANSCRIPT_CHARS
        and not e.get("intents")
    ]
    print(f"\n{'='*78}\nNO-MATCH TURNS ({len(rows)})\n{'='*78}")
    print("Transcript matched zero keywords -- these fell through to a generic")
    print("reprompt or LLM fallback. Recurring phrasings here are candidates for")
    print("new keyword coverage in knowledge_react_abc.py.\n")
    counts = Counter(e["transcript"].strip().lower() for e in rows)
    for text, n in counts.most_common(40):
        tag = f" (x{n})" if n > 1 else ""
        print(f"  {text}{tag}")
    if len(counts) > 40:
        print(f"  ... and {len(counts) - 40} more distinct transcripts")


def report_tied(events):
    rows = [e for e in events if e.get("intents") and len(e["intents"]) >= 2]
    print(f"\n{'='*78}\nMULTI-INTENT TURNS ({len(rows)})\n{'='*78}")
    print("2+ intents matched in one turn -- route_objection()'s priority chain")
    print("picked one. Spot-check that the winner was actually correct for the")
    print("transcript, especially for pairs you haven't seen before.\n")
    pair_counts = Counter()
    examples = {}
    for e in rows:
        key = tuple(sorted(e["intents"]))
        pair_counts[key] += 1
        examples.setdefault(key, e["transcript"])
    for pair, n in pair_counts.most_common(40):
        print(f"  {' + '.join(pair):55s} x{n:<4d} e.g. '{examples[pair][:70]}'")
    if len(pair_counts) > 40:
        print(f"  ... and {len(pair_counts) - 40} more distinct intent combinations")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=float, default=7, help="lookback window (default 7 days)")
    ap.add_argument("--only", choices=["no_match", "tied"], default=None)
    ap.add_argument("--log-path", default=DEFAULT_LOG_PATH)
    args = ap.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    events = list(_load_route_events(args.log_path, since))
    print(f"Loaded {len(events)} route events from the last {args.days} day(s).")

    if args.only in (None, "no_match"):
        report_no_match(events)
    if args.only in (None, "tied"):
        report_tied(events)


if __name__ == "__main__":
    main()
