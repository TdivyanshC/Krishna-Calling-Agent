# -*- coding: utf-8 -*-
"""
Regression test for DNC (do-not-call) detection across all three react-family
turn handlers -- handle_reactivation_turn (react_a/b/c Call1), handle_call2_turn,
handle_call3_turn.

Written alongside two fixes:
  1. supabase_calling.py's finalize_call() outbound_leads write (the
     "_not_interested" check) reads session.react_intents_seen, which
     handle_call2_turn/handle_call3_turn never populated before this change --
     an explicit "not_interested" (not the literal "dnc" phrase) on a call2/3
     turn was previously invisible to that check entirely.
  2. All three handlers already call check_hard_rejection() -> _fire_immediate_dnc()
     -> mark_dnc_immediate() the moment the "dnc" intent fires (this part
     pre-dates this change and is not new), which is a direct, immediate
     Supabase write independent of finalize_call(). That's the fast path;
     finalize_call()'s own check is the end-of-call fallback for a dropped
     connection between the opt-out turn and /hangup.

test_objection_routing.py already monkeypatches _fire_immediate_dnc (as
recorder.dnc_fired) but no existing case in that file drives an actual DNC
phrase through any handler and asserts on it -- this is new coverage, not a
duplicate.

Usage:
    python3 test_dnc_react_paths.py
"""
import asyncio
import sys
from types import SimpleNamespace

import webhook_reactivation as wr

DNC_TRANSCRIPT = "mujhe call mat karna"  # same phrase used in the live test call

FAILURES = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def make_session(**overrides):
    s = SimpleNamespace()
    s.customer_phone = "+919999900000"
    s.customer_name  = "Test"
    s.campaign       = "react_a"
    s.dnc            = False
    s.wa_sent        = False
    s.silence_count  = 0
    s.turn_count     = 0
    s.turn_idx       = 1
    s.conversation   = []
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


class Recorder:
    def __init__(self):
        self.played = []
        self.dnc_fired = False
        self.dnc_fired_phone = None


def patch_io(recorder: Recorder):
    async def fake_play_key(call_uuid, key, session=None, log_transcript=True):
        recorder.played.append(key)
        return True

    def fake_fire_immediate_dnc(session, call_uuid):
        recorder.dnc_fired = True
        recorder.dnc_fired_phone = getattr(session, "customer_phone", None)

    orig_play_key, orig_dnc = wr.play_key, wr._fire_immediate_dnc
    wr.play_key = fake_play_key
    wr._fire_immediate_dnc = fake_fire_immediate_dnc
    return orig_play_key, orig_dnc


def unpatch_io(orig_play_key, orig_dnc):
    wr.play_key = orig_play_key
    wr._fire_immediate_dnc = orig_dnc


def finalize_call_would_mark_dnc(session) -> bool:
    """
    Exact boolean this codebase's finalize_call() (supabase_calling.py) uses
    to decide outbound_leads.dnc=True -- reproduced here rather than importing
    finalize_call itself, since that function also makes real Supabase HTTP
    calls we don't want in a unit test.
    """
    react_intents_seen = getattr(session, "react_intents_seen", set())
    return (
        "not_interested" in react_intents_seen
        or "dnc" in react_intents_seen
        or getattr(session, "dnc", False)
    )


async def run_case(label, coro_fn, session):
    recorder = Recorder()
    orig_play_key, orig_dnc = patch_io(recorder)
    try:
        should_continue = await coro_fn(session, DNC_TRANSCRIPT, "test-call-uuid-dnc")
    finally:
        unpatch_io(orig_play_key, orig_dnc)

    print(f"\n-- {label} --")
    check(f"{label}: session.dnc set True", session.dnc is True, f"dnc={session.dnc}")
    check(f"{label}: _fire_immediate_dnc called (mark_dnc_immediate fast path)", recorder.dnc_fired)
    check(f"{label}: _fire_immediate_dnc called with correct phone", recorder.dnc_fired_phone == session.customer_phone,
          f"got {recorder.dnc_fired_phone!r}")
    check(f"{label}: handler ends the call (should_continue=False)", should_continue is False)
    check(f"{label}: 'dnc' recorded in react_intents_seen (finalize_call fallback path)",
          "dnc" in getattr(session, "react_intents_seen", set()),
          f"react_intents_seen={getattr(session, 'react_intents_seen', None)}")
    check(f"{label}: finalize_call() would mark outbound_leads.dnc=True",
          finalize_call_would_mark_dnc(session))


async def main():
    # react_a Call1 -- GREETING state, the entry point for every fresh react_a call.
    s1 = make_session(campaign="react_a", react_state="GREETING")
    await run_case("react_a Call1 (GREETING)", wr.handle_reactivation_turn, s1)

    # Call2 -- GREETING state (call_cycle="2" conversations always start here).
    s2 = make_session(campaign="react_a", call_cycle="2", c2_state="GREETING")
    await run_case("Call2 (GREETING)", wr.handle_call2_turn, s2)

    # Call3 -- GREETING state (call_cycle="3").
    s3 = make_session(campaign="react_a", call_cycle="3", c3_state="GREETING")
    await run_case("Call3 (GREETING)", wr.handle_call3_turn, s3)

    # Also check a mid-flow state isn't a blind spot -- Call2's DATE_ASK,
    # reached after WA_CHECK, since check_hard_rejection() is called before
    # any state dispatch in every handler and should catch it regardless.
    s4 = make_session(campaign="react_a", call_cycle="2", c2_state="DATE_ASK")
    await run_case("Call2 (DATE_ASK, mid-flow)", wr.handle_call2_turn, s4)


if __name__ == "__main__":
    asyncio.run(main())
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL PASS")
