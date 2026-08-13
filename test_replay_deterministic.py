# -*- coding: utf-8 -*-
"""
test_replay_deterministic.py — deterministic verification of 4 real call-flow
paths through the REAL websocket handler (webhook.ws_handler), instead of
relying on someone speaking a script live into a test call.

Audio for all 4 cases is synthetic (a sine-wave "speech" burst / near-silence,
8kHz mu-law, 20ms frames matching Vobiz's real media-frame cadence) — NOT
recorded human speech, since none exists locally (recordings/ is empty) and
generating real TTS speech would require a live, paid Sarvam call for a
one-off test fixture. This is enough for case (a), which only depends on
VAD/RMS timing, not transcript content. For cases (b)-(d), the "utterance"
each scenario is actually testing is the STT TRANSCRIPT text (config'd below
verbatim as the task specified), fed back via a mocked Sarvam response —
audio content past the VAD boundary doesn't matter for those, only that a
speech segment closes out and the exact text reaches detect_intents()/the
real state-machine code unmodified.

Mocked (network-boundary only, per the task's instruction to mock
Vobiz/Sarvam HTTP): webhook.py's and webhook_reactivation.py's own `httpx`
name (Play/hangup/STT calls) and webhook_reactivation.fire_whatsapp (so no
real WhatsApp gets sent to test numbers). supabase_calling.py's `httpx` is
DELIBERATELY left untouched — case (d)'s assertion IS the real
mark_dnc_immediate() Supabase write landing on the seeded
+918799712556 outbound_leads row.

Everything else — CallSession.ingest()'s VAD/barge-in framing, transcribe(),
detect_intents(), route_objection(), _handle_reactivation_turn_impl()'s full
state machine, play_key()'s cache resolution — runs unmodified through the
real @app.websocket("/ws/{call_uuid}") handler via FastAPI's TestClient.

Usage: python3 test_replay_deterministic.py
"""
import audioop
import math
import struct
import time
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import webhook
import webhook_reactivation as wr

# ─────────────────────────────────────────────────────────────────────────
# Synthetic audio — 8kHz mu-law, 20ms/frame (160 samples), matching
# SILENCE_THRESHOLD/MIN_SPEECH_FRAMES/TRAILING_SILENCE/BARGE_IN_FRAMES in
# webhook.py, which all count in units of "one ingest() call".
# ─────────────────────────────────────────────────────────────────────────
FRAME_SAMPLES = 160


def _pcm_frame(amplitude: int, freq: float = 300.0) -> bytes:
    samples = [int(amplitude * math.sin(2 * math.pi * freq * n / 8000)) for n in range(FRAME_SAMPLES)]
    return struct.pack(f"<{FRAME_SAMPLES}h", *samples)


def speech_frame() -> bytes:
    return audioop.lin2ulaw(_pcm_frame(9000), 2)


def silence_frame() -> bytes:
    return audioop.lin2ulaw(_pcm_frame(0), 2)


# ─────────────────────────────────────────────────────────────────────────
# Fakes for the Vobiz/Sarvam HTTP boundary
# ─────────────────────────────────────────────────────────────────────────
_CURRENT_TRANSCRIPT = {"text": ""}


class FakeResponse:
    def __init__(self, status_code=202, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json


class FakeAsyncClient:
    is_closed = False

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, *a, **kw):
        if "speech-to-text" in url:
            return FakeResponse(200, {"transcript": _CURRENT_TRANSCRIPT["text"]})
        if "text-to-speech" in url:
            return FakeResponse(200, {"audios": []})
        return FakeResponse(202, {})

    async def delete(self, url, *a, **kw):
        return FakeResponse(200, {})

    async def patch(self, url, *a, **kw):
        return FakeResponse(200, {})

    async def get(self, url, *a, **kw):
        return FakeResponse(200, [])


class _FakeHttpxNS:
    """Swaps only webhook.py's/webhook_reactivation.py's own `httpx` name —
    supabase_calling.py's `httpx` (the actual module object) is untouched, so
    its real Supabase writes still go through for real."""
    AsyncClient = FakeAsyncClient
    import httpx as _real
    ConnectError = _real.ConnectError
    ReadError = _real.ReadError
    RemoteProtocolError = _real.RemoteProtocolError
    TimeoutException = _real.TimeoutException


def _install_mocks():
    webhook.httpx = _FakeHttpxNS
    wr.httpx = _FakeHttpxNS
    webhook.stop_audio = AsyncMock()
    async def _no_hangup_if_silent(*a, **kw):
        return None
    webhook._hangup_if_silent = _no_hangup_if_silent
    wr.fire_whatsapp = AsyncMock(return_value=True)


client = TestClient(webhook.app)


def _drive_call(call_uuid: str, campaign: str, phone: str, react_state: str | None,
                 frames: list[bytes], transcript: str, settle_s: float = 3.0):
    """Opens the real /ws/{call_uuid}, primes session state, feeds frames
    through the real ingest()/respond() path, returns the live session."""
    import base64, json as _json
    _CURRENT_TRANSCRIPT["text"] = transcript
    with client.websocket_connect(f"/ws/{call_uuid}") as ws:
        ws.send_json({"event": "start", "start": {"streamId": "s1"}})
        time.sleep(0.05)
        session = webhook.sessions[call_uuid]
        session.campaign = campaign
        session.customer_phone = phone
        if react_state is not None:
            session.react_state = react_state
            session.wa_sent = False
            session.dnc = False
            session.silence_count = 0

        for frame in frames:
            ws.send_json({"event": "media", "media": {"payload": base64.b64encode(frame).decode()}})

        deadline = time.time() + settle_s
        while time.time() < deadline:
            time.sleep(0.05)
        ws.send_json({"event": "stop"})
    return session


RESULTS = []


def _check(name: str, cond: bool, detail: str = ""):
    RESULTS.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# ─────────────────────────────────────────────────────────────────────────
# (a) speech injected mid-clip → stop_audio() barge-in
# ─────────────────────────────────────────────────────────────────────────
def test_barge_in():
    call_uuid = "test-replay-bargein-0001"
    with client.websocket_connect(f"/ws/{call_uuid}") as ws:
        import base64
        ws.send_json({"event": "start", "start": {"streamId": "s1"}})
        time.sleep(0.05)
        session = webhook.sessions[call_uuid]
        session.campaign = "react_a"
        # Simulate "3s into a long clip": Priya is already mid-reply.
        session.is_priya_speaking = True
        session.barge_frames = 0

        # A few quiet frames first (mid-clip silence), then real speech —
        # BARGE_IN_FRAMES (10) consecutive speech frames required to fire.
        for _ in range(5):
            ws.send_json({"event": "media", "media": {"payload": base64.b64encode(silence_frame()).decode()}})
        for _ in range(webhook.BARGE_IN_FRAMES + 2):
            ws.send_json({"event": "media", "media": {"payload": base64.b64encode(speech_frame()).decode()}})

        deadline = time.time() + 1.5
        while time.time() < deadline:
            time.sleep(0.05)
        ws.send_json({"event": "stop"})

    _check(
        "(a) barge-in → stop_audio() called",
        webhook.stop_audio.await_count >= 1,
        f"stop_audio await_count={webhook.stop_audio.await_count}, "
        f"is_priya_speaking now={session.is_priya_speaking}",
    )


# ─────────────────────────────────────────────────────────────────────────
# (b) "abhi budget nahi hai" → objection route (expensive)
# ─────────────────────────────────────────────────────────────────────────
def test_objection_route():
    frames = [speech_frame()] * 15 + [silence_frame()] * (webhook.TRAILING_SILENCE + 2)
    session = _drive_call(
        "test-replay-objection-0001", "react_a", "+910000000001", "PRESENT_OFFER",
        frames, "abhi budget nahi hai",
    )
    _check(
        "(b) objection → 'expensive' intent detected + routed",
        "expensive" in getattr(session, "react_intents_seen", set()) and session.react_state == "WHATSAPP_CTA",
        f"react_intents_seen={getattr(session, 'react_intents_seen', None)}, react_state={session.react_state}",
    )


# ─────────────────────────────────────────────────────────────────────────
# (c) "Sunday aa jaunga" → date captured
# ─────────────────────────────────────────────────────────────────────────
def test_date_capture():
    frames = [speech_frame()] * 15 + [silence_frame()] * (webhook.TRAILING_SILENCE + 2)
    session = _drive_call(
        "test-replay-date-0001", "react_a", "+910000000002", "APPOINTMENT",
        frames, "Sunday aa jaunga",
    )
    _check(
        "(c) date capture → appointment_confirmed + visit_date_raw_text",
        getattr(session, "appointment_confirmed", False) and getattr(session, "visit_date_raw_text", "") == "Sunday aa jaunga",
        f"appointment_confirmed={getattr(session, 'appointment_confirmed', None)}, "
        f"visit_date_raw_text={getattr(session, 'visit_date_raw_text', None)!r} "
        f"(note: real code stores this on session.visit_date_raw_text, NOT session.slots — "
        f"session.slots is a separate dict used only by the fresh-lead funnel)",
    )


# ─────────────────────────────────────────────────────────────────────────
# (d) "mujhe call mat karna" → dnc=true written to outbound_leads (REAL write)
# ─────────────────────────────────────────────────────────────────────────
def test_dnc_write():
    import os, httpx as real_httpx

    phone = "+918799712556"  # the seeded lead row from item 4
    frames = [speech_frame()] * 15 + [silence_frame()] * (webhook.TRAILING_SILENCE + 2)
    session = _drive_call(
        "test-replay-dnc-0001", "react_a", phone, "PRESENT_OFFER",
        frames, "mujhe call mat karna",
    )

    # Give the fire-and-forget mark_dnc_immediate() task (real Supabase PATCH,
    # NOT mocked) a moment to land, then verify for real.
    time.sleep(1.5)
    env = {}
    for line in open("/home/voiceagent/voice-ai/.env"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    r = real_httpx.get(
        f"{env['SUPABASE_URL']}/rest/v1/outbound_leads?phone=eq.{phone.replace('+', '%2B')}&select=phone,status,dnc",
        headers={"apikey": env["SUPABASE_SERVICE_KEY"], "Authorization": f"Bearer {env['SUPABASE_SERVICE_KEY']}"},
        timeout=15,
    )
    rows = r.json()
    ok = bool(rows) and rows[0].get("dnc") is True
    _check(
        "(d) dnc intent → real outbound_leads.dnc=true write",
        "dnc" in getattr(session, "react_intents_seen", set()) and session.dnc is True and ok,
        f"session.dnc={getattr(session, 'dnc', None)}, session.react_intents_seen={getattr(session, 'react_intents_seen', None)}, "
        f"outbound_leads row={rows}",
    )


if __name__ == "__main__":
    _install_mocks()
    test_barge_in()
    test_objection_route()
    test_date_capture()
    test_dnc_write()

    print("\n=== SUMMARY ===")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    print(f"\n{passed}/{len(RESULTS)} passed")
