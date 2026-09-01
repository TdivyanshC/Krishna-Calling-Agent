# -*- coding: utf-8 -*-
"""
Handler-level regression test for route_objection()'s repeat, price, and
trust wiring (Phase 1c/2a of the objection-handling redesign,
webhook_reactivation.py).

test_reply_state_regression.py deliberately does NOT cover this layer -- it
only exercises detect_intents() and the standalone predicate functions, never
the actual turn handlers (handle_fresh_cta_turn, handle_reactivation_turn,
handle_call2_turn, handle_call3_turn). This test drives those handlers
directly, with play_key()/fire_whatsapp()/_fire_immediate_dnc() monkeypatched
to no-op recorders (no real TTS/Vobiz/Supabase calls), and asserts which
cache key gets requested and what session state results, across every state
in every flow -- i.e. it verifies the actual routing behavior the JSON-case
suite is blind to.

Usage:
    python3 test_objection_routing.py
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import webhook_reactivation as wr


REPEAT_TRANSCRIPT = "kya bola"                       # exact "repeat" phrase
PRICE_TRANSCRIPT = "mahenga hai"                      # exact "expensive" phrase
TRUST_TRANSCRIPT = "fake hai"                         # exact "trust_issue" phrase
PRICE_AND_TRUST_TRANSCRIPT = "mahenga hai fake hai"   # both intents in one turn
NOT_INTERESTED_TRANSCRIPT = "nahi chahiye"            # exact "not_interested" phrase
BUSY_TRANSCRIPT = "busy hoon"                         # exact "busy" phrase
SOCHNA_HAI_TRANSCRIPT = "sochna hai"                  # exact "sochna_hai" phrase
NI_AND_REPEAT_TRANSCRIPT = "nahi chahiye kya bola"
NI_AND_PRICE_TRANSCRIPT = "nahi chahiye mahenga hai"
NI_AND_TRUST_TRANSCRIPT = "nahi chahiye fake hai"
NI_AND_BUSY_TRANSCRIPT = "nahi chahiye busy hoon"


class Recorder:
    def __init__(self):
        self.played = []       # list of key strings, in call order
        self.wa_fired = False
        self.dnc_fired = False


def make_session(**overrides):
    s = SimpleNamespace()
    s.customer_phone = "+919999900000"
    s.customer_name = "Test"
    s.dnc = False
    s.wa_sent = False
    s.silence_count = 0
    s.turn_count = 0
    s.conversation = []
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def patch_io(monkeypatch_target, recorder: Recorder):
    async def fake_play_key(call_uuid, key, session=None, log_transcript=True):
        recorder.played.append(key)
        return True

    async def fake_play_keys(call_uuid, keys, session=None, log_transcript=True):
        # play_keys() (2026-08-13) combines what used to be separate
        # play_key() calls into one native multi-URL Vobiz request -- record
        # each key in call order, same as if play_key() had been called for
        # each, so existing test expectations (a flat list of keys) still hold.
        recorder.played.extend(keys)
        return True

    async def fake_fire_whatsapp(session, call_uuid):
        recorder.wa_fired = True
        return True

    def fake_fire_immediate_dnc(session, call_uuid):
        recorder.dnc_fired = True

    monkeypatch_target.play_key = fake_play_key
    monkeypatch_target.play_keys = fake_play_keys
    monkeypatch_target.fire_whatsapp = fake_fire_whatsapp
    monkeypatch_target._fire_immediate_dnc = fake_fire_immediate_dnc


async def run_case(label, coro_fn, session, transcript, expected_key,
                    expect_continue=None, expect_no_generic=False,
                    expect_session_attrs=None):
    recorder = Recorder()
    orig_play_key, orig_fire_wa, orig_dnc = wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc
    patch_io(wr, recorder)
    try:
        should_continue = await coro_fn(session, transcript, "test-call-uuid")
    finally:
        wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc = orig_play_key, orig_fire_wa, orig_dnc

    ok = True
    detail = []

    if expected_key is not None:
        if expected_key not in recorder.played:
            ok = False
            detail.append(f"expected key {expected_key!r} to be played, got {recorder.played!r}")

    if expect_no_generic and any(k.startswith("obj_repeat_generic") for k in recorder.played):
        ok = False
        detail.append(f"expected no obj_repeat_generic_* key to be played, got {recorder.played!r}")

    if expect_continue is not None and should_continue != expect_continue:
        ok = False
        detail.append(f"expected should_continue={expect_continue}, got {should_continue}")

    for attr, expected_val in (expect_session_attrs or {}).items():
        actual_val = getattr(session, attr, "<unset>")
        if actual_val != expected_val:
            ok = False
            detail.append(f"expected session.{attr}={expected_val!r}, got {actual_val!r}")

    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label:<52} played={recorder.played!r} should_continue={should_continue}")
    if not ok:
        for d in detail:
            print(f"       {d}")
    return ok


async def main():
    results = []

    # ═══════════════════════════════════════════════════════════════════════
    # repeat/didn't-understand (Phase 1c) -- unchanged, re-verified alongside
    # the new price/trust wiring to confirm it still works after the change.
    # ═══════════════════════════════════════════════════════════════════════

    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / APPOINTMENT / repeat",
        wr.handle_fresh_cta_turn, s, REPEAT_TRANSCRIPT,
        expected_key="obj_repeat_generic_simran", expect_continue=True,
    ))

    s = make_session(campaign="react_a", call_cycle=None, react_state="GREETING")
    results.append(await run_case(
        "react_call1(a) / GREETING / repeat (owns its own line)",
        wr.handle_reactivation_turn, s, REPEAT_TRANSCRIPT,
        expected_key="ra_greet_repeat", expect_continue=True, expect_no_generic=True,
    ))

    for campaign, expected_voice in (("react_a", "ritu"), ("react_b", "shreya"), ("react_c", "simran")):
        for state in ("PRESENT_OFFER", "WHATSAPP_CTA", "APPOINTMENT"):
            s = make_session(campaign=campaign, call_cycle=None, react_state=state)
            results.append(await run_case(
                f"react_call1({campaign[-1]}) / {state} / repeat",
                wr.handle_reactivation_turn, s, REPEAT_TRANSCRIPT,
                expected_key=f"obj_repeat_generic_{expected_voice}", expect_continue=True,
            ))

    for state in ("CLOSE", "DONE"):
        s = make_session(campaign="react_a", call_cycle=None, react_state=state)
        results.append(await run_case(
            f"react_call1 / {state} / repeat (terminal — must still end call)",
            wr.handle_reactivation_turn, s, REPEAT_TRANSCRIPT,
            expected_key=None, expect_continue=False, expect_no_generic=True,
        ))

    for state in ("GREETING", "WA_CHECK", "DATE_ASK"):
        s = make_session(campaign="react_a", call_cycle="2", c2_state=state)
        results.append(await run_case(
            f"call2 / {state} / repeat",
            wr.handle_call2_turn, s, REPEAT_TRANSCRIPT,
            expected_key="obj_repeat_generic_ritu", expect_continue=True,
        ))

    for state in ("GREETING", "DECISION_DATE"):
        s = make_session(campaign="react_a", call_cycle="3", c3_state=state)
        results.append(await run_case(
            f"call3 / {state} / repeat",
            wr.handle_call3_turn, s, REPEAT_TRANSCRIPT,
            expected_key="obj_repeat_generic_simran", expect_continue=True,
        ))

    # ═══════════════════════════════════════════════════════════════════════
    # price / trust (Phase 2a) -- the 5 gap wirings.
    # ═══════════════════════════════════════════════════════════════════════

    # fresh_cta price + trust: single state, no state-advance concern.
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / APPOINTMENT / price (new)",
        wr.handle_fresh_cta_turn, s, PRICE_TRANSCRIPT,
        expected_key="fresh_price", expect_continue=True,
    ))
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / APPOINTMENT / trust (new)",
        wr.handle_fresh_cta_turn, s, TRUST_TRANSCRIPT,
        expected_key="fresh_trust", expect_continue=True,
    ))

    # call2 WA_CHECK trust reuse: must advance c2_state -> DATE_ASK so the
    # customer's next-turn date reply doesn't land back in WA_CHECK.
    s = make_session(campaign="react_a", call_cycle="2", c2_state="WA_CHECK")
    results.append(await run_case(
        "call2 / WA_CHECK / trust (reuse c2_obj_scam, must advance state)",
        wr.handle_call2_turn, s, TRUST_TRANSCRIPT,
        expected_key="c2_obj_scam", expect_continue=True,
        expect_session_attrs={"c2_state": "DATE_ASK"},
    ))

    # call3 GREETING price + trust reuse: must advance c3_state ->
    # DECISION_DATE, and (per the "continue, don't end" decision) must NOT
    # end the call the way DECISION_DATE's own c3_obj_price does.
    s = make_session(campaign="react_a", call_cycle="3", c3_state="GREETING")
    results.append(await run_case(
        "call3 / GREETING / price (reuse c3_obj_price, continue+advance, not end)",
        wr.handle_call3_turn, s, PRICE_TRANSCRIPT,
        expected_key="c3_obj_price", expect_continue=True,
        expect_session_attrs={"c3_state": "DECISION_DATE"},
    ))
    s = make_session(campaign="react_a", call_cycle="3", c3_state="GREETING")
    results.append(await run_case(
        "call3 / GREETING / trust (reuse c3_obj_scam, must advance state)",
        wr.handle_call3_turn, s, TRUST_TRANSCRIPT,
        expected_key="c3_obj_scam", expect_continue=True,
        expect_session_attrs={"c3_state": "DECISION_DATE"},
    ))

    # ── Non-gap states must be COMPLETELY unaffected -- price/trust there
    #    are still owned by the state's own chain, not route_objection() ────
    s = make_session(campaign="react_a", call_cycle=None, react_state="PRESENT_OFFER")
    results.append(await run_case(
        "react_call1(a) / PRESENT_OFFER / price (already state-owned, unaffected)",
        wr.handle_reactivation_turn, s, PRICE_TRANSCRIPT,
        expected_key="ra_obj_expensive", expect_continue=True,
    ))
    s = make_session(campaign="react_a", call_cycle=None, react_state="PRESENT_OFFER")
    results.append(await run_case(
        "react_call1(a) / PRESENT_OFFER / trust (already state-owned, unaffected)",
        wr.handle_reactivation_turn, s, TRUST_TRANSCRIPT,
        expected_key="ra_offer_trust", expect_continue=True,
    ))
    s = make_session(campaign="react_a", call_cycle="2", c2_state="DATE_ASK")
    results.append(await run_case(
        "call2 / DATE_ASK / trust (already state-owned, unaffected)",
        wr.handle_call2_turn, s, TRUST_TRANSCRIPT,
        expected_key="c2_obj_scam", expect_continue=True,
    ))

    # ── Regression guard for the fall-through bug caught during review: a
    #    turn with BOTH price and trust intents, at a state that's a GAP for
    #    trust but NOT a gap for price (call2/WA_CHECK), must still reach and
    #    fire the trust branch -- an earlier draft's price branch returned
    #    None unconditionally on a price non-match, which would have exited
    #    route_objection() before the trust check ever ran. ──────────────────
    s = make_session(campaign="react_a", call_cycle="2", c2_state="WA_CHECK")
    results.append(await run_case(
        "call2 / WA_CHECK / price+trust together (trust must still fire)",
        wr.handle_call2_turn, s, PRICE_AND_TRUST_TRANSCRIPT,
        expected_key="c2_obj_scam", expect_continue=True,
        expect_session_attrs={"c2_state": "DATE_ASK"},
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # not-interested (Phase 2b) -- the 1 gap wiring: call2/WA_CHECK.
    # ═══════════════════════════════════════════════════════════════════════

    s = make_session(campaign="react_a", call_cycle="2", c2_state="WA_CHECK")
    results.append(await run_case(
        "call2 / WA_CHECK / not_interested (reuse, terminal)",
        wr.handle_call2_turn, s, NOT_INTERESTED_TRANSCRIPT,
        expected_key="c2_close_declined", expect_continue=False,
    ))
    # Non-gap state unaffected -- DATE_ASK already owns not_interested.
    s = make_session(campaign="react_a", call_cycle="2", c2_state="DATE_ASK")
    results.append(await run_case(
        "call2 / DATE_ASK / not_interested (already state-owned, unaffected)",
        wr.handle_call2_turn, s, NOT_INTERESTED_TRANSCRIPT,
        expected_key="c2_close_declined", expect_continue=False,
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # timing/deferral -- busy + sochna_hai (Phase 2b).
    # ═══════════════════════════════════════════════════════════════════════

    # GREETING-stage gap, all 3 react plans + call2 + call3 -- two-play
    # (shared acknowledgment, then that flow's own next default line).
    # Tested with BOTH busy and sochna_hai at least once each to confirm the
    # single combined check routes both sub-intents identically for ra/rb/rc
    # (neither has pre-existing GREETING handling there, so both are genuine
    # gaps). c2/c3 are NOT tested with busy here -- busy has its own
    # pre-existing, correct, call-ending branch at c2/c3 GREETING
    # (c2_close_busy/c3_close_busy) that this dispatcher must not shadow; see
    # the dedicated "must NOT be shadowed" cases further below instead.
    s = make_session(campaign="react_a", call_cycle=None, react_state="GREETING")
    results.append(await run_case(
        "react_call1(a) / GREETING / busy (two-play, advance to PRESENT_OFFER)",
        wr.handle_reactivation_turn, s, BUSY_TRANSCRIPT,
        expected_key="ra_offer_main", expect_continue=True,
        expect_session_attrs={"react_state": "PRESENT_OFFER"},
    ))
    s = make_session(campaign="react_a", call_cycle=None, react_state="GREETING")
    results.append(await run_case(
        "react_call1(a) / GREETING / sochna_hai (same shared line+advance)",
        wr.handle_reactivation_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="ra_offer_main", expect_continue=True,
        expect_session_attrs={"react_state": "PRESENT_OFFER"},
    ))
    s = make_session(campaign="react_b", call_cycle=None, react_state="GREETING")
    results.append(await run_case(
        "react_call1(b) / GREETING / busy",
        wr.handle_reactivation_turn, s, BUSY_TRANSCRIPT,
        expected_key="rb_offer_main", expect_continue=True,
        expect_session_attrs={"react_state": "PRESENT_OFFER"},
    ))
    s = make_session(campaign="react_c", call_cycle=None, react_state="GREETING")
    results.append(await run_case(
        "react_call1(c) / GREETING / busy",
        wr.handle_reactivation_turn, s, BUSY_TRANSCRIPT,
        expected_key="rc_offer_main", expect_continue=True,
        expect_session_attrs={"react_state": "PRESENT_OFFER"},
    ))
    s = make_session(campaign="react_a", call_cycle="2", c2_state="GREETING")
    results.append(await run_case(
        "call2 / GREETING / sochna_hai (advance to WA_CHECK)",
        wr.handle_call2_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="c2_wa_check", expect_continue=True,
        expect_session_attrs={"c2_state": "WA_CHECK"},
    ))
    s = make_session(campaign="react_a", call_cycle="3", c3_state="GREETING")
    results.append(await run_case(
        "call3 / GREETING / sochna_hai (advance to DECISION_DATE)",
        wr.handle_call3_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="c3_decision_date", expect_continue=True,
        expect_session_attrs={"c3_state": "DECISION_DATE"},
    ))

    # Call2 WA_CHECK gap -- single-play, no second key.
    s = make_session(campaign="react_a", call_cycle="2", c2_state="WA_CHECK")
    results.append(await run_case(
        "call2 / WA_CHECK / busy (single-play, advance to DATE_ASK)",
        wr.handle_call2_turn, s, BUSY_TRANSCRIPT,
        expected_key="c2_obj_timing", expect_continue=True,
        expect_session_attrs={"c2_state": "DATE_ASK"},
    ))
    s = make_session(campaign="react_a", call_cycle="2", c2_state="WA_CHECK")
    results.append(await run_case(
        "call2 / WA_CHECK / sochna_hai (same single-play key)",
        wr.handle_call2_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="c2_obj_timing", expect_continue=True,
        expect_session_attrs={"c2_state": "DATE_ASK"},
    ))

    # react_a/b/c PRESENT_OFFER gap (sochna_hai only -- busy already handled
    # natively there) -- full sibling treatment: {p}_obj_think ->
    # WHATSAPP_CTA -> {p}_wa_cta -> fire_whatsapp.
    s = make_session(campaign="react_a", call_cycle=None, react_state="PRESENT_OFFER")
    results.append(await run_case(
        "react_call1(a) / PRESENT_OFFER / sochna_hai (full sibling treatment)",
        wr.handle_reactivation_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="ra_obj_think", expect_continue=True,
        expect_session_attrs={"react_state": "WHATSAPP_CTA"},
    ))
    s = make_session(campaign="react_a", call_cycle=None, react_state="PRESENT_OFFER")
    r = await run_case(
        "react_call1(a) / PRESENT_OFFER / sochna_hai also plays ra_wa_cta",
        wr.handle_reactivation_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="ra_wa_cta", expect_continue=True,
    )
    results.append(r)
    s = make_session(campaign="react_b", call_cycle=None, react_state="PRESENT_OFFER")
    results.append(await run_case(
        "react_call1(b) / PRESENT_OFFER / sochna_hai",
        wr.handle_reactivation_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="rb_obj_think", expect_continue=True,
        expect_session_attrs={"react_state": "WHATSAPP_CTA"},
    ))
    # busy at PRESENT_OFFER already state-owned, unaffected.
    s = make_session(campaign="react_a", call_cycle=None, react_state="PRESENT_OFFER")
    results.append(await run_case(
        "react_call1(a) / PRESENT_OFFER / busy (already state-owned, unaffected)",
        wr.handle_reactivation_turn, s, BUSY_TRANSCRIPT,
        expected_key="ra_obj_busy", expect_continue=True,
    ))

    # react_a/b/c APPOINTMENT gap (sochna_hai only) -- joins the existing
    # not_interested+busy -> {p}_close terminal group.
    s = make_session(campaign="react_a", call_cycle=None, react_state="APPOINTMENT")
    results.append(await run_case(
        "react_call1(a) / APPOINTMENT / sochna_hai (joins terminal close group)",
        wr.handle_reactivation_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="ra_close", expect_continue=False,
        expect_session_attrs={"react_state": "CLOSE"},
    ))
    # busy at APPOINTMENT already state-owned (grouped w/ not_interested),
    # unaffected -- same class of check as PRESENT_OFFER's busy test above,
    # confirming the narrowed "sochna_hai in intents" scoping actually holds
    # here too, not just at PRESENT_OFFER.
    s = make_session(campaign="react_a", call_cycle=None, react_state="APPOINTMENT")
    results.append(await run_case(
        "react_call1(a) / APPOINTMENT / busy (already state-owned, unaffected)",
        wr.handle_reactivation_turn, s, BUSY_TRANSCRIPT,
        expected_key="ra_close", expect_continue=False,
        expect_session_attrs={"react_state": "CLOSE"},
    ))

    # Call2 DATE_ASK and Call3 DECISION_DATE left as-is (deliberate,
    # documented) -- confirm they still hit their EXISTING fallthrough, not
    # any new key.
    s = make_session(campaign="react_a", call_cycle="2", c2_state="DATE_ASK")
    results.append(await run_case(
        "call2 / DATE_ASK / busy (left as-is, existing reask fallthrough)",
        wr.handle_call2_turn, s, BUSY_TRANSCRIPT,
        expected_key="c2_date_reask", expect_continue=True,
    ))
    s = make_session(campaign="react_a", call_cycle="3", c3_state="DECISION_DATE")
    results.append(await run_case(
        "call3 / DECISION_DATE / sochna_hai (left as-is, documented F*)",
        wr.handle_call3_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="c3_date_reask", expect_continue=True,
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # Ordering guard: not_interested must never be silently overridden by a
    # higher-priority-on-paper category when it has a pre-existing, correct
    # resolution -- retroactively verifies Phase 1c (repeat) and Phase 2a
    # (price/trust), not just the new Phase 2b (timing) wiring.
    # ═══════════════════════════════════════════════════════════════════════

    # repeat (Phase 1c) vs not_interested -- PRESENT_OFFER has no repeat
    # exception (only GREETING does), so this is the real regression case.
    s = make_session(campaign="react_a", call_cycle=None, react_state="PRESENT_OFFER")
    results.append(await run_case(
        "react_call1(a) / PRESENT_OFFER / not_interested+repeat (NI must win)",
        wr.handle_reactivation_turn, s, NI_AND_REPEAT_TRANSCRIPT,
        expected_key="ra_obj_not_interested", expect_continue=False,
    ))

    # price (Phase 2a) vs not_interested at c3/GREETING -- the exact
    # regression case found during design review.
    s = make_session(campaign="react_a", call_cycle="3", c3_state="GREETING")
    results.append(await run_case(
        "call3 / GREETING / not_interested+price (NI must win, not c3_obj_price)",
        wr.handle_call3_turn, s, NI_AND_PRICE_TRANSCRIPT,
        expected_key="c3_greet_hostile", expect_continue=False,
    ))

    # trust (Phase 2a) vs not_interested at c3/GREETING.
    s = make_session(campaign="react_a", call_cycle="3", c3_state="GREETING")
    results.append(await run_case(
        "call3 / GREETING / not_interested+trust (NI must win, not c3_obj_scam)",
        wr.handle_call3_turn, s, NI_AND_TRUST_TRANSCRIPT,
        expected_key="c3_greet_hostile", expect_continue=False,
    ))

    # timing (Phase 2b, new) vs not_interested at react_a GREETING.
    s = make_session(campaign="react_a", call_cycle=None, react_state="GREETING")
    results.append(await run_case(
        "react_call1(a) / GREETING / not_interested+busy (NI must win)",
        wr.handle_reactivation_turn, s, NI_AND_BUSY_TRANSCRIPT,
        expected_key="ra_greet_hostile", expect_continue=False,
    ))

    # The ONE confirmed exception: call2/WA_CHECK, where not_interested is
    # ITSELF a same-round gap (not pre-existing) -- original priority order
    # applies normally, both trust and repeat still outrank it there.
    s = make_session(campaign="react_a", call_cycle="2", c2_state="WA_CHECK")
    results.append(await run_case(
        "call2 / WA_CHECK / not_interested+trust (exception: trust still wins)",
        wr.handle_call2_turn, s, NI_AND_TRUST_TRANSCRIPT,
        expected_key="c2_obj_scam", expect_continue=True,
        expect_session_attrs={"c2_state": "DATE_ASK"},
    ))
    s = make_session(campaign="react_a", call_cycle="2", c2_state="WA_CHECK")
    results.append(await run_case(
        "call2 / WA_CHECK / not_interested+repeat (exception: repeat still wins)",
        wr.handle_call2_turn, s, NI_AND_REPEAT_TRANSCRIPT,
        expected_key="obj_repeat_generic_ritu", expect_continue=True,
    ))
    # But not_interested still correctly outranks timing there (timing is
    # BELOW not-interested in the priority order even at the exception
    # state -- this falls out of simple code ordering, not the guard).
    s = make_session(campaign="react_a", call_cycle="2", c2_state="WA_CHECK")
    results.append(await run_case(
        "call2 / WA_CHECK / not_interested+busy (NI still outranks timing)",
        wr.handle_call2_turn, s, NI_AND_BUSY_TRANSCRIPT,
        expected_key="c2_close_declined", expect_continue=False,
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # call2/call3 GREETING "busy" shadowing regression guard. Found via
    # production-replay audit (2026-07-19): route_objection()'s GREETING
    # timing gap-fill used to fire for busy OR sochna_hai at c2/c3 GREETING,
    # unconditionally shadowing each state's own pre-existing, correct,
    # call-ending busy branch (c2_close_busy/c3_close_busy) -- a real
    # customer saying "busy hoon" got pushed into a date-ask instead. Fixed
    # by scoping the c2/c3 GREETING branch to sochna_hai only, same as the
    # PRESENT_OFFER/APPOINTMENT sochna_hai-only checks already covered above.
    # ═══════════════════════════════════════════════════════════════════════

    s = make_session(campaign="react_a", call_cycle="2", c2_state="GREETING")
    results.append(await run_case(
        "call2 / GREETING / busy -> own c2_close_busy (must NOT be shadowed)",
        wr.handle_call2_turn, s, BUSY_TRANSCRIPT,
        expected_key="c2_close_busy", expect_continue=False,
    ))
    s = make_session(campaign="react_a", call_cycle="3", c3_state="GREETING")
    results.append(await run_case(
        "call3 / GREETING / busy -> own c3_close_busy (must NOT be shadowed)",
        wr.handle_call3_turn, s, BUSY_TRANSCRIPT,
        expected_key="c3_close_busy", expect_continue=False,
    ))
    # sochna_hai is a genuine gap at these states (no pre-existing handling)
    # and must still get the two-play gap-fill -- confirms the fix didn't
    # overcorrect and kill the case it was never meant to change.
    s = make_session(campaign="react_a", call_cycle="2", c2_state="GREETING")
    results.append(await run_case(
        "call2 / GREETING / sochna_hai -> still gets timing gap-fill (unchanged)",
        wr.handle_call2_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="c2_wa_check", expect_continue=True,
        expect_session_attrs={"c2_state": "WA_CHECK"},
    ))
    s = make_session(campaign="react_a", call_cycle="3", c3_state="GREETING")
    results.append(await run_case(
        "call3 / GREETING / sochna_hai -> still gets timing gap-fill (unchanged)",
        wr.handle_call3_turn, s, SOCHNA_HAI_TRANSCRIPT,
        expected_key="c3_decision_date", expect_continue=True,
        expect_session_attrs={"c3_state": "DECISION_DATE"},
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # call2 DATE_ASK price-pending -- date-in-same-reply regression guard.
    # Found via production-replay audit (call 8d46a889): once the price
    # objection sets c2_price_asked=True, the next turn used to unconditionally
    # re-ask for a date via c2_date_direct even when the reply already
    # contained one ("सैटरडे को फ्री रहेंगे" / "saturday ko free rahenge").
    # ═══════════════════════════════════════════════════════════════════════

    s = make_session(campaign="react_a", call_cycle="2", c2_state="DATE_ASK", c2_price_asked=True)
    results.append(await run_case(
        "call2 / DATE_ASK(price_asked=True) / date in same reply -> books, no redundant reask",
        wr.handle_call2_turn, s, "saturday ko free rahenge",
        expected_key="c2_booked", expect_continue=False,
        expect_session_attrs={"appointment_confirmed": True, "c2_price_asked": False},
    ))
    # Vague reply (no date) must still fall back to the original re-ask --
    # confirms the fix didn't regress the case it was never meant to change.
    s = make_session(campaign="react_a", call_cycle="2", c2_state="DATE_ASK", c2_price_asked=True)
    results.append(await run_case(
        "call2 / DATE_ASK(price_asked=True) / vague reply -> still c2_date_direct (unchanged)",
        wr.handle_call2_turn, s, "haan theek hai",
        expected_key="c2_date_direct", expect_continue=True,
        expect_session_attrs={"c2_price_asked": False},
    ))
    # not_interested must still win even if a date-like word is also present.
    s = make_session(campaign="react_a", call_cycle="2", c2_state="DATE_ASK", c2_price_asked=True)
    results.append(await run_case(
        "call2 / DATE_ASK(price_asked=True) / not_interested still wins over a date mention",
        wr.handle_call2_turn, s, "nahi chahiye, saturday ko bhi nahi",
        expected_key="c2_close_price", expect_continue=False,
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # 2026-08-20 — fresh_cta sequential budget/urgency/visit-date flow,
    # chair/office-chair product handling, and the interior-design branch.
    # Multi-turn: each block reuses the SAME session object across several
    # run_case() calls, since fresh_step now needs to persist turn-over-turn
    # (run_case doesn't reset session state between calls — confirmed by
    # its signature, it just invokes coro_fn directly on whatever session
    # object is passed in).
    # ═══════════════════════════════════════════════════════════════════════

    def check(label, condition, detail=""):
        status = "PASS" if condition else "FAIL"
        print(f"[{status}] {label:<52} {detail}")
        return condition

    # -- Product pre-known (fresh_product="sofa") -> straight to budget,
    #    skipping any product question, full sequence through to booking.
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="sofa")
    results.append(await run_case(
        "fresh_cta / sequence / product known -> turn1 asks budget (skips product ask)",
        wr.handle_fresh_cta_turn, s, "haan bataiye",
        expected_key="fresh_ask_budget", expect_continue=True,
        expect_session_attrs={"fresh_step": "BUDGET"},
    ))
    results.append(check("fresh_cta / sequence / product pre-captured into session.lead",
                          s.lead.get("product") == "sofa", detail=f"lead={s.lead!r}"))

    results.append(await run_case(
        "fresh_cta / sequence / turn2 budget answer -> asks urgency",
        wr.handle_fresh_cta_turn, s, "50 hazar tak",
        expected_key="fresh_ask_urgency", expect_continue=True,
        expect_session_attrs={"fresh_step": "URGENCY"},
    ))
    results.append(check("fresh_cta / sequence / budget extracted (extract_budget reused)",
                          s.lead.get("budget") == "₹50,000", detail=f"lead={s.lead!r}"))

    results.append(await run_case(
        "fresh_cta / sequence / turn3 urgency answer -> asks visit date",
        wr.handle_fresh_cta_turn, s, "jaldi chahiye",
        expected_key="fresh_ask_visit_date", expect_continue=True,
        expect_session_attrs={"fresh_step": "VISIT_DATE"},
    ))
    results.append(check("fresh_cta / sequence / urgency captured",
                          bool(s.lead.get("urgency")), detail=f"lead={s.lead!r}"))

    results.append(await run_case(
        "fresh_cta / sequence / turn4 gives a date -> appointment confirmed (existing behavior, unchanged)",
        wr.handle_fresh_cta_turn, s, "kal aa jaungi",
        expected_key="fresh_appointment_confirmed", expect_continue=False,
        expect_session_attrs={"appointment_confirmed": True},
    ))

    # -- Product NOT known upfront -> customer states it in their reply to
    #    the greeting -> extracted opportunistically, still reaches budget
    #    the same turn (no wasted turn on a separate product question).
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / sequence / product unknown, stated in reply -> still asks budget same turn",
        wr.handle_fresh_cta_turn, s, "mujhe bed chahiye tha",
        expected_key="fresh_ask_budget", expect_continue=True,
        expect_session_attrs={"fresh_step": "BUDGET"},
    ))
    results.append(check("fresh_cta / sequence / product extracted from reply into session.lead",
                          s.lead.get("product") == "bed", detail=f"lead={s.lead!r}"))

    # -- chair / office chair: product-key normalization (bed/sofa/wardrobe/
    #    dining previously had dedicated audio; chair did not, until today).
    results.append(check("normalize_fresh_product_key('chair') == 'chair'",
                          wr.normalize_fresh_product_key("chair") == "chair"))
    results.append(check("normalize_fresh_product_key('office chair') == 'chair'",
                          wr.normalize_fresh_product_key("office chair") == "chair"))
    results.append(check("normalize_fresh_product_key('gaming chair') == 'chair'",
                          wr.normalize_fresh_product_key("gaming chair") == "chair"))

    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="office chair")
    results.append(await run_case(
        "fresh_cta / sequence / office chair pre-known -> greeting-key product resolves + asks budget",
        wr.handle_fresh_cta_turn, s, "haan bataiye",
        expected_key="fresh_ask_budget", expect_continue=True,
    ))
    results.append(check("fresh_cta / sequence / office chair normalized to 'chair' in session.lead",
                          s.lead.get("product") == "chair", detail=f"lead={s.lead!r}"))

    # -- Interior design branch: distinct exit, one budget question then a
    #    manager handoff -- no urgency/visit-date asks for this path.
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / interior_design / turn1 mentions interior design -> asks budget",
        wr.handle_fresh_cta_turn, s, "kya aap interior design karte ho",
        expected_key="fresh_interior_budget_ask", expect_continue=True,
        expect_session_attrs={"fresh_step": "INTERIOR_BUDGET"},
    ))
    results.append(await run_case(
        "fresh_cta / interior_design / turn2 gives budget -> manager handoff, call ends",
        wr.handle_fresh_cta_turn, s, "1 lakh tak",
        expected_key="fresh_interior_handoff", expect_continue=False,
        expect_session_attrs={"fresh_step": "INTERIOR_HANDOFF_DONE", "lead_tier_override": "hot"},
    ))
    results.append(check("fresh_cta / interior_design / budget + interest_type captured",
                          s.lead.get("interest_type") == "interior_design" and bool(s.lead.get("budget")),
                          detail=f"lead={s.lead!r}"))
    # Never advances into the normal furniture budget/urgency/visit-date
    # sequence -- confirms the two paths stay mutually exclusive.
    results.append(check("fresh_cta / interior_design / never touched normal sequence's 'budget' framing",
                          "urgency" not in s.lead, detail=f"lead={s.lead!r}"))

    # -- Regression guard: a bare free-form answer that matches no
    #    detect_intents() keyword (very common for budget/urgency replies)
    #    must NOT trip the not_understood streak/LLM-refusal path while
    #    fresh_step is awaiting one of these answers. If _expects_freeform_
    #    answer's guard (webhook_reactivation.py) were missing, this would
    #    either hang on a real LLM call or wrongly close the call.
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="sofa")
    await run_case("fresh_cta / freeform-answer-guard / turn1 (setup)",
                    wr.handle_fresh_cta_turn, s, "ok", expected_key="fresh_ask_budget", expect_continue=True)
    results.append(await run_case(
        "fresh_cta / freeform-answer-guard / bare unrecognized budget reply doesn't trip not_understood",
        wr.handle_fresh_cta_turn, s, "40 hazar ke aas paas",
        expected_key="fresh_ask_urgency", expect_continue=True,
        expect_session_attrs={"not_understood_streak": 0},
    ))

    # -- Regression guard, 2026-08-20 same-day fix: a genuine question asked
    #    mid-sequence ("king size bed hai kya") must be answered via the LLM
    #    Q&A fallback, not silently swallowed as the answer to whatever
    #    question was pending (confirmed live before this fix: the question
    #    text itself got stored as session.lead["budget"] and the call moved
    #    straight to asking urgency without ever answering). Mocks
    #    _llm_fallback_with_filler/play_dynamic_text (patch_io doesn't cover
    #    these -- they're the dynamic-TTS LLM path, not the cached-key path)
    #    to simulate a successful LLM answer without a real network call.
    # 2026-08-23: mocks moved to _resolve_dynamic_url/_vobiz_play, same
    # reason as the other two Q&A blocks below -- _play_dynamic_then_key()
    # combines the answer + reprompt into one _vobiz_play() call now, not
    # separate play_key()/play_keys() calls, so recorder.played can't see
    # the reprompt half anymore. Directly asserts _vobiz_play got ONE call
    # with both urls, which is the actual fix under test.
    orig_llm_fallback = wr._llm_fallback_with_filler
    orig_resolve_dynamic = wr._resolve_dynamic_url
    orig_vobiz_play = wr._vobiz_play
    _vobiz_calls = []

    async def fake_llm_fallback(call_uuid, t, session, voice, facts=None, lang="hi"):
        return "Hume king size bed available hai, store mein dekh sakte hain."

    async def fake_resolve_dynamic(call_uuid, text, voice="shreya", lang="hi"):
        return "https://voice.thesocialhood.in/audio/dynamic/fake.wav", b"fake-wav-bytes"

    async def fake_vobiz_play(call_uuid, audio_url, turn=0, kind="reply"):
        _vobiz_calls.append(audio_url)
        return True

    wr._llm_fallback_with_filler = fake_llm_fallback
    wr._resolve_dynamic_url = fake_resolve_dynamic
    wr._vobiz_play = fake_vobiz_play
    try:
        s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="bed")
        await run_case("fresh_cta / question-mid-sequence / turn1 (setup)",
                        wr.handle_fresh_cta_turn, s, "haan bataiye", expected_key="fresh_ask_budget", expect_continue=True)

        _recorder1 = Recorder()
        orig_play_key1, orig_fire_wa1, orig_dnc1 = wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc
        patch_io(wr, _recorder1)  # safety net -- guards any unrelated play_key/fire_whatsapp call
        try:
            should_continue = await wr.handle_fresh_cta_turn(s, "aapke paas king size bed hai kya", "test-call-uuid")
        finally:
            wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc = orig_play_key1, orig_fire_wa1, orig_dnc1
        # 2026-09-01: "aapke paas king size bed hai kya" now matches the
        # specific-product recogniser (match_fresh_product -> "king_bed")
        # BEFORE the LLM Q&A path, so it's answered instantly from the
        # pre-cached fresh_have_king_bed key instead of a dynamic 2-URL Play.
        results.append(check(
            "fresh_cta / question-mid-sequence / real question gets answered, not swallowed as budget",
            should_continue is True and "fresh_have_king_bed" in _recorder1.played,
            detail=f"should_continue={should_continue} played={_recorder1.played!r}",
        ))
        results.append(check("fresh_cta / question-mid-sequence / fresh_step unchanged, budget still pending",
                              s.fresh_step == "BUDGET", detail=f"fresh_step={s.fresh_step!r}"))
        results.append(check("fresh_cta / question-mid-sequence / question text NOT stored as budget",
                              "budget" not in s.lead, detail=f"lead={s.lead!r}"))
        # Next turn: the real budget answer is still captured correctly.
        results.append(await run_case(
            "fresh_cta / question-mid-sequence / follow-up turn still captures the real budget answer",
            wr.handle_fresh_cta_turn, s, "60 hazar tak",
            expected_key="fresh_ask_urgency", expect_continue=True,
            expect_session_attrs={"fresh_step": "URGENCY"},
        ))
        results.append(check("fresh_cta / question-mid-sequence / budget correctly captured on the real answer",
                              s.lead.get("budget") == "₹60,000", detail=f"lead={s.lead!r}"))
    finally:
        wr._llm_fallback_with_filler = orig_llm_fallback
        wr._resolve_dynamic_url = orig_resolve_dynamic
        wr._vobiz_play = orig_vobiz_play

    # -- Regression guard, 2026-08-22: CONFIRMED LIVE on a real test call --
    #    a genuine call-1 session has session.call_cycle == "" (empty
    #    string, set at webhook.py:1839), never Python None. The step
    #    machine's init used to check `is None`, which is False for "" --
    #    every real call-1 silently got fresh_step=None (step machine fully
    #    disabled) despite call_cycle=None working correctly in every test
    #    above. This is deliberately call_cycle="" (not None) to catch
    #    exactly the gap that let the bug ship undetected the first time.
    s = make_session(campaign="fresh_cta", call_cycle="", react_state="APPOINTMENT", fresh_product="sofa")
    results.append(await run_case(
        "fresh_cta / call_cycle='' (real call-1 shape) / step machine IS active, asks budget",
        wr.handle_fresh_cta_turn, s, "haan bataiye",
        expected_key="fresh_ask_budget", expect_continue=True,
        expect_session_attrs={"fresh_step": "BUDGET"},
    ))

    # -- Regression guard, 2026-08-22: CONFIRMED LIVE on the first real test
    #    call after the call_cycle fix -- a question that ALSO names a
    #    product ("बेड में क्या-क्या ऑप्शंस हैं आपके पास?", "what bed options
    #    do you have?") matched extract_product() -> "bed" successfully, so
    #    the old code treated it purely as "customer wants a bed" and never
    #    answered the actual question. Fixed by OR-ing _looks_like_question
    #    into the detour check regardless of extraction success. Also
    #    confirms fresh_step correctly advances to BUDGET on the detour
    #    (not stuck re-running AWAIT_FIRST_REPLY next turn).
    # -- Bilingual Q&A regression, 2026-08-22: CONFIRMED LIVE -- an English
    #    caller's real question got a Hindi-generated answer (or none at
    #    all, on timeout) because lang was hardcoded to "hi" throughout the
    #    fallback pipeline regardless of session.lang. Asserts the lang
    #    actually threaded through to both _llm_fallback_with_filler
    #    (drives the generation prompt's output language) and
    #    _resolve_dynamic_url (drives the TTS render language) when
    #    session.lang == "en".
    #
    #    2026-08-23: mocks moved one level deeper (_resolve_dynamic_url +
    #    _vobiz_play, not play_dynamic_text) -- the answer+reprompt path now
    #    goes through _play_dynamic_then_key(), which calls those directly
    #    to combine both into one Play request (see that helper's docstring:
    #    two separate Play requests let the second cut off the first,
    #    confirmed live on the Pratham call).
    _seen_langs = {}
    orig_llm_fallback3 = wr._llm_fallback_with_filler
    orig_resolve_dynamic3 = wr._resolve_dynamic_url
    orig_vobiz_play3 = wr._vobiz_play

    async def fake_llm_fallback3(call_uuid, t, session, voice, facts=None, lang="hi"):
        _seen_langs["llm_fallback"] = lang
        return "We have several bed options, you can check them at the store."

    async def fake_resolve_dynamic3(call_uuid, text, voice="shreya", lang="hi"):
        _seen_langs["resolve_dynamic"] = lang
        return "https://voice.thesocialhood.in/audio/dynamic/fake.wav", b"fake-wav-bytes"

    async def fake_vobiz_play3(call_uuid, audio_url, turn=0, kind="reply"):
        return True

    wr._llm_fallback_with_filler = fake_llm_fallback3
    wr._resolve_dynamic_url = fake_resolve_dynamic3
    wr._vobiz_play = fake_vobiz_play3
    try:
        s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="bed", lang="en")
        # expected_key=None: this reprompt now goes through _play_dynamic_then_key's
        # combined _vobiz_play() call, not play_key()/play_keys() -- recorder.played
        # can't see it. The two _seen_langs checks below are the real assertions.
        # 2026-09-01: transcript changed from "what kind of beds do you have"
        # (now intercepted by match_fresh_broad_category -> fresh_range_bed,
        # a static key, before the LLM path) to a genuine free-form question
        # with no product/category-listing shape, so it still exercises the
        # bilingual LLM-fallback path this test is actually about.
        await run_case(
            "fresh_cta / bilingual Q&A / English caller's question",
            wr.handle_fresh_cta_turn, s, "which materials do you use",
            expected_key=None, expect_continue=True,
        )
        results.append(check("fresh_cta / bilingual Q&A / lang='en' reached _llm_fallback_with_filler",
                              _seen_langs.get("llm_fallback") == "en", detail=f"{_seen_langs!r}"))
        results.append(check("fresh_cta / bilingual Q&A / lang='en' reached _resolve_dynamic_url",
                              _seen_langs.get("resolve_dynamic") == "en", detail=f"{_seen_langs!r}"))
    finally:
        wr._llm_fallback_with_filler = orig_llm_fallback3
        wr._resolve_dynamic_url = orig_resolve_dynamic3
        wr._vobiz_play = orig_vobiz_play3

    # 2026-08-23: mocks moved to _resolve_dynamic_url/_vobiz_play (see the
    # bilingual Q&A block above for why) -- _play_dynamic_then_key() no
    # longer calls play_key()/play_keys() for the reprompt half, so
    # recorder.played (populated only by those two) can't see it anymore.
    # Asserts directly on what _vobiz_play was actually called with instead
    # -- specifically that it's ONE call with BOTH urls combined, which is
    # the actual bug this whole refactor exists to fix (two separate Play
    # requests let the second cut off the first, confirmed live).
    orig_llm_fallback2 = wr._llm_fallback_with_filler
    orig_resolve_dynamic2 = wr._resolve_dynamic_url
    orig_vobiz_play2 = wr._vobiz_play
    _vobiz_calls2 = []

    async def fake_llm_fallback2(call_uuid, t, session, voice, facts=None, lang="hi"):
        return "Hume bed ke kai options milte hain, store mein dekh sakte hain."

    async def fake_resolve_dynamic2(call_uuid, text, voice="shreya", lang="hi"):
        return "https://voice.thesocialhood.in/audio/dynamic/fake.wav", b"fake-wav-bytes"

    async def fake_vobiz_play2(call_uuid, audio_url, turn=0, kind="reply"):
        _vobiz_calls2.append(audio_url)
        return True

    wr._llm_fallback_with_filler = fake_llm_fallback2
    wr._resolve_dynamic_url = fake_resolve_dynamic2
    wr._vobiz_play = fake_vobiz_play2
    _recorder2 = Recorder()
    orig_play_key2, orig_fire_wa2, orig_dnc2 = wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc
    patch_io(wr, _recorder2)  # safety net only -- guards any unrelated play_key/fire_whatsapp call from hitting real network
    try:
        s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
        should_continue = await wr.handle_fresh_cta_turn(s, "बेड में क्या-क्या ऑप्शंस हैं आपके पास?", "test-call-uuid")
        results.append(check("fresh_cta / question-names-a-product / answered, not swallowed as a product statement",
                              should_continue is True and len(_vobiz_calls2) == 1 and isinstance(_vobiz_calls2[0], list) and len(_vobiz_calls2[0]) == 2,
                              detail=f"should_continue={should_continue} vobiz_calls={_vobiz_calls2!r}"))
        results.append(check("fresh_cta / question-names-a-product / fresh_step advanced to BUDGET, not stuck re-asking",
                              s.fresh_step == "BUDGET", detail=f"fresh_step={s.fresh_step!r}"))
        results.append(check("fresh_cta / question-names-a-product / product still opportunistically captured",
                              s.lead.get("product") == "bed", detail=f"lead={s.lead!r}"))
        # Next turn: a real budget answer is captured correctly, not re-treated as AWAIT_FIRST_REPLY.
        results.append(await run_case(
            "fresh_cta / question-names-a-product / follow-up turn captures the real budget, doesn't repeat itself",
            wr.handle_fresh_cta_turn, s, "40 hazar tak",
            expected_key="fresh_ask_urgency", expect_continue=True,
            expect_session_attrs={"fresh_step": "URGENCY"},
        ))
        results.append(check("fresh_cta / question-names-a-product / budget correctly captured",
                              s.lead.get("budget") == "₹40,000", detail=f"lead={s.lead!r}"))
    finally:
        wr._llm_fallback_with_filler = orig_llm_fallback2
        wr._resolve_dynamic_url = orig_resolve_dynamic2
        wr._vobiz_play = orig_vobiz_play2
        wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc = orig_play_key2, orig_fire_wa2, orig_dnc2

    # -- _looks_like_question() marker gaps, 2026-08-22: CONFIRMED LIVE --
    #    STT rendered reduplicated question words with a hyphen instead of
    #    a space ("क्या-क्या", "कौन-कौन"), which the marker list (space-only
    #    at the time) missed entirely -- a real question slipped through
    #    undetected and got stored as raw urgency text.
    results.append(check("_looks_like_question / hyphenated 'kya-kya' now detected",
                          wr._looks_like_question("बेड में क्या-क्या ऑप्शंस हैं आपके पास?")))
    results.append(check("_looks_like_question / hyphenated 'kaun-kaun' now detected",
                          wr._looks_like_question("आपके पास बेड कौन-कौन से हैं, ये तो बताओ।")))

    # -- Regression guard, 2026-08-22: CONFIRMED LIVE on a real test call --
    #    "what will be the options..." and "what are the options..." (words
    #    inserted between "what" and "options") both slipped past the
    #    exact-phrase marker list. Token-based co-occurrence check added.
    results.append(check("_looks_like_question / 'what will be the options...' now detected",
                          wr._looks_like_question("I said, around 60 to 70,000, what will be the options in the bed I will be getting?")))
    results.append(check("_looks_like_question / 'what are the options' now detected",
                          wr._looks_like_question("First please tell me what are the options then I will tell you.")))

    # -- Regression guard, 2026-08-22: CONFIRMED LIVE -- a Groq classify
    #    failure (rate-limit, in the real case) makes llm_fallback_reply()
    #    return the generic "didn't catch that" text, same as a genuinely
    #    unclear utterance. _try_fresh_llm_qa used to treat that string as a
    #    real answer -- played a FALSE "I didn't catch that" claim (STT had
    #    transcribed it fine) AND skipped the caller's own budget/urgency
    #    extraction for that turn, silently discarding a real stated budget
    #    range. Fixed: treat the REPROMPT_TEXT fallback as "no real answer",
    #    same as any other failure -- the caller's own extraction still runs.
    orig_llm_fallback4 = wr._llm_fallback_with_filler
    orig_play_dynamic4 = wr.play_dynamic_text

    async def fake_llm_fallback_reprompt(call_uuid, t, session, voice, facts=None, lang="hi"):
        return wr._REACT_LLM_REPROMPT_TEXT  # simulates a classify-step exception/rate-limit

    async def fake_play_dynamic4(call_uuid, text, session=None, voice="shreya", lang="hi"):
        return True

    wr._llm_fallback_with_filler = fake_llm_fallback_reprompt
    wr.play_dynamic_text = fake_play_dynamic4
    try:
        s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="bed")
        await run_case("fresh_cta / classify-failure-guard / turn1 (setup)",
                        wr.handle_fresh_cta_turn, s, "haan bataiye", expected_key="fresh_ask_budget", expect_continue=True)
        results.append(await run_case(
            "fresh_cta / classify-failure-guard / budget question + real number still gets captured, not a false 'didn't catch that'",
            wr.handle_fresh_cta_turn, s, "लगभग 60,000 के 80,000 के बीच में कौन कौन से बेड होंगे?",
            expected_key="fresh_ask_urgency", expect_continue=True,
            expect_session_attrs={"fresh_step": "URGENCY"},
        ))
        results.append(check("fresh_cta / classify-failure-guard / budget was NOT discarded",
                              s.lead.get("budget") not in (None, ""), detail=f"lead={s.lead!r}"))
    finally:
        wr._llm_fallback_with_filler = orig_llm_fallback4
        wr.play_dynamic_text = orig_play_dynamic4

    # -- Regression guard, 2026-08-29: CONFIRMED LIVE on a real test call --
    #    a PURE question with NO extractable number at all ("ओके, कौन-कौन सी
    #    कैटेगरीज़ हैं आपके पास?" -- "OK, which categories do you have?") hit
    #    the LLM Q&A pipeline, which failed to answer (simulated here via the
    #    same REPROMPT_TEXT fallback as above -- fresh_qa_unavailable gets
    #    played, _try_fresh_llm_qa returns False). The old code then fell
    #    through unconditionally to `_budget or t`, and since extract_budget
    #    found no number, stored the RAW QUESTION TEXT as the customer's
    #    budget -- confirmed live in call_summaries.budget_mentioned. Must
    #    now re-ask fresh_ask_budget instead, leave fresh_step at BUDGET,
    #    and leave session.lead["budget"] unset.
    orig_llm_fallback6 = wr._llm_fallback_with_filler

    async def fake_llm_fallback_reprompt6(call_uuid, t, session, voice, facts=None, lang="hi"):
        return wr._REACT_LLM_REPROMPT_TEXT  # simulates the LLM Q&A pipeline failing

    wr._llm_fallback_with_filler = fake_llm_fallback_reprompt6
    try:
        s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT",
                          fresh_product="bed", fresh_step="BUDGET")
        results.append(await run_case(
            "fresh_cta / pure question + LLM Q&A failure -> re-asks budget, does NOT store question text as budget",
            wr.handle_fresh_cta_turn, s, "ओके, कौन-कौन सी कैटेगरीज़ हैं आपके पास?",
            expected_key="fresh_ask_budget", expect_continue=True,
            expect_session_attrs={"fresh_step": "BUDGET"},
        ))
        results.append(check("fresh_cta / pure question + LLM Q&A failure / budget NOT corrupted with question text",
                              s.lead.get("budget") in (None, ""), detail=f"lead={s.lead!r}"))

        # Same fix, INTERIOR_BUDGET -- more consequential there since falling
        # through also fired the manager handoff prematurely.
        s2 = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT",
                           fresh_product="", fresh_step="INTERIOR_BUDGET")
        results.append(await run_case(
            "fresh_cta / INTERIOR_BUDGET / pure question + LLM Q&A failure -> re-asks, no premature handoff",
            wr.handle_fresh_cta_turn, s2, "ओके, कौन-कौन सी कैटेगरीज़ हैं आपके पास?",
            expected_key="fresh_interior_budget_ask", expect_continue=True,
            expect_session_attrs={"fresh_step": "INTERIOR_BUDGET"},
        ))
        results.append(check("fresh_cta / INTERIOR_BUDGET / pure question + LLM Q&A failure / no handoff fired",
                              s2.lead.get("interest_type") != "interior_design", detail=f"lead={s2.lead!r}"))
    finally:
        wr._llm_fallback_with_filler = orig_llm_fallback6

    # -- Regression guard, 2026-08-29: CONFIRMED LIVE, severe -- fresh_cta's
    #    dispatch in webhook.py `return`s right after calling
    #    handle_fresh_cta_turn, before the shared session.turn_count_substantive
    #    increment further down in that same function ever runs. Every other
    #    multi-turn handler (react_a/b/c, call2, call3) increments this
    #    counter itself internally; fresh_cta never did, so
    #    _hard_cap_reason()'s duration_cap_close branch (meant only for a
    #    truly dead call with ZERO real speech) fired on EVERY fresh_cta call
    #    that simply ran past 180s wall-clock, no matter how substantive --
    #    confirmed live: 12 real turns of price/category Q&A, force-closed at
    #    212s with reason=duration_cap_close. Fixed: handle_fresh_cta_turn now
    #    increments turn_count_substantive itself for any real (non-empty,
    #    non-IVR-fragment) turn.
    _old_ts = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
    _recent_ts = datetime.now(timezone.utc).isoformat()
    # First real turn (call still fresh, well under 180s) must set the
    # counter to 1 -- isolates the increment itself from the hard-cap check
    # (which reads the counter's value from BEFORE this turn, so a call's
    # very first turn can never retroactively protect itself the same turn
    # it happens on -- that's expected; the real-world protection kicks in
    # from the NEXT turn onward, tested below).
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT",
                      fresh_product="sofa", started_at=_recent_ts)
    results.append(await run_case(
        "fresh_cta / turn_count_substantive now increments -> first real turn sets it to 1",
        wr.handle_fresh_cta_turn, s, "sofa ki price kya hai",
        expected_key="fresh_price_sofa", expect_continue=True,
    ))
    results.append(check("fresh_cta / turn_count_substantive == 1 after one real turn",
                          getattr(s, "turn_count_substantive", 0) == 1))
    # A call that's already had a real substantive turn (counter now >0)
    # must NOT be force-closed just because wall-clock has since passed
    # 180s -- this is the exact live scenario that was broken: 12 real
    # turns of price/category Q&A, force-closed anyway at 212s because the
    # counter had never once left 0.
    s2 = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT",
                       fresh_product="sofa", started_at=_old_ts, turn_count_substantive=1)
    results.append(await run_case(
        "fresh_cta / long-but-engaged call (>180s, prior real turns) NOT force-closed",
        wr.handle_fresh_cta_turn, s2, "wardrobe kitne ka hai",
        expected_key="fresh_price_wardrobe", expect_continue=True,
    ))
    # A genuinely dead call (only IVR/voicemail fragments, zero real speech)
    # must still be force-closed past 180s -- this is the ORIGINAL intended
    # behavior of this safety net and must not regress.
    s3 = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT",
                       fresh_product="sofa", started_at=_old_ts)
    results.append(await run_case(
        "fresh_cta / genuinely dead call (zero real speech, >180s) still force-closed",
        wr.handle_fresh_cta_turn, s3, "",
        expected_key="fresh_no_date_close", expect_continue=False,
    ))

    # -- _looks_like_question() coverage, 2026-08-20: verified against a
    #    batch of realistic product-detail phrasings a user asked to check
    #    (sofa types, leather, fabric, colours) -- the first-pass marker
    #    list missed 4/15 of these entirely. Pure unit checks on the
    #    function itself (no LLM/network involved) to lock in the fix and
    #    catch any future narrowing.
    _real_questions = [
        "kis tarah ke sofa hai aapke paas", "kaunse type ke sofa milte hain",
        "leather wala hai kya", "fabric mein kya kya hai", "fabric options kya hai",
        "sofa colours kaunse hain", "sofa kis kis colour mein milta hai",
        "what kind of sofa do you have", "do you have leather sofas",
        "what do you have in fabric",
    ]
    for q in _real_questions:
        results.append(check(f"_looks_like_question / detects real question: {q!r}",
                              wr._looks_like_question(q)))

    _plain_answers = [
        "60 hazar ke aas paas hoga", "agle mahine tak chahiye", "jaldi chahiye",
        "1 lakh ke andar", "sofa chahiye tha", "kal aa jaungi", "haan bataiye",
    ]
    for a in _plain_answers:
        results.append(check(f"_looks_like_question / no false positive on plain answer: {a!r}",
                              not wr._looks_like_question(a)))

    # -- Call 2/3 retries: new sequence must stay OFF, original
    #    date-confirmation-only behavior unchanged (fresh_step stays None).
    s = make_session(campaign="fresh_cta", call_cycle="2", react_state="APPOINTMENT", fresh_product="sofa")
    results.append(await run_case(
        "fresh_cta / call_cycle=2 / step machine inactive -> falls through to unchanged fresh_objection reask",
        wr.handle_fresh_cta_turn, s, "haan bataiye",
        expected_key="fresh_objection", expect_continue=True,
        expect_session_attrs={"fresh_step": None},
    ))

    # -- Regression guard, 2026-08-23: CONFIRMED LIVE -- once fresh_step
    #    reaches VISIT_DATE (or is None, call_cycle 2/3), a genuine
    #    recognized question (ask_offer_scope, ask_price_range) goes through
    #    the ORIGINAL LLM-fallback call site, not _try_fresh_llm_qa -- that
    #    site never got the 2026-08-22 fixes, so a real caller got silently
    #    reprompted twice with zero acknowledgment. Same fresh_qa_unavailable
    #    fallback now applies here too.
    orig_llm_fallback5 = wr._llm_fallback_with_filler
    orig_play_dynamic5 = wr.play_dynamic_text

    async def fake_llm_fallback_fail(call_uuid, t, session, voice, facts=None, lang="hi"):
        return None  # simulates a full pipeline failure/timeout

    async def fake_play_dynamic5(call_uuid, text, session=None, voice="shreya", lang="hi"):
        return True

    wr._llm_fallback_with_filler = fake_llm_fallback_fail
    wr.play_dynamic_text = fake_play_dynamic5
    try:
        s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT",
                          fresh_product="sofa", fresh_step="VISIT_DATE")
        # "kaun si kaun si furniture categories hain" (used here originally)
        # is now correctly intercepted by the dedicated ask_categories/
        # ask_offer_scope branch (2026-08-23, answered instantly from a
        # cached key, not the dynamic LLM path this test targets) --
        # swapped to "aapka naam kya hai" (ask_name), one of the
        # _INFORMATIONAL_QA_INTENTS with no dedicated fresh_cta branch, to
        # keep testing the LLM-fallback acknowledgment-on-failure path.
        results.append(await run_case(
            "fresh_cta / VISIT_DATE / recognized question with failed LLM -> gets acknowledgment, not silence",
            wr.handle_fresh_cta_turn, s, "aapka naam kya hai",
            expected_key="fresh_qa_unavailable", expect_continue=True,
        ))
    finally:
        wr._llm_fallback_with_filler = orig_llm_fallback5
        wr.play_dynamic_text = orig_play_dynamic5

    # -- Regression guard, 2026-08-23: CONFIRMED LIVE on the Pratham call --
    #    play_dynamic_text() used to append ("assistant", text) to
    #    session.conversation BEFORE even attempting TTS synthesis, so a
    #    real answer that was generated but then failed to synthesize (a
    #    genuine 6.5s timeout, not mocked away) got permanently recorded in
    #    the stored transcript as something the customer heard, even though
    #    zero audio was ever produced. Tests the REAL function body (not the
    #    wr.play_key/play_dynamic_text mocks every other test above uses) by
    #    patching tts_engine.get_speech directly, one level deeper.
    import tts_engine as _tts_engine
    orig_get_speech = _tts_engine.get_speech

    async def fake_get_speech_fails(*a, **kw):
        raise TimeoutError("simulated Sarvam TTS timeout")

    _tts_engine.get_speech = fake_get_speech_fails
    try:
        s2 = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT")
        played = await wr.play_dynamic_text("test-call-uuid", "Hamare paas sofa, bed, dining table hain.", s2, voice="simran", lang="hi")
        results.append(check("play_dynamic_text / TTS failure -> returns False", played is False))
        results.append(check("play_dynamic_text / TTS failure -> conversation NOT polluted with an unspoken line",
                              not any("sofa, bed, dining" in str(turn) for turn in s2.conversation),
                              detail=f"conversation={s2.conversation!r}"))
    finally:
        _tts_engine.get_speech = orig_get_speech

    # Success path must still log correctly -- confirms the fix didn't just
    # suppress logging altogether.
    orig_vobiz_play = wr._vobiz_play

    async def fake_get_speech_succeeds(*a, **kw):
        return b"fake-wav-bytes", "https://voice.thesocialhood.in/audio/dynamic/fake.wav", False

    async def fake_vobiz_play(call_uuid, audio_url, turn=0, kind="reply"):
        return True

    _tts_engine.get_speech = fake_get_speech_succeeds
    wr._vobiz_play = fake_vobiz_play
    try:
        s3 = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT")
        played2 = await wr.play_dynamic_text("test-call-uuid", "Hamare paas sofa hai.", s3, voice="simran", lang="hi")
        results.append(check("play_dynamic_text / TTS success -> returns True", played2 is True))
        results.append(check("play_dynamic_text / TTS success -> conversation correctly logged",
                              ("assistant", "Hamare paas sofa hai.") in s3.conversation,
                              detail=f"conversation={s3.conversation!r}"))
    finally:
        _tts_engine.get_speech = orig_get_speech
        wr._vobiz_play = orig_vobiz_play

    # -- Category/price/store Q&A, 2026-08-23 (real user-provided catalog
    # and store list). All answered from pre-cached keys, not the dynamic
    # LLM path -- no mocking needed, these should never even attempt it.
    from knowledge_react_abc import match_price_category, match_store_city

    _price_category_checks = [
        ("sofa ki price kya hai", "sofa"), ("bed ka rate kya hai", "bed"),
        ("wardrobe kitne ka hai", "wardrobe"), ("dining set ki price batao", "dining"),
        ("office table kitne ka hai", "office_table"), ("office chair ka rate", "office_chair"),
        ("lounge chair ki price", "lobby_chair"), ("ottoman kitne ka hai", "ottoman"),
        ("tv unit ka rate kya hai", "tv_unit"), ("bedroom chair ki price", "bedroom_chair"),
        ("garden furniture kitne ka hai", "garden_furniture"), ("coffee table ki price", "center_table"),
        ("mattress ki price kya hai", None),  # not in the real catalog -- must not guess a category
    ]
    for text, expected in _price_category_checks:
        results.append(check(f"match_price_category({text!r}) == {expected!r}",
                              match_price_category(text) == expected))

    _city_checks = [
        ("gurgaon mein kaha hai", "gurgaon"), ("gurugram wala store", "gurgaon"),
        ("noida mein location", "noida"), ("faridabad mein hai kya", "faridabad"),
        ("delhi wala store", "delhi"), ("ghitorni mein hai kya", "delhi"),
        ("mumbai mein hai kya", None),  # not a real store city
    ]
    for text, expected in _city_checks:
        results.append(check(f"match_store_city({text!r}) == {expected!r}",
                              match_store_city(text) == expected))

    # 2026-08-29 fix: trailing punctuation right after the last word must
    # not break the match (confirmed live -- "Do you have starting price of
    # bed?" previously returned None because the old boundary-space check
    # needed " bed " but got " bed?").
    _punct_checks = [
        ("Do you have starting price of bed?", "bed"),
        ("sofa ki price kya hai?", "sofa"),
        ("aapka store kahan hai?", None),  # sanity: unrelated q-mark text still None
    ]
    for text, expected in _punct_checks:
        results.append(check(f"match_price_category({text!r}) == {expected!r} (trailing punctuation)",
                              match_price_category(text) == expected))

    from knowledge_react_abc import mentions_non_catalog_item
    _non_catalog_checks = [
        ("mattress ki price kya hai", True), ("curtain ka rate kya hai", True),
        ("starting price kya hai", False), ("sofa ki price kya hai", False),
    ]
    for text, expected in _non_catalog_checks:
        results.append(check(f"mentions_non_catalog_item({text!r}) == {expected!r}",
                              mentions_non_catalog_item(text) == expected))

    # Specific product named -> instant dedicated price key, no LLM involved.
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / price Q&A / named category -> dedicated price key",
        wr.handle_fresh_cta_turn, s, "sofa ki price kya hai",
        expected_key="fresh_price_sofa", expect_continue=True,
    ))
    # No product named -> ask which category they mean (2026-08-29 fix:
    # this was wrongly going to fresh_price_unavailable, contradicting the
    # user's own spec for a vague price ask -- confirmed live on a real
    # test call, "What is our starting price?" got the "I don't have it"
    # line instead of "which furniture's price do you want").
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / price Q&A / vague price question -> asks which category",
        wr.handle_fresh_cta_turn, s, "starting price kya hai",
        expected_key="fresh_categories_list", expect_continue=True,
    ))
    # Trailing punctuation right after the category word must not break the
    # match (2026-08-29 fix: confirmed live, "Do you have starting price of
    # bed?" fell through to fresh_price_unavailable because the old
    # boundary-space check needed " bed " but the transcript had " bed?"
    # with no space before the question mark).
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / price Q&A / trailing punctuation right after category word still matches",
        wr.handle_fresh_cta_turn, s, "Do you have starting price of bed?",
        expected_key="fresh_price_bed", expect_continue=True,
    ))
    # Category not in the real catalog -> same honest fallback, never fabricated.
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / price Q&A / item not in catalog -> honest unavailable fallback, not a guess",
        wr.handle_fresh_cta_turn, s, "mattress ki price kya hai",
        expected_key="fresh_price_unavailable", expect_continue=True,
    ))
    # General "what do you sell" -> full list + its own clarifying question.
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / categories Q&A / vague -> full categories list",
        wr.handle_fresh_cta_turn, s, "kya kya milta hai aapke store mein",
        expected_key="fresh_categories_list", expect_continue=True,
    ))
    # Real customer phrasing that hits ask_offer_scope, not ask_categories --
    # confirmed live (Pratham) -- must still resolve to the categories list.
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / categories Q&A / ask_offer_scope phrasing treated as a synonym",
        wr.handle_fresh_cta_turn, s, "kaun si kaun si furniture categories hain",
        expected_key="fresh_categories_list", expect_continue=True,
    ))
    # City named -> dedicated store reply; call continues, doesn't hang up
    # (2026-08-23 fix -- confirmed live the old hard return False after
    # answering a location question read as an abrupt cutoff, Pratham call).
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / location Q&A / named city -> dedicated store key, call continues",
        wr.handle_fresh_cta_turn, s, "gurgaon mein showroom kahan hai",
        expected_key="fresh_store_gurgaon", expect_continue=True,
    ))
    # No city named -> general list, which itself asks which city.
    s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="")
    results.append(await run_case(
        "fresh_cta / location Q&A / vague -> general list + clarifying question",
        wr.handle_fresh_cta_turn, s, "aapka store kahan hai",
        expected_key="fresh_location_info", expect_continue=True,
    ))

    total = len(results)
    passed = sum(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
