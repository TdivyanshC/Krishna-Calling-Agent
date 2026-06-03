"""
respond_pipeline.py — Drop-in respond() replacement for webhook.py

WHAT CHANGED vs your current code:
  1. Language detected on every turn → lang stored in session
  2. Filler plays INSTANTLY while TTS generates (eliminates silence gap)
  3. TTS uses correct voice per language
  4. LLM gets language instruction so replies match caller's language
  5. Static cache checked before any API call
  6. Filler + TTS run as parallel tasks when possible

HOW TO INTEGRATE:
  Copy this file to /home/voiceagent/voice-ai/respond_pipeline.py
  In webhook.py, add these imports at the top:
      from respond_pipeline import respond_v2
  Then replace your existing respond() call with respond_v2().

  Your existing respond() function signature:
      async def respond(ws, session, audio, call_uuid)
  This has the SAME signature — it's a drop-in.

DEPENDENCIES (all already in your venv):
  - httpx (already installed)
  - lang_detect.py  (new — copy from upgrade/)
  - tts_engine.py   (new — copy from upgrade/)
  - filler_audio.py (new — copy from upgrade/)
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


# ── These imports assume files are in the same directory ─────────────────────
# Adjust paths if needed based on your project structure
from lang_detect import detect_lang, get_lang_instruction
from tts_engine  import get_speech, get_speech_url, STATIC_RESPONSES
from filler_audio import get_filler_for_context, load_filler_cache


# ── Vobiz Play helper (same as your existing one) ─────────────────────────────
async def _play_url(call_uuid: str, url: str, vobiz_client, account_sid: str) -> bool:
    """
    Trigger Vobiz to play an audio URL.
    This mirrors your existing play logic — adapt to match your actual impl.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.vobiz.ai/api/v1/Account/{account_sid}/Call/{call_uuid}/Play/",
                headers={"Content-Type": "application/json"},
                json={"url": url},
            )
        success = r.status_code in (200, 202)
        if success:
            logger.info(f"[{call_uuid}] Play → {r.status_code} | {url}")
        else:
            logger.error(f"[{call_uuid}] Play FAILED {r.status_code}")
        return success
    except Exception as e:
        logger.error(f"[{call_uuid}] Play error: {e}")
        return False


# ── Filler + TTS parallel strategy ────────────────────────────────────────────

async def _play_filler_then_tts(
    ws,
    session,
    call_uuid: str,
    reply: str,
    lang: str,
    source: str,
    static_key: Optional[str],
    play_fn,
) -> None:
    """
    Core latency optimization:
      Step 1: Play filler IMMEDIATELY (from disk, 0ms wait)
      Step 2: Generate TTS in parallel
      Step 3: Play real response when ready

    On cache HIT: skip filler (response is already instant)
    On cache MISS: filler fills the silence gap
    """
    from tts_engine import get_dynamic_audio, get_static_audio

    # Check if we have a cached response before deciding on filler
    cached_wav = None
    if static_key:
        cached_wav = get_static_audio(static_key, lang)
    if cached_wav is None:
        cached_wav = get_dynamic_audio(reply, lang)

    t0 = time.time()

    if cached_wav is not None:
        # Cache hit — play immediately, no filler needed
        _, url, _ = await get_speech(reply, lang, static_key)
        if url:
            await play_fn(call_uuid, url)
            logger.info(f"[{call_uuid}] CACHE HIT [{lang}] | {time.time()-t0:.2f}s")
        return

    # Cache miss — play filler immediately, generate TTS in background
    filler_url = get_filler_for_context(source, lang)

    async def play_filler():
        if filler_url:
            logger.info(f"[{call_uuid}] FILLER → {filler_url}")
            await play_fn(call_uuid, filler_url)

    async def generate_and_play_tts():
        _, url, was_cached = await get_speech(reply, lang, static_key)
        if url:
            await play_fn(call_uuid, url)
            logger.info(f"[{call_uuid}] TTS DONE [{lang}] | cached={was_cached} | {time.time()-t0:.2f}s")

    # Play filler immediately, TTS generates concurrently
    await asyncio.gather(play_filler(), generate_and_play_tts())


# ── Main respond function ─────────────────────────────────────────────────────

async def respond_v2(ws, session, audio: bytes, call_uuid: str, play_fn=None) -> None:
    """
    Drop-in replacement for your existing respond() function.

    NEW vs OLD:
    - Detects language from STT transcript
    - Stores lang in session.lang (persists across turns)
    - Uses lang-aware TTS voice
    - Injects language instruction into LLM
    - Plays filler on cache miss
    - Same state machine / FAQ logic as before
    """
    if session.is_processing:
        return
    session.is_processing = True
    t0 = time.time()

    try:
        # ── 1. STT (same as before) ───────────────────────────────────────────
        from webhook import transcribe, ulaw_to_wav  # your existing functions
        text = await transcribe(ulaw_to_wav(audio))
        if not text or len(text.strip()) < 2:
            logger.info(f"[{call_uuid}] Empty transcript — skip")
            return

        # ── 2. Language detection ─────────────────────────────────────────────
        # Detect on THIS turn but also inherit from session if caller is consistent
        turn_lang = detect_lang(text)

        # Smooth: if we've detected language 2+ turns in a row, trust it
        if not hasattr(session, "lang"):
            session.lang = turn_lang
            session.lang_streak = 1
        elif turn_lang == session.lang:
            session.lang_streak = getattr(session, "lang_streak", 0) + 1
        else:
            # Language switched — update if two consecutive turns agree
            session.lang_streak = 1
            session.lang = turn_lang  # Switch immediately (callers may switch)

        lang = session.lang
        logger.info(f"[{call_uuid}] STT [{lang}] → '{text}'")

        # ── 3. Noise / ACK gate (same as before) ─────────────────────────────
        from knowledge import ACK_WORDS, JUNK_WORDS, is_noise, fix_stt

        if is_noise(text):
            logger.info(f"[{call_uuid}] NOISE — skip")
            return

        raw_lower = text.strip(".,!? ।").lower()
        if raw_lower in ACK_WORDS or text.strip(".,!? ।") in ACK_WORDS:
            logger.info(f"[{call_uuid}] ACK — silent")
            return

        text_fixed = fix_stt(text)

        # ── 4. State machine (same as before — your existing state_machine()) ─
        from webhook import state_machine  # your existing function
        reply, source = state_machine(text_fixed, text, session, call_uuid)

        # Play pending acknowledgement (e.g. "अच्छा bed देखना है!") before main response
        pending_ack = getattr(session, "pending_ack", None)
        if pending_ack and reply:
            session.pending_ack = None
            from tts_engine import STATIC_RESPONSES
            ack_text = STATIC_RESPONSES.get(pending_ack, {}).get(lang)
            if ack_text:
                ack_key = pending_ack
                ack_wav = get_static_audio(ack_key, lang)
                if ack_wav:
                    ack_url = f"{BASE_URL}/audio/static/{ack_key}_{lang}.wav"
                    await play_fn(call_uuid, ack_url)
                    logger.info(f"[{call_uuid}] ACK played → {ack_key}")
                    await asyncio.sleep(0.8)

        if not reply:
            return

        logger.info(f"[{call_uuid}] REPLY [{lang}] src={source} | '{reply[:60]}'")

        # ── 5. Build TTS with language awareness ──────────────────────────────
        # Determine if this is a pre-generated static response
        static_key = _source_to_static_key(source, lang)

        # If static key has a language variant, use it
        if static_key and static_key in STATIC_RESPONSES:
            lang_map = STATIC_RESPONSES[static_key]
            if lang in lang_map:
                # Override reply text with the correct language version
                reply = lang_map[lang]
            elif "hinglish" in lang_map:
                reply = lang_map["hinglish"]

        # ── 6. Play with filler-first strategy ───────────────────────────────
        if play_fn is None:
            # Build a play_fn from your existing Vobiz credentials
            from webhook import VOBIZ_ACCOUNT_SID  # or whatever your var is called
            async def _play(cid, url):
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.post(
                        f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT_SID}/Call/{cid}/Play/",
                        headers={"Content-Type": "application/json"},
                        json={"url": url},
                    )
                logger.info(f"[{cid}] Play → {r.status_code}")
            play_fn = _play

        await _play_filler_then_tts(
            ws=ws,
            session=session,
            call_uuid=call_uuid,
            reply=reply,
            lang=lang,
            source=source,
            static_key=static_key,
            play_fn=play_fn,
        )

        # ── 7. Track conversation (same as before) ────────────────────────────
        if source not in ("repeat", "noise", "ack"):
            session.last_reply = reply
            session.last_source = source

        logger.info(f"[{call_uuid}] Pipeline {time.time()-t0:.2f}s | lang={lang} | src={source}")

    except Exception as e:
        logger.exception(f"[{call_uuid}] respond_v2 error: {e}")
    finally:
        session.is_processing = False


# ── Source → Static key mapping ───────────────────────────────────────────────

def _source_to_static_key(source: str, lang: str) -> Optional[str]:
    """
    Maps a response source tag to a static cache key.
    Returns None if no static version exists (→ use dynamic cache / fresh TTS).
    """
    # Direct state machine sources
    STATE_MAP = {
        "greeting":          "greeting_inbound",
        "greeting_outbound": "greeting_outbound",
        "qualify_product":   "qualify_product",
        "qualify_budget":    "qualify_budget",
        "qualify_urgency":   "qualify_urgency",
        "wrap_whatsapp":     "wrap_whatsapp",
        "goodbye":           "goodbye",
        "repeat":            "faq_repeat",
        "not_understood":    "not_understood",
        "ask_product":       "ask_product",
        "ask_budget":        "ask_budget",
        "ack_sofa":          "ack_sofa",
        "ack_bed":           "ack_bed",
        "ack_sofa_bed":      "ack_sofa_bed",
        "ack_dining":        "ack_dining",
        "ack_wardrobe":      "ack_wardrobe",
        "ack_office":        "ack_office",
        "ack_general":       "ack_general",
        "ack_budget":        "ack_budget",
        "not_understood_budget":  "not_understood_budget",
        "not_understood_urgency": "not_understood_urgency",
    }

    # FAQ source tags (from knowledge.py)
    FAQ_MAP = {
        # Old faq: tags
        "faq:location":           "faq_location",
        "faq:delivery":           "faq_delivery",
        "faq:delivery_delay":     "faq_delivery",
        "faq:emi":                "faq_emi",
        "faq:warranty":           "faq_warranty",
        "faq:customisation":      "faq_customisation",
        "faq:repeat":             "faq_repeat",
        # Direct keyword match tags (from DIRECT_KEYWORD_MAP)
        "faq:store_location":     "store_location",
        "faq:delivery_charges":   "delivery_charges",
        "faq:delivery_delay":     "delivery_delay",
        "faq:general_discount_offer": "general_discount_offer",
        "faq:exchange_offer":     "exchange_offer",
        "faq:warranty_quality":   "warranty_quality",
        "faq:timing_hours":       "timing_hours",
        "faq:installation_assembly": "installation_assembly",
        "faq:customization":      "customization",
        "faq:manufacturing":      "manufacturing",
        "faq:payment_methods":    "faq_emi",
        "faq:head_branch":        "store_location",
        "faq:pan_india_delivery":      "delivery_charges",
        "faq:wholesale_bulk":          "faq_location",
        "faq:store_address_request":   "store_address_request",
        "faq:goodbye":                 "goodbye",
    }

    # Objection tags
    OBJ_MAP = {
        "obj_expensive":       "obj_expensive",
        "obj_think":           "obj_think",
        "obj_online":          "obj_online",
        "obj_busy":            "obj_busy",
        "faq:expensive":       "obj_expensive",
        "faq:think":           "obj_think",
        "faq:online_comp":     "obj_online",
        "faq:busy":            "obj_busy",
        # ── New objection handlers ──────────────────────────────────────
        "obj_think_wrapup":    "obj_think_wrapup",
        "obj_online_wrapup":   "obj_online_wrapup",
        "goodbye_warm":        "goodbye_warm",
        "hook_positive":       "hook_positive",
        "hook_hesitant":       "hook_hesitant",
        "hook_negative_1":     "hook_negative_1",
        "hook_negative_2":     "hook_negative_2",
        "product_vague":       "product_vague",
        "product_busy":        "product_busy",
        # ── Wrap-up per product ─────────────────────────────────────────
        "wrap_up_dining":      "wrap_up_dining",
        "wrap_up_sofa":        "wrap_up_sofa",
        "wrap_up_bed":         "wrap_up_bed",
        "wrap_up_office":      "wrap_up_office",
        "wrap_up_general":     "wrap_up_general",
    }

    key = STATE_MAP.get(source) or FAQ_MAP.get(source) or OBJ_MAP.get(source)
    return key


# ── LLM context injection (add to your build_llm_context) ────────────────────

def build_multilingual_llm_system_prompt(session, base_context: str) -> str:
    """
    Wraps your existing build_llm_context() output with language instructions.
    Call this instead of build_llm_context() when building LLM messages.

    Usage in webhook.py:
        from respond_pipeline import build_multilingual_llm_system_prompt
        # Replace:
        #   context = build_llm_context()
        # With:
        #   context = build_multilingual_llm_system_prompt(session, build_llm_context())
    """
    lang = getattr(session, "lang", "hinglish")
    from lang_detect import get_lang_instruction
    lang_rule = get_lang_instruction(lang)

    naturalness_rules = """
NATURALNESS RULES (critical for phone calls):
- You are Priya, a real sales rep at Krishna Furniture, on a phone call
- Keep replies SHORT — 1-2 sentences max on phone calls
- Use natural spoken language, NOT written language
- Add natural pauses with commas: "Haan ji, bilkul — kaunsa product dekh rahe hain?"
- Do NOT say: "Main samajhti hoon ki aap furniture khareedna chahte hain"
- DO say: "Haan ji, batao — sofa chahiye ya kuch aur?"
- Do NOT start replies with "Bilkul ji, main aapko batana chahungi ki..."
- DO start with: "Haan ji," or "Bilkul," or "Dekho," or "Acha," then get to the point
- NEVER make up prices, product specs, or store locations — only say what you know
- If unsure, say: "Ek second, check karte hain" (then the FAQ system handles it)
- NEVER say "I am an AI" or "I am a bot" — you are Priya, a human sales rep
"""

    return f"{base_context}\n\n{lang_rule}\n\n{naturalness_rules}"