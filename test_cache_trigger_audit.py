# -*- coding: utf-8 -*-
"""
test_cache_trigger_audit.py — full cache-trigger honesty audit for
fresh_cta + react_a/b/c Call1/2/3 (webhook_reactivation.py).

Three passes, run in order:

  1. STATIC   — every key literal / f-string this file's code can produce,
                per (flow, state), independent of whether any transcript
                actually reaches it. Cross-checked against the script dicts
                (knowledge_react_abc.py) both directions.
  2. DYNAMIC  — drives the real turn handlers (handle_fresh_cta_turn,
                handle_reactivation_turn, handle_call2_turn, handle_call3_turn)
                with one representative transcript per (flow, state, intent),
                play_key()/fire_whatsapp()/_fire_immediate_dnc() monkeypatched
                to no-op recorders exactly like test_objection_routing.py.
                Records which key(s) play_key() actually resolved to.
  3. AUDIO    — for every key seen in pass 2, calls the REAL
                webhook_reactivation._static_url() (unpatched) to determine
                cache-hit vs silent-fallback-to-live-TTS, and separately
                stats the .wav file (exists / size).

Usage: python3 test_cache_trigger_audit.py
Prints a machine-parseable report to stdout; no assertions, no exit-code
failure — this is an audit, not a regression gate.
"""
import asyncio
import os
import sys
from types import SimpleNamespace

import webhook_reactivation as wr
from knowledge_react_abc import (
    REACT_A_SCRIPT, REACT_B_SCRIPT, REACT_C_SCRIPT, FRESH_CTA_SCRIPT,
    FRESH_CALL2_SCRIPT, FRESH_CALL3_SCRIPT, CALL2_SCRIPT, CALL3_SCRIPT,
    SHARED_SCRIPT, PREFIX_VOICE_MAP,
)

STATIC_DIR = "/home/voiceagent/voice-ai/tts-cache/static"

# ─────────────────────────────────────────────────────────────────────────
# PASS 1 — STATIC key inventory, hand-traced from every play_key() call
# site in webhook_reactivation.py (including route_objection() and
# check_hard_rejection()). One entry per (flow, state) -> set of keys that
# site can produce. "GLOBAL" entries apply regardless of state (dnc, repeat
# fallback voice keys, timing fallback voice keys).
# ─────────────────────────────────────────────────────────────────────────

def prefix_keys(p):
    return {
        f"{p}_dnc", f"{p}_obj_busy", f"{p}_greet_who", f"{p}_greet_repeat",
        f"{p}_greet_privacy", f"{p}_greet_hostile", f"{p}_offer_main",
        f"{p}_offer_explain", f"{p}_offer_trust", f"{p}_offer_urgency",
        f"{p}_obj_expensive", f"{p}_obj_online", f"{p}_obj_not_interested",
        f"{p}_wa_cta", f"{p}_hook_cta", f"{p}_obj_recovery", f"{p}_obj_think",
        f"{p}_close", f"{p}_q_location", f"{p}_q_name", f"{p}_q_valuation",
        f"{p}_appointment_ask", f"{p}_appointment_confirmed",
        f"{p}_appointment_reask",
    }

STATIC_INVENTORY = {}
for _plan_prefix in ("ra", "rb", "rc"):
    voice = PREFIX_VOICE_MAP[_plan_prefix]
    STATIC_INVENTORY[f"react_call1({_plan_prefix})"] = {
        "GREETING": {f"{_plan_prefix}_greet_who", f"{_plan_prefix}_offer_main",
                     f"{_plan_prefix}_greet_repeat", f"{_plan_prefix}_greet_privacy",
                     f"{_plan_prefix}_greet_hostile", f"{_plan_prefix}_dnc",
                     # NOTE: obj_repeat_generic_{voice} is deliberately EXCLUDED here --
                     # route_objection()'s repeat branch returns None unconditionally for
                     # (prefix in ra/rb/rc, state==GREETING), so it is NOT reachable at
                     # this specific (flow,state) even though the f-string literal is
                     # reachable for this same prefix at every OTHER state below.
                     f"obj_timing_greet_generic_{voice}"},
        "PRESENT_OFFER": {f"{_plan_prefix}_offer_explain", f"{_plan_prefix}_offer_trust",
                           f"{_plan_prefix}_offer_urgency", f"{_plan_prefix}_wa_cta",
                           f"{_plan_prefix}_obj_expensive", f"{_plan_prefix}_obj_online",
                           f"{_plan_prefix}_obj_not_interested", f"{_plan_prefix}_obj_busy",
                           f"{_plan_prefix}_hook_cta", f"{_plan_prefix}_dnc",
                           f"obj_repeat_generic_{voice}", f"{_plan_prefix}_obj_think"},
        "WHATSAPP_CTA": {f"{_plan_prefix}_wa_cta", f"{_plan_prefix}_offer_trust",
                          f"{_plan_prefix}_obj_recovery", f"{_plan_prefix}_obj_not_interested",
                          f"{_plan_prefix}_obj_think", f"{_plan_prefix}_close",
                          f"{_plan_prefix}_greet_who", f"{_plan_prefix}_q_location",
                          f"{_plan_prefix}_q_name", f"{_plan_prefix}_q_valuation",
                          f"{_plan_prefix}_appointment_ask", f"{_plan_prefix}_dnc",
                          f"obj_repeat_generic_{voice}"},
        "APPOINTMENT": {f"{_plan_prefix}_greet_who", f"{_plan_prefix}_q_location",
                         f"{_plan_prefix}_q_name", f"{_plan_prefix}_q_valuation",
                         f"{_plan_prefix}_appointment_ask", f"{_plan_prefix}_close",
                         f"{_plan_prefix}_appointment_confirmed", f"{_plan_prefix}_appointment_reask",
                         f"{_plan_prefix}_dnc", f"obj_repeat_generic_{voice}"},
        "CLOSE/DONE": set(),  # terminal -- route_objection short-circuits, no play_key ever fires
    }

STATIC_INVENTORY["fresh_cta"] = {
    "APPOINTMENT": {
        "ra_dnc", "fresh_price", "fresh_trust", "fresh_appointment_confirmed",
        "fresh_soft_defer", "fresh_greet_who_bed", "fresh_greet_who_sofa",
        "fresh_greet_who_wardrobe", "fresh_greet_who_dining", "fresh_greet_who_generic",
        "fresh_location_info", "fresh_objection", "fresh_no_date_close",
        f"obj_repeat_generic_{PREFIX_VOICE_MAP['fresh']}",
        # NOTE: obj_timing_greet_generic_* NOT reachable for fresh -- route_objection's
        # timing branch only fires at state=="GREETING", and fresh's session.react_state
        # is hard-set to "APPOINTMENT" and never anything else.
    },
}

STATIC_INVENTORY["call2"] = {
    "GREETING": {"c2_close_busy", "c2_greet_reorient", "c2_wa_check",
                 "c2_obj_not_interested", "c2_close_declined", "ra_dnc",
                 f"obj_repeat_generic_{PREFIX_VOICE_MAP['c2']}",
                 f"obj_timing_greet_generic_{PREFIX_VOICE_MAP['c2']}"},
    "WA_CHECK": {"c2_invite_resend", "c2_obj_price", "c2_invite_seen", "ra_dnc",
                 "c2_obj_scam", "c2_obj_not_interested", "c2_close_declined",
                 "c2_obj_timing", f"obj_repeat_generic_{PREFIX_VOICE_MAP['c2']}"},
    "DATE_ASK": {"c2_close_price", "c2_date_direct", "c2_obj_not_interested",
                 "c2_close_declined", "c2_obj_price", "c2_obj_scam", "c2_booked",
                 "c2_date_reask", "c2_close_thinking", "ra_dnc",
                 f"obj_repeat_generic_{PREFIX_VOICE_MAP['c2']}"},
}

STATIC_INVENTORY["call3"] = {
    "GREETING": {"c3_greet_reorient", "c3_decision_date", "c3_greet_hostile",
                 "c3_close_busy", "ra_dnc", "c3_obj_price", "c3_obj_scam",
                 f"obj_repeat_generic_{PREFIX_VOICE_MAP['c3']}",
                 f"obj_timing_greet_generic_{PREFIX_VOICE_MAP['c3']}"},
    "DECISION_DATE": {"c3_declined", "c3_obj_price", "c3_obj_scam", "c3_booked",
                       "c3_date_reask", "c3_close_thinking_final", "ra_dnc",
                       f"obj_repeat_generic_{PREFIX_VOICE_MAP['c3']}"},
}

# Pre-stream greeting keys -- constructed directly in webhook.py's
# /answer-outbound as a hardcoded <Play> URL, NEVER through play_key().
# Included here for completeness/Step 3 audio verification only -- these
# are NOT part of webhook_reactivation.py's play_key()/route_objection()
# call graph, so Step 2 (dynamic drive) cannot and does not exercise them.
PRESTREAM_GREETING_KEYS = {
    "ra_greet_combined", "rb_greet_combined", "rc_greet_combined",
    "c2_greet_main", "c3_greet_main",
    "fresh_greet_bed", "fresh_greet_sofa", "fresh_greet_wardrobe",
    "fresh_greet_dining", "fresh_greet_generic",
    "fresh_c2_greet_bed", "fresh_c2_greet_sofa", "fresh_c2_greet_wardrobe",
    "fresh_c2_greet_dining", "fresh_c2_greet_generic",
    "fresh_c3_greet_bed", "fresh_c3_greet_sofa", "fresh_c3_greet_wardrobe",
    "fresh_c3_greet_dining", "fresh_c3_greet_generic",
    "wa_decline_confirm_greet", "universal_greeting", "react_greet_main",
    "react_followup_wa",
}

ALL_SCRIPT_DICTS = {
    **{k: v for k, v in REACT_A_SCRIPT.items()},
    **{k: v for k, v in REACT_B_SCRIPT.items()},
    **{k: v for k, v in REACT_C_SCRIPT.items()},
    **{k: v for k, v in FRESH_CTA_SCRIPT.items()},
    **{k: v for k, v in FRESH_CALL2_SCRIPT.items()},
    **{k: v for k, v in FRESH_CALL3_SCRIPT.items()},
    **{k: v for k, v in CALL2_SCRIPT.items()},
    **{k: v for k, v in CALL3_SCRIPT.items()},
    **{k: v for k, v in SHARED_SCRIPT.items()},
}


def run_static_pass():
    print("=" * 100)
    print("PASS 1 — STATIC KEY INVENTORY (code -> script dict cross-check)")
    print("=" * 100)
    all_code_keys = set()
    for flow, states in STATIC_INVENTORY.items():
        for state, keys in states.items():
            all_code_keys |= keys
    all_code_keys |= PRESTREAM_GREETING_KEYS

    missing_from_script = sorted(k for k in all_code_keys if k not in ALL_SCRIPT_DICTS)
    print(f"\nTotal distinct keys referenced by code (incl. pre-stream greetings): {len(all_code_keys)}")
    print(f"Keys referenced in code but MISSING from any script dict (would break at runtime "
          f"via play_key's 'No text for key' error, or 404 on the hardcoded pre-stream URL): "
          f"{len(missing_from_script)}")
    for k in missing_from_script:
        print(f"    MISSING-FROM-SCRIPT: {k}")

    orphaned_in_script = sorted(k for k in ALL_SCRIPT_DICTS if k not in all_code_keys
                                 and not k.endswith(("_filler_1", "_filler_2", "_filler_3",
                                                      "_filler_4", "_filler_5", "_filler_6")))
    print(f"\nKeys present in a script dict but referenced by NO code path in "
          f"webhook_reactivation.py or the /answer-outbound pre-stream greeting "
          f"(fillers excluded -- separate system, out of scope): {len(orphaned_in_script)}")
    for k in orphaned_in_script:
        print(f"    ORPHANED-IN-SCRIPT: {k}")

    return all_code_keys


# ─────────────────────────────────────────────────────────────────────────
# PASS 2 — DYNAMIC drive: one representative transcript per named intent,
# fired at every (flow, state) this file's handlers expose.
# ─────────────────────────────────────────────────────────────────────────

INTENT_TRANSCRIPTS = {
    "positive":            "haan",
    "confusion_who":       "kaun",
    "repeat":              "kya bola",
    "privacy_concern":     "spam",
    "offer_clarify":       "kya offer",
    "trust_issue":         "fake hai",
    "buying_signal":       "interested hoon",
    "wa_ok":                "bhejo",
    "wa_no_whatsapp":      "whatsapp nahi hai",
    "wa_diff_number":      "alag number",
    "wa_prefers":          "whatsapp pe hi",
    "busy":                "busy hoon",
    "not_interested":      "interested nahi",
    "expensive":           "mahenga hai",
    "online_cheaper":      "online sasta",
    "sochna_hai":          "sochna hai",
    "escalate":            "manager se baat",
    "dnc":                 "dobara call mat karna",
    "personal_question":   "robot ho",
    "ask_location":        "kahan hai",
    "ask_name":            "tumhara naam",
    "ask_timings":         "time kya",
    "ask_valuation":       "valuation kaise",
    "ask_delivery":        "delivery kab",
    "appointment_confirm_day":   "monday",
    "appointment_confirm_digit": "20 tareek",
    "silence":             "",
    "machine_ivr":         "please stay on the line",
}


class Recorder:
    def __init__(self):
        self.played = []
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


async def drive(handler, session, transcript):
    recorder = Recorder()
    orig_play_key, orig_fire_wa, orig_dnc = wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc

    async def fake_play_key(call_uuid, key, session=None, log_transcript=True):
        recorder.played.append(key)
        return True

    async def fake_fire_whatsapp(session, call_uuid):
        recorder.wa_fired = True
        return True

    def fake_fire_immediate_dnc(session, call_uuid):
        recorder.dnc_fired = True

    wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc = fake_play_key, fake_fire_whatsapp, fake_fire_immediate_dnc
    try:
        should_continue = await handler(session, transcript, "audit-call-uuid")
    finally:
        wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc = orig_play_key, orig_fire_wa, orig_dnc
    return recorder, should_continue


ROWS = []  # (flow, state, intent, transcript, played_keys, continue_, notes)


async def sweep_react_call1():
    for plan in ("react_a", "react_b", "react_c"):
        p = wr.get_prefix(plan)
        for state in ("GREETING", "PRESENT_OFFER", "WHATSAPP_CTA", "APPOINTMENT"):
            for intent, transcript in INTENT_TRANSCRIPTS.items():
                s = make_session(campaign=plan, call_cycle=None, react_state=state)
                rec, cont = await drive(wr.handle_reactivation_turn, s, transcript)
                ROWS.append((f"react_call1({p})", state, intent, transcript, rec.played, cont, ""))
        # CLOSE/DONE terminal states -- confirm truly zero plays
        for state in ("CLOSE", "DONE"):
            s = make_session(campaign=plan, call_cycle=None, react_state=state)
            rec, cont = await drive(wr.handle_reactivation_turn, s, "kya bola")
            ROWS.append((f"react_call1({p})", state, "repeat(terminal-check)", "kya bola", rec.played, cont, "terminal"))


def make_bare_fresh_session(**overrides):
    # handle_fresh_cta_turn uses `not hasattr(session, "dnc")` as its own
    # first-turn bootstrap sentinel (sets session.dnc/react_state itself) --
    # make_session() unconditionally pre-sets .dnc, which would skip that
    # bootstrap and leave react_state unset (AttributeError in route_objection).
    # A real session has neither attribute before its first turn, so this
    # constructor deliberately omits both, matching production.
    s = SimpleNamespace()
    s.customer_phone = "+919999900000"
    s.customer_name = "Test"
    s.conversation = []
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


async def sweep_fresh_cta():
    for product in ("bed", "sofa", "wardrobe", "dining", ""):
        for intent, transcript in INTENT_TRANSCRIPTS.items():
            s = make_bare_fresh_session(campaign="fresh_cta", call_cycle=None, fresh_product=product)
            rec, cont = await drive(wr.handle_fresh_cta_turn, s, transcript)
            tag = f"product={product or 'generic'}"
            ROWS.append(("fresh_cta", "APPOINTMENT", intent, transcript, rec.played, cont, tag))
    # Second-reask fallback: appt_reask_tried already True -> fresh_no_date_close.
    # This IS a genuine 2nd-turn scenario, so dnc/react_state are pre-set here
    # deliberately (mimicking state carried over from turn 1), unlike the bare
    # first-turn sessions above.
    s = make_session(campaign="fresh_cta", call_cycle=None, fresh_product="", appt_reask_tried=True,
                      dnc=False, react_state="APPOINTMENT")
    rec, cont = await drive(wr.handle_fresh_cta_turn, s, "koi random baat")
    ROWS.append(("fresh_cta", "APPOINTMENT", "unmatched_2nd_turn", "koi random baat", rec.played, cont,
                 "appt_reask_tried=True pre-set"))


async def sweep_call2():
    for state in ("GREETING", "WA_CHECK", "DATE_ASK"):
        for intent, transcript in INTENT_TRANSCRIPTS.items():
            s = make_session(campaign="react_a", call_cycle="2", c2_state=state)
            rec, cont = await drive(wr.handle_call2_turn, s, transcript)
            ROWS.append(("call2", state, intent, transcript, rec.played, cont, ""))
    # DATE_ASK price-pending sub-branch (only reachable after WA_CHECK sets it)
    for intent_tag, transcript in (("not_interested", "interested nahi"), ("other", "haan")):
        s = make_session(campaign="react_a", call_cycle="2", c2_state="DATE_ASK", c2_price_asked=True)
        rec, cont = await drive(wr.handle_call2_turn, s, transcript)
        ROWS.append(("call2", "DATE_ASK(price_asked=True)", intent_tag, transcript, rec.played, cont,
                     "c2_price_asked pre-set True"))
    # 2nd-turn reask-exhausted fallback -> c2_close_thinking (needs c2_reask_tried
    # already True, which only happens after a real 1st vague turn -- single-turn
    # sweep above can't reach this on its own).
    s = make_session(campaign="react_a", call_cycle="2", c2_state="DATE_ASK", c2_reask_tried=True)
    rec, cont = await drive(wr.handle_call2_turn, s, "haan")
    ROWS.append(("call2", "DATE_ASK(reask_tried=True)", "vague_2nd_turn", "haan", rec.played, cont,
                 "c2_reask_tried pre-set True"))


async def sweep_call3():
    for state in ("GREETING", "DECISION_DATE"):
        for intent, transcript in INTENT_TRANSCRIPTS.items():
            s = make_session(campaign="react_a", call_cycle="3", c3_state=state)
            rec, cont = await drive(wr.handle_call3_turn, s, transcript)
            ROWS.append(("call3", state, intent, transcript, rec.played, cont, ""))
    # 2nd-turn reask-exhausted fallback -> c3_close_thinking_final (mirrors
    # call2's DATE_ASK check above).
    s = make_session(campaign="react_a", call_cycle="3", c3_state="DECISION_DATE", c3_reask_tried=True)
    rec, cont = await drive(wr.handle_call3_turn, s, "haan")
    ROWS.append(("call3", "DECISION_DATE(reask_tried=True)", "vague_2nd_turn", "haan", rec.played, cont,
                 "c3_reask_tried pre-set True"))


async def sweep_silence_chains():
    """
    3 consecutive silent turns on ONE session -- the silence>=3 branch in
    every handler runs BEFORE route_objection()/the state chain (checked
    first, on transcript=="" alone), so it's unaffected by the GREETING
    busy/sochna_hai shadowing route_objection introduces for c2/c3 (see
    sweep_call2/sweep_call3's single-turn 'busy' rows). This isolates
    whether {key}_close_busy is reachable via repeated silence even though
    the SPOKEN "busy" utterance path to the same key is now dead.
    """
    combos = [
        ("react_call1(ra)", wr.handle_reactivation_turn, dict(campaign="react_a", call_cycle=None, react_state="GREETING"), "ra_obj_busy"),
        ("call2", wr.handle_call2_turn, dict(campaign="react_a", call_cycle="2", c2_state="GREETING"), "c2_close_busy"),
        ("call3", wr.handle_call3_turn, dict(campaign="react_a", call_cycle="3", c3_state="GREETING"), "c3_close_busy"),
    ]
    for label, handler, session_kwargs, expected_key in combos:
        s = make_session(**session_kwargs)
        last_played, last_cont = [], None
        for turn in range(1, 4):
            rec, cont = await drive(handler, s, "")
            last_played, last_cont = rec.played, cont
        ROWS.append((label, "GREETING(3x-silence-chain)", "silence_x3", "'' x3", last_played, last_cont,
                     f"3 consecutive empty turns on one session; expected {expected_key}"))


async def run_dynamic_pass():
    print("\n" + "=" * 100)
    print("PASS 2 — DYNAMIC DRIVE (real handlers, real detect_intents(), real route_objection())")
    print("=" * 100)
    await sweep_react_call1()
    await sweep_fresh_cta()
    await sweep_call2()
    await sweep_call3()
    await sweep_silence_chains()

    triggered_keys = set()
    for flow, state, intent, transcript, played, cont, notes in ROWS:
        triggered_keys.update(played)

    print(f"\nTotal (flow,state,intent) combinations driven: {len(ROWS)}")
    print(f"Total distinct keys actually resolved by play_key() across all combinations: {len(triggered_keys)}")

    print("\n--- full per-combination trace ---")
    for flow, state, intent, transcript, played, cont, notes in ROWS:
        note_s = f"  [{notes}]" if notes else ""
        print(f"[{flow:<16}] [{state:<26}] intent={intent:<28} transcript={transcript!r:<26} "
              f"-> played={played}  continue={cont}{note_s}")

    return triggered_keys


# ─────────────────────────────────────────────────────────────────────────
# PASS 3 — AUDIO verification for every key seen in pass 2 (+ static-only
# extras: pre-stream greetings, since those matter for real call quality
# even though play_key() never touches them).
# ─────────────────────────────────────────────────────────────────────────

def run_audio_pass(triggered_keys):
    print("\n" + "=" * 100)
    print("PASS 3 — AUDIO VERIFICATION (file exists? size? play_key._static_url cache-hit or fallback?)")
    print("=" * 100)

    all_keys_to_check = sorted(triggered_keys | PRESTREAM_GREETING_KEYS)
    results = []
    for key in all_keys_to_check:
        path = os.path.join(STATIC_DIR, f"{key}_hi.wav")
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else 0
        # Real, unpatched _static_url() -- exact cache-hit logic play_key() uses.
        cache_url = wr._static_url(key)
        is_prestream = key in PRESTREAM_GREETING_KEYS
        if is_prestream:
            # /answer-outbound builds this URL directly with NO existence check
            # and NO live-TTS fallback -- if missing, Vobiz gets a dead URL.
            status = "FILE-OK-HARDCODED-NO-FALLBACK" if (exists and size > 1000) else "MISSING-HARDCODED-NO-FALLBACK-DEAD-AIR"
        elif cache_url:
            status = "CACHE-HIT"
        elif exists and size <= 1000:
            status = "FILE-TOO-SMALL-FALLS-TO-LIVE-TTS"
        else:
            status = "MISSING-FALLS-TO-LIVE-TTS"
        results.append((key, exists, size, status, is_prestream))
        print(f"  {key:<40} exists={str(exists):<5} size={size:<8} status={status}")

    return results


async def main():
    all_code_keys = run_static_pass()
    triggered_keys = await run_dynamic_pass()
    audio_results = run_audio_pass(triggered_keys)

    print("\n" + "=" * 100)
    print("PASS 4 — HONEST SUMMARY")
    print("=" * 100)
    reachable_not_triggered = sorted(all_code_keys - triggered_keys - PRESTREAM_GREETING_KEYS)
    print(f"Total distinct keys statically reachable by code (excl. pre-stream greetings): "
          f"{len(all_code_keys - PRESTREAM_GREETING_KEYS)}")
    print(f"Of those, actually triggered by >=1 realistic transcript in pass 2: {len(triggered_keys)}")
    print(f"Reachable in code but NOT triggered by any realistic transcript tried "
          f"(dead in practice, even if not dead in principle): {len(reachable_not_triggered)}")
    for k in reachable_not_triggered:
        print(f"    NOT-TRIGGERED: {k}")

    cache_hit = sum(1 for r in audio_results if r[3] == "CACHE-HIT")
    fallback = sum(1 for r in audio_results if r[3] in ("FILE-TOO-SMALL-FALLS-TO-LIVE-TTS", "MISSING-FALLS-TO-LIVE-TTS"))
    dead_air = sum(1 for r in audio_results if "DEAD-AIR" in r[3])
    print(f"\nOf triggered+prestream keys checked: {len(audio_results)}")
    print(f"  CACHE-HIT (real audio, confirmed play_key resolves from cache): {cache_hit}")
    print(f"  FALLS-TO-LIVE-TTS (missing/undersized, play_key would live-generate): {fallback}")
    print(f"  MISSING-HARDCODED-NO-FALLBACK (pre-stream greeting, dead air if hit): {dead_air}")


if __name__ == "__main__":
    asyncio.run(main())
