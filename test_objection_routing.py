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

    total = len(results)
    passed = sum(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
