# -*- coding: utf-8 -*-
"""
Adversarial regression suite for the reactivation funnels' reply/state logic
(react_a/b/c, call2, call3, fresh_cta -- webhook_reactivation.py) plus the
LLM price-grounding check (knowledge.py, fresh_lead FAQ_MODE fallthrough).

Runs directly against the real matching/state functions -- no live telephony,
no network calls, no LLM calls. Cases live in
test_reply_state_regression_cases.json (mined from real call_summaries
transcripts + constructed adversarial variants); see that file for sourcing
notes.

Usage:
    python3 test_reply_state_regression.py            # full report
    python3 test_reply_state_regression.py --category dnc_optout
    python3 test_reply_state_regression.py --failures-only
"""
import argparse
import json
import sys
from collections import defaultdict

from webhook_reactivation import (
    detect_intents,
    _is_appointment_deferral,
    _has_standalone_day_suffix,
    _has_date_context_digit,
    _is_timing_question,
    _is_vague_time_without_commitment,
)
from knowledge import reply_has_ungrounded_price

CASES_PATH = "/home/voiceagent/voice-ai/test_reply_state_regression_cases.json"


def is_appointment_confirmed(t: str) -> bool:
    """Mirrors the compound confirm expression used verbatim at all 4 call
    sites in webhook_reactivation.py (handle_reactivation_turn's APPOINTMENT
    state, handle_call2_turn's DATE_ASK, handle_call3_turn's DECISION_DATE,
    handle_fresh_cta_turn) -- built from the same importable primitives those
    call sites use, not reimplemented independently."""
    intents = detect_intents(t)
    has_digit = _has_date_context_digit(t)
    has_day_suffix = _has_standalone_day_suffix(t)
    deferral = _is_appointment_deferral(t)
    timing_question = _is_timing_question(t)
    vague_no_commit = _is_vague_time_without_commitment(t)
    return (("appointment_confirm" in intents or has_digit or has_day_suffix)
            and not deferral and not timing_question and not vague_no_commit)


def is_dnc(t: str) -> bool:
    return "dnc" in detect_intents(t)


def evaluate(case: dict) -> dict:
    """Returns {check_name: (expected, actual, passed)} for every recognized
    check key present in case['expected']. Unrecognized keys (free-text notes
    accidentally left in an expected dict) are ignored."""
    text = case["input"]
    expected = case["expected"]
    results = {}

    if "contains_ungrounded_price" in expected:
        actual = reply_has_ungrounded_price(text)
        results["contains_ungrounded_price"] = (expected["contains_ungrounded_price"], actual,
                                                  actual == expected["contains_ungrounded_price"])
        # Price-fabrication-bait cases only check the grounding function --
        # skip the intent/appointment/dnc checks below, they're not applicable
        # to a candidate LLM reply string.
        return results

    actual_intents = detect_intents(text) if text else []

    if "intents_contains" in expected:
        missing = [i for i in expected["intents_contains"] if i not in actual_intents]
        results["intents_contains"] = (expected["intents_contains"], actual_intents, len(missing) == 0)

    if "intents_forbidden" in expected:
        present = [i for i in expected["intents_forbidden"] if i in actual_intents]
        results["intents_forbidden"] = (expected["intents_forbidden"], actual_intents, len(present) == 0)

    if "appointment_confirmed" in expected:
        actual = is_appointment_confirmed(text)
        results["appointment_confirmed"] = (expected["appointment_confirmed"], actual,
                                             actual == expected["appointment_confirmed"])

    if "dnc_triggered" in expected:
        actual = is_dnc(text)
        results["dnc_triggered"] = (expected["dnc_triggered"], actual, actual == expected["dnc_triggered"])

    return results


def run(cases, category_filter=None):
    if category_filter:
        cases = [c for c in cases if c["category"] == category_filter]

    per_case = []
    for case in cases:
        checks = evaluate(case)
        passed = all(v[2] for v in checks.values()) if checks else True
        per_case.append({"case": case, "checks": checks, "passed": passed})
    return per_case


def report(results, failures_only=False):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"\n{'='*78}\nOVERALL: {passed}/{total} passed ({passed/total*100:.1f}%)\n{'='*78}\n")

    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["case"]["category"]].append(r)

    print(f"{'CATEGORY':<32} {'PASS':>6} {'TOTAL':>6} {'RATE':>7}")
    print("-" * 55)
    for cat in sorted(by_cat):
        rs = by_cat[cat]
        p = sum(1 for r in rs if r["passed"])
        print(f"{cat:<32} {p:>6} {len(rs):>6} {p/len(rs)*100:>6.1f}%")

    print(f"\n{'='*78}\nFAILURE DETAIL\n{'='*78}")
    n_fail = 0
    for r in results:
        if r["passed"]:
            continue
        n_fail += 1
        case = r["case"]
        print(f"\n[{case['id']}] category={case['category']}  call_tag={case['call_tag']}  source={case['source']}")
        print(f"  input: {case['input']!r}")
        for check_name, (expected, actual, ok) in r["checks"].items():
            if not ok:
                print(f"  FAIL {check_name}: expected={expected!r} actual={actual!r}")
        if case.get("note"):
            print(f"  note: {case['note']}")
    if n_fail == 0:
        print("\n(no failures)")

    if not failures_only:
        pass  # failure detail already printed above; pass-only detail omitted by design

    print(f"\n{'='*78}\nTOTAL FAILURES: {n_fail}\n{'='*78}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default=None)
    ap.add_argument("--failures-only", action="store_true")
    ap.add_argument("--json-out", default=None, help="write machine-readable results to this path")
    args = ap.parse_args()

    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    results = run(cases, category_filter=args.category)
    report(results, failures_only=args.failures_only)

    if args.json_out:
        serializable = [
            {
                "id": r["case"]["id"],
                "category": r["case"]["category"],
                "call_tag": r["case"]["call_tag"],
                "source": r["case"]["source"],
                "input": r["case"]["input"],
                "passed": r["passed"],
                "checks": {k: {"expected": v[0], "actual": v[1], "ok": v[2]} for k, v in r["checks"].items()},
                "note": r["case"].get("note", ""),
            }
            for r in results
        ]
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=1)

    n_fail = sum(1 for r in results if not r["passed"])
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
