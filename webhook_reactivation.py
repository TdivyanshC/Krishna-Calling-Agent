"""
webhook_reactivation.py
Reactivation A/B/C campaign state machine for Priya.
Supports campaign_type: react_a, react_b, react_c
"""

import asyncio
import logging
import os
import time

import httpx

from knowledge_react_abc import REACT_ABC_INTENTS, get_script, get_prefix, SHARED_INTENTS

logger = logging.getLogger(__name__)

VOBIZ_ACCOUNT  = os.getenv("VOBIZ_ACCOUNT_SID", "MA_P0E0RLUU")
VOBIZ_AUTH_ID  = os.getenv("VOBIZ_AUTH_ID", "")
VOBIZ_AUTH_TOK = os.getenv("VOBIZ_AUTH_TOKEN", "")
BASE_URL        = os.getenv("BASE_URL", "https://voice.thesocialhood.in")
STATIC_DIR      = "/home/voiceagent/voice-ai/tts-cache/static"
N8N_WA_URL      = os.getenv(
    "N8N_WA_WEBHOOK_URL",
    "https://n8n-production-aed7.up.railway.app/webhook/voice-call-complete",
)

_http_client: httpx.AsyncClient | None = None

async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=8)
    return _http_client


def _static_wav_path(key: str) -> str:
    return os.path.join(STATIC_DIR, f"{key}_hi.wav")

def _static_url(key: str) -> str | None:
    path = _static_wav_path(key)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return f"{BASE_URL}/audio/static/{key}_hi.wav"
    return None

async def _vobiz_play(call_uuid: str, audio_url: str) -> bool:
    url = (
        f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}"
        f"/Call/{call_uuid}/Play/"
    )
    payload = {"urls": [audio_url], "legs": "aleg", "mix": False}
    hdrs = {"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK}
    _t0 = time.time()
    try:
        client = await _get_http_client()
        r = await asyncio.wait_for(client.post(url, json=payload, headers=hdrs), timeout=3.0)
        ok = r.status_code == 202
        logger.info(f"[{call_uuid}] React play {'OK' if ok else 'FAIL'} {r.status_code} | {time.time()-_t0:.2f}s → {audio_url}")
        return ok
    except asyncio.TimeoutError:
        _elapsed = time.time() - _t0
        logger.warning(f"[{call_uuid}] React play TIMEOUT after {_elapsed:.2f}s → {audio_url}")
        return True
    except Exception as exc:
        logger.error(f"[{call_uuid}] React play error: {type(exc).__name__}: {exc}")
        global _http_client
        if isinstance(exc, (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
            logger.warning(f"[{call_uuid}] resetting react http client due to {type(exc).__name__}")
            _http_client = None
        return False

async def play_key(call_uuid: str, key: str, session=None, log_transcript: bool = True) -> bool:
    campaign = getattr(session, "campaign", "react_a") if session else "react_a"
    script   = get_script(campaign)

    if session is not None and log_transcript:
        if not hasattr(session, "conversation"):
            session.conversation = []
        text = script.get(key, key)
        session.conversation.append(("assistant", text))

    url = _static_url(key)
    if url:
        logger.info(f"[{call_uuid}] CACHE HIT → {key}")
        return await _vobiz_play(call_uuid, url)

    logger.warning(f"[{call_uuid}] CACHE MISS → {key} — generating live")
    text = script.get(key)
    if not text:
        logger.error(f"[{call_uuid}] No text for key: {key}")
        return False
    try:
        from tts_engine import get_speech
        _, audio_url, _ = await get_speech(text, lang="hi", static_key=key)
        if audio_url:
            return await _vobiz_play(call_uuid, audio_url)
    except Exception as exc:
        logger.error(f"[{call_uuid}] Live TTS failed for {key}: {exc}")
    return False


async def fire_whatsapp(session, call_uuid: str) -> bool:
    if getattr(session, "wa_sent", False):
        logger.info(f"[{call_uuid}] WA already sent — skip")
        return True
    session.wa_sent = True
    phone    = getattr(session, "customer_phone", "").replace("+", "").strip()
    name     = getattr(session, "customer_name", "") or "Customer"
    campaign = getattr(session, "campaign", "react_a")
    payload  = {"phone": phone, "name": name, "offer": "25+25% exchange offer", "campaign": "reactivation"}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(N8N_WA_URL, json=payload)
        logger.info(f"[{call_uuid}] WA trigger → {r.status_code} phone={phone} campaign={campaign}")
        return r.status_code < 300
    except Exception as exc:
        logger.error(f"[{call_uuid}] WA trigger failed: {exc}")
        return False


def detect_intents(transcript: str) -> list[str]:
    t = transcript.lower().strip()
    if not t:
        return []
    if any(kw.lower() in t for kw in REACT_ABC_INTENTS.get("dnc", [])):
        return ["dnc"]
    matched = []
    for intent, keywords in REACT_ABC_INTENTS.items():
        if intent == "dnc":
            continue
        if keywords and any(kw.lower() in t for kw in keywords):
            matched.append(intent)
    # Also check shared intents (appointment / Q&A)
    for intent, keywords in SHARED_INTENTS.items():
        if keywords and any(kw.lower() in t for kw in keywords):
            matched.append(intent)
    return matched


async def handle_followup_wa_turn(session, transcript: str, call_uuid: str) -> bool:
    if not hasattr(session, "followup_played"):
        session.followup_played = False
    if not session.followup_played:
        session.followup_played = True
        session.turn_count = getattr(session, "turn_count", 0) + 1
        p = get_prefix(getattr(session, "campaign", "react_a"))
        await play_key(call_uuid, f"{p}_wa_cta", session)
        await fire_whatsapp(session, call_uuid)
        await asyncio.sleep(12)
        return False
    return False


async def handle_reactivation_turn(session, transcript: str, call_uuid: str) -> bool:
    if not hasattr(session, "react_state"):
        session.react_state   = "GREETING"
        session.silence_count = 0
        session.wa_sent       = False
        session.dnc           = False

    session.turn_count = getattr(session, "turn_count", 0) + 1
    campaign = getattr(session, "campaign", "react_a")
    p        = get_prefix(campaign)
    state    = session.react_state
    t        = transcript.strip() if transcript else ""
    intents  = detect_intents(t) if t else []

    logger.info(f"[{call_uuid}] react state={state} campaign={campaign} transcript='{t[:60]}' intents={intents}")

    if not hasattr(session, "react_intents_seen"):
        session.react_intents_seen = set()
    session.react_intents_seen.update(intents)

    # ── Silence ───────────────────────────────────────────────────────────────
    if not t:
        session.silence_count += 1
        if session.silence_count >= 3:
            await play_key(call_uuid, f"{p}_obj_busy", session)
            await fire_whatsapp(session, call_uuid)
            return False
        return True

    session.silence_count = 0
    if not hasattr(session, "conversation"):
        session.conversation = []
    session.conversation.append(("user", t))

    # ── Machine/IVR detection — hang up immediately ───────────────────────────
    _machine_phrases = [
        "please stay on the line", "stay on the line", "प्लीज स्टे ऑन द लाइन",
        "your call is being connected", "please hold", "all our representatives",
        "press 1", "press 2", "दबाएं", "के लिए 1", "के लिए 2",
        "voicemail", "leave a message", "not available right now",
        "the number you have dialed", "is not reachable", "switched off",
        "स्विच्ड ऑफ", "नॉट रीचेबल", "उपलब्ध नहीं",
    ]
    if any(phrase.lower() in t.lower() for phrase in _machine_phrases):
        logger.info(f"[{call_uuid}] Machine/IVR detected — hanging up")
        session.machine_detected = True
        return False

    # ── DNC ───────────────────────────────────────────────────────────────────
    if "dnc" in intents:
        session.dnc = True
        await play_key(call_uuid, f"{p}_dnc", session)
        return False

    # ── GREETING ──────────────────────────────────────────────────────────────
    if state == "GREETING":
        if "confusion_who" in intents:
            await play_key(call_uuid, f"{p}_greet_who", session)
            session.react_state = "PRESENT_OFFER"
            asyncio.create_task(fire_whatsapp(session, call_uuid))
            await play_key(call_uuid, f"{p}_offer_main", session)
            return True
        if "repeat" in intents:
            await play_key(call_uuid, f"{p}_greet_repeat", session)
            session.react_state = "PRESENT_OFFER"
            asyncio.create_task(fire_whatsapp(session, call_uuid))
            await play_key(call_uuid, f"{p}_offer_main", session, log_transcript=False)
            return True
        if "privacy_concern" in intents:
            await play_key(call_uuid, f"{p}_greet_privacy", session)
            session.react_state = "PRESENT_OFFER"
            asyncio.create_task(fire_whatsapp(session, call_uuid))
            return True
        if "not_interested" in intents:
            await play_key(call_uuid, f"{p}_greet_hostile", session)
            await fire_whatsapp(session, call_uuid)
            return False
        # Default — fire WA immediately on first response, then present offer
        session.react_state = "PRESENT_OFFER"
        asyncio.create_task(fire_whatsapp(session, call_uuid))
        await play_key(call_uuid, f"{p}_offer_main", session)
        return True

    # ── PRESENT_OFFER ─────────────────────────────────────────────────────────
    if state == "PRESENT_OFFER":
        if "offer_clarify" in intents:
            await play_key(call_uuid, f"{p}_offer_explain", session)
            return True
        if "trust_issue" in intents:
            await play_key(call_uuid, f"{p}_offer_trust", session)
            return True
        if "buying_signal" in intents:
            await play_key(call_uuid, f"{p}_offer_urgency", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, f"{p}_wa_cta", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        if "expensive" in intents:
            await play_key(call_uuid, f"{p}_obj_expensive", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, f"{p}_wa_cta", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        if "online_cheaper" in intents:
            await play_key(call_uuid, f"{p}_obj_online", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, f"{p}_wa_cta", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        if "not_interested" in intents:
            await play_key(call_uuid, f"{p}_obj_not_interested", session)
            await fire_whatsapp(session, call_uuid)
            return False
        if "busy" in intents:
            await play_key(call_uuid, f"{p}_obj_busy", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, f"{p}_wa_cta", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        await play_key(call_uuid, f"{p}_hook_cta", session)
        asyncio.create_task(fire_whatsapp(session, call_uuid))
        session.react_state = "WHATSAPP_CTA"
        return True

    # ── WHATSAPP_CTA ──────────────────────────────────────────────────────────
    if state == "WHATSAPP_CTA":
        if "wa_diff_number" in intents:
            await play_key(call_uuid, f"{p}_wa_cta", session)
            return True
        if "trust_issue" in intents:
            await play_key(call_uuid, f"{p}_offer_trust", session)
            return True
        if "not_interested" in intents:
            if not getattr(session, "recovery_tried", False):
                session.recovery_tried = True
                await play_key(call_uuid, f"{p}_obj_recovery", session)
                return True
            await play_key(call_uuid, f"{p}_obj_not_interested", session)
            return False
        if "busy" in intents or "sochna_hai" in intents:
            await play_key(call_uuid, f"{p}_obj_think", session)
            session.react_state = "CLOSE"
            await play_key(call_uuid, f"{p}_close", session)
            return False
        # Any question about who/location/name/valuation/delivery → answer + move to APPOINTMENT
        qa_keys = {
            "confusion_who": f"{p}_greet_who",
            "ask_location":  f"{p}_q_location",
            "ask_timings":   f"{p}_q_location",
            "ask_name":      f"{p}_q_name",
            "ask_valuation": f"{p}_q_valuation",
            "ask_delivery":  f"{p}_q_valuation",
        }
        for intent_name, plan_key in qa_keys.items():
            if intent_name in intents:
                session.interest_signals = getattr(session, "interest_signals", 0) + 1
                await play_key(call_uuid, plan_key, session)
                session.react_state = "APPOINTMENT"
                await play_key(call_uuid, f"{p}_appointment_ask", session, log_transcript=False)
                await fire_whatsapp(session, call_uuid)
                return True
        # Default: positive engagement → fire WA, move to APPOINTMENT, ask
        await fire_whatsapp(session, call_uuid)
        session.interest_signals = getattr(session, "interest_signals", 0) + 1
        session.react_state = "APPOINTMENT"
        await play_key(call_uuid, f"{p}_appointment_ask", session)
        return True

    # ── APPOINTMENT ───────────────────────────────────────────────────────────
    if state == "APPOINTMENT":
        # Any question still gets answered FIRST, then re-ask for date (before any confirm check)
        qa_keys = {
            "confusion_who": f"{p}_greet_who",
            "ask_location":  f"{p}_q_location",
            "ask_timings":   f"{p}_q_location",
            "ask_name":      f"{p}_q_name",
            "ask_valuation": f"{p}_q_valuation",
            "ask_delivery":  f"{p}_q_valuation",
        }
        for intent_name, plan_key in qa_keys.items():
            if intent_name in intents:
                await play_key(call_uuid, plan_key, session)
                await play_key(call_uuid, f"{p}_appointment_ask", session, log_transcript=False)
                return True
        if "not_interested" in intents or "busy" in intents:
            session.react_state = "CLOSE"
            await play_key(call_uuid, f"{p}_close", session)
            return False
        # Treat as confirmation if a concrete date/day keyword was used,
        # OR if the transcript contains a digit (e.g. "6 august", "15 tareek", "20 july")
        # since we are explicitly in the APPOINTMENT state asking for a date.
        # Plain "haan"/"positive" alone is NOT enough to confirm an appointment.
        _has_digit = any(ch.isdigit() for ch in t)
        _has_day_suffix = "डे" in t and len(t.split()) >= 2
        if "appointment_confirm" in intents or _has_digit or _has_day_suffix:
            # HOT LEAD — appointment confirmed
            session.appointment_confirmed = True
            session.visit_date_raw_text = t
            session.lead_tier_override = "hot"
            session.lead_score_override = 85
            session.react_state = "CLOSE"
            await play_key(call_uuid, f"{p}_appointment_confirmed", session)
            await asyncio.sleep(3.0)
            return False
        # Unclear response — acknowledge + re-ask once with a different line
        if not getattr(session, "appt_reask_tried", False):
            session.appt_reask_tried = True
            await play_key(call_uuid, f"{p}_appointment_reask", session, log_transcript=False)
            return True
        session.react_state = "CLOSE"
        await play_key(call_uuid, f"{p}_close", session)
        return False

    # ── CLOSE ─────────────────────────────────────────────────────────────────
    if state in ("CLOSE", "DONE"):
        return False

    logger.warning(f"[{call_uuid}] Unknown react_state: {state}")
    return False
