# -*- coding: utf-8 -*-
"""
Regression test for the two unbounded-loop guards added to
webhook.py::state_machine() after call aa747696-c47a-4b9c-b2d4-4cfbd588a60e
ran 51 turns of "समझ नहीं पाई" — a match_faq_detour hit was resetting
not_understood_streak to 0 on every other turn, so the existing streak>=3
close never re-accumulated.

No existing test file covers this path — test_reply_state_regression.py,
test_objection_routing.py, test_ivr_fragment_detection.py, and
test_cache_trigger_audit.py all drive webhook_reactivation.py's turn
handlers (fresh_cta/react_a/b/c/call2/call3), never webhook.py's own
state_machine()/QUALIFY_PRODUCT/QUALIFY_BUDGET flow, so this is new
coverage, not a duplicate.

Two things this file proves:
  1. not_understood_total (never reset by match_faq_detour, unlike the
     streak) forces the same DONE/not_understood_close path at >= 5, even
     while the streak itself never exceeds 1.
  2. session.turn_count >= 25 forces DONE/turn_cap_close unconditionally,
     even mid-faq_mode where the streak logic isn't reachable at all.

Usage:
    python3 test_not_understood_guards.py
"""
import sys

import webhook
from webhook import CallSession, state_machine

FAILURES = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def test_not_understood_total_forces_close_despite_streak_resets():
    """
    Reproduces the reference failure's shape: alternate a not-understood
    turn (streak+total both +1) with an FAQ-detour hit (streak reset to 0,
    total untouched) four times, then one more not-understood turn. The
    streak never gets past 1, but total reaches 5 on the 9th turn — this
    must trigger the same not_understood_close/DONE path.
    """
    session = CallSession("test-call-total-guard")
    session.state = "QUALIFY_PRODUCT"

    _orig_match_faq_detour = webhook.match_faq_detour

    def _fake_match_faq_detour(text, sess):
        if text == "FAQ_TRIGGER":
            return "यहाँ FAQ जवाब है", "fake_faq_id"
        return None, None

    webhook.match_faq_detour = _fake_match_faq_detour
    try:
        gibberish = "zzqzzq unintelligible mumble"
        last_reply, last_source = None, None
        for i in range(4):
            reply, source = state_machine(gibberish, gibberish, session, "test-call-total-guard")
            check(
                f"total-guard turn {2*i+1} (not-understood #{i+1}) stays open",
                session.state != "DONE",
                f"state={session.state} after not-understood turn {i+1}",
            )
            reply, source = state_machine("FAQ_TRIGGER", "FAQ_TRIGGER", session, "test-call-total-guard")
            check(
                f"total-guard turn {2*i+2} (faq hit) resets streak, stays open",
                session.not_understood_streak == 0 and session.state != "DONE",
                f"streak={session.not_understood_streak} state={session.state}",
            )
        # 9th turn: 5th not-understood turn. Streak is only 1 (just reset),
        # but total is now 5 -> must force close.
        last_reply, last_source = state_machine(gibberish, gibberish, session, "test-call-total-guard")
        check(
            "not_understood_total reaches 5",
            session.not_understood_total == 5,
            f"not_understood_total={getattr(session, 'not_understood_total', None)}",
        )
        check(
            "not_understood_streak is still low (proves total, not streak, drove the close)",
            session.not_understood_streak < 3,
            f"not_understood_streak={session.not_understood_streak}",
        )
        check(
            "state forced to DONE on total>=5",
            session.state == "DONE",
            f"state={session.state}",
        )
        check(
            "source is not_understood_close",
            last_source == "not_understood_close",
            f"source={last_source}",
        )
    finally:
        webhook.match_faq_detour = _orig_match_faq_detour


def test_turn_count_cap_forces_done_regardless_of_state():
    """
    session.turn_count >= 25 must force DONE/turn_cap_close unconditionally
    -- even mid faq_mode, where the streak/total logic below the faq_mode
    early-return is never reached at all.
    """
    session = CallSession("test-call-turn-cap")
    session.faq_mode = True
    session.state = "FAQ_MODE"
    session.turn_count = 24  # this call becomes turn 25

    reply, source = state_machine("koi bhi sawaal", "koi bhi sawaal", session, "test-call-turn-cap")

    check("turn_count reaches 25", session.turn_count == 25, f"turn_count={session.turn_count}")
    check("state forced to DONE at turn 25 even in faq_mode", session.state == "DONE", f"state={session.state}")
    check("source is turn_cap_close", source == "turn_cap_close", f"source={source}")
    check("reply is non-empty", bool(reply))


if __name__ == "__main__":
    test_not_understood_total_forces_close_despite_streak_resets()
    test_turn_count_cap_forces_done_regardless_of_state()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL PASS")
