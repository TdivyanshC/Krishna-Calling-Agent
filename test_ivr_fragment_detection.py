# -*- coding: utf-8 -*-
"""
Regression test for the phonetic-Devanagari IVR/voicemail fragment check
(webhook_reactivation._is_ivr_fragment / _mark_ivr_fragment), wired as an
early check -- before detect_intents() -- into all 4 turn handlers
(handle_fresh_cta_turn, handle_reactivation_turn, handle_call2_turn,
handle_call3_turn).

Grounding: audio-replay analysis of the 95-call production dataset found 13
real calls where STT transcribed a carrier IVR/voicemail message phonetically
into Devanagari script (English audio -> Devanagari text), which the
existing English-only _machine_phrases lists never catch. Turn-duration/VAD
silence pattern was evaluated as an alternative signal and rejected: it did
not separate cleanly from real single-turn calls (see conversation record).
The transcripts below are the real STT output from those 13 calls,
call_uuid-tagged in comments for traceability.

Two things this file must prove:
  1. REGRESSION -- all 13 known real IVR transcripts get flagged (no play_key
     call, should_continue=True, "ivr_fragment_detected" recorded), across
     every handler they're capable of reaching.
  2. FALSE-POSITIVE GUARD -- real customer transcripts (from the same
     dataset's confirmed-real multi-turn calls, plus test_objection_routing's
     existing transcripts) must NOT be flagged -- i.e. normal routing must
     still fire and play_key() must still be called.

Usage:
    python3 test_ivr_fragment_detection.py
"""
import asyncio
import sys

import webhook_reactivation as wr
from test_objection_routing import make_session, patch_io, Recorder


# ─────────────────────────────────────────────────────────────────────────
# 13 known real IVR/voicemail fragments (12 named in the task + 1 more of
# the same "please stay on the line" family found while grounding Step 1,
# call_uuid 8994abe1..., flagged as an out-of-scope addition).
# ─────────────────────────────────────────────────────────────────────────
IVR_CASES = [
    # (call_uuid prefix, campaign/handler, transcript)
    ("5560c111", "react_a", "व्हेन यू हैव फिनिश्ड रिकॉर्डिंग, यू मे हैंग अप।"),
    ("a69afcb8", "react_b", "में हैंग अप।"),
    ("aa9174a5", "react_b", "यू मे हैंग अप।"),
    ("f3623be4", "react_b", "आई एम सॉरी, दिस पर्सन इज नॉट अवेलेबल।"),
    ("f3623be4", "react_b", "इफ यू वुड लाइक टू लीव एन एडिशनल मैसेज प्लीज रिप्लाई आफ्टर।"),
    ("10db1ed7", "react_a", "आई एम सॉरी, दिस पर्सन इज नॉट अवेलेबल।"),
    ("10db1ed7", "react_a", "इफ यू वुड लाइक टू लीव एन एडिशनल मैसेज प्लीज।"),
    ("fb2aa079", "react_a", "फिनिश्ड रिकॉर्डिंग यू मे हैंग अप।"),
    ("6f9ec6b5", "react_b", "वे यू हैव फिनिश्ड रिकॉर्डिंग यू मे हैंग अप।"),
    ("f05ce9df", "react_a", "और यू मे हैंग अप।"),
    ("75ce8795", "react_a", "में हैंग अप।"),
    ("cf581555", "react_a", "फिनिश्ड रिकॉर्डिंग में है।"),
    ("64e44b62", "react_b", "हांग अप।"),
    ("8994abe1", "react_c", "प्लीज स्टे ऑन द लाइन।"),
    ("2cc8c244", "fresh_cta", "द पर्सन यू आर स्पीकिंग विथ हैज़ पुट योर कॉल ऑन होल्ड, प्लीज़ स्टे ऑन द लाइन।"),
    ("2cc8c244", "fresh_cta", "आप जिस व्यक्ति से बात कर रहे हैं उसने आपकी कॉल को होल्ड पर रखा है।"),
]

# Real customer transcripts (from the same 95-call dataset's confirmed-real
# multi-turn calls) that must NOT be flagged as IVR fragments.
REAL_CASES = [
    ("react_a", "हम्म।"),
    ("react_b", "हाँ।"),
    ("react_b", "बहुत बुरा हाल है भैया यहां से जाम है वैसे पर उधर जाम है जाम।"),
    ("react_a", "मुझे कुछ नहीं चाहिए आपके लिए।"),
    ("react_c", "नहीं मैम, मैं इंटरेस्टिव नहीं हूं।"),
    ("react_a", "मैं गुड़गांव में नहीं रहता हूं और।"),
    ("react_b", "ये वेम टूल लेना था तो फर्नीचर का सामान थोड़ा भी काम चल रहा है करके।"),
    ("fresh_cta", "कौन बोल रहे हैं?"),
    ("react_c", "और टॉप कार मॉडल्स ऑफ योर चॉप।"),
]

_HANDLER_BY_CAMPAIGN = {
    "react_a": wr.handle_reactivation_turn,
    "react_b": wr.handle_reactivation_turn,
    "react_c": wr.handle_reactivation_turn,
    "fresh_cta": wr.handle_fresh_cta_turn,
}


async def run_ivr_case(uuid_prefix, campaign, transcript):
    handler = _HANDLER_BY_CAMPAIGN[campaign]
    kwargs = {"campaign": campaign, "call_cycle": None}
    if campaign == "fresh_cta":
        kwargs.update(react_state="APPOINTMENT", fresh_product="")
    s = make_session(**kwargs)

    recorder = Recorder()
    orig_play_key, orig_fire_wa, orig_dnc = wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc
    patch_io(wr, recorder)
    try:
        # Real carrier IVR/voicemail loops repeat the same message across
        # many turns (this is exactly what produced the 370-turn/2731s
        # "Rajni" incident) -- a single fixture transcript only ever
        # exercises one turn, so 3 repeated calls on the SAME session is
        # the minimal way to actually reach ivr_fragment_count>=3 rather
        # than asserting a threshold no single-turn case could ever hit.
        should_continue = True
        for _ in range(3):
            should_continue = await handler(s, transcript, f"test-{uuid_prefix}")
    finally:
        wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc = orig_play_key, orig_fire_wa, orig_dnc

    ok = True
    detail = []
    if recorder.played:
        ok = False
        detail.append(f"expected NO play_key calls, got {recorder.played!r}")
    if not should_continue:
        ok = False
        detail.append(f"expected should_continue=True (stay silent, keep listening), got {should_continue}")
    if "ivr_fragment_detected" not in getattr(s, "intents_fired", set()):
        ok = False
        detail.append("expected 'ivr_fragment_detected' in session.intents_fired")
    if getattr(s, "ivr_fragment_count", 0) < 3:
        ok = False
        detail.append(f"expected ivr_fragment_count>=3 after 3 repeated fragment turns, got {getattr(s, 'ivr_fragment_count', 0)}")

    label = f"[{uuid_prefix}] {campaign:<10} {transcript[:40]!r}"
    print(f"[{'PASS' if ok else 'FAIL'}] {label}  ivr_fragment_count={getattr(s, 'ivr_fragment_count', 0)}")
    for d in detail:
        print(f"       {d}")
    return ok


async def run_real_case(campaign, transcript):
    handler = _HANDLER_BY_CAMPAIGN[campaign]
    kwargs = {"campaign": campaign, "call_cycle": None}
    if campaign == "fresh_cta":
        kwargs.update(react_state="APPOINTMENT", fresh_product="")
    s = make_session(**kwargs)

    recorder = Recorder()
    orig_play_key, orig_fire_wa, orig_dnc = wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc
    patch_io(wr, recorder)
    try:
        await handler(s, transcript, "test-real")
    finally:
        wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc = orig_play_key, orig_fire_wa, orig_dnc

    ok = True
    detail = []
    if not recorder.played:
        ok = False
        detail.append("expected normal routing to play something, got NO play_key calls (false positive)")
    if "ivr_fragment_detected" in getattr(s, "intents_fired", set()):
        ok = False
        detail.append("expected NOT flagged as ivr_fragment_detected (false positive)")
    if getattr(s, "ivr_fragment_count", 0) >= 3:
        ok = False
        detail.append(f"expected ivr_fragment_count<3 (ideally 0) on a real customer transcript, got {getattr(s, 'ivr_fragment_count', 0)}")

    label = f"{campaign:<10} {transcript[:40]!r}"
    print(f"[{'PASS' if ok else 'FAIL'}] {label}  played={recorder.played!r}  ivr_fragment_count={getattr(s, 'ivr_fragment_count', 0)}")
    for d in detail:
        print(f"       {d}")
    return ok


async def main():
    results = []

    print("=== 13 known real IVR/voicemail fragments (must be flagged) ===")
    for uuid_prefix, campaign, transcript in IVR_CASES:
        results.append(await run_ivr_case(uuid_prefix, campaign, transcript))

    # call2/call3 don't have a real IVR example among the 13, but the check
    # is shared code (_is_ivr_fragment is identical for all 4 handlers) --
    # cover them directly with the same real fragment text for completeness.
    for label, handler, campaign, kwargs in (
        ("call2/GREETING", wr.handle_call2_turn, "react_a", {"call_cycle": "2", "c2_state": "GREETING"}),
        ("call3/GREETING", wr.handle_call3_turn, "react_a", {"call_cycle": "3", "c3_state": "GREETING"}),
    ):
        s = make_session(campaign=campaign, **kwargs)
        recorder = Recorder()
        orig_play_key, orig_fire_wa, orig_dnc = wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc
        patch_io(wr, recorder)
        try:
            should_continue = True
            for _ in range(3):
                should_continue = await handler(s, "यू मे हैंग अप।", "test-call2call3")
        finally:
            wr.play_key, wr.fire_whatsapp, wr._fire_immediate_dnc = orig_play_key, orig_fire_wa, orig_dnc
        ok = (not recorder.played) and should_continue and ("ivr_fragment_detected" in s.intents_fired) and (getattr(s, "ivr_fragment_count", 0) >= 3)
        print(f"[{'PASS' if ok else 'FAIL'}] {label} 'यू मे हैंग अप।'  played={recorder.played!r} continue={should_continue} ivr_fragment_count={getattr(s, 'ivr_fragment_count', 0)}")
        results.append(ok)

    print("\n=== False-positive guard: real customer transcripts (must NOT be flagged) ===")
    for campaign, transcript in REAL_CASES:
        results.append(await run_real_case(campaign, transcript))

    total = len(results)
    passed = sum(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
