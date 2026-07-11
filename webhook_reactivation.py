"""
webhook_reactivation.py
Reactivation A/B/C campaign state machine for Priya.
Supports campaign_type: react_a, react_b, react_c
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import httpx

from knowledge_react_abc import REACT_ABC_INTENTS, get_script, get_prefix, SHARED_INTENTS, CALL2_SCRIPT, CALL3_SCRIPT

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
SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
TENANT_ID            = os.getenv("TENANT_ID", "krishna_furniture")

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
    call_cycle = getattr(session, "call_cycle", None) if session else None
    if call_cycle == "2":
        script = CALL2_SCRIPT
    elif call_cycle == "3":
        script = CALL3_SCRIPT
    else:
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
    ok = False
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(N8N_WA_URL, json=payload)
        logger.info(f"[{call_uuid}] WA trigger → {r.status_code} phone={phone} campaign={campaign}")
        ok = r.status_code < 300
    except Exception as exc:
        logger.error(f"[{call_uuid}] WA trigger failed: {exc}")

    if ok:
        await _mark_wa_sent(session, call_uuid)

    return ok


async def _mark_wa_sent(session, call_uuid: str) -> None:
    """
    Persists wa_sent/wa_sent_at on the outbound_leads row for this call —
    fire_whatsapp() previously only set session.wa_sent in-memory, so the DB
    columns (which already existed in the schema) were never populated.
    Matched by phone + tenant_id, same pattern supabase_calling.py's own
    outbound_leads PATCHes use (see finalize_call()).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    raw_phone = getattr(session, "customer_phone", "")  # outbound_leads.phone keeps the '+' prefix
    if not raw_phone:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/outbound_leads"
                f"?phone=eq.{raw_phone.replace('+', '%2B')}&tenant_id=eq.{TENANT_ID}",
                headers={
                    "apikey":        SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "wa_sent":    True,
                    "wa_sent_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        logger.info(f"[{call_uuid}] outbound_lead → wa_sent=True phone={raw_phone}")
    except Exception as exc:
        logger.error(f"[{call_uuid}] wa_sent persist error: {exc}")


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


async def handle_fresh_cta_turn(session, transcript: str, call_uuid: str) -> bool:
    """
    fresh_cta funnel — no GREETING/OFFER/CTA buildup, enters directly at the
    appointment-ask equivalent. The greeting itself (fresh_greet_{product} /
    fresh_greet_generic) is played by /answer-outbound's initial <Play>,
    before the stream opens — NOT from inside this handler. respond() only
    ever invokes a turn handler in reaction to detected customer speech, so a
    self-playing "first turn" here would be unreachable the same way
    handle_followup_wa_turn's is for real (streamed) calls. Every invocation
    of this function is processing the customer's reply to that already-played
    line.
    """
    if not hasattr(session, "dnc"):
        session.dnc = False
        session.react_state = "APPOINTMENT"  # for call_summaries reporting only — no other state exists in this funnel

    session.turn_count = getattr(session, "turn_count", 0) + 1
    t       = transcript.strip() if transcript else ""
    intents = detect_intents(t) if t else []

    logger.info(f"[{call_uuid}] fresh_cta transcript='{t[:60]}' intents={intents}")

    if not hasattr(session, "conversation"):
        session.conversation = []
    if t:
        session.conversation.append(("user", t))

    # Same product-key derivation /answer-outbound uses to pick the initial
    # greeting (session.fresh_product is the raw query-param string threaded
    # through via _session_meta — not pre-validated, so re-check it here
    # exactly the same way rather than trusting it's one of the 4 known values).
    _raw_product = getattr(session, "fresh_product", "") or ""
    _product_key = _raw_product if _raw_product in ("bed", "sofa", "wardrobe", "dining") else None

    # Hard decline — "not_interested" per spec; "dnc" folded in too (same
    # top-priority hard-stop convention every other handler in this file uses).
    # Reuses react_a's cached DNC audio directly — no new fresh_dnc key, per spec.
    if "dnc" in intents or "not_interested" in intents:
        session.dnc = True
        await play_key(call_uuid, "ra_dnc", session)
        return False

    # Same confirmation detection as the APPOINTMENT state in
    # handle_reactivation_turn, verbatim — mirrored, not reimplemented.
    _has_digit      = any(ch.isdigit() for ch in t)
    _has_day_suffix = "डे" in t and len(t.split()) >= 2
    if "appointment_confirm" in intents or _has_digit or _has_day_suffix:
        session.appointment_confirmed = True
        session.visit_date_raw_text   = t
        session.lead_tier_override    = "hot"
        session.lead_score_override   = 85
        await play_key(call_uuid, "fresh_appointment_confirmed", session)
        await asyncio.sleep(3.0)
        return False

    # Soft, no-push exit — "busy right now" / "let me think and get back to you".
    # Distinct from the general objection catch-all below: no reask, no pressure,
    # straight to WhatsApp and end the call gracefully.
    if "busy" in intents or "sochna_hai" in intents:
        await play_key(call_uuid, "fresh_soft_defer", session)
        await fire_whatsapp(session, call_uuid)
        return False

    # Confusion about who's calling / where from — reorient with the same
    # WhatsApp-followup framing the greeting itself used, then wait for their
    # reply (a date, another question, or still confused — which falls through
    # to the general reask/objection path below on the next turn, unchanged).
    if "confusion_who" in intents:
        _key = f"fresh_greet_who_{_product_key}" if _product_key else "fresh_greet_who_generic"
        await play_key(call_uuid, _key, session)
        return True

    # Location ask — one-shot response covering all 5 real showrooms (Gurugram x2,
    # Delhi, Noida, Faridabad) without naming any of them individually; full address
    # + Maps link goes over WhatsApp instead, per this codebase's established
    # "never speak a full street address on a call" convention. No follow-up city
    # question, no further date prompt — WhatsApp is where they confirm from here.
    if "ask_location" in intents:
        await play_key(call_uuid, "fresh_location_info", session)
        await fire_whatsapp(session, call_uuid)
        return False

    # General objection/hesitant/unclear catch-all (stock questions, "WhatsApp
    # options weren't great", expensive, online_cheaper, trust_issue, anything else
    # non-matching): exactly one reask, same appt_reask_tried pattern as the
    # APPOINTMENT state.
    if not getattr(session, "appt_reask_tried", False):
        session.appt_reask_tried = True
        await play_key(call_uuid, "fresh_objection", session)
        return True

    await play_key(call_uuid, "fresh_no_date_close", session)
    await fire_whatsapp(session, call_uuid)
    return False


async def handle_reactivation_turn(session, transcript: str, call_uuid: str) -> bool:
    """
    Timing wrapper — records the same session.turn_latencies / first_reply_ts
    fields the fresh_lead pipeline (webhook.py respond()) records, so
    call_summaries.avg_response_latency / first_response_latency are populated
    for react_a/react_b/reactivation calls too. Actual turn logic is unchanged,
    in _handle_reactivation_turn_impl below.
    """
    _t0 = time.time()
    should_continue = await _handle_reactivation_turn_impl(session, transcript, call_uuid)
    _latency = round(time.time() - _t0, 3)
    if not hasattr(session, "turn_latencies"):
        session.turn_latencies = []
    session.turn_latencies.append(_latency)
    if getattr(session, "first_reply_ts", None) is None:
        session.first_reply_ts = _latency
    logger.info(f"[{call_uuid}] React turn latency {_latency:.2f}s")
    return should_continue


async def _handle_reactivation_turn_impl(session, transcript: str, call_uuid: str) -> bool:
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
                if intent_name in ("ask_valuation", "ask_delivery"):
                    # q_valuation already ends by asking for a date — don't re-ask via appointment_ask
                    return True
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


async def handle_call2_turn(session, transcript: str, call_uuid: str) -> bool:
    """
    Call 2 (Ritu) — second real conversation with this lead, no date given yet.
    States: GREETING -> WA_CHECK -> DATE_ASK. Simpler graph than react_a/b/c —
    no PRESENT_OFFER/WHATSAPP_CTA buildup, since the lead already heard the
    offer on Call 1.
    """
    if not hasattr(session, "c2_state"):
        session.c2_state      = "GREETING"
        session.silence_count = 0
        session.wa_sent       = False
        session.dnc           = False

    session.turn_count = getattr(session, "turn_count", 0) + 1
    state   = session.c2_state
    t       = transcript.strip() if transcript else ""
    intents = detect_intents(t) if t else []

    logger.info(f"[{call_uuid}] call2 state={state} transcript='{t[:60]}' intents={intents}")

    # ── Silence ───────────────────────────────────────────────────────────────
    if not t:
        session.silence_count += 1
        if session.silence_count >= 3:
            await play_key(call_uuid, "c2_close_busy", session)
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

    # ── DNC — no dedicated c2_dnc key, reuses ra_dnc's cached audio (same
    # precedent as handle_fresh_cta_turn) ───────────────────────────────────────
    if "dnc" in intents:
        session.dnc = True
        await play_key(call_uuid, "ra_dnc", session)
        return False

    # ── GREETING ──────────────────────────────────────────────────────────────
    if state == "GREETING":
        if "confusion_who" in intents:
            await play_key(call_uuid, "c2_greet_reorient", session)
            session.c2_state = "WA_CHECK"
            await play_key(call_uuid, "c2_wa_check", session, log_transcript=False)
            return True
        if "busy" in intents:
            await play_key(call_uuid, "c2_close_busy", session)
            return False
        if "not_interested" in intents:
            await play_key(call_uuid, "c2_obj_not_interested", session)
            await play_key(call_uuid, "c2_close_declined", session)
            return False
        # Default (neutral or impatient) — no "annoyed, hurry up" shortcut;
        # both go straight to WA_CHECK.
        session.c2_state = "WA_CHECK"
        await play_key(call_uuid, "c2_wa_check", session)
        return True

    # ── WA_CHECK ──────────────────────────────────────────────────────────────
    if state == "WA_CHECK":
        session.c2_state = "DATE_ASK"
        if "wa_no_whatsapp" in intents or "wa_diff_number" in intents:
            await play_key(call_uuid, "c2_invite_resend", session)
            await fire_whatsapp(session, call_uuid)
            return True
        # Default — assume they saw it. Both invite_seen and invite_resend
        # already contain the date question, so no separate date-ask turn.
        await play_key(call_uuid, "c2_invite_seen", session)
        return True

    # ── DATE_ASK ──────────────────────────────────────────────────────────────
    if state == "DATE_ASK":
        # Resolve a pending price objection first — this turn is the customer's
        # yes/no reply to c2_obj_price, and takes precedence over the general
        # not_interested/expensive branches below.
        if getattr(session, "c2_price_asked", False):
            session.c2_price_asked = False
            if "not_interested" in intents:
                await play_key(call_uuid, "c2_close_price", session)
                return False
            await play_key(call_uuid, "c2_date_direct", session)
            return True

        if "not_interested" in intents:
            await play_key(call_uuid, "c2_obj_not_interested", session)
            await play_key(call_uuid, "c2_close_declined", session)
            return False
        if "expensive" in intents or "online_cheaper" in intents:
            await play_key(call_uuid, "c2_obj_price", session)
            session.c2_price_asked = True
            return True
        if "trust_issue" in intents:
            # c2_obj_scam re-asks the date itself — stay in DATE_ASK.
            await play_key(call_uuid, "c2_obj_scam", session)
            return True

        # Same confirmation detection as APPOINTMENT state in
        # handle_reactivation_turn, verbatim.
        _has_digit      = any(ch.isdigit() for ch in t)
        _has_day_suffix = "डे" in t and len(t.split()) >= 2
        if "appointment_confirm" in intents or _has_digit or _has_day_suffix:
            session.appointment_confirmed = True
            session.visit_date_raw_text   = t
            session.lead_tier_override    = "hot"
            session.lead_score_override   = 85
            await play_key(call_uuid, "c2_booked", session)
            await asyncio.sleep(3.0)
            return False

        # Vague — one reask, then close.
        if not getattr(session, "c2_reask_tried", False):
            session.c2_reask_tried = True
            await play_key(call_uuid, "c2_date_reask", session)
            return True
        await play_key(call_uuid, "c2_close_thinking", session)
        return False

    logger.warning(f"[{call_uuid}] Unknown c2_state: {state}")
    return False


async def handle_call3_turn(session, transcript: str, call_uuid: str) -> bool:
    """
    Call 3 (Simran) — third real conversation, last attempt before the
    existing answered_no_date_count>=3 cadence exit. States: GREETING ->
    DECISION_DATE, one reask, no re-argue on price objection (per script design).
    """
    if not hasattr(session, "c3_state"):
        session.c3_state      = "GREETING"
        session.silence_count = 0
        session.wa_sent       = False
        session.dnc           = False

    session.turn_count = getattr(session, "turn_count", 0) + 1
    state   = session.c3_state
    t       = transcript.strip() if transcript else ""
    intents = detect_intents(t) if t else []

    logger.info(f"[{call_uuid}] call3 state={state} transcript='{t[:60]}' intents={intents}")

    # ── Silence ───────────────────────────────────────────────────────────────
    if not t:
        session.silence_count += 1
        if session.silence_count >= 3:
            await play_key(call_uuid, "c3_close_busy", session)
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

    # ── DNC — no dedicated c3_dnc key, reuses ra_dnc's cached audio (same
    # precedent as handle_fresh_cta_turn) ───────────────────────────────────────
    if "dnc" in intents:
        session.dnc = True
        await play_key(call_uuid, "ra_dnc", session)
        return False

    # ── GREETING ──────────────────────────────────────────────────────────────
    if state == "GREETING":
        if "confusion_who" in intents:
            await play_key(call_uuid, "c3_greet_reorient", session)
            session.c3_state = "DECISION_DATE"
            await play_key(call_uuid, "c3_decision_date", session, log_transcript=False)
            return True
        if "not_interested" in intents:
            # NOTE: no dedicated "hostile" intent exists in REACT_ABC_INTENTS —
            # reusing not_interested here is a deliberate simplification, flagged
            # back rather than inventing a new intent category.
            await play_key(call_uuid, "c3_greet_hostile", session)
            return False
        if "busy" in intents:
            await play_key(call_uuid, "c3_close_busy", session)
            return False
        session.c3_state = "DECISION_DATE"
        await play_key(call_uuid, "c3_decision_date", session)
        return True

    # ── DECISION_DATE ─────────────────────────────────────────────────────────
    if state == "DECISION_DATE":
        if "not_interested" in intents:
            await play_key(call_uuid, "c3_declined", session)
            return False
        if "expensive" in intents or "online_cheaper" in intents:
            # No re-argue, no return path — deliberate, per script design.
            await play_key(call_uuid, "c3_obj_price", session)
            return False
        if "trust_issue" in intents:
            # c3_obj_scam re-asks the date itself — stay in DECISION_DATE.
            await play_key(call_uuid, "c3_obj_scam", session)
            return True

        _has_digit      = any(ch.isdigit() for ch in t)
        _has_day_suffix = "डे" in t and len(t.split()) >= 2
        if "appointment_confirm" in intents or _has_digit or _has_day_suffix:
            session.appointment_confirmed = True
            session.visit_date_raw_text   = t
            session.lead_tier_override    = "hot"
            session.lead_score_override   = 85
            await play_key(call_uuid, "c3_booked", session)
            await asyncio.sleep(3.0)
            return False

        # Vague (including busy/sochna_hai, which fall through to here for
        # this state) — one reask, then final close.
        if not getattr(session, "c3_reask_tried", False):
            session.c3_reask_tried = True
            await play_key(call_uuid, "c3_date_reask", session)
            return True
        await play_key(call_uuid, "c3_close_thinking_final", session)
        return False

    logger.warning(f"[{call_uuid}] Unknown c3_state: {state}")
    return False
