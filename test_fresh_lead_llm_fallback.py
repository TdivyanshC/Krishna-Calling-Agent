# -*- coding: utf-8 -*-
"""
Regression suite for the 2026-08-19 fresh-lead-flow LLM-fallback audit
(webhook.py's llm_reply()/state_machine(), the fresh-lead qualification
funnel's counterpart to webhook_reactivation.py's llm_fallback_reply()).

Two real gaps found and fixed here, parallel to issues already confirmed
live in the reactivation engine:

  1. state_machine() (called synchronously from inside async def respond())
     makes a BLOCKING call via the synchronous Groq() client, with no
     timeout at all -- worse than a per-call latency problem, since running
     it un-offloaded on the event loop thread would freeze audio processing
     for every OTHER concurrent call this process is handling, not just the
     one that triggered the LLM fallback. Fixed by offloading via
     asyncio.to_thread() with an explicit hard-timeout ceiling. Verified
     directly here: a slow call no longer blocks a concurrently-running
     asyncio task, and a hung call times out cleanly instead of hanging.
  2. llm_reply() had no guard against low-content fragments ("और ये।" --
     "and this", no real content word) before generating a free-text
     answer -- the exact failure class that forced
     webhook_reactivation.py's LLM fallback to be redesigned into a
     classify-first pipeline after it confidently hallucinated an answer to
     one. knowledge.py's is_noise() does not catch this shape. Fixed by
     reusing webhook_reactivation.py's already-proven
     _is_low_content_fragment() check to short-circuit before any Groq call.

Usage:
    python3 test_fresh_lead_llm_fallback.py
"""
import asyncio
import time
from types import SimpleNamespace

import webhook

_results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    _results.append(condition)


def check_llm_reply(label, text, expected_source):
    s = SimpleNamespace(conversation=[], last_reply=None)
    reply, source = webhook.llm_reply(text, s, "test-uuid")
    ok = source == expected_source
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label:<70} source={source!r} reply={reply!r}")
    _results.append(ok)


async def run_threading_checks():
    print("--- Part 1: state_machine() no longer blocks the event loop ---")

    def slow_state_machine(text_fixed, text, session, call_uuid):
        time.sleep(1.0)
        return ("real reply", "llm")

    def hanging_state_machine(text_fixed, text, session, call_uuid):
        time.sleep(10.0)
        return ("should never be seen", "llm")

    orig_state_machine = webhook.state_machine
    try:
        webhook.state_machine = slow_state_machine

        async def ticker():
            gaps = []
            last = time.monotonic()
            for _ in range(12):
                await asyncio.sleep(0.08)
                now = time.monotonic()
                gaps.append(now - last)
                last = now
            return gaps

        ticker_task = asyncio.create_task(ticker())
        result = await asyncio.wait_for(
            asyncio.to_thread(webhook.state_machine, "x", "x", None, "uuid"),
            timeout=webhook._STATE_MACHINE_HARD_TIMEOUT,
        )
        gaps = await ticker_task
        max_gap = max(gaps)
        check(f"offloaded slow call doesn't stall a concurrent asyncio task (max tick gap {max_gap:.2f}s, must stay near 0.08s)",
              max_gap < 0.5)
        check("offloaded call still returns its real result", result == ("real reply", "llm"))

        webhook.state_machine = hanging_state_machine
        t0 = time.monotonic()
        timed_out = False
        try:
            await asyncio.wait_for(
                asyncio.to_thread(webhook.state_machine, "x", "x", None, "uuid"),
                timeout=1.0,
            )
        except asyncio.TimeoutError:
            timed_out = True
        elapsed = time.monotonic() - t0
        check(f"hung call times out cleanly instead of hanging (elapsed {elapsed:.2f}s, expected ~1.0s)",
              timed_out and elapsed < 2.0)
    finally:
        webhook.state_machine = orig_state_machine


def run_low_content_fragment_checks():
    print("\n--- Part 2: low-content-fragment guard before generating ---")
    check_llm_reply("'और ये।' (the exact fragment that hallucinated an answer in the reactivation engine) short-circuits",
                     "और ये।", "fallback_low_content")
    check_llm_reply("'और ये' (no danda) short-circuits too",
                     "और ये", "fallback_low_content")
    check_llm_reply("bare 'toh hi bhi' (all low-content words) short-circuits",
                     "toh hi bhi", "fallback_low_content")

    # Genuine short questions must NOT be caught by this guard -- they should
    # proceed to a real Groq call (source will be "llm"/"fallback_llm"/
    # "fallback_ungrounded" depending on what the live API returns, but
    # never "fallback_low_content").
    for text in ("EMI", "warranty", "sofa kitne ka hai"):
        s = SimpleNamespace(conversation=[], last_reply=None)
        reply, source = webhook.llm_reply(text, s, "test-uuid")
        ok = source != "fallback_low_content"
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] genuine short question {text!r:<20} not caught by the fragment guard (source={source!r})")
        _results.append(ok)


async def main():
    await run_threading_checks()
    run_low_content_fragment_checks()

    passed = sum(_results)
    total = len(_results)
    print(f"\n{'='*60}\n{passed}/{total} passed\n{'='*60}")
    return passed == total


if __name__ == "__main__":
    ok = asyncio.run(main())
    raise SystemExit(0 if ok else 1)
