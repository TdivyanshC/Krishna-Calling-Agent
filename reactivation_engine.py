"""
reactivation_engine.py — Reactivation campaign state machine.

Call flow per customer turn:
    respond() in webhook.py  →  handle_reactivation_turn(session, transcript)
                             ←  True  (keep call alive)
                             ←  False (trigger hangup)

All audio is played inline via play_react(), which blocks until the clip
finishes so multi-clip turns play in sequence without overlap.

State path (happy path):
    GREETING → THANK_CUSTOMER → PRESENT_OFFER → WHATSAPP_CTA → CLOSE
"""

import asyncio
import logging
import os

import httpx

from knowledge_reactivation import REACTIVATION_INTENTS, REACTIVATION_SCRIPT
from tts_engine import get_speech

logger = logging.getLogger(__name__)

_VOBIZ_ID  = os.getenv("VOBIZ_AUTH_ID", "MA_P0E0RLUU")
_VOBIZ_TOK = os.getenv("VOBIZ_AUTH_TOKEN", "")
_N8N_URL   = os.getenv("N8N_WA_WEBHOOK_URL", "")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def detect_intents(transcript: str) -> list[str]:
    """Return matched intent keys (all that match, ordered by dict insertion)."""
    t = transcript.lower().strip()
    return [
        intent
        for intent, keywords in REACTIVATION_INTENTS.items()
        if keywords and any(kw.lower() in t for kw in keywords)
    ]


async def play_react(session, key: str) -> None:
    """
    Look up script text for key, get TTS from cache or Sarvam, play via Vobiz.
    Blocks until audio finishes so sequential plays don't overlap.
    key is the short slug (e.g. "greet_main"), NOT the full cache key.
    """
    text = REACTIVATION_SCRIPT.get(key)
    if not text:
        logger.error(f"[{session.call_uuid}] Missing reactivation key: {key}")
        return

    static_key = f"react_{key}"
    wav, url, was_cached = await get_speech(text, "hi", static_key)

    if not url:
        logger.error(f"[{session.call_uuid}] TTS failed for react_{key}")
        return

    logger.info(f"[{session.call_uuid}] React [{static_key}] cached={was_cached}")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.vobiz.ai/api/v1/Account/{_VOBIZ_ID}/Call/{session.call_uuid}/Play/",
                headers={
                    "X-Auth-ID":    _VOBIZ_ID,
                    "X-Auth-Token": _VOBIZ_TOK,
                    "Content-Type": "application/json",
                },
                json={"urls": [url], "legs": "aleg", "mix": False},
            )
        logger.info(f"[{session.call_uuid}] Vobiz play → {r.status_code}")
    except Exception as e:
        logger.error(f"[{session.call_uuid}] Vobiz play error: {e}")
        return

    dur = session.priya_starts_speaking(wav) if wav else 2.5
    await asyncio.sleep(dur + 0.2)
    session.priya_stops_speaking()


async def fire_whatsapp(session) -> None:
    """POST to n8n to trigger WhatsApp message. Fires at most once per call."""
    if getattr(session, "wa_sent", False):
        return
    session.wa_sent = True

    if not _N8N_URL:
        logger.warning(f"[{session.call_uuid}] N8N_WA_WEBHOOK_URL not set — WA not sent")
        return

    phone = getattr(session, "customer_phone", "").replace("+", "")
    payload = {
        "phone":    phone,
        "name":     getattr(session, "customer_name", "") or "Customer",
        "offer":    "exchange offer 25+25%",
        "campaign": "reactivation_jun2026",
    }
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.post(_N8N_URL, json=payload)
        logger.info(f"[{session.call_uuid}] WA trigger → {r.status_code} | phone={phone}")
    except Exception as e:
        logger.error(f"[{session.call_uuid}] WA trigger failed: {e}")


# ─── State machine ─────────────────────────────────────────────────────────────

async def handle_reactivation_turn(session, transcript: str) -> bool:
    """
    Process one customer turn for a reactivation call.
    Returns True to keep the call alive, False to trigger hangup.

    Initialises state attributes on first call if missing.
    """
    # Initialise per-call state if this is the first turn
    if not hasattr(session, "react_state"):
        session.react_state   = "GREETING"
        session.silence_count = 0
        session.wa_sent       = False
        session.dnc           = False

    t      = transcript.strip()
    state  = session.react_state
    intents = detect_intents(t) if t else []

    logger.info(
        f"[{session.call_uuid}] React [{state}] "
        f"transcript='{t[:60]}' intents={intents}"
    )

    # ── Silence / zombie guard ──────────────────────────────────────────────────
    if not t:
        session.silence_count += 1
        logger.info(f"[{session.call_uuid}] Silence #{session.silence_count}")
        if session.silence_count >= 3:
            await play_react(session, "obj_zombie")
            await fire_whatsapp(session)
            return False
        return True

    session.silence_count = 0

    # ── DNC — always highest priority ──────────────────────────────────────────
    if "dnc" in intents:
        session.dnc = True
        await play_react(session, "dnc_close")
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # GREETING — customer heard the opening question, now responding
    # ══════════════════════════════════════════════════════════════════════════
    if state == "GREETING":
        if "confusion_who" in intents:
            await play_react(session, "greet_confusion")
            session.react_state = "THANK_CUSTOMER"
            return True

        if "privacy_concern" in intents:
            await play_react(session, "greet_privacy")
            session.react_state = "THANK_CUSTOMER"
            return True

        if "not_interested" in intents:
            # Hostile on first turn — send WA and exit gracefully
            await play_react(session, "greet_hostile")
            await fire_whatsapp(session)
            return False

        # Any positive, neutral, or unknown → advance
        session.react_state = "THANK_CUSTOMER"
        await play_react(session, "thank_main")
        session.react_state = "PRESENT_OFFER"
        await play_react(session, "offer_main")
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # THANK_CUSTOMER — separate state so customer can interrupt pleasantries
    # ══════════════════════════════════════════════════════════════════════════
    if state == "THANK_CUSTOMER":
        if "skip_pleasantries" in intents:
            await play_react(session, "thank_skip")

        session.react_state = "PRESENT_OFFER"
        await play_react(session, "offer_main")
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # PRESENT_OFFER — handle all offer questions/objections
    # ══════════════════════════════════════════════════════════════════════════
    if state == "PRESENT_OFFER":
        if "offer_clarify" in intents:
            await play_react(session, "offer_explain_simple")
            return True  # re-enter same state on next turn

        if "offer_maths_challenge" in intents:
            # Smart customer who caught the maths — acknowledge, pivot to WA
            await play_react(session, "offer_explain_maths")
            session.react_state = "WHATSAPP_CTA"
            await play_react(session, "wa_cta_main")
            await fire_whatsapp(session)
            return True

        if "trust_issue" in intents:
            await play_react(session, "offer_trust")
            return True

        if "past_bad_experience" in intents:
            await play_react(session, "offer_past_bad")
            session.react_state = "WHATSAPP_CTA"
            await play_react(session, "wa_cta_main")
            await fire_whatsapp(session)
            return True

        if "not_needed_now" in intents:
            await play_react(session, "offer_not_needed")
            session.react_state = "WHATSAPP_CTA"
            await play_react(session, "wa_cta_main")
            await fire_whatsapp(session)
            return True

        if "buying_signal" in intents:
            await play_react(session, "offer_urgency")
            session.react_state = "WHATSAPP_CTA"
            await play_react(session, "wa_cta_main")
            await fire_whatsapp(session)
            return True

        # Product-specific: detect which product and play the matching line
        if "product_sofa" in intents:
            await play_react(session, "offer_product_sofa")
            session.react_state = "WHATSAPP_CTA"
            await play_react(session, "wa_cta_main")
            await fire_whatsapp(session)
            return True

        if "product_bed" in intents:
            await play_react(session, "offer_product_bed")
            session.react_state = "WHATSAPP_CTA"
            await play_react(session, "wa_cta_main")
            await fire_whatsapp(session)
            return True

        if "product_wardrobe" in intents:
            await play_react(session, "offer_product_wardrobe")
            session.react_state = "WHATSAPP_CTA"
            await play_react(session, "wa_cta_main")
            await fire_whatsapp(session)
            return True

        if "expensive" in intents:
            await play_react(session, "obj_too_expensive")
            session.react_state = "WHATSAPP_CTA"
            await play_react(session, "wa_cta_main")
            await fire_whatsapp(session)
            return True

        if "online_cheaper" in intents:
            await play_react(session, "obj_online_cheaper")
            session.react_state = "WHATSAPP_CTA"
            await play_react(session, "wa_cta_main")
            await fire_whatsapp(session)
            return True

        # Default: any positive/neutral/unmatched → advance to CTA
        session.react_state = "WHATSAPP_CTA"
        await play_react(session, "wa_cta_main")
        await fire_whatsapp(session)
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # WHATSAPP_CTA — customer heard "sending you WhatsApp details"
    # ══════════════════════════════════════════════════════════════════════════
    if state == "WHATSAPP_CTA":
        if "wa_prefers" in intents:
            await play_react(session, "wa_cta_prefers_wa")
            session.react_state = "CLOSE"
            await play_react(session, "close_warm")
            return False

        if "wa_diff_number" in intents:
            await play_react(session, "wa_cta_diff_number")
            # Stay in CTA; next turn will come back here and likely ACK then close
            return True

        if "wa_no_whatsapp" in intents:
            await play_react(session, "wa_cta_no_whatsapp")
            session.react_state = "CLOSE"
            # Don't auto-hangup — let them respond about showroom / callback
            return True

        if "busy" in intents or "sochna_hai" in intents:
            await play_react(session, "obj_busy")
            session.react_state = "CLOSE"
            await play_react(session, "close_main")
            return False

        if "not_interested" in intents:
            await play_react(session, "obj_not_interested")
            session.react_state = "CLOSE"
            return False

        if "escalate" in intents:
            await play_react(session, "obj_escalate")
            session.react_state = "CLOSE"
            await play_react(session, "close_main")
            return False

        if "personal_question" in intents:
            await play_react(session, "obj_identity")
            return True  # stay in CTA, answer then come back

        if "expensive" in intents:
            await play_react(session, "obj_too_expensive")
            session.react_state = "CLOSE"
            await play_react(session, "close_main")
            return False

        # Any ACK / positive → close warmly
        session.react_state = "CLOSE"
        await play_react(session, "close_main")
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # CLOSE — catch-all for any stray turns after close audio played
    # ══════════════════════════════════════════════════════════════════════════
    if state == "CLOSE":
        return False

    # Unknown state — safe exit
    logger.warning(f"[{session.call_uuid}] Unknown react_state={state!r}")
    return False
