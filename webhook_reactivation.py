"""
webhook_reactivation.py
Reactivation campaign state machine for Priya.

Self-contained — builds its own play_fn using call_uuid and Vobiz env vars,
matching how webhook.py plays audio (serve from static dir + Vobiz Play API).
"""

import asyncio
import logging
import os

import httpx

from knowledge_reactivation import REACTIVATION_INTENTS, REACTIVATION_SCRIPT

logger = logging.getLogger(__name__)

VOBIZ_ACCOUNT  = os.getenv("VOBIZ_ACCOUNT_SID", "MA_P0E0RLUU")
VOBIZ_AUTH_ID  = os.getenv("VOBIZ_AUTH_ID", "")
VOBIZ_AUTH_TOK = os.getenv("VOBIZ_AUTH_TOKEN", "")
BASE_URL        = os.getenv("BASE_URL", "https://voice.thesocialhood.in")
# /audio mounts to tts-cache/, so tts-cache/static/x.wav → /audio/static/x.wav
STATIC_DIR      = "/home/voiceagent/voice-ai/tts-cache/static"

# Persistent HTTP client — avoids SSL handshake overhead on every play call
_http_client: httpx.AsyncClient | None = None

async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=8)
    return _http_client
N8N_WA_URL      = os.getenv(
    "N8N_WA_WEBHOOK_URL",
    "https://n8n-production-aed7.up.railway.app/webhook/voice-call-complete",
)


# ── Audio helpers ─────────────────────────────────────────────────────────────

def _static_wav_path(key: str) -> str:
    return os.path.join(STATIC_DIR, f"{key}_hi.wav")


def _static_url(key: str) -> str | None:
    path = _static_wav_path(key)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return f"{BASE_URL}/audio/static/{key}_hi.wav"
    return None


async def _vobiz_play(call_uuid: str, audio_url: str) -> bool:
    """POST to Vobiz Play API. Returns True on 202."""
    url = (
        f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}"
        f"/Call/{call_uuid}/Play/"
    )
    payload = {"urls": [audio_url], "legs": "aleg", "mix": False}
    hdrs = {"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK}
    try:
        client = await _get_http_client()
        # Use short timeout — don't wait for Vobiz to fully process
        r = await asyncio.wait_for(client.post(url, json=payload, headers=hdrs), timeout=1.5)
        ok = r.status_code == 202
        logger.info(f"[{call_uuid}] React play {'OK' if ok else 'FAIL'} {r.status_code} → {audio_url}")
        return ok
    except asyncio.TimeoutError:
        logger.info(f"[{call_uuid}] React play SENT (timeout ok) → {audio_url}")
        return True  # assume it worked — Vobiz queued it
    except Exception as exc:
        logger.error(f"[{call_uuid}] React play error: {exc}")
        _http_client = None
        return False


async def _vobiz_play_nowait(call_uuid: str, audio_url: str):
    """Fire Vobiz Play and don't wait for response — for minimum latency."""
    url = (
        f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}"
        f"/Call/{call_uuid}/Play/"
    )
    payload = {"urls": [audio_url], "legs": "aleg", "mix": False}
    hdrs = {"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK}
    try:
        client = await _get_http_client()
        asyncio.create_task(client.post(url, json=payload, headers=hdrs))
        logger.info(f"[{call_uuid}] React play FIRED (nowait) → {audio_url}")
    except Exception as exc:
        logger.error(f"[{call_uuid}] React play nowait error: {exc}")


async def play_key(call_uuid: str, key: str, session=None, log_transcript: bool = True) -> bool:
    """
    Play a reactivation audio line by cache key.
    Hits static file if pre-generated, falls back to live Sarvam TTS.
    """
    # Log Priya reply to session transcript
    if session is not None and log_transcript:
        if not hasattr(session, "conversation"): session.conversation = []
        text = REACTIVATION_SCRIPT.get(key, key)
        session.conversation.append(("assistant", text))
    url = _static_url(key)
    if url:
        logger.info(f"[{call_uuid}] CACHE HIT → {key}")
        return await _vobiz_play(call_uuid, url)

    # Cache miss — generate on the fly
    logger.warning(f"[{call_uuid}] CACHE MISS → {key} — generating live")
    text = REACTIVATION_SCRIPT.get(key)
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


# ── WhatsApp trigger ──────────────────────────────────────────────────────────

async def fire_whatsapp(session, call_uuid: str) -> bool:
    """POST to n8n WhatsApp webhook. Idempotent — skips if already sent."""
    if getattr(session, "wa_sent", False):
        logger.info(f"[{call_uuid}] WA already sent — skip")
        return True

    session.wa_sent = True
    phone = getattr(session, "customer_phone", "").replace("+", "").strip()
    name  = getattr(session, "customer_name", "") or "Customer"

    payload = {
        "phone":    phone,
        "name":     name,
        "offer":    "25+25% exchange offer",
        "campaign": "reactivation",
    }

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(N8N_WA_URL, json=payload)
        logger.info(f"[{call_uuid}] WA trigger → {r.status_code} phone={phone}")
        return r.status_code < 300
    except Exception as exc:
        logger.error(f"[{call_uuid}] WA trigger failed: {exc}")
        return False


# ── Intent detection ─────────────────────────────────────────────────────────

def detect_intents(transcript: str) -> list[str]:
    t = transcript.lower().strip()
    if not t:
        return []
    # DNC always wins — return immediately
    if any(kw.lower() in t for kw in REACTIVATION_INTENTS.get("dnc", [])):
        return ["dnc"]
    matched = []
    for intent, keywords in REACTIVATION_INTENTS.items():
        if intent == "dnc":
            continue
        if keywords and any(kw.lower() in t for kw in keywords):
            matched.append(intent)
    return matched


# ── Product helper ────────────────────────────────────────────────────────────

_PRODUCT_MAP = [
    ("product_sofa",     "react_offer_product_sofa"),
    ("product_dining",   "react_offer_product_dining"),
    ("product_bed",      "react_offer_product_bed"),
    ("product_wardrobe", "react_offer_product_wardrobe"),
]

def get_product_key(intents: list[str]) -> str | None:
    for intent, key in _PRODUCT_MAP:
        if intent in intents:
            return key
    return None


# ── State machine ─────────────────────────────────────────────────────────────

async def handle_followup_wa_turn(session, transcript: str, call_uuid: str) -> bool:
    """
    Short follow-up call for mid_answered leads.
    Just plays WA reminder, fires WhatsApp, hangs up.
    Only runs once — plays message on first turn then ends.
    """
    if not hasattr(session, "followup_played"):
        session.followup_played = False

    if not session.followup_played:
        session.followup_played = True
        session.turn_count = getattr(session, "turn_count", 0) + 1
        if not hasattr(session, "conversation"): session.conversation = []
        session.conversation.append(("assistant", REACTIVATION_SCRIPT.get("react_followup_wa", "")))
        await play_key(call_uuid, "react_followup_wa", session)
        await fire_whatsapp(session, call_uuid)
        await asyncio.sleep(12)  # wait for audio to finish
        return False  # hang up after message plays
    return False


async def handle_followup_wa_turn(session, transcript: str, call_uuid: str) -> bool:
    if not hasattr(session, "followup_played"):
        session.followup_played = False
    if not session.followup_played:
        session.followup_played = True
        session.turn_count = getattr(session, "turn_count", 0) + 1
        if not hasattr(session, "conversation"): session.conversation = []
        session.conversation.append(("assistant", REACTIVATION_SCRIPT.get("react_followup_wa", "")))
        await play_key(call_uuid, "react_followup_wa", session)
        await fire_whatsapp(session, call_uuid)
        await asyncio.sleep(12)
        return False
    return False


async def handle_reactivation_turn(
    session,
    transcript: str,
    call_uuid: str,
) -> bool:
    """
    Process one STT turn for the reactivation campaign.
    Returns True = keep call alive, False = hangup now.

    Session attributes used:
        react_state      str   — current state (init: GREETING)
        silence_count    int   — consecutive empty transcripts
        wa_sent          bool  — WA already fired for this call
        dnc              bool  — customer requested DNC
        customer_phone   str   — +91XXXXXXXXXX
        customer_name    str
    """
    if not hasattr(session, "react_state"):
        session.react_state   = "GREETING"
        session.silence_count = 0
        session.wa_sent       = False
        session.dnc           = False
    session.turn_count = getattr(session, "turn_count", 0) + 1

    state   = session.react_state
    t       = transcript.strip() if transcript else ""
    intents = detect_intents(t) if t else []

    logger.info(
        f"[{call_uuid}] react state={state} "
        f"transcript='{t[:60]}' intents={intents}"
    )
    # Accumulate all intents seen across turns for scoring at hangup
    if not hasattr(session, "react_intents_seen"): session.react_intents_seen = set()
    session.react_intents_seen.update(intents)

    # ── Silence / ghost call ──────────────────────────────────────────────────
    if not t:
        session.silence_count += 1
        logger.info(f"[{call_uuid}] silence #{session.silence_count}")
        if session.silence_count >= 3:
            await play_key(call_uuid, "react_obj_zombie", session)
            await fire_whatsapp(session, call_uuid)
            return False
        return True

    session.silence_count = 0
    # ── Log customer turn to transcript ──────────────────────────────────────
    if not hasattr(session, "conversation"): session.conversation = []
    session.conversation.append(("user", t))

    # ── DNC — always overrides state ─────────────────────────────────────────
    if "dnc" in intents:
        session.dnc = True
        await play_key(call_uuid, "react_dnc_close", session)
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # S1 — GREETING
    # ══════════════════════════════════════════════════════════════════════════
    if state == "GREETING":
        if "confusion_who" in intents:
            await play_key(call_uuid, "react_greet_confusion", session)
            session.react_state = "PRESENT_OFFER"
            return True
        if "privacy_concern" in intents:
            await play_key(call_uuid, "react_greet_privacy", session)
            session.react_state = "PRESENT_OFFER"
            return True
        if "not_interested" in intents:
            await play_key(call_uuid, "react_greet_hostile", session)
            await fire_whatsapp(session, call_uuid)
            return False
        session.react_state = "PRESENT_OFFER"
        await play_key(call_uuid, "react_offer_main", session)
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # S3 — PRESENT_OFFER
    # ══════════════════════════════════════════════════════════════════════════
    if state == "PRESENT_OFFER":
        if "offer_clarify" in intents:
            await play_key(call_uuid, "react_offer_explain_simple", session)
            return True
        if "offer_maths_challenge" in intents:
            await play_key(call_uuid, "react_offer_explain_maths", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, "react_wa_cta_main", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        if "trust_issue" in intents:
            await play_key(call_uuid, "react_offer_trust", session)
            return True
        if "past_bad_experience" in intents:
            await play_key(call_uuid, "react_offer_past_bad", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, "react_wa_cta_main", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        if "not_needed_now" in intents:
            await play_key(call_uuid, "react_offer_not_needed", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, "react_wa_cta_main", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        if "buying_signal" in intents:
            await play_key(call_uuid, "react_offer_urgency", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, "react_wa_cta_main", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        product_key = get_product_key(intents)
        if product_key:
            await play_key(call_uuid, product_key)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, "react_wa_cta_main", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        if "expensive" in intents:
            await play_key(call_uuid, "react_obj_expensive", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, "react_wa_cta_main", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        if "online_cheaper" in intents:
            await play_key(call_uuid, "react_obj_online", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, "react_wa_cta_main", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        if "not_interested" in intents:
            await play_key(call_uuid, "react_obj_not_interested", session)
            await fire_whatsapp(session, call_uuid)
            return False
        if "busy" in intents:
            await play_key(call_uuid, "react_obj_busy", session)
            session.react_state = "WHATSAPP_CTA"
            await play_key(call_uuid, "react_wa_cta_main", session, log_transcript=False)
            await fire_whatsapp(session, call_uuid)
            return True
        # Default — any response → hook then CTA
        # DO NOT fire WhatsApp here — wait for customer to say yes to CTA
        session.react_state = "WHATSAPP_CTA"
        await play_key(call_uuid, "react_hook_before_cta", session)
        await play_key(call_uuid, "react_wa_cta_main", session, log_transcript=False)
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # S4 — WHATSAPP_CTA
    # ══════════════════════════════════════════════════════════════════════════
    if state == "WHATSAPP_CTA":
        if "wa_prefers" in intents:
            await play_key(call_uuid, "react_wa_cta_prefers_wa", session)
            session.react_state = "CLOSE"
            await play_key(call_uuid, "react_close_warm", session)
            return False
        if "wa_diff_number" in intents:
            await play_key(call_uuid, "react_wa_cta_diff_number", session)
            return True
        if "wa_no_whatsapp" in intents:
            await play_key(call_uuid, "react_wa_cta_no_whatsapp", session)
            session.react_state = "CLOSE"
            await play_key(call_uuid, "react_close_main", session)
            return False
        if "personal_question" in intents:
            await play_key(call_uuid, "react_obj_personal", session)
            return True
        if "escalate" in intents:
            await play_key(call_uuid, "react_obj_escalate", session)
            session.react_state = "CLOSE"
            await play_key(call_uuid, "react_close_main", session)
            return False
        if "trust_issue" in intents:
            await play_key(call_uuid, "react_offer_trust", session)
            return True
        if "not_interested" in intents:
            if not getattr(session, "recovery_tried", False):
                session.recovery_tried = True
                await play_key(call_uuid, "react_obj_recovery", session)
                return True  # give one more chance
            await play_key(call_uuid, "react_obj_not_interested", session)
            return False
        if "busy" in intents or "sochna_hai" in intents:
            await play_key(call_uuid, "react_obj_busy", session)
            session.react_state = "CLOSE"
            await play_key(call_uuid, "react_close_main", session)
            return False
        # Any acknowledgement → conviction close
        session.react_state = "CLOSE"
        await play_key(call_uuid, "react_close_conviction", session)
        await asyncio.sleep(7.0)  # let close audio finish before hangup
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # S5 — CLOSE / DONE
    # ══════════════════════════════════════════════════════════════════════════
    if state in ("CLOSE", "DONE"):
        return False

    logger.warning(f"[{call_uuid}] Unknown react_state: {state}")
    return False
