# -*- coding: utf-8 -*-
"""
Regression suite for the 2026-08-19 keyword-matching audit
(_VERB_FORM_ALIASES + the 2 priority-order fixes in webhook_reactivation.py /
knowledge_react_abc.py). Grew out of a real customer complaint (Pratham:
"kya aap mujhe baad mein call kar sakte hain?" matched nothing but "busy")
that turned into a systematic pass over verb-conjugation coverage and
route_objection()'s priority chain.

Three things are verified here, each end-to-end (detect_intents() ->
route_objection()/the real turn handler -> actual spoken reply key), not just
the matched-label level test_reply_state_regression.py stops at:

  1. _VERB_FORM_ALIASES generalizes conjugation coverage across 6 categories
     (callback_later, want_human, cancel_appointment, reschedule_appointment,
     ask_pickup_logistics, wa_ok) without needing every inflection listed as
     a literal keyword -- command/polite-question/honorific-imperative forms,
     in both Hindi and Hinglish, each get the correct reply.
  2. The alias table's generalization doesn't reopen the negation-blind
     false-positive class fixed earlier the same day ("mat"/"nahi" directly
     before the aliased verb token must still block the match).
  3. The two real bugs found while auditing route_objection()'s priority
     order against every category's keyword list are fixed and stay fixed:
     wa_prefers's dead "call nahi" keyword (DNC's short-circuit meant it could
     never actually fire as wa_prefers) and personal_question/ask_name's
     duplicate "tumhara naam" keyword (personal_question ran first in
     route_objection(), so a bare "what's your name" always got the generic
     AI-assistant deflection instead of ask_name's actual answer).

Usage:
    python3 test_verb_equivalence_audit.py
"""
import asyncio
import contextlib
from types import SimpleNamespace

import webhook_reactivation as wr
from webhook_reactivation import detect_intents


class Recorder:
    def __init__(self):
        self.played = []
        self.calls = []  # (fn_name, keys) -- tracks whether play_key or play_keys was used


def make_session(**overrides):
    s = SimpleNamespace()
    s.customer_phone = "+919999900000"
    s.customer_name = "Test"
    s.dnc = False
    s.wa_sent = False
    s.silence_count = 0
    s.turn_count = 0
    s.conversation = []
    s.appointment_confirmed = False
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def patch_io(monkeypatch_target, recorder: Recorder):
    async def fake_play_key(call_uuid, key, session=None, log_transcript=True):
        recorder.played.append(key)
        recorder.calls.append(("play_key", [key]))
        return True

    async def fake_play_keys(call_uuid, keys, session=None, log_transcript=True):
        recorder.played.extend(keys)
        recorder.calls.append(("play_keys", list(keys)))
        return True

    async def fake_fire_whatsapp(session, call_uuid):
        return True

    def fake_fire_immediate_dnc(session, call_uuid):
        pass

    async def fake_play_dynamic_text(call_uuid, text, session=None, voice="shreya"):
        recorder.played.append(text)
        return True

    monkeypatch_target.play_key = fake_play_key
    monkeypatch_target.play_keys = fake_play_keys
    monkeypatch_target.fire_whatsapp = fake_fire_whatsapp
    monkeypatch_target._fire_immediate_dnc = fake_fire_immediate_dnc
    monkeypatch_target.play_dynamic_text = fake_play_dynamic_text


_results = []


def check_intent(label, transcript, expected_intent, forbidden_intents=()):
    intents = detect_intents(transcript)
    ok = expected_intent in intents and not any(f in intents for f in forbidden_intents)
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label:<70} intents={intents!r}")
    _results.append(ok)
    return ok


@contextlib.asynccontextmanager
async def patched_wr(recorder: Recorder, llm_reply=None):
    """Single save/restore point for every wr.* attribute a test might mock
    (play_key/play_keys/fire_whatsapp/_fire_immediate_dnc/play_dynamic_text,
    optionally llm_fallback_reply too) -- added 2026-08-19 during a code
    review after finding this save/restore boilerplate duplicated across
    check_reply() and 3 separate blocks in
    run_llm_fallback_coverage_checks(), the exact kind of duplication that
    already caused a real bug earlier this session (play_dynamic_text was
    left unmocked in one of those blocks, silently making the fallback path
    look like it always failed under test). One helper now, used everywhere.
    """
    orig = {
        "play_key": wr.play_key, "play_keys": wr.play_keys,
        "fire_whatsapp": wr.fire_whatsapp, "_fire_immediate_dnc": wr._fire_immediate_dnc,
        "play_dynamic_text": wr.play_dynamic_text,
    }
    if llm_reply is not None:
        orig["llm_fallback_reply"] = wr.llm_fallback_reply
    patch_io(wr, recorder)
    if llm_reply is not None:
        wr.llm_fallback_reply = llm_reply
    try:
        yield recorder
    finally:
        for name, fn in orig.items():
            setattr(wr, name, fn)


async def check_reply(label, coro_fn, session, transcript, expected_key):
    recorder = Recorder()
    async with patched_wr(recorder):
        await coro_fn(session, transcript, "test-call-uuid")
    ok = expected_key in recorder.played
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label:<70} played={recorder.played!r}")
    _results.append(ok)
    return ok


# ═══════════════════════════════════════════════════════════════════════════
# Part 1: verb-form-alias coverage, per category, across sentence-form axes
# (command / polite-question / honorific-imperative), Hindi + Hinglish.
# Each of these 6 categories was found this session missing at least one of
# these forms despite already covering the command form.
# ═══════════════════════════════════════════════════════════════════════════

INTENT_AXIS_CASES = [
    # (label, transcript, expected_intent)
    ("callback_later / command",            "baad mein call karo",                          "callback_later"),
    ("callback_later / polite-question",    "kya aap baad mein call kar sakte hain",         "callback_later"),
    ("callback_later / honorific-imperative","baad mein call kar dijiye",                    "callback_later"),
    ("callback_later / english",            "can you call me back later",                   "callback_later"),
    ("callback_later / hinglish-mixed",     "sir thoda baad mein call kar sakte ho please",  "callback_later"),
    ("callback_later / devanagari question","क्या आप बाद में कॉल कर सकते हैं",                  "callback_later"),
    ("callback_later / real Pratham phrase","kya aap mujhe baad mein call kar sakte hain?",  "callback_later"),
    ("callback_later / kar lijiye variant",  "aap baad mein call kar lijiye please",         "callback_later"),

    ("want_human / command",                "insaan se baat karwao",                        "want_human"),
    ("want_human / polite-question",        "kya insaan se baat karwa sakte hain",           "want_human"),
    ("want_human / need-to statement",      "mujhe insaan se baat karni hai",                "want_human"),
    ("want_human / devanagari causative",   "इंसान से बात कराओ",                              "want_human"),
    ("want_human / hinglish-mixed",         "sir please real agent se baat karwa dijiye",    "want_human"),

    ("cancel_appointment / command",        "appointment cancel karo",                       "cancel_appointment"),
    ("cancel_appointment / polite-question","kya aap appointment cancel kar sakte hain",      "cancel_appointment"),
    ("cancel_appointment / polite-ho-form", "kya aap appointment cancel kar sakte ho",        "cancel_appointment"),
    ("cancel_appointment / honorific",      "meri appointment cancel kar dijiye",             "cancel_appointment"),
    ("cancel_appointment / devanagari",     "अपॉइंटमेंट कैंसिल कर सकते हैं",                     "cancel_appointment"),

    ("reschedule_appointment / command",       "meri appointment reschedule karo",            "reschedule_appointment"),
    ("reschedule_appointment / polite-question","meri date reschedule kar sakte hain",         "reschedule_appointment"),
    ("reschedule_appointment / need-to",       "date change karni hai",                        "reschedule_appointment"),
    ("reschedule_appointment / bare-imperative","date reschedule karo",                        "reschedule_appointment"),
    ("reschedule_appointment / honorific",     "meri date reschedule kijiye",                  "reschedule_appointment"),

    ("ask_pickup_logistics / command",        "purana furniture kaun le jaega",               "ask_pickup_logistics"),
    ("ask_pickup_logistics / polite-question","purana furniture khud le ja sakte hain",        "ask_pickup_logistics"),
    ("ask_pickup_logistics / polite-ho-form", "purana furniture khud le ja sakte ho kya",      "ask_pickup_logistics"),

    ("wa_ok / command",                       "whatsapp par bhej do",                          "wa_ok"),
    ("wa_ok / polite-question",               "whatsapp par bhej sakte hain",                  "wa_ok"),
    ("wa_ok / polite-ho-form",                "kya aap whatsapp par bhej sakte ho",            "wa_ok"),
    ("wa_ok / honorific",                     "whatsapp par bhej dijiye",                      "wa_ok"),
]


# ═══════════════════════════════════════════════════════════════════════════
# Part 2: negation guard must still block the aliased forms -- the alias
# table normalizes surface conjugations, but "mat"/"nahi" immediately before
# the (now-aliased) verb token must still reverse the match, same as it did
# for the literal "karo" form before this change.
# ═══════════════════════════════════════════════════════════════════════════

NEGATION_CASES = [
    ("cancel_appointment negated / karo",     "appointment cancel mat karo",       "cancel_appointment"),
    ("cancel_appointment negated / kar",      "appointment cancel mat kar",        "cancel_appointment"),
    ("cancel_appointment negated / kariye",   "appointment cancel mat kariye",     "cancel_appointment"),
    ("cancel_appointment negated / devanagari","अपॉइंटमेंट कैंसिल मत करो",           "cancel_appointment"),
    ("want_human negated / karwao",           "mujhe insaan se baat mat karwao",   "want_human"),
    ("reschedule negated / kijiye",           "meri date reschedule mat kijiye",   "reschedule_appointment"),
]


# ═══════════════════════════════════════════════════════════════════════════
# Part 3: the two real priority-order bugs found auditing route_objection()
# against every category's keyword list.
# ═══════════════════════════════════════════════════════════════════════════

async def run_priority_order_fixes():
    print("\n--- Part 3: priority-order fixes ---")

    # Bug 1: wa_prefers's own "call nahi" keyword could never fire -- DNC's
    # short-circuit in detect_intents() always wins first. Fixed by removing
    # the dead keyword (not by touching DNC's opt-out detector, which is a
    # compliance-sensitive decision left to a human -- see the removal
    # comment in knowledge_react_abc.py). Verify "call nahi" still correctly
    # resolves to dnc (unchanged, deliberate), and that wa_prefers's
    # remaining keywords are unaffected.
    check_intent("wa_prefers dead-keyword: 'call nahi' still resolves to dnc (unchanged by design)",
                 "call nahi", "dnc")
    check_intent("wa_prefers: 'whatsapp pe hi' still fires (untouched keyword)",
                 "whatsapp pe hi", "wa_prefers")
    check_intent("wa_prefers: 'message me instead' still fires (untouched keyword)",
                 "message me instead", "wa_prefers")

    # Bug 2: personal_question and ask_name both listed "tumhara naam" --
    # personal_question is checked centrally in route_objection() (priority
    # 8), ask_name only in per-state Q&A blocks reached after
    # route_objection() returns None, so the duplicate always resolved to
    # personal_question's generic "I'm an AI assistant" deflection instead of
    # ask_name's actually-responsive "mera naam Priya hai" -- confirmed live
    # in production audit.jsonl: 153 real turns hit exactly this collision.
    check_intent("ask_name/personal_question: bare 'tumhara naam' now resolves to ask_name only",
                 "tumhara naam", "ask_name", forbidden_intents=("personal_question",))
    check_intent("ask_name/personal_question: 'tumhara naam kya hai' resolves to ask_name",
                 "tumhara naam kya hai", "ask_name", forbidden_intents=("personal_question",))
    check_intent("personal_question: bot-identity phrasing still fires correctly",
                 "kaun ho tum, bot ho kya", "personal_question")
    check_intent("personal_question: 'are you a bot' still fires correctly",
                 "are you a bot", "personal_question")

    # End-to-end reply verification for bug 2, at the state that actually
    # answers ask_name (PRESENT_OFFER's qa_keys loop) -- confirms the FIX
    # produces the correct spoken reply, not just the correct intent label.
    s = make_session(campaign="react_a", call_cycle=None, react_state="PRESENT_OFFER")
    await check_reply("ask_name end-to-end: 'tumhara naam' now plays ra_q_name (not the AI deflection)",
                       wr.handle_reactivation_turn, s, "tumhara naam", "ra_q_name")


# ═══════════════════════════════════════════════════════════════════════════
# Part 4: end-to-end reply verification for a sample of the axis cases above
# -- confirms route_objection() actually plays the right key, not just that
# detect_intents() returns the right label.
# ═══════════════════════════════════════════════════════════════════════════

async def run_end_to_end_reply_checks():
    print("\n--- Part 4: end-to-end reply checks (real handler + route_objection) ---")

    e2e_cases = [
        ("callback_later polite-question -> obj_callback_later_generic_ritu",
         "react_a", None, "GREETING", "kya aap mujhe baad mein call kar sakte hain",
         "obj_callback_later_generic_ritu"),
        ("want_human need-to-statement -> obj_want_human_generic_ritu",
         "react_a", None, "PRESENT_OFFER", "mujhe insaan se baat karni hai",
         "obj_want_human_generic_ritu"),
        ("cancel_appointment polite-ho-form -> obj_cancel_appointment_generic_ritu",
         "react_a", None, "APPOINTMENT", "kya aap appointment cancel kar sakte ho",
         "obj_cancel_appointment_generic_ritu"),
        ("reschedule_appointment honorific -> obj_reschedule_appointment_generic_ritu",
         "react_a", None, "APPOINTMENT", "meri date reschedule kijiye",
         "obj_reschedule_appointment_generic_ritu"),
        ("ask_pickup_logistics polite-ho-form -> obj_ask_pickup_logistics_generic_ritu",
         "react_a", None, "PRESENT_OFFER", "purana furniture khud le ja sakte ho kya",
         "obj_ask_pickup_logistics_generic_ritu"),
        ("wa_ok polite-ho-form -> obj_wa_ok_generic_ritu",
         "react_a", None, "PRESENT_OFFER", "kya aap whatsapp par bhej sakte ho",
         "obj_wa_ok_generic_ritu"),
    ]
    for label, campaign, call_cycle, state, transcript, expected_key in e2e_cases:
        s = make_session(campaign=campaign, call_cycle=call_cycle, react_state=state)
        await check_reply(label, wr.handle_reactivation_turn, s, transcript, expected_key)

    # The specific real-world scenario this whole audit started from: a
    # callback_later phrase that ALSO matches appointment_confirm's bare
    # day/time words ("shaam"/evening) must NOT get booked as a showroom
    # visit -- route_objection() must intercept callback_later first.
    s = make_session(campaign="react_a", call_cycle=None, react_state="APPOINTMENT")
    await check_reply("callback_later must win over appointment_confirm co-match (not book a fake visit)",
                       wr.handle_reactivation_turn, s, "shaam ko call karna",
                       "obj_callback_later_generic_ritu")
    if s.appointment_confirmed:
        print("[FAIL] appointment_confirmed was incorrectly set True for a callback request")
        _results.append(False)
    else:
        print("[PASS] appointment_confirmed correctly left False")
        _results.append(True)


# ═══════════════════════════════════════════════════════════════════════════
# Part 5: the keyword.md coverage-widening merge (2026-08-19) added ~865 new
# keyword phrases across every category. This surfaced one real bug: wa_ok's
# generic "kar do"/"de do" keywords shadowed the new reschedule_appointment/
# cancel_appointment phrasings ending the same way, since wa_ok is dispatched
# earlier in route_objection()'s priority chain with no allowlist scoping.
# ═══════════════════════════════════════════════════════════════════════════

async def run_keyword_md_merge_checks():
    print("\n--- Part 5: keyword.md merge -- wa_ok/reschedule/cancel suppression fix ---")

    merge_cases = [
        ("cancel_appointment: 'appointment cancel kar do' no longer shadowed by wa_ok",
         "appointment cancel kar do", "obj_cancel_appointment_generic_ritu"),
        ("cancel_appointment: 'visit cancel kar do' no longer shadowed by wa_ok",
         "visit cancel kar do", "obj_cancel_appointment_generic_ritu"),
        ("reschedule_appointment: 'doosri date de do' no longer shadowed by wa_ok",
         "doosri date de do", "obj_reschedule_appointment_generic_ritu"),
        ("reschedule_appointment: 'koi aur din de do' no longer shadowed by wa_ok",
         "koi aur din de do", "obj_reschedule_appointment_generic_ritu"),
        ("reschedule_appointment: 'shift kar do appointment' no longer shadowed by wa_ok",
         "shift kar do appointment", "obj_reschedule_appointment_generic_ritu"),
    ]
    for label, transcript, expected_key in merge_cases:
        s = make_session(campaign="react_a", call_cycle=None, react_state="APPOINTMENT")
        await check_reply(label, wr.handle_reactivation_turn, s, transcript, expected_key)

    # Sanity: a genuine WhatsApp-only request (no competing appointment
    # intent) must still resolve to wa_ok -- the suppression must be scoped
    # to the reschedule/cancel co-match, not a blanket wa_ok regression.
    s = make_session(campaign="react_a", call_cycle=None, react_state="PRESENT_OFFER")
    await check_reply("wa_ok still fires normally with no competing intent",
                       wr.handle_reactivation_turn, s, "haan whatsapp pe bhej do",
                       "obj_wa_ok_generic_ritu")


# ═══════════════════════════════════════════════════════════════════════════
# Part 6: LLM-fallback coverage extension (2026-08-19) -- call2's GREETING/
# DATE_ASK and call3's GREETING/DECISION_DATE previously had NO fallback at
# all (react_a/b/c and call2's WA_CHECK already had it). Verifies the
# fallback now fires for genuinely unmatched turns AND for recognized-but-
# unanswerable Q&A intents (ask_location etc, which these 4 states have no
# qa_keys loop for), while still NOT firing on bare acknowledgments that
# merely co-occur with "positive" -- that would waste real LLM latency on
# something that was never a question.
# ═══════════════════════════════════════════════════════════════════════════

async def _fake_llm_fallback_reply(t, call_uuid, facts=None):
    return "MOCKED_LLM_ANSWER"


async def run_llm_fallback_coverage_checks():
    print("\n--- Part 6: LLM-fallback coverage extension (call2/call3) ---")

    # fresh_cta was the one flow with ZERO LLM-fallback coverage at all.
    # Verified separately (not via the generic cases list below) because it
    # needs its own dedicated facts block (_FRESH_LLM_FACTS, not
    # _REACT_LLM_FACTS -- different campaign, no exchange-offer framing
    # established for this funnel) -- this checks BOTH that the fallback
    # fires AND that it's using the correct, campaign-appropriate facts.
    captured = {}

    async def _fake_llm_fallback_reply_capturing(t, call_uuid, facts=None):
        captured["facts"] = facts
        return "FRESH_CTA_MOCKED_ANSWER"

    recorder = Recorder()
    async with patched_wr(recorder, llm_reply=_fake_llm_fallback_reply_capturing):
        s = make_session(campaign="fresh_cta", call_cycle=None, react_state="APPOINTMENT", fresh_product="sofa")
        await wr.handle_fresh_cta_turn(s, "sofa ki delivery kitne din mein hogi", "test-call-uuid")
    ok = ("FRESH_CTA_MOCKED_ANSWER" in recorder.played
          and captured.get("facts") is wr._FRESH_LLM_FACTS)
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {'fresh_cta: unanswered question tries fallback with _FRESH_LLM_FACTS (not react FACTS)':<85} played={recorder.played!r}")
    _results.append(ok)

    cases = [
        ("call3 GREETING: genuinely unmatched turn now tries the fallback",
         wr.handle_call3_turn, dict(campaign="react_a", call_cycle="3", c3_state="GREETING"),
         "aap mujhe apni company ka pura profile bata sakte ho"),
        ("call3 DECISION_DATE: genuinely unmatched turn now tries the fallback",
         wr.handle_call3_turn, dict(campaign="react_a", call_cycle="3", c3_state="DECISION_DATE"),
         "aap mujhe apni company ka pura profile bata sakte ho"),
        ("call2 GREETING: genuinely unmatched turn now tries the fallback",
         wr.handle_call2_turn, dict(campaign="react_a", call_cycle="2", c2_state="GREETING"),
         "aap mujhe apni company ka pura profile bata sakte ho"),
        ("call2 DATE_ASK: genuinely unmatched turn now tries the fallback",
         wr.handle_call2_turn, dict(campaign="react_a", call_cycle="2", c2_state="DATE_ASK"),
         "aap mujhe apni company ka pura profile bata sakte ho"),
        ("call2 DATE_ASK: recognized-but-unanswerable ask_location (co-matched with positive) tries the fallback",
         wr.handle_call2_turn, dict(campaign="react_a", call_cycle="2", c2_state="DATE_ASK"),
         "showroom kahan hai bhai batao zara"),
        ("call3 GREETING: recognized ask_price_range tries the fallback",
         wr.handle_call3_turn, dict(campaign="react_a", call_cycle="3", c3_state="GREETING"),
         "sofa kitne ka hai"),
    ]
    for label, coro_fn, sess_kwargs, transcript in cases:
        recorder = Recorder()
        async with patched_wr(recorder, llm_reply=_fake_llm_fallback_reply):
            s = make_session(**sess_kwargs)
            await coro_fn(s, transcript, "test-call-uuid")
        ok = "MOCKED_LLM_ANSWER" in recorder.played
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {label:<85} played={recorder.played!r}")
        _results.append(ok)

    # Negative case: a bare acknowledgment ("haan theek hai", intents=['positive']
    # only) must NOT trigger the fallback -- confirmed this was a real bug found
    # while building the fix above (a naive "not intents" widening would have
    # fired the slow LLM path on every bare "yes/ok" reply too).
    recorder = Recorder()
    async with patched_wr(recorder, llm_reply=_fake_llm_fallback_reply):
        s = make_session(campaign="react_a", call_cycle="2", c2_state="DATE_ASK")
        await wr.handle_call2_turn(s, "haan theek hai", "test-call-uuid")
    ok = "MOCKED_LLM_ANSWER" not in recorder.played
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {'bare acknowledgment must NOT trigger the LLM fallback':<85} played={recorder.played!r}")
    _results.append(ok)


# ═══════════════════════════════════════════════════════════════════════════
# Part 7: real test-call findings (2026-08-19) -- customer said "aap mujhe
# thodi der mein call karna, abhi busy hoon" (call me in a while, I'm busy
# right now). Two separate bugs in one turn:
#   1. "thodi der mein call karna" ("mein" = in) didn't match callback_later
#      (only "thodi der baad call karo", "baad" = after, was covered) --
#      only "busy" matched, and GREETING's busy handling pushes forward into
#      the offer pitch rather than actually honoring the callback request.
#   2. GREETING's busy/sochna_hai acknowledgment used two SEPARATE
#      play_key() calls (across react_a/b/c AND call2/call3) instead of one
#      combined play_keys() call -- the exact interrupt/latency bug already
#      fixed at every other two-line branch in this file, just missed here.
#      Confirmed live: the two separate Vobiz Play API round-trips took
#      2.43s and 4.99s back to back, and the second almost certainly
#      interrupted the first before the customer heard it.
# ═══════════════════════════════════════════════════════════════════════════

async def run_greeting_busy_playkeys_and_callback_checks():
    print("\n--- Part 7: real-call findings -- callback_later coverage + GREETING play_keys() ---")

    # Bug 1: the exact real transcript must now resolve to callback_later,
    # not just busy, and must play the callback-time-ask reply.
    recorder = Recorder()
    async with patched_wr(recorder):
        s = make_session(campaign="react_a", call_cycle=None, react_state="GREETING")
        await wr.handle_reactivation_turn(s, "आप मुझे थोड़ी देर में कॉल करना, अभी बिज़ी हूँ।", "test-call-uuid")
    ok = "obj_callback_later_generic_ritu" in recorder.played
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {'real transcript (\"thodi der mein\") now resolves to callback_later, not just busy':<85} played={recorder.played!r}")
    _results.append(ok)

    # Bug 2: GREETING busy/sochna_hai must issue ONE combined play_keys()
    # call, never two separate play_key() calls -- across all 3 flows.
    for label, coro_fn, sess_kwargs in (
        ("react_a GREETING sochna_hai", wr.handle_reactivation_turn,
         dict(campaign="react_a", call_cycle=None, react_state="GREETING")),
        ("call2 GREETING sochna_hai", wr.handle_call2_turn,
         dict(campaign="react_a", call_cycle="2", c2_state="GREETING")),
        ("call3 GREETING sochna_hai", wr.handle_call3_turn,
         dict(campaign="react_a", call_cycle="3", c3_state="GREETING")),
    ):
        recorder = Recorder()
        async with patched_wr(recorder):
            s = make_session(**sess_kwargs)
            await coro_fn(s, "sochna hai abhi", "test-call-uuid")
        combined_calls = [c for c in recorder.calls if c[0] == "play_keys" and len(c[1]) == 2]
        separate_calls = [c for c in recorder.calls if c[0] == "play_key"]
        ok = bool(combined_calls) and not separate_calls
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {label + ': one combined play_keys() call, not two separate play_key() calls':<85} calls={recorder.calls!r}")
        _results.append(ok)


async def main():
    print("--- Part 1: verb-form-alias axis coverage ---")
    for label, transcript, expected in INTENT_AXIS_CASES:
        check_intent(label, transcript, expected)

    print("\n--- Part 2: negation guard still holds under aliased forms ---")
    for label, transcript, forbidden in NEGATION_CASES:
        intents = detect_intents(transcript)
        ok = forbidden not in intents
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {label:<50} intents={intents!r} (must NOT contain {forbidden!r})")
        _results.append(ok)

    await run_priority_order_fixes()
    await run_end_to_end_reply_checks()
    await run_keyword_md_merge_checks()
    await run_llm_fallback_coverage_checks()
    await run_greeting_busy_playkeys_and_callback_checks()

    passed = sum(_results)
    total = len(_results)
    print(f"\n{'='*60}\n{passed}/{total} passed\n{'='*60}")
    return passed == total


if __name__ == "__main__":
    ok = asyncio.run(main())
    raise SystemExit(0 if ok else 1)
