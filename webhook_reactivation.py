"""
webhook_reactivation.py
Reactivation A/B/C campaign state machine for Priya.
Supports campaign_type: react_a, react_b, react_c
"""

import asyncio
import io
import logging
import os
import re
import time
import wave
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import httpx
from groq import AsyncGroq

from knowledge_react_abc import REACT_ABC_INTENTS, get_script, get_prefix, SHARED_INTENTS, SHARED_SCRIPT, PREFIX_VOICE_MAP, CALL2_SCRIPT, CALL3_SCRIPT, normalize_fresh_product_key, match_price_category, match_store_city, mentions_non_catalog_item, match_fresh_product, match_fresh_broad_category, _FRESH_PRODUCT_BROAD
from knowledge_react_abc_en import get_script_en, SHARED_SCRIPT_EN, CALL2_SCRIPT_EN, CALL3_SCRIPT_EN, EN_SPEAKER
from supabase_calling import mark_dnc_immediate
from audit_log import audit_event

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

# Phonetic-Devanagari fragments of carrier IVR/voicemail messages that
# audio-replay grounding (12+1 known production calls, 0 false positives
# across a 95-call sample) confirmed the existing English-only
# _machine_phrases lists below never catch -- STT renders the machine's
# English audio phonetically into Devanagari script rather than transcribing
# it as English text. Independent of _machine_phrases on purpose (belt and
# suspenders): a match here does NOT hang up like _machine_phrases does,
# since this signal is less certain -- it just withholds objection/sales
# content for this turn and waits for a real reply, which self-corrects if
# a real customer produced this transcript by mistake. Turn-duration/VAD
# silence pattern was evaluated as an alternative/additional signal and
# rejected: it doesn't separate cleanly (real single-turn calls up to 128s
# overlap the IVR calls' range down to 50s).
_IVR_FRAGMENT_PATTERNS = [
    # "When you have finished recording, you may hang up."
    "रिकॉर्डिंग", "हैंग अप", "हांग अप",
    # "I'm sorry, this person is not available ... leave a message."
    # "अवेलेबल" (available) removed 2026-08-13 -- it's just the common
    # Hindi/English loanword for "available", no negation requirement, so it
    # matched ordinary customer speech too. Confirmed live: a real customer
    # asking "is this offer available on everything?" / "what's this
    # available on?" got silently treated as a voicemail fragment on both
    # turns, suppressing all replies to genuine, substantive questions for
    # the rest of that call (ivr_fragment_count never resets down once set).
    # Bare "मैसेज" (message) narrowed the SAME way on 2026-08-14 -- the exact
    # same false-positive shape the "available" fix above already
    # documented, just missed at the time: "मैसेज" alone matched a real
    # customer saying "WhatsApp pe hi message karo" (please just message me
    # on WhatsApp -- itself one of this file's own wa_prefers/wa_ok keywords)
    # and silently withheld the reply for an entirely legitimate turn.
    # Narrowed to the actual carrier phrase this list was built to catch --
    # confirmed against the real captured fragments in
    # test_ivr_fragment_detection.py ("इफ यू वुड लाइक टू लीव एन एडिशनल
    # मैसेज...") -- requiring "लीव"+"मैसेज" adjacency instead of either word
    # alone still catches the real greeting.
    "लीव एन एडिशनल मैसेज", "लीव एन मैसेज", "लीव मैसेज",
    # "Your call has been put on hold, please stay on the line."
    "होल्ड पर", "स्टे ऑन द लाइन", "पुट योर कॉल",
    # "... please leave a message after the tone." — confirmed live
    # 2026-08-11 (hot_warm_leads_conversations.docx audit): "आफ्टर द टोन"
    # alone (STT apparently split this off from the rest of the voicemail
    # greeting into its own turn) matched none of the patterns above and
    # was scored as a real customer reply to a date-ask, warm=50.
    "आफ्टर द टोन", "द टोन",
]


def _is_ivr_fragment(t: str) -> bool:
    return any(p in t for p in _IVR_FRAGMENT_PATTERNS)


def _mark_ivr_fragment(session) -> None:
    if not hasattr(session, "intents_fired"):
        session.intents_fired = set()
    session.intents_fired.add("ivr_fragment_detected")
    session.ivr_fragment_count = getattr(session, "ivr_fragment_count", 0) + 1


# Absolute safety nets, independent of state/intent routing — mirrors
# webhook.py state_machine()'s TURN_CAP (25) and adds a wall-clock backstop
# alongside it. TURN_CAP alone caught the react_a "Rajni" call
# (919910566742, 2026-07-25, 370 turns / 2731s against a carrier hold-loop)
# too late because none of these handlers had ANY turn cap before this fix —
# turn_count was incrementing the whole time, just never checked. Checked at
# DURATION_CAP_SECONDS in case a future stuck call has slower/longer turns
# where 25 turns alone would still run past a reasonable wall-clock ceiling.
TURN_CAP = 25
DURATION_CAP_SECONDS = 180


def _hard_cap_reason(session) -> str | None:
    """
    Returns a short reason string if this call must be force-closed right
    now, else None. Checked before per-turn IVR-fragment/silence/intent
    logic in every handler so a fragment loop (which returns early and never
    reaches intent logic) can't dodge either trigger.
    turn_count_substantive is only ever incremented past each handler's
    IVR-fragment early-return, so "zero real speech" here already excludes
    fragment turns without needing a separate counter.
    """
    if session.turn_count >= TURN_CAP:
        return "turn_cap_close"
    if getattr(session, "turn_count_substantive", 0) == 0:
        started = getattr(session, "started_at", None)
        if started:
            try:
                elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds()
            except ValueError:
                elapsed = 0
            if elapsed > DURATION_CAP_SECONDS:
                return "duration_cap_close"
    return None


_http_client: httpx.AsyncClient | None = None

async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=8)
    return _http_client


# Since _vobiz_play() fires its POST as a background task rather than
# awaiting it, two plays issued in the same turn (e.g. obj_expensive then
# wa_cta) are no longer naturally serialized by the caller awaiting each one
# in turn -- both tasks can be in flight together over the shared client's
# pooled connections and complete in either order. One Lock per call_uuid
# means the second play's POST doesn't actually go out until the first one's
# has resolved, preserving issue order, without making play_key() itself
# block on the network round-trip. Entries are never explicitly cleaned up
# (a live call only ever needs one at a time and the dict is keyed by
# call_uuid, so it grows by one small Lock object per call for the process's
# lifetime -- negligible next to the service's periodic restarts).
_play_locks: dict[str, asyncio.Lock] = {}


def _static_wav_path(key: str, lang: str = "hi") -> str:
    return os.path.join(STATIC_DIR, f"{key}_{lang}.wav")

def _static_url(key: str, lang: str = "hi") -> str | None:
    path = _static_wav_path(key, lang)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return f"{BASE_URL}/audio/static/{key}_{lang}.wav"
    return None


def _wav_file_duration(path: str) -> float:
    try:
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


def _wav_bytes_duration(wav_bytes: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0

async def _vobiz_play(call_uuid: str, audio_url, turn: int = 0, kind: str = "reply") -> bool:
    """
    audio_url: a single URL, or a list of URLs to play back-to-back.
    Confirmed live 2026-08-13: two separate play_key() calls fired in quick
    succession (the "answer, then continue" pattern used throughout this
    file -- e.g. answer a question, then immediately ask for the visit date)
    were sending TWO separate Play requests to Vobiz. Independently verified
    against a real recording (STT on the actual audio, not just our own
    logs) that the SECOND request interrupts/replaces the first rather than
    queuing after it -- the first message (the actual answer) was
    completely inaudible on the real call, cut off by the second request
    arriving milliseconds later, even though both were correctly logged as
    "played". Vobiz's Play API already accepts a urls LIST natively (this
    payload always has, just previously with only ever one element) --
    passing multiple URLs in ONE request lets Vobiz sequence them itself
    instead of two requests racing each other on the same leg.
    """
    audio_urls = audio_url if isinstance(audio_url, list) else [audio_url]
    url = (
        f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}"
        f"/Call/{call_uuid}/Play/"
    )
    payload = {"urls": audio_urls, "legs": "aleg", "mix": False}
    hdrs = {"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK}
    for _u in audio_urls:
        audit_event(call_uuid, "play_issue", turn=turn, audio_url=_u, kind=kind)
    lock = _play_locks.setdefault(call_uuid, asyncio.Lock())

    async def _fire() -> None:
        _t0 = time.time()
        global _http_client
        try:
            # Serializes this call's actual network sends: a second play
            # issued in the same turn waits here until the first one's POST
            # has resolved, so the two still reach Vobiz in the order
            # play_key() was called, even though neither blocks the caller.
            async with lock:
                # Filler-finish gate: if a filler clip is still playing on
                # this leg, hold this reply's Play until it finishes so
                # Vobiz sequences them instead of chopping the filler
                # mid-word. Only for real replies (a filler must never wait
                # on itself), and capped so a stale entry can't stall a turn.
                if kind == "reply":
                    _ff = _filler_finish_at.pop(call_uuid, None)
                    if _ff is not None:
                        _gap = _ff - time.monotonic()
                        if 0.05 < _gap <= 3.0:
                            await asyncio.sleep(_gap)
                client = await _get_http_client()
                # httpx-native timeout, not asyncio.wait_for: wait_for cancels the
                # request from outside httpx's transport, which can leave a stalled
                # connection looking healthy in the pool and get it reused by the
                # next play — that's what produced the observed pattern where one
                # timeout on a call predicts a 70% chance the next play on that
                # same call times out too. httpx's own timeout closes the
                # connection itself instead of yanking the task.
                r = await client.post(url, json=payload, headers=hdrs, timeout=3.0)
            _elapsed = time.time() - _t0
            logger.info(f"[{call_uuid}] React play {'OK' if r.status_code == 202 else 'FAIL'} {r.status_code} | {_elapsed:.2f}s → {audio_url}")
            audit_event(call_uuid, "play_result", turn=turn, status_code=r.status_code, elapsed_ms=round(_elapsed * 1000), kind=kind)
        except httpx.TimeoutException:
            _elapsed = time.time() - _t0
            logger.warning(f"[{call_uuid}] React play TIMEOUT after {_elapsed:.2f}s → {audio_url}")
            audit_event(call_uuid, "play_timeout", turn=turn, elapsed_ms=round(_elapsed * 1000), kind=kind, audio_url=audio_url)
            # A real httpx-level timeout is itself evidence the connection is
            # bad — nothing else will evict it, so do it here.
            _http_client = None
        except Exception as exc:
            _elapsed = time.time() - _t0
            logger.error(f"[{call_uuid}] React play error: {type(exc).__name__}: {exc}")
            audit_event(call_uuid, "play_result", turn=turn, status_code=None, elapsed_ms=round(_elapsed * 1000), kind=kind, error=type(exc).__name__)
            if isinstance(exc, (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
                logger.warning(f"[{call_uuid}] resetting react http client due to {type(exc).__name__}")
                _http_client = None

    # Vobiz's Play endpoint returns 202 (fire-and-forget) and every play_key()
    # caller already discards this function's return value, so nothing is
    # waiting on the HTTP round-trip — awaiting it only added up to 3s of
    # dead air per turn when Vobiz stalled. Fire it in the background instead.
    asyncio.create_task(_fire())
    return True

# Independence Day flash sale (flat 50% off, 2026-08-11 through 2026-08-16
# IST) ended and its script/keyword content was removed 2026-08-17 --
# offer's gone, back to the exchange offer as the only live pitch for now.
# _sale_active()/_SALE_END and the "_sale" key-swap in _resolve_key_url()
# below are gone with it -- they're not just dormant, the "_sale"-suffixed
# keys themselves no longer exist in knowledge_react_abc.py's script dicts.
# If a future flash sale needs the same pattern again, re-add a dated
# window check here rather than reviving this specific removed code.


async def _resolve_key_url(call_uuid: str, key: str, session=None, log_transcript: bool = True) -> str | None:
    """
    Everything play_key() used to do except the actual _vobiz_play() call:
    sale-variant swap, offer_explained flag, transcript logging, cache
    lookup / live-TTS-fallback. Returns the resolved audio URL, or None if
    resolution failed. Split out 2026-08-13 so play_keys() (below) can
    resolve several keys and hand Vobiz one combined multi-URL request
    instead of firing separate Play calls that interrupt each other — see
    _vobiz_play()'s docstring for why that matters.
    """
    # Bilingual: session.lang is "hi"/"hinglish"/"en" (lang_detect.detect_lang(),
    # tracked once per turn in webhook.py's respond() -- see that block's
    # comment for why it now runs for every flow, not just fresh_lead).
    # "hinglish" collapses to the Hindi dict here on purpose: the existing
    # Hindi script content is already Hinglish-natural (English loanwords
    # mixed in throughout), so there's no separate third register to
    # maintain -- only a caller who's detected as genuinely speaking English
    # gets the English dict.
    lang = "en" if getattr(session, "lang", "hi") == "en" else "hi"

    call_cycle = getattr(session, "call_cycle", None) if session else None
    if lang == "en":
        if call_cycle == "2":
            script = CALL2_SCRIPT_EN
        elif call_cycle == "3":
            script = CALL3_SCRIPT_EN
        else:
            campaign = getattr(session, "campaign", "react_a") if session else "react_a"
            script   = get_script_en(campaign)
        shared = SHARED_SCRIPT_EN
    else:
        if call_cycle == "2":
            script = CALL2_SCRIPT
        elif call_cycle == "3":
            script = CALL3_SCRIPT
        else:
            campaign = getattr(session, "campaign", "react_a") if session else "react_a"
            script   = get_script(campaign)
        shared = SHARED_SCRIPT

    # Checked against the base key on purpose, before the sale-variant swap
    # below — offer_explained tracks the semantic slot (was the offer
    # pitched/explained this call), which holds regardless of which offer
    # copy is currently live.
    if session is not None and (key.endswith("_offer_main") or key.endswith("_offer_explain")):
        session.offer_explained = True

    # Falls back to the shared dict for keys not in the active flow's own
    # script (e.g. route_objection()'s obj_repeat_generic, which is
    # flow-agnostic and deliberately not duplicated into every per-plan
    # dict). Existing keys are unaffected -- they're always found in their
    # primary script, so this fallback never triggers for them.
    _resolved_text = script.get(key) or shared.get(key) or key

    # 2026-08-23 CONFIRMED-LIVE BUG (same class, see play_dynamic_text's
    # comment): the conversation append used to happen HERE, before even
    # checking whether this key resolves to a real cached file, let alone
    # before a cache-miss's live-TTS-fallback succeeding -- so a genuinely
    # uncached key whose live generation then failed would still get logged
    # into the transcript as something the customer heard. Rare in practice
    # (nearly every key call here hits the pre-generated static cache), but
    # a real, uncached key is exactly the scenario this matters for. Moved
    # to append only at each point where a URL is actually about to be
    # returned, mirroring play_dynamic_text's fix.
    def _log_turn():
        if session is not None and log_transcript:
            if not hasattr(session, "conversation"):
                session.conversation = []
            session.conversation.append(("assistant", _resolved_text))

    _turn = getattr(session, "turn_idx", None) if session else None
    if _turn is None:
        _turn = getattr(session, "turn_count", 0) if session else 0

    url = _static_url(key, lang)
    if url:
        logger.info(f"[{call_uuid}] CACHE HIT → {key} [{lang}]")
        audit_event(call_uuid, "tts", turn=_turn, key=key, cached=True)
        if session is not None:
            session.turn_audio_duration = getattr(session, "turn_audio_duration", 0.0) + _wav_file_duration(_static_wav_path(key, lang))
        _log_turn()
        return url

    logger.warning(f"[{call_uuid}] CACHE MISS → {key} [{lang}] — generating live")
    audit_event(call_uuid, "tts", turn=_turn, key=key, cached=False)
    text = script.get(key) or shared.get(key)
    if not text:
        logger.error(f"[{call_uuid}] No text for key: {key} [{lang}]")
        return None
    try:
        from tts_engine import get_speech
        speaker = EN_SPEAKER if lang == "en" else None
        wav_bytes, audio_url, _ = await get_speech(text, lang=lang, static_key=key, speaker=speaker)
        if audio_url:
            if session is not None:
                session.turn_audio_duration = getattr(session, "turn_audio_duration", 0.0) + _wav_bytes_duration(wav_bytes or b"")
            _log_turn()
            return audio_url
    except Exception as exc:
        logger.error(f"[{call_uuid}] Live TTS failed for {key}: {exc}")
    return None


async def play_key(call_uuid: str, key: str, session=None, log_transcript: bool = True) -> bool:
    _turn = getattr(session, "turn_idx", None) if session else None
    if _turn is None:
        _turn = getattr(session, "turn_count", 0) if session else 0
    url = await _resolve_key_url(call_uuid, key, session, log_transcript)
    if not url:
        return False
    return await _vobiz_play(call_uuid, url, turn=_turn, kind="reply")


async def play_keys(call_uuid: str, keys: list[str], session=None, log_transcript=True) -> bool:
    """
    Plays several keys as ONE native Vobiz multi-URL sequence instead of
    separate play_key() calls -- use this for any "answer, then continue"
    pattern (e.g. answer a question, then ask for the visit date). See
    _vobiz_play()'s docstring: firing two separate Play requests back to
    back lets the second interrupt the first before a real customer ever
    hears it, confirmed against an actual call recording 2026-08-13.

    log_transcript: a single bool applied to every key, or a list of bools
    matching keys one-to-one -- most call sites here log the first
    (substantive) key and not the second (an obvious continuation), same
    asymmetry play_key() call sites already used before this existed.
    """
    if isinstance(log_transcript, list):
        _log_flags = log_transcript
    else:
        _log_flags = [log_transcript] * len(keys)
    _turn = getattr(session, "turn_idx", None) if session else None
    if _turn is None:
        _turn = getattr(session, "turn_count", 0) if session else 0
    urls = []
    for key, _log in zip(keys, _log_flags):
        url = await _resolve_key_url(call_uuid, key, session, _log)
        if url:
            urls.append(url)
    if not urls:
        return False
    return await _vobiz_play(call_uuid, urls, turn=_turn, kind="reply")


async def fire_whatsapp(session, call_uuid: str) -> bool:
    if getattr(session, "wa_sent", False):
        logger.info(f"[{call_uuid}] WA already sent — skip")
        return True
    session.wa_sent = True
    phone    = getattr(session, "customer_phone", "").replace("+", "").strip()
    name     = getattr(session, "customer_name", "") or "Customer"
    campaign = getattr(session, "campaign", "react_a")
    # Independence Day sale removed 2026-08-17 -- back to the exchange offer
    # unconditionally (see the comment above _resolve_key_url()).
    _offer_label = "25+25% exchange offer"
    payload  = {"phone": phone, "name": name, "offer": _offer_label, "campaign": "reactivation"}
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
                    # Dashboard-specific flag (supabase_migration_whatsapp_cta_sent.sql) --
                    # separate columns from wa_sent/wa_sent_at on purpose, set together
                    # at the same call site, so the CRM card can key off this one
                    # specifically without assuming anything about wa_sent's other uses.
                    "whatsapp_cta_sent":    True,
                    "whatsapp_cta_sent_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        logger.info(f"[{call_uuid}] outbound_lead → wa_sent=True phone={raw_phone}")
    except Exception as exc:
        logger.error(f"[{call_uuid}] wa_sent persist error: {exc}")


def _fire_immediate_dnc(session, call_uuid: str) -> None:
    """
    Fire-and-forget mark_dnc_immediate() for the caller's phone — every
    "dnc" intent branch in this file used to only set session.dnc = True
    in-memory, and the actual outbound_leads write happened later, at
    /hangup, via finalize_call(). This closes the same window
    mark_dnc_immediate() documents: a dropped call between the opt-out
    turn and the hangup webhook would otherwise leave the lead unmarked.
    """
    phone = getattr(session, "customer_phone", "")
    if phone:
        asyncio.create_task(mark_dnc_immediate(phone, call_uuid))


async def check_hard_rejection(
    session,
    call_uuid: str,
    intents: list[str],
    dnc_key: str,
    also_reject_on: tuple[str, ...] = (),
) -> bool:
    """
    Shared DNC/hard-rejection check — extracted verbatim from 4 duplicated
    inline copies (handle_fresh_cta_turn, _handle_reactivation_turn_impl,
    handle_call2_turn, handle_call3_turn), each previously re-implementing
    the same "dnc" in intents / session.dnc / _fire_immediate_dnc / play_key
    sequence independently. Pure extraction — the per-call-site differences
    (which cache key plays, and whether "not_interested" also counts as a
    hard reject) are now explicit parameters instead of copy-pasted
    variations, but produce byte-identical behavior to before:
      - react_a/b/c Call1 passes dnc_key=f"{p}_dnc" (plan-specific key).
      - fresh_cta / Call2 / Call3 all pass dnc_key="ra_dnc" — no dedicated
        c2_dnc/c3_dnc/fresh_dnc key exists, same precedent as before.
      - fresh_cta additionally passes also_reject_on=("not_interested",) —
        its single-state flow treats a plain "not interested" as a hard
        stop too; Call1/Call2/Call3 do not (they have softer
        not_interested branches of their own further down).
    Returns True if this turn was a hard rejection — caller ends the call
    (return False) immediately after.
    """
    if "dnc" in intents or any(i in intents for i in also_reject_on):
        session.dnc = True
        _fire_immediate_dnc(session, call_uuid)
        await play_key(call_uuid, dnc_key, session)
        return True
    return False


# Terminal state names across the flows that use a named-state variable
# (react Call1 only -- Call2/Call3 have no separate CLOSE/DONE state, they
# return False directly from within their last active state instead).
# route_objection() must never fire here: those states already return False
# unconditionally to end the call, and route_objection returning True
# (should_continue) in a terminal state would incorrectly keep the call
# open instead of hanging up.
_TERMINAL_STATES = {"CLOSE", "DONE"}


async def route_objection(
    session,
    call_uuid: str,
    prefix: str,
    state: str,
    intents: list[str],
    transcript: str,
) -> bool | None:
    """
    Shared pre-state objection dispatcher — Phase 1c skeleton for the
    objection-handling redesign. Checked once per turn in each of the 4
    handlers, immediately after that handler's check_hard_rejection() call
    and before its own state-specific chain.

    `prefix` identifies both the flow AND the plan/voice in one value —
    "ra"/"rb"/"rc" (react Call1, one of 3 plans), "c2", "c3", or "fresh" —
    the same prefix each handler already threads through to play_key() for
    its own state-specific keys, and the same one PREFIX_VOICE_MAP uses to
    resolve which of the 3 obj_repeat_generic_{voice} variants matches
    whatever voice is already speaking in this call.

    Priority order below is repeat > price > trust > not-interested > timing.
    Stale note removed 2026-08-13: this docstring used to say only category 2
    (repeat) was live and 3-6 were stubs -- that's no longer true, all of
    categories 2-6 below are live, gap-only dispatch (each scoped to the
    specific (prefix, state) pairs whose own chain didn't already handle
    that intent correctly; see each category's own comment for its
    allowlist and why). Categories that already had correct handling in
    their state's own chain are deliberately left alone here.

    Returns None if this dispatcher did not handle the turn -- caller must
    continue into its own state chain unchanged, exactly as before this
    function existed. Returns a bool should_continue value if it did handle
    the turn.
    """
    if state in _TERMINAL_STATES:
        return None

    # not_interested has a pre-existing, CORRECT resolution at every
    # (prefix, state) route_objection() is ever invoked for, with exactly
    # one exception: (c2, WA_CHECK). fresh_cta's not_interested is caught
    # upstream by check_hard_rejection() before this function is even
    # reached; every other flow's state chain already handles it and
    # pre-dates this whole redesign (confirmed by a full pass over every
    # (prefix, state) pair this function sees, not just the ones already
    # wired -- see conversation notes). (c2, WA_CHECK) is the one true
    # exception: its not_interested handling doesn't pre-date this redesign
    # either -- it's a gap filled in category 5 below, in this SAME round --
    # so it's genuinely "new" in the same sense repeat/price/trust are
    # there too, and the originally-agreed priority order (repeat > price >
    # trust > not-interested > timing) is exactly what should decide a
    # same-utterance collision between two categories that are BOTH new,
    # same as any other such collision -- no guard needed there.
    #
    # Everywhere else, letting repeat/price/trust/timing (all checked below,
    # all "higher priority" than not-interested on paper) fire instead of an
    # ALREADY-CORRECT not_interested resolution would silently swallow a
    # decline and keep the call going -- a worse failure than the reverse.
    # The priority order governs which NEW fix wins when several gaps are
    # new; it was never meant to let a new fix outrank content that already
    # worked.
    _defer_to_not_interested = "not_interested" in intents and not (prefix == "c2" and state == "WA_CHECK")

    # -1. awaiting_callback_time -- added 2026-08-19. Confirmed live on a real
    #     test call: category 12 below (callback_later) asks "kaunsa time
    #     aapke liye theek rahega?" and promises "main usi waqt call kar
    #     loongi" -- but the call previously just ended right there
    #     (`return False`), regardless of any answer, because nothing in this
    #     system captures or acts on a stated callback time. The customer
    #     never got a chance to answer a question the script explicitly
    #     asked. Fixed at the mechanism level: category 12 now sets this flag
    #     and keeps the call open instead of ending it; this block runs FIRST
    #     on the very next turn, before any other intent handling, so the
    #     answer isn't misrouted into appointment_confirm's SHOWROOM-VISIT
    #     date logic (a real risk -- "shaam ko"/"kal" are bare appointment_
    #     confirm keywords, and confirming a callback time is NOT the same
    #     thing as confirming a store visit). Deferred to the normal
    #     not_interested handling below if the customer declined instead of
    #     answering (check_hard_rejection() already catches an explicit DNC/
    #     decline before route_objection() is even reached; this only guards
    #     against a softer not_interested still reaching this far).
    #     UPDATED 2026-08-19 -- real callback-time scheduling MVP. Now tries
    #     _parse_callback_time_bucket() (see that function's own comment) to
    #     turn a small set of clear phrasings into an actual UTC datetime,
    #     persisted via _mark_callback_requested() onto outbound_leads.
    #     callback_requested_at (supabase_migration_callback_requested_at.sql)
    #     -- outbound_orchestrator.py's get_due_callback_leads() polls that
    #     column and actually fires the call when it comes due. Deliberately
    #     switched the noted-vs-unclear line choice to key off the PARSER'S
    #     success specifically, not the looser "does this look date-ish at
    #     all" signal the original fix used -- obj_callback_time_noted_*
    #     says "main usi samay call karne ki koshish karungi" (I'll try to
    #     call at that time), which is only honest to say when a specific
    #     time was actually captured and scheduled, not just recognized as
    #     vaguely time-shaped.
    if getattr(session, "awaiting_callback_time", False):
        session.awaiting_callback_time = False
        if not _defer_to_not_interested:
            voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
            _callback_at = _parse_callback_time_bucket(transcript)
            if _callback_at is not None:
                await play_key(call_uuid, f"obj_callback_time_noted_{voice}", session)
                asyncio.create_task(_mark_callback_requested(session, call_uuid, _callback_at))
            else:
                await play_key(call_uuid, f"obj_callback_time_unclear_{voice}", session)
            return False

    # 0a. legal_threat -- added 2026-08-15 (Agent_Replies_Warm.md rewrite).
    #     Highest priority in this function: a caller threatening legal or
    #     regulatory action is a real compliance-risk signal, not an
    #     ordinary objection, so it's checked before repeat/price/trust and
    #     fires unconditionally (not deferred to not_interested). Terminal,
    #     same family as DNC. NOTE: only the script + call-end behavior is
    #     implemented here -- NEW_CATEGORIES_PROPOSAL.md flagged that this
    #     should ALSO flag the lead for real human review (who sees it,
    #     where it surfaces); that mechanism doesn't exist anywhere in this
    #     codebase and is NOT built by this change. Today a legal_threat
    #     call just ends politely and otherwise leaves no trace beyond the
    #     normal call transcript/logs -- flagging for a real decision later.
    if "legal_threat" in intents:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_legal_threat_generic_{voice}", session)
        return False

    # 0b. wrong_number -- added 2026-08-15. Terminal: apologize once, end
    #     the call. Deliberately NOT written to any new lead status (e.g. a
    #     `wrong_number` status distinct from DNC) -- see the documented
    #     silent-status-write-failure pattern (status values not present in
    #     the DB's CHECK constraint fail silently on write). Adding a new
    #     status value needs a real DB-side decision first, not a guess
    #     baked into this dispatcher. Today this only ends the call
    #     politely; the orchestrator's retry logic still treats this number
    #     like any other unconfirmed lead and may call it again later.
    if "wrong_number" in intents:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_wrong_number_generic_{voice}", session)
        return False

    # 0c. person_unavailable -- added 2026-08-15. Terminal for THIS call
    #     only (not DNC, not wrong_number -- same lead, just wrong moment).
    #     No callback-time capture on this path -- that's callback_later's
    #     job, kept separate since this is "not even the right person," not
    #     "right person, bad time."
    if "person_unavailable" in intents:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_person_unavailable_generic_{voice}", session)
        return False

    # 0d. not_my_customer -- added 2026-08-15. NOT terminal -- this could
    #     still be a real prospect who just isn't a *repeat* customer, so
    #     acknowledge and let the call continue naturally (no state change);
    #     if they push back again the existing not_interested handling
    #     downstream takes over, same as the doc's "if they push back again,
    #     treat as not_interested" guidance.
    if "not_my_customer" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_not_my_customer_generic_{voice}", session)
        return True

    # 0e. bare_negative -- added 2026-08-15. Exact-whole-utterance check
    #     (see _is_bare_negative()'s docstring near _is_filler_continuer
    #     above), not a keyword in `intents` -- a bare "nahi"/"no" doesn't
    #     say no to *what*, so this asks one soft clarifying question rather
    #     than treating it as a decline. Checked only when nothing else in
    #     `intents` already matched anything above (a bare "no" alongside
    #     another real signal should let that signal drive routing, not be
    #     shadowed by this).
    if not intents and _is_bare_negative(transcript) and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_bare_negative_generic_{voice}", session)
        return True

    # 1. hard-rejection/DNC -- already handled by check_hard_rejection() at
    #    each call site, immediately before this function is called. Not
    #    repeated here; this dispatcher only runs for turns that were NOT a
    #    hard rejection.

    # 2. repeat / didn't-understand -- LIVE.
    if "repeat" in intents and not _defer_to_not_interested:
        if prefix in ("ra", "rb", "rc") and state == "GREETING":
            # That state's own branch already plays {p}_greet_repeat and
            # then continues on into offer_main -- richer than a bare
            # acknowledgment, and the only state across all 4 flows with
            # real content-specific repeat handling today (per the coverage
            # audit). Left owned by that branch rather than duplicated here.
            return None
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_repeat_generic_{voice}", session)
        return True

    # 3. price -- LIVE, gap-only (Phase 2a). Allowlist, not denylist: only
    #    the 2 states with NO existing price handling are listed here.
    #    PRESENT_OFFER/WHATSAPP_CTA (react_call1) and DATE_ASK (call2) all
    #    already handle expensive/online_cheaper correctly in their own state
    #    chains and must be left alone -- NOT returning None unconditionally
    #    here on a non-match, so a turn that doesn't match the price
    #    allowlist still falls through to the trust check below rather than
    #    exiting route_objection() entirely (a turn with both an unmatched
    #    price mention AND a matched trust mention must still get the trust
    #    branch).
    if any(i in intents for i in ("expensive", "online_cheaper")) and not _defer_to_not_interested:
        if prefix == "fresh" and state == "APPOINTMENT":
            await play_key(call_uuid, "fresh_price", session)
            return True
        if prefix == "c3" and state == "GREETING":
            # Reuses DECISION_DATE's c3_obj_price verbatim, but does NOT
            # inherit its "no re-argue, end the call" behavior -- that's
            # deliberate at DECISION_DATE because the customer has already
            # been asked to visit and pushed back; at GREETING they haven't
            # been asked anything yet, so ending the call here would cut off
            # a possibly-interested lead before Call3 ever makes its actual
            # ask. Continue the ask instead, same treatment as the trust
            # reuses below.
            await play_key(call_uuid, "c3_obj_price", session)
            session.c3_state = "DECISION_DATE"
            return True
        # Not a price gap state -- that state's own chain already handles
        # this correctly. Fall through (do not return) so trust is still
        # checked below.

    # 4. trust/skepticism -- LIVE, gap-only (Phase 2a). Same allowlist
    #    discipline as price above.
    if "trust_issue" in intents and not _defer_to_not_interested:
        if prefix == "fresh" and state == "APPOINTMENT":
            await play_key(call_uuid, "fresh_trust", session)
            return True
        if prefix == "c2" and state == "WA_CHECK":
            # Reuses DATE_ASK's c2_obj_scam verbatim -- its date-ask ("kab
            # free honge, ek date bata dijiye") fits WA_CHECK fine. Must
            # advance state to DATE_ASK here (WA_CHECK's own chain does this
            # unconditionally for every other outcome) -- otherwise the
            # customer's date reply next turn lands back in WA_CHECK, which
            # doesn't check dates at all, and gets silently dropped for a
            # turn. Same bug shape as the original DATE_ASK-vs-WA_CHECK
            # finding, just relocated if left unhandled.
            await play_key(call_uuid, "c2_obj_scam", session)
            session.c2_state = "DATE_ASK"
            return True
        if prefix == "c3" and state == "GREETING":
            # Reuses DECISION_DATE's c3_obj_scam verbatim; same state-advance
            # requirement as c2/WA_CHECK above, for the same reason.
            await play_key(call_uuid, "c3_obj_scam", session)
            session.c3_state = "DECISION_DATE"
            return True
        # Not a trust gap state -- fall through.

    # 5. not-interested -- LIVE, gap-only (Phase 2b). Only (c2, WA_CHECK) --
    #    every other (prefix, state) pair's not_interested is already
    #    handled correctly by its own state chain (or, for fresh_cta, by
    #    check_hard_rejection before this function is ever reached) and
    #    must not be touched here. Note this check does NOT need to test
    #    _defer_to_not_interested itself -- that guard exists to keep
    #    categories 2-4 out of the way of THIS category, not the reverse.
    if "not_interested" in intents:
        if prefix == "c2" and state == "WA_CHECK":
            # Reuses GREETING/DATE_ASK's existing not_interested treatment
            # verbatim -- terminal, matches every other not_interested
            # resolution in this flow.
            # Two plays combined into one native Vobiz sequence -- see
            # _vobiz_play()'s docstring (confirmed live 2026-08-13: two
            # separate play_key() calls let the second interrupt the first).
            await play_keys(call_uuid, ["c2_obj_not_interested", "c2_close_declined"], session)
            return False
        # Not a gap state -- the state chain already resolves this
        # correctly (categories 2-4 above already deferred via
        # _defer_to_not_interested, so falling through here lands cleanly
        # on that existing, correct resolution). Fall through.

    # 6. timing/deferral (busy/sochna_hai) -- LIVE, gap-only (Phase 2b).
    #    Same _defer_to_not_interested discipline as categories 2-4: a
    #    combined "not interested, I'm busy" utterance must resolve as
    #    not_interested (a decline), not get acknowledged as a soft defer
    #    that keeps the call going.
    if any(i in intents for i in ("busy", "sochna_hai")) and not _defer_to_not_interested:
        # GREETING-stage gap (react_a/b/c, call2, call3): mirrors the
        # established two-play convention every other GREETING-stage intent
        # already uses there (confusion_who etc: acknowledge -> immediately
        # deliver that flow's own next default line, same turn) -- rather
        # than a bare acknowledge-and-silently-advance, which would be its
        # own small inconsistency with every sibling intent at these states.
        # c2/c3 already have dedicated, correct, call-ending "busy" handling
        # in their own GREETING chains (c2_close_busy / c3_close_busy) that
        # PRE-DATES this redesign -- unlike ra/rb/rc, which have no GREETING
        # busy/sochna_hai handling of their own at all, so both intents are
        # genuine gaps there. A prior version of this branch used the
        # unscoped combined busy-or-sochna_hai condition for c2/c3 too and
        # silently shadowed that pre-existing branch (route_objection()
        # always runs before the state chain) -- confirmed via
        # production-replay audit (2026-07-19): c2_close_busy/c3_close_busy
        # became unreachable by any spoken "busy" utterance (only 3x
        # consecutive silence could still reach them), and a customer saying
        # "busy hoon" got pushed into a date-ask instead of the correct,
        # softer call-ending response -- a regression this redesign itself
        # introduced, not a pre-existing gap. Scoped to sochna_hai for c2/c3
        # here, same precise-scoping discipline as the PRESENT_OFFER/
        # APPOINTMENT sochna_hai-only checks further below.
        if state == "GREETING" and (
            prefix in ("ra", "rb", "rc")
            or (prefix in ("c2", "c3") and "sochna_hai" in intents)
        ):
            # Fixed 2026-08-19 -- confirmed live on a real test call: two
            # SEPARATE play_key() calls here let the second interrupt the
            # first before it finished playing (the customer heard
            # obj_timing_greet_generic cut off mid-sentence by the offer
            # pitch), and each separate Vobiz Play API round-trip added its
            # own latency on top (2.43s + 4.99s back-to-back in the
            # confirmed call, vs one combined request) -- the exact same
            # interrupt/latency bug already found and fixed at every OTHER
            # two-line branch in this file via play_keys() (see e.g.
            # WHATSAPP_CTA's qa_keys handling, PRESENT_OFFER's sochna_hai
            # branch below), just missed at this one call site. Combined
            # into one native multi-URL Vobiz sequence like everywhere else.
            voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
            _first_key = f"obj_timing_greet_generic_{voice}"
            if prefix in ("ra", "rb", "rc"):
                session.react_state = "PRESENT_OFFER"
                asyncio.create_task(fire_whatsapp(session, call_uuid))
                await play_keys(call_uuid, [_first_key, f"{prefix}_offer_main"], session,
                                 log_transcript=[True, False])
            elif prefix == "c2":
                session.c2_state = "WA_CHECK"
                await play_keys(call_uuid, [_first_key, "c2_wa_check"], session,
                                 log_transcript=[True, False])
            elif prefix == "c3":
                session.c3_state = "DECISION_DATE"
                await play_keys(call_uuid, [_first_key, "c3_decision_date"], session,
                                 log_transcript=[True, False])
            return True
        # Call2 WA_CHECK gap: single-play, self-contained (asks for a date
        # itself, same shape as its own invite_seen/invite_resend siblings --
        # WA_CHECK's own branches are single-play, unlike GREETING's).
        if prefix == "c2" and state == "WA_CHECK":
            await play_key(call_uuid, "c2_obj_timing", session)
            session.c2_state = "DATE_ASK"
            return True
        # react_a/b/c PRESENT_OFFER gap: sochna_hai ONLY -- busy is already
        # handled correctly by this state's own chain ({p}_obj_busy). Must
        # check "sochna_hai" specifically here, not the outer busy-or-
        # sochna_hai condition, or a pure "busy" turn would incorrectly get
        # sochna_hai's content instead of falling through to its own
        # correct handling (caught by test_objection_routing.py during
        # review -- an earlier draft used the outer condition unscoped and
        # a "busy hoon" transcript at PRESENT_OFFER got ra_obj_think instead
        # of ra_obj_busy). Reuse {p}_obj_think verbatim, full sibling
        # treatment matching busy/expensive/online_cheaper at this exact
        # state (advance -> WHATSAPP_CTA -> {p}_wa_cta -> fire WA) -- not a
        # shortened version of it.
        if prefix in ("ra", "rb", "rc") and state == "PRESENT_OFFER" and "sochna_hai" in intents:
            await play_keys(call_uuid, [f"{prefix}_obj_think", f"{prefix}_wa_cta"], session, log_transcript=[True, False])
            session.react_state = "WHATSAPP_CTA"
            await fire_whatsapp(session, call_uuid)
            return True
        # react_a/b/c APPOINTMENT gap: sochna_hai ONLY -- busy is already
        # grouped with not_interested in the state chain there. Scoped for
        # the same reason as PRESENT_OFFER above, even though today the two
        # outcomes happen to coincide (both end at {p}_close) -- precise
        # scoping matters if that content ever diverges later. Joins the
        # existing not_interested+busy -> {p}_close terminal group;
        # late-stage, matches its neighbors (same "no re-argue past the
        # ask" principle already applied to Call3 GREETING price/trust).
        if prefix in ("ra", "rb", "rc") and state == "APPOINTMENT" and "sochna_hai" in intents:
            session.react_state = "CLOSE"
            await play_key(call_uuid, f"{prefix}_close", session)
            return False
        # Not a timing gap state -- fall through. Call2 DATE_ASK and Call3
        # DECISION_DATE are both intentionally left to their own documented
        # vague-reask-then-close fallthrough (see comments at those sites) --
        # not gaps to fix, deliberate design choices.

    # 7. escalate (manager request) -- added 2026-08-14, closing a real gap:
    #    detected correctly by detect_intents() for months, never checked by
    #    any state's routing. No live manager transfer exists in this
    #    system, so the reply says so honestly instead of implying one.
    #    Not terminal -- acknowledges and the call continues. Deferred to a
    #    hard decline like every other category above.
    if "escalate" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_escalate_generic_{voice}", session)
        return True

    # 8. personal_question ("are you a bot/human/AI") -- added 2026-08-14,
    #    same gap shape as escalate: detected, never routed. Answered
    #    honestly (it is an AI) rather than dodged, then continues.
    if "personal_question" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_personal_question_generic_{voice}", session)
        return True

    # 9/10. wa_ok / wa_prefers -- added 2026-08-14. Both already feed lead
    #    scoring in supabase_calling.py (interest_signals, customer_response)
    #    but neither ever produced a spoken acknowledgment -- a customer
    #    explicitly saying "haan bhejo" or "WhatsApp pe hi baat karo" got
    #    silently absorbed into scoring with nothing said back. Light-touch
    #    only: acknowledge, don't change state, don't touch the scoring
    #    logic these already feed.
    if "wa_ok" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_wa_ok_generic_{voice}", session)
        return True
    if "wa_prefers" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_wa_prefers_generic_{voice}", session)
        return True

    # 11. already_called (customer complains about call frequency) -- added
    #     2026-08-15. Not terminal -- acknowledge once, call continues.
    #     NEW_CATEGORIES_PROPOSAL.md's routing note also proposed widening
    #     this lead's retry cooldown in supabase_calling.py as a direct
    #     consequence of this intent (distinct from ordinary disinterest) --
    #     NOT implemented here, script-only for now.
    if "already_called" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_already_called_generic_{voice}", session)
        return True

    # 12. callback_later -- added 2026-08-15. NEW_CATEGORIES_PROPOSAL.md
    #     flagged this needs a real decision: there's no callback-time slot
    #     anywhere in this system (appointment_confirm captures a showroom
    #     visit DATE, not a callback TIME), so honoring "call me at 6pm"
    #     would need new orchestrator capability, not just a line.
    #
    #     UPDATED 2026-08-19 -- confirmed live on a real test call: this line
    #     explicitly asks "kaunsa time aapke liye theek rahega?" and promises
    #     "main usi waqt call kar loongi", but `return False` ended the call
    #     immediately after asking, before the customer could answer at all
    #     -- the script promised to listen, the code never did. Now sets
    #     awaiting_callback_time and keeps the call open (`return True`) so
    #     the very next turn -- handled by the -1 block above, BEFORE any
    #     other intent dispatch -- actually hears the answer. Still doesn't
    #     capture/act on the stated time anywhere real (see the flag's own
    #     comment) -- that's still separate, larger work -- this only fixes
    #     the immediate "asks a question, hangs up before hearing the
    #     answer" bug.
    if "callback_later" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_callback_later_generic_{voice}", session)
        session.awaiting_callback_time = True
        return True

    # 13. lang_pref_english/lang_pref_hindi/lang_pref_other -- rewritten
    #     2026-08-18 now that real English support exists
    #     (knowledge_react_abc_en.py) -- an explicit request always wins
    #     instantly, same principle as the auto-detect gating in
    #     webhook.py's respond() (see that block's comment): don't wait for
    #     detect_lang() confidence to catch up, flip session.lang right away
    #     and lock the streak high so the very next ordinary turn doesn't
    #     immediately flip it back on some ambiguous signal. Not terminal,
    #     no react/call2/call3 STATE change -- only the language changes.
    if "lang_pref_english" in intents and not _defer_to_not_interested:
        session.lang = "en"
        session.lang_streak = 5
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_lang_pref_english_generic_{voice}", session)
        return True
    if "lang_pref_hindi" in intents and not _defer_to_not_interested:
        session.lang = "hi"
        session.lang_streak = 5
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_lang_pref_hindi_generic_{voice}", session)
        return True
    if "lang_pref_other" in intents and not _defer_to_not_interested:
        # Punjabi (or anything else unsupported) -- honest, doesn't touch
        # session.lang either way.
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_lang_pref_other_generic_{voice}", session)
        return True

    # 14. uncertain ("pata nahi"/"shayad") -- added 2026-08-15. Treated like
    #     a softer sochna_hai: offer WhatsApp info, don't push for a date,
    #     no state change.
    if "uncertain" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_uncertain_generic_{voice}", session)
        return True

    # 15. Product/commercial Q&A fallbacks -- added 2026-08-15. Same honest-
    #     deflection pattern as the existing ask_valuation/ask_price_range
    #     handling: acknowledge the question, don't fabricate a number,
    #     route to WhatsApp/showroom. Not terminal, no state change.
    #     ask_invoice_gst is answered directly (plain yes/no a retailer
    #     should just confirm), everything else defers.
    _QA_FALLBACK_INTENTS = (
        "ask_emi", "ask_payment_method", "ask_warranty", "ask_delivery_charge",
        "ask_return_policy", "ask_bargain", "ask_invoice_gst",
        "ask_product_quality", "ask_pickup_logistics", "ask_call_recorded",
    )
    for _qa_intent in _QA_FALLBACK_INTENTS:
        if _qa_intent in intents and not _defer_to_not_interested:
            voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
            await play_key(call_uuid, f"obj_{_qa_intent}_generic_{voice}", session)
            return True

    # 16. reschedule_appointment / cancel_appointment -- added 2026-08-15,
    #     script-only. NEW_CATEGORIES_PROPOSAL.md's routing notes call for
    #     real state logic here (clearing session.appointment_confirmed and
    #     re-opening the same date-capture flow appointment_confirm already
    #     uses for reschedule; clearing the confirmed date and moving to a
    #     soft, still-eligible-for-recontact close for cancel) -- NOT
    #     implemented. This only plays the acknowledgment line; it does not
    #     touch session.appointment_confirmed or any stored visit date, so a
    #     "reschedule" request today gets a warm verbal reply but the old
    #     date/confirmation state is left exactly as it was.
    if "reschedule_appointment" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_reschedule_appointment_generic_{voice}", session)
        return True
    if "cancel_appointment" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_cancel_appointment_generic_{voice}", session)
        return True

    # 17. want_human -- added 2026-08-15, same honesty principle as escalate
    #     (category 7 above): no live transfer capability exists, so this
    #     says so plainly and redirects to the Customer Relations Head
    #     callback (same not-yet-backed promise documented on
    #     obj_escalate_generic above) rather than pretending a transfer is
    #     happening.
    if "want_human" in intents and not _defer_to_not_interested:
        voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
        await play_key(call_uuid, f"obj_want_human_generic_{voice}", session)
        return True

    return None


_TOKEN_EDGE_PUNCT = ".,!?;:'\"()[]{}—-–।॥*"


# Verb-conjugation equivalence classes -- added 2026-08-19 as the structural
# fix for a recurring bug class: 5 categories (callback_later, want_human,
# cancel_appointment, ask_pickup_logistics, wa_ok) were each found missing the
# polite "kar sakte hain" question form of a verb whose imperative form
# ("karo") was already covered, discovered one real customer call at a time
# (Pratham's "baad mein call kar sakte hain?"). Hand-enumerating every
# inflection of every verb in every category is a losing game against Hindi/
# Hinglish morphology (the same request can be phrased as karo/karna/karenge/
# kariye/kijiye/kar sakte hain/karni hai, in Latin or Devanagari) -- so instead
# of listing more phrases, this normalizes surface inflections of the handful
# of verbs that actually drive this domain's action-request categories down to
# ONE canonical spelling, applied identically to keyword tokens and transcript
# tokens (same mechanism as the chandrabindu/nuqta normalization above), so a
# single keyword written in its existing spelling transparently also matches
# every inflected variant.
#
# Deliberately an explicit, exact-token equivalence table -- not a generic
# suffix-stripping stemmer. A real stemmer risks silently merging unrelated
# words that happen to share a suffix (Devanagari conjuncts especially punish
# naive suffix rules, per _tokenize()'s own \w-splitting lesson above), and
# would be unverifiable against the small, specific verb vocabulary this file
# actually uses. Every group below is grounded in verb forms that actually
# occur in REACT_ABC_INTENTS/SHARED_INTENTS today (see the audit that produced
# this change), not hypothetical conjugations.
#
# Each canonical target is the spelling ALREADY used by existing keywords in
# knowledge_react_abc.py (karo/sakte/do/करो/सकते/दो/करवाओ are all pre-existing
# literal keyword tokens) -- so this needs zero changes to that file to take
# effect; it purely widens what a keyword written once already matches.
#
# Deliberately EXCLUDES 1st-person future/declarative forms (karunga/lunga/
# jaunga/करूंगा -- "I will do X") from the request-verb group below, even
# though they share the same "karna" root: those are a different speech act
# ("I will complain" is a threat/statement, not "please do X for me"/"can you
# do X"), used today only inside dnc/legal_threat phrases where mixing them
# into the same equivalence class as callback_later/want_human/etc.'s request
# forms would let a customer's self-declaration falsely satisfy a request-
# shaped keyword. Kept out on purpose -- verified via the negation/false-
# positive sweep in Part 1's audit that no test case relies on merging them.
_VERB_FORM_ALIASES = {
    # "karna" (to do) -- 2nd-person imperative / honorific-imperative /
    # infinitive / polite-future / "need to" forms, all requesting or
    # asking about an action. Canonical target: "karo" (existing keyword
    # spelling, 28 occurrences -- the most common form already in the file).
    "karna": "karo", "kar": "karo", "kariye": "karo", "kijiye": "karo",
    "karte": "karo", "karta": "karo", "karti": "karo", "karni": "karo",
    "karoge": "karo", "karenge": "karo", "karein": "karo", "karen": "karo",
    "करना": "करो", "कर": "करो", "करिये": "करो", "कीजिए": "करो", "कीजिये": "करो",
    "करते": "करो", "करता": "करो", "करती": "करो", "करनी": "करो",
    "करोगे": "करो", "करेंगे": "करो", "करें": "करो",
    # "sakna" (can/able to) -- auxiliary "can you" forms. Canonical target:
    # "sakte" (existing spelling, 10 occurrences).
    "sakta": "sakte", "sakti": "sakte", "sako": "sakte",
    "sakoge": "sakte", "sakenge": "sakte",
    "सकता": "सकते", "सकती": "सकते", "सको": "सकते",
    "सकोगे": "सकते", "सकेंगे": "सकते",
    # "dena" (to give/allow) -- used in wa_ok/pickup-logistics-style "send
    # it"/"give it" requests. Canonical target: "do" (existing spelling, 17
    # occurrences). Bare "do" itself is left as the target, not remapped --
    # it's also the English word "do", and this table only ever normalizes
    # INTO it, never rewrites it away, so the pre-existing English-collision
    # risk (unchanged from before this fix) isn't made any worse.
    "dena": "do", "dijiye": "do", "de": "do",
    "देना": "दो", "दीजिए": "दो", "दीजिये": "दो", "दे": "दो",
    # "karwana"/"karana" (causative -- "have someone do X") -- only used in
    # want_human today ("insaan se baat karwao"/"karwa sakte hain"). Canonical
    # target: "karwao" (existing spelling).
    "karao": "karwao", "karwa": "karwao", "karwaoge": "karwao",
    "कराओ": "करवाओ", "करवा": "करवाओ",
}


def _tokenize(text: str) -> list[str]:
    # Split on WHITESPACE ONLY, then trim punctuation off each token's edges —
    # deliberately not regex \w+/\b. Both \w and \b are unreliable inside
    # Devanagari conjuncts: the virama (्, U+094D) has Unicode category Mn,
    # which Python's \w does not include, so `\w+` (and `\b`) treat it as a
    # separator and incorrectly split "सर्कल" (circle) into "सर" + "कल" —
    # confirmed live, this let "कल" (tomorrow) false-match inside "सर्कल".
    # Hindi text already uses real whitespace between words (unlike e.g. Thai),
    # so splitting on whitespace never breaks a word internally — punctuation
    # only needs trimming from token edges, not stripped mid-token.
    #
    # Chandrabindu (ँ, U+0901) normalized to anusvara (ं, U+0902) 2026-08-19 --
    # confirmed live: STT returned "बिज़ी हूँ" (chandrabindu) for a real "busy
    # hoon" turn, but every "busy" keyword in this file spells it "हूं"
    # (anusvara) -- 212 anusvara occurrences vs 5 chandrabindu across
    # knowledge_react_abc.py, so normalizing toward anusvara here fixes the
    # mismatch for every affected keyword at once (this file's whole nasal
    # vocabulary: हूं/हैं/मैं/नहीं/वहां/कहां/...) instead of hunting down and
    # duplicating each one individually. Applied to BOTH sides of every match
    # automatically since _phrase_in_tokens() tokenizes the keyword through
    # this same function.
    text = text.replace("ँ", "ं")
    # Nuqta-bearing consonants (ज़/फ़/ख़/ग़/क़/ड़/ढ़ -- borrowed sounds from
    # Persian/Arabic/English loanwords) normalized to their base consonant
    # 2026-08-19 -- confirmed live: STT returned "बिजी" (no nuqta) for a real
    # "busy" turn, but the keyword list spells it "बिज़ी" (with nuqta) --
    # same shape as the chandrabindu/anusvara fix above, just a different
    # pair of interchangeable-in-casual-writing characters. Native speakers
    # routinely drop the nuqta in informal Hindi (texting, casual writing),
    # and evidently so does STT sometimes -- normalizing both sides toward
    # the base consonant here fixes it for every affected keyword at once.
    for _nuqta, _base in (("ज़", "ज"), ("फ़", "फ"), ("ख़", "ख"), ("ग़", "ग"), ("क़", "क"), ("ड़", "ड"), ("ढ़", "ढ")):
        text = text.replace(_nuqta, _base)
    tokens = []
    for raw in text.lower().split():
        tok = raw.strip(_TOKEN_EDGE_PUNCT)
        if tok:
            tokens.append(_VERB_FORM_ALIASES.get(tok, tok))
    return tokens


# Bare acknowledgment/hesitation sounds -- not a real answer, but not silence
# either. Business decision 2026-08-04: let the conversation keep moving on
# these rather than reprompting (reprompting on "hmm" reads as naggy), but
# deliberately NOT wired into detect_intents()/REACT_ABC_INTENTS -- these
# must never reach react_intents_seen. interest_signals/cta_accepted/
# lead_score/lead_tier are all computed by counting react_intents_seen
# (supabase_calling.py _compute_reactivation_score / call_summaries payload),
# and the 2026-08-02 ground-truth follow-up on this exact "acknowledgment-only"
# signal (haan/ji/ok, already in the positive/wa_ok lists) showed several
# false hot/warm leads, two of which blocked the caller's number. Filler
# should move the call forward without being counted as a stronger version
# of that same already-unreliable signal.
# "हेलो"/"hello" added 2026-08-13 -- knowledge.py's ACK_WORDS already treats
# a bare "hello" mid-call as "caller checking if agent is there", not a real
# question; this file's filler list never had the same carve-out. Confirmed
# live on the Pratham call (919911117660): a customer utterance the STT
# rendered as "हेलो" landed in APPOINTMENT state, got sent to the ungrounded
# LLM-answer path as if it were a genuine question, and got the canned "I
# don't have this detail, I'll WhatsApp it" non-sequitur instead of being
# treated as a check-in and re-asked for the date like any other filler.
# "ye"/"ये"/"yeh"/"यह" added 2026-08-14 -- knowledge.py's ACK_WORDS already
# labels these "pickup sounds" (a casual "yeah?"/half-heard ack, not the
# demonstrative "this"). Confirmed live, same session, campaign ra: STT
# rendered a customer utterance as "ये है।" then, next turn, "ये।" -- both
# matched nothing and burned a full LLM-fallback round trip each time before
# falling back to "sorry, didn't catch that". Deliberately NOT added to the
# substring-matched "positive" list in knowledge_react_abc.py -- bare
# "यह"/"ye" there would collide with real questions like "ye kitna hai"
# (how much is this), the same false-positive class already rejected for
# "यह" in that file. Safe here specifically because
# _is_filler_continuer() only fires when EVERY token in the utterance is a
# filler word -- "ye kitna hai" has two non-filler tokens and still falls
# through to real intent matching untouched.
_FILLER_CONTINUER_WORDS = {"hmm", "hmmm", "हम्म", "हम्म्म", "hello", "हेलो",
                            "ye", "ये", "yeh", "यह"}


def _is_filler_continuer(text: str) -> bool:
    tokens = _tokenize(text)
    return bool(tokens) and all(tok in _FILLER_CONTINUER_WORDS for tok in tokens)


# bare_negative -- added 2026-08-15 (NEW_CATEGORIES_PROPOSAL.md's own
# caution, carried over): a bare "no" needs exact-whole-utterance matching,
# same mechanism as _is_filler_continuer() above, NOT a substring/token
# keyword in knowledge_react_abc.py's REACT_ABC_INTENTS -- "nahi"/"no" as a
# token-matched keyword would false-fire inside completely unrelated
# sentences that merely contain the word ("mujhe nahi pata", "abhi nahi
# lekin sochunga"), where the customer isn't giving a bare negative reply at
# all. Only fires when EVERY token in the utterance is one of these bare
# negation words -- multi-token utterances fall through to real intent
# matching untouched, same discipline as _is_filler_continuer.
_BARE_NEGATIVE_WORDS = {"nahi", "nahin", "na", "नहीं", "ना", "नही", "no"}


def _is_bare_negative(text: str) -> bool:
    tokens = _tokenize(text)
    return bool(tokens) and all(tok in _BARE_NEGATIVE_WORDS for tok in tokens)


_BRIDGING_FILLERS = {"bhi", "भी", "mein", "में", "hi", "ही", "toh", "तो"}

# Used by _phrase_in_tokens()'s windowed-matching negation guard below --
# deliberately a smaller set than _OPTOUT_NEGATION_WORDS/_BARE_NEGATIVE_WORDS
# (no "no"/"nahin" alone) since this only needs to catch the single-token
# "mat/nahi/not/don't immediately before the verb" shape, not the broader
# opt-out-anywhere-nearby matching those other detectors do.
_WINDOWED_NEGATION_WORDS = {"nahi", "nahin", "mat", "not", "don't", "dont", "ना", "नहीं", "मत"}


# Categories excluded from _phrase_in_tokens()'s windowed (any-order,
# negation-blind) fallback -- added 2026-08-19 after finding a real false
# positive: "hindi ke bare mein baat mat karo abhi" ("don't talk about
# Hindi right now") matched lang_pref_hindi's "hindi mein baat karo",
# because the windowed check just requires all 4 tokens present nearby, in
# any order, with no awareness that "mat" sitting right before "karo"
# REVERSES the meaning. Every other windowed-eligible category just plays
# an acknowledgment line if mis-triggered -- low-consequence even when
# wrong. These three are uniquely dangerous to false-positive on: they
# instantly flip session.lang for the rest of the call with no further
# confirmation step (see webhook.py's language-tracking block). Scoped
# narrowly to just these three rather than teaching the windowed fallback
# about negation generally, which would need to reason about every
# possible negation word/position for every one of the ~40 other 3+-token
# keyword phrases in this file -- not worth the added complexity for
# categories where a false match just plays a low-stakes acknowledgment.
_WINDOWED_MATCH_EXCLUDED_INTENTS = {"lang_pref_english", "lang_pref_hindi", "lang_pref_other"}


def _phrase_in_tokens(keyword: str, boundary_text: str, allow_windowed: bool = True) -> bool:
    kw_tokens = _tokenize(keyword)
    if not kw_tokens:
        return False
    if f" {' '.join(kw_tokens)} " in boundary_text:
        return True
    # Fallback for 2-token phrases only: allow exactly one common bridging
    # filler word between the two keyword tokens -- e.g. "address bhi batao"
    # should still match keyword "address batao", "online mein sasta" should
    # still match "online sasta". Confirmed gap via regression audit
    # (2026-07-15): natural filler-word insertions caused real phrase misses.
    # Deliberately NOT generalized to longer phrases or arbitrary gap words
    # (e.g. negation words like "na"/"ना" are excluded on purpose) -- kept
    # narrow to avoid opening new false-positive surface across the ~200
    # other keyword phrases in this file.
    if len(kw_tokens) == 2:
        for filler in _BRIDGING_FILLERS:
            if f" {kw_tokens[0]} {filler} {kw_tokens[1]} " in boundary_text:
                return True
    # Added 2026-08-19 -- fallback for 3+ token phrases: same problem class
    # as the 2-token bridging fallback above (natural speech doesn't always
    # keep a phrase's words adjacent/in order), but confirmed live this
    # session on LONGER phrases the 2-token mechanism doesn't cover at all:
    # "मुझे किसी इंसान से बात कराओ, मैनेजर से।" didn't match keyword
    # "मैनेजर से बात" because the real utterance had "से" reordered to the
    # end (बात...मैनेजर से, not मैनेजर से बात); "Can you please speak to me
    # in English?" didn't match "please speak in english" because "to me"
    # sits between "speak" and "in". Patching each such case individually
    # doesn't scale -- this is the same shape of gap recurring across
    # unrelated keywords. Now checks whether all of the keyword's tokens
    # appear together, IN ANY ORDER, within a bounded window of the
    # transcript (window size = keyword length + 3, i.e. up to 3 extra/
    # inserted words tolerated) -- verified against both real failures
    # above before shipping. Scoped to 3+ token phrases specifically
    # (unlike the 2-token case): requiring 3+ SPECIFIC words to all appear
    # together is a strong, low-false-positive signal even unordered --
    # scattered single/paired common words wouldn't accidentally satisfy 3
    # simultaneous constraints. Bounded window (not "anywhere in the
    # utterance") keeps it from matching across unrelated clauses in a long,
    # multi-topic sentence.
    if len(kw_tokens) >= 3 and allow_windowed:
        boundary_tokens = boundary_text.split()
        kw_set = set(kw_tokens)
        window = len(kw_tokens) + 3
        last_kw_token = kw_tokens[-1]
        for i in range(len(boundary_tokens)):
            window_tokens = boundary_tokens[i:i + window]
            if not kw_set.issubset(window_tokens):
                continue
            # Negation guard -- added 2026-08-19 after a systematic sweep
            # (user asked for a deeper pass on language-hallucination risk,
            # which led to auditing every windowed-eligible category, not
            # just the language ones): confirmed live, "appointment cancel
            # MAT karo" (please DON'T cancel my appointment) matched
            # "appointment cancel karo" anyway, because the windowed check
            # only verifies all required tokens are present nearby -- it had
            # no idea "mat" sitting right before the final token (usually
            # the action verb in Hindi's SOV order) reverses the request.
            # Same root cause as the lang_pref false positive fixed earlier
            # today, but that fix excluded 3 whole categories from windowed
            # matching -- category-by-category exclusion doesn't scale once
            # the same bug shows up in cancel_appointment/
            # reschedule_appointment/want_human/escalate too (all found in
            # this same sweep), and blanket-excluding those would have
            # thrown away the real reordering fix they needed (e.g.
            # escalate's "मैनेजर से बात" reordering). Fixed at the
            # mechanism instead: within whichever window matched, find
            # every occurrence of the keyword's LAST token (its usual verb/
            # action word) and reject the match only if EVERY occurrence is
            # immediately preceded by a negation word -- a real match
            # elsewhere in a longer, unrelated utterance still succeeds,
            # only the genuinely-negated reading is blocked. Verified this
            # rejects all 4 confirmed live false positives while leaving
            # the non-negated escalate/want_human reordering fixes intact.
            verb_positions = [j for j, tok in enumerate(window_tokens) if tok == last_kw_token]
            if verb_positions and all(
                j > 0 and window_tokens[j - 1] in _WINDOWED_NEGATION_WORDS
                for j in verb_positions
            ):
                continue
            return True
    return False


# ── Callback-time scheduling MVP -- added 2026-08-19 ────────────────────────
# Maps a small set of clear, unambiguous Hindi/Hinglish callback-time
# phrasings to a concrete datetime, so a stated "kal subah call karna" can
# actually be scheduled (see supabase_migration_callback_requested_at.sql +
# outbound_orchestrator.py's get_due_callback_leads()) instead of only being
# acknowledged verbally (obj_callback_time_noted_*, built earlier the same
# day, which never persisted anywhere).
#
# Deliberately NOT general free-form time parsing -- explicit product
# decision: a misread time fires a real call at the wrong moment for a real
# customer, which is worse than the previous "doesn't schedule anything"
# gap. Recognizes only the phrasings below; anything else returns None and
# the existing honest obj_callback_time_unclear_* fallback is unchanged.
IST = ZoneInfo("Asia/Kolkata")

# Mirrors outbound_orchestrator.py's CALL_START_HOUR/CALL_END_HOUR_DEFAULT
# (10:00-20:00 IST) -- kept as a local copy rather than importing that module
# here, since webhook_reactivation.py doesn't otherwise depend on it and the
# two processes run independently (this file only ever WRITES the computed
# timestamp; the orchestrator is what reads and acts on it later).
_CALLBACK_CALL_START_HOUR = 10
_CALLBACK_CALL_END_HOUR = 20


def _clamp_to_calling_window(dt_ist: datetime) -> datetime:
    """Push a computed callback time into the 10:00-20:00 IST window. Before
    the window -> same day at window-open. At/after the window -> next day
    at window-open."""
    if dt_ist.hour < _CALLBACK_CALL_START_HOUR:
        return dt_ist.replace(hour=_CALLBACK_CALL_START_HOUR, minute=0, second=0, microsecond=0)
    if dt_ist.hour >= _CALLBACK_CALL_END_HOUR:
        return (dt_ist + timedelta(days=1)).replace(hour=_CALLBACK_CALL_START_HOUR, minute=0, second=0, microsecond=0)
    return dt_ist


# anchor word -> hour offset a bare "N baje" (o'clock) digit combines with,
# e.g. "shaam 6 baje" -> (6 % 12) + 12 = 18:00. Only these 4 anchors (day-
# part words already established elsewhere in this file's keyword lists) --
# a bare digit with no anchor is NOT confidently AM/PM and falls through to
# None (the honest "unclear" fallback), not a guess.
_CALLBACK_TIME_ANCHOR_HOURS = {
    "subah": 0, "सुबह": 0,
    "dopeher": 12, "दोपहर": 12,
    "shaam": 12, "शाम": 12,
    "raat": 12, "रात": 12,
}
_CALLBACK_CLOCK_TIME_RE = re.compile(r"\b(\d{1,2})\s*(?:baje|बजे)\b")


def _parse_callback_time_bucket(transcript: str, now: datetime | None = None) -> datetime | None:
    """
    Returns a concrete UTC datetime for a small set of clear callback-time
    phrasings, or None if the transcript doesn't confidently match one.
    `now` is injectable for testing (must be tz-aware); defaults to the
    real current time.
    """
    now_ist = (now or datetime.now(timezone.utc)).astimezone(IST)
    tomorrow_ist = now_ist + timedelta(days=1)
    tokens = _tokenize(transcript)
    boundary_text = f" {' '.join(tokens)} "

    # Most specific phrases first -- "kal subah"/"kal shaam" must not fall
    # through to the bare "kal" bucket below.
    if any(_phrase_in_tokens(p, boundary_text) for p in ("kal subah", "कल सुबह")):
        target = tomorrow_ist.replace(hour=10, minute=30, second=0, microsecond=0)
        return _clamp_to_calling_window(target).astimezone(timezone.utc)

    if any(_phrase_in_tokens(p, boundary_text) for p in ("kal shaam", "कल शाम")):
        target = tomorrow_ist.replace(hour=18, minute=0, second=0, microsecond=0)
        return _clamp_to_calling_window(target).astimezone(timezone.utc)

    if any(_phrase_in_tokens(p, boundary_text) for p in
           ("aaj shaam", "shaam ko", "आज शाम", "शाम को")):
        target = now_ist.replace(hour=18, minute=0, second=0, microsecond=0)
        if target <= now_ist:
            target += timedelta(days=1)
        return _clamp_to_calling_window(target).astimezone(timezone.utc)

    # Explicit clock time + an unambiguous day-part anchor word in the same
    # utterance (e.g. "shaam 6 baje", "subah 10 baje").
    m = _CALLBACK_CLOCK_TIME_RE.search(transcript.lower())
    if m:
        digit = int(m.group(1))
        if 1 <= digit <= 12:
            anchor_hour = next((h for a, h in _CALLBACK_TIME_ANCHOR_HOURS.items() if a in tokens), None)
            if anchor_hour is not None:
                hour24 = (digit % 12) + anchor_hour
                target = now_ist.replace(hour=hour24, minute=0, second=0, microsecond=0)
                if target <= now_ist:
                    target += timedelta(days=1)
                return _clamp_to_calling_window(target).astimezone(timezone.utc)

    # Bare "kal" alone (no subah/shaam qualifier, already handled above) --
    # unqualified-daytime default, a documented judgment call, not a guess
    # at a specific hour the customer never stated.
    if "kal" in tokens or "कल" in tokens:
        target = tomorrow_ist.replace(hour=13, minute=0, second=0, microsecond=0)
        return _clamp_to_calling_window(target).astimezone(timezone.utc)

    return None


async def _mark_callback_requested(session, call_uuid: str, callback_at_utc: datetime) -> None:
    """
    Persists the computed callback time onto outbound_leads.
    callback_requested_at, matched by phone + tenant_id -- same pattern as
    _mark_wa_sent() above. outbound_orchestrator.py's get_due_callback_leads()
    polls this column and fires the actual call once it's due.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    raw_phone = getattr(session, "customer_phone", "")
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
                json={"callback_requested_at": callback_at_utc.isoformat()},
            )
        logger.info(f"[{call_uuid}] outbound_lead → callback_requested_at={callback_at_utc.isoformat()} phone={raw_phone}")
    except Exception as exc:
        logger.error(f"[{call_uuid}] callback_requested_at persist error: {exc}")


_OPTOUT_NEGATION_WORDS = {"मत", "ना", "नहीं", "mat", "na", "nahi", "nahin",
                           # English coverage added 2026-07-15 -- the Hindi/Hinglish-only
                           # negation set left fluent English opt-outs ("please don't call
                           # me again", "stop calling me") completely undetected, the same
                           # failure mode as the दोबारा कॉल ना करें miss above, just in the
                           # other language. Confirmed via regression audit.
                           "don't", "dont", "not"}
_OPTOUT_CALL_WORDS     = {"कॉल", "फोन", "call", "phone",
                           # "calling"/"contact" variants -- "stop calling me"/"don't
                           # contact me" use these instead of the bare "call"/"phone" noun.
                           "calling", "phoning", "contact", "contacting"}
_OPTOUT_WINDOW         = 3
_CLAUSE_SPLIT_RE       = re.compile(r"[,।;.!?]+")
# "phone"/"फोन" is ambiguous -- it can mean the handset ("phone charge nahi ho
# raha" = my phone isn't charging) as well as "call". Confirmed live via
# regression audit: an unrelated phone-battery complaint false-triggered dnc
# because "phone" and "nahi" landed in the same proximity window. Only
# "phone"/"फोन" get this check -- "call"/"कॉल"/"contact" aren't ambiguous the
# same way, so their recall is untouched.
_OPTOUT_DEVICE_NOUNS = {"charge", "चार्ज", "battery", "बैटरी", "network",
                         "नेटवर्क", "signal", "सिग्नल", "kharab", "ख़राब", "खराब"}
# "koi baat nahi" / "koi problem nahi" / "koi issue nahi" ("never mind"/"no
# problem") are common Hindi/Hinglish idioms where "nahi" closes out an
# unrelated clause rather than negating whatever comes next. The clause
# split above only helps when STT punctuation is present — it usually isn't
# — so "koi baat nahi call karke bata dena jab discount ho" (no comma) still
# lands "nahi" and "call" in the same window and false-triggered dnc.
# Confirmed via direct testing before this detector was reused in a second
# call flow (webhook.py). Scoped to negations immediately preceded by one of
# these precursor nouns, not a general reduction of window recall.
_OPTOUT_NEUTRAL_PRECURSORS = {"baat", "बात", "problem", "प्रॉब्लम", "issue",
                               "इशू", "tension", "टेंशन", "zaroorat", "ज़रूरत", "जरूरत"}


def _is_explicit_optout(text: str) -> bool:
    """
    Token-proximity fallback for "don't call [me] again" opt-outs, catching
    phrasing variants the literal dnc keyword list doesn't enumerate —
    confirmed live: "दोबारा कॉल ना करें" (customer's actual wording, call
    3cf6a87b) used "ना करें" negation, a different conjugation from the only
    listed phrase "दोबारा कॉल मत करना", and went completely undetected; the
    agent kept pursuing a showroom date after an explicit opt-out.

    Requires a negation word and a call-word within a small window of the
    SAME clause — text is split on comma/danda/sentence punctuation first, so
    two unrelated clauses that happen to each contain one of the two words
    don't bridge together. Caught in testing: "koi baat nahi, call karke
    bata dena jab discount ho" (a benign non-opt-out — "never mind" is one
    clause, "call and let me know" is a separate one) false-positived under
    a naive whole-utterance window before this clause split was added. The
    _OPTOUT_NEUTRAL_PRECURSORS check below covers the same phrase WITHOUT the
    comma, which real STT transcripts usually omit.

    NOTE: deliberately does NOT include "stop" or "बंद" in the negation-word
    set — "stop"/"बंद" are prohibitive verbs, not negations, and are too
    context-dependent for a blind proximity window ("call disconnected
    suddenly"/"कॉल बंद हो गई" would false-positive). "Stop calling"-style
    phrasing is instead covered by exact phrases in REACT_ABC_INTENTS["dnc"].
    """
    for clause in _CLAUSE_SPLIT_RE.split(text):
        tokens = _tokenize(clause)
        for i in range(len(tokens)):
            window = tokens[i:i + _OPTOUT_WINDOW]
            neg_positions = [k for k, w in enumerate(window) if w in _OPTOUT_NEGATION_WORDS]
            if not neg_positions:
                continue
            valid_negation = any(
                (i + k == 0 or tokens[i + k - 1] not in _OPTOUT_NEUTRAL_PRECURSORS)
                for k in neg_positions
            )
            if not valid_negation:
                continue
            for j, w in enumerate(window):
                if w not in _OPTOUT_CALL_WORDS:
                    continue
                if w in ("phone", "फोन"):
                    abs_idx = i + j
                    next_tok = tokens[abs_idx + 1] if abs_idx + 1 < len(tokens) else ""
                    if next_tok in _OPTOUT_DEVICE_NOUNS:
                        continue  # handset, not a call -- e.g. "phone charge nahi ho raha"
                return True
    return False


# Proximity-window fallback for "I didn't receive/get [the WhatsApp message]" --
# same shape as _is_explicit_optout() above, for the same reason: confirmed live
# (calls c51fc807.../09c970a7..., 2026-08-01/02) that the exact-phrase
# wa_no_whatsapp list ("whatsapp nahi hai"/"no whatsapp") misses how people
# actually phrase this -- "mujhe nahi mili"/"abhi tak nahi aaya" -- and misses
# it even when they say "WhatsApp" explicitly alongside it ("व्हाट्सएप पे...
# मुझे नहीं मिली"), because exact-phrase matching needs the negation and
# "whatsapp" pre-listed as one contiguous phrase. Reuses _OPTOUT_NEGATION_WORDS
# (same negation set, no need for a second list) and _CLAUSE_SPLIT_RE.
_WA_RECEIPT_WORDS = {"मिली", "mili", "मिला", "mila", "आया", "aaya", "आई", "aayi",
                     "आयी", "aai", "received", "आयी है", "मिली है"}
_WA_NOT_RECEIVED_WINDOW = 4

# "आपने व्हाट्सएप तो किया ही नहीं" ("you didn't even send WhatsApp") -- accuses
# the AGENT of not sending, using "किया" (did), not the "receive" framing
# ("mili"/"aaya") _WA_RECEIPT_WORDS above already covers. Confirmed live
# 2026-08-13, matched nothing. "किया" alone is far too generic to add to
# _WA_RECEIPT_WORDS (it's the ordinary "did" verb, would false-positive on
# any unrelated "didn't do X" statement) -- scoped separately, requiring
# "व्हाट्सएप"/"whatsapp" in the same clause as evidence this specific "किया"
# is actually about the WhatsApp send, not something else.
_WA_SEND_VERB_WORDS = {"किया", "kiya", "किया है", "kiya hai"}
_WHATSAPP_MENTION_WORDS = {"व्हाट्सएप", "whatsapp", "व्हाट्सप्प", "watsapp"}


def _is_wa_not_received(text: str) -> bool:
    for clause in _CLAUSE_SPLIT_RE.split(text):
        tokens = _tokenize(clause)
        has_whatsapp_mention = any(w in _WHATSAPP_MENTION_WORDS for w in tokens)
        for i, w in enumerate(tokens):
            if w not in _OPTOUT_NEGATION_WORDS:
                continue
            window = tokens[max(0, i - _WA_NOT_RECEIVED_WINDOW):i + _WA_NOT_RECEIVED_WINDOW + 1]
            if any(rw in window for rw in _WA_RECEIPT_WORDS):
                return True
            if has_whatsapp_mention and any(rw in window for rw in _WA_SEND_VERB_WORDS):
                return True
    return False


# Proximity-window fallback for price questions, same shape as
# _is_wa_not_received() above -- confirmed live 2026-08-13: ask_price_range's
# exact-phrase list ("price kya hai") missed "क्या प्राइस रेंज है" (what's
# your price range?) purely because of word order ("kya X hai" vs "X kya
# hai"), and the customer got reprompted twice then a generic bailout
# instead of an answer. Hindi word order is genuinely flexible here, so
# exact-phrase matching will keep missing variants one at a time -- proximity
# instead: any price-word within a small window of any question-word, order
# doesn't matter.
_PRICE_WORDS = {"price", "प्राइस", "rate", "रेट", "रेंज", "range", "दाम", "कीमत"}
_PRICE_QUESTION_WORDS = {"kya", "क्या", "kitna", "कितना", "kitne", "कितने", "kitni", "कितनी"}
_PRICE_QUESTION_WINDOW = 4


def _is_price_question(text: str) -> bool:
    for clause in _CLAUSE_SPLIT_RE.split(text):
        tokens = _tokenize(clause)
        for i, w in enumerate(tokens):
            if w not in _PRICE_WORDS:
                continue
            window = tokens[max(0, i - _PRICE_QUESTION_WINDOW):i + _PRICE_QUESTION_WINDOW + 1]
            if any(qw in window for qw in _PRICE_QUESTION_WORDS):
                return True
    return False


# Same proximity approach for "which products/furniture is this on" --
# ask_offer_scope's exact-phrase list has the identical word-order fragility
# _is_price_question() above was built to fix. Requires a product-word AND a
# "which/all"-word together (not bare "kaun" alone, which is what caused the
# confusion_who false-positive earlier this same day) -- co-occurrence with
# a product word is what makes this specific, safe to broaden.
_OFFER_SCOPE_PRODUCT_WORDS = {"furniture", "फर्नीचर", "product", "प्रोडक्ट", "item",
                              "आइटम", "cheez", "चीज़", "चीज"}
_OFFER_SCOPE_QUESTION_WORDS = {"kaun", "कौन", "kis", "किस", "sab", "सब", "sari",
                               "सारी", "sabhi", "सभी", "har", "हर", "kaunse", "कौनसे"}
_OFFER_SCOPE_WINDOW = 4


def _is_offer_scope_question(text: str) -> bool:
    for clause in _CLAUSE_SPLIT_RE.split(text):
        tokens = _tokenize(clause)
        for i, w in enumerate(tokens):
            if w not in _OFFER_SCOPE_PRODUCT_WORDS:
                continue
            window = tokens[max(0, i - _OFFER_SCOPE_WINDOW):i + _OFFER_SCOPE_WINDOW + 1]
            if any(qw in window for qw in _OFFER_SCOPE_QUESTION_WORDS):
                return True
    return False


def detect_intents(transcript: str) -> list[str]:
    t = transcript.lower().strip()
    if not t:
        return []
    tokens = _tokenize(t)
    boundary_text = f" {' '.join(tokens)} "

    if any(_phrase_in_tokens(kw, boundary_text) for kw in REACT_ABC_INTENTS.get("dnc", [])) or _is_explicit_optout(t):
        return ["dnc"]
    matched = []
    for intent, keywords in REACT_ABC_INTENTS.items():
        if intent == "dnc":
            continue
        _allow_windowed = intent not in _WINDOWED_MATCH_EXCLUDED_INTENTS
        if keywords and any(_phrase_in_tokens(kw, boundary_text, allow_windowed=_allow_windowed) for kw in keywords):
            matched.append(intent)
    # Also check shared intents (appointment / Q&A)
    for intent, keywords in SHARED_INTENTS.items():
        if keywords and any(_phrase_in_tokens(kw, boundary_text) for kw in keywords):
            matched.append(intent)
    if "wa_no_whatsapp" not in matched and _is_wa_not_received(t):
        matched.append("wa_no_whatsapp")
    if "ask_price_range" not in matched and _is_price_question(t):
        matched.append("ask_price_range")
    if "ask_offer_scope" not in matched and _is_offer_scope_question(t):
        matched.append("ask_offer_scope")
    # Added 2026-08-19, per explicit product decision: "baad mein call
    # karo/karna" (call me later, no specific time) should be treated as an
    # explicit callback request, not the generic "busy" deferral -- but
    # "busy"'s own keyword list already has bare "baad mein" (correct for
    # standalone use, e.g. "abhi nahi, baad mein baat karte hain"), so both
    # intents match this exact phrase simultaneously. "busy" sits earlier in
    # route_objection()'s priority chain (and several states already have
    # their own native busy-handling that runs before route_objection() is
    # even reached), so without this, callback_later's more specific signal
    # would get silently shadowed no matter where it's positioned in that
    # chain. Suppress "busy" here instead -- same idiom already used for
    # not_interested vs busy/timing (_defer_to_not_interested in
    # route_objection()), just resolved at detection time instead of dispatch
    # time since "busy" isn't centrally dispatched the way those are.
    if "callback_later" in matched and "busy" in matched:
        matched.remove("busy")
    # Added 2026-08-19, found auditing the keyword.md coverage-widening merge:
    # "kar do"/"de do" are wa_ok keywords (generic "do it"/"give it" -- meant
    # to catch a bare approval to send WhatsApp), but they're also just the
    # last two words of many unrelated imperative requests -- the new
    # reschedule_appointment/cancel_appointment phrasings this merge added
    # ("doosri date de do", "appointment cancel kar do", "shift kar do
    # appointment") all end the same way. wa_ok sits earlier in
    # route_objection()'s priority chain (checked unconditionally, no
    # allowlist scoping like expensive/trust have), so confirmed live: a
    # customer asking to cancel/reschedule their appointment got "Bilkul ji,
    # abhi bhej rahi hoon WhatsApp par" (okay, sending the WhatsApp now) --
    # a non-sequitur reply to an appointment-change request. Same suppression
    # idiom as callback_later/busy above -- reschedule/cancel are always the
    # more specific, more actionable signal when both match the same turn;
    # wa_ok here would only ever have played an acknowledgment anyway (the
    # actual WhatsApp send is triggered by fire_whatsapp() elsewhere in each
    # flow, not gated on this intent), so suppressing it loses no real
    # functionality.
    if ("reschedule_appointment" in matched or "cancel_appointment" in matched) and "wa_ok" in matched:
        matched.remove("wa_ok")
    return matched


# Added 2026-08-19 -- call2's DATE_ASK/GREETING and call3's GREETING/
# DECISION_DATE have no qa_keys answer-loop at all (unlike react_a/b/c's
# PRESENT_OFFER/WHATSAPP_CTA/APPOINTMENT states), and no dedicated {c2,c3}_q_*
# cached-audio keys exist for them either -- confirmed by checking
# knowledge_react_abc.py directly. So when detect_intents() correctly
# recognizes one of these informational-question categories in those states,
# there was nothing to answer it with; the turn silently fell through to
# that state's default flow-advance/reask logic instead, as if the customer
# had said nothing recognizable. Used below to widen the LLM-fallback trigger
# in those 4 states beyond "intents is completely empty" to also cover "the
# only thing recognized was a Q&A-style question this state can't answer
# itself" -- deliberately NOT a blanket "intents didn't lead to an early
# return" check, which would also re-trigger the slower LLM path for bare
# low-content replies like "haan theek hai" (intents=['positive']) that
# aren't actually questions and would just burn 1.5-4s to correctly resolve
# to UNCLEAR before landing on the exact same reask anyway.
_INFORMATIONAL_QA_INTENTS = {
    "confusion_who", "ask_location", "ask_timings", "ask_name",
    "ask_valuation", "ask_delivery", "ask_price_range", "ask_offer_scope",
}


def _only_unanswered_qa_intents(intents: list[str]) -> bool:
    """True if `intents` is empty, or contains only informational Q&A
    categories this state has no scripted/cached answer for (see
    _INFORMATIONAL_QA_INTENTS above) -- either way, worth trying the LLM
    fallback rather than silently falling through to the default flow.

    "positive" is discounted from the check (neither counted toward nor
    against it) -- confirmed live via testing: "showroom kahan hai bhai
    batao zara" matches both ask_location AND positive (bare "batao" is a
    positive keyword), and a naive subset check against intents including
    "positive" rejected this obviously-real question. But "positive" alone
    (e.g. a bare "haan theek hai" acknowledgment, not a real question) must
    still NOT trigger the fallback -- that would waste 1.5-4s classifying
    something that was never a question before landing on the same reask
    anyway. So: strip "positive" first, then the fallback only fires if
    something is left AND that something is entirely informational-Q&A."""
    if not intents:
        return True
    meaningful = set(intents) - {"positive"}
    return bool(meaningful) and meaningful <= _INFORMATIONAL_QA_INTENTS


_groq_async_client: "AsyncGroq | None" = None


# Kill switch for the 4 call sites below -- deploy gate (test 4 of Design 1's
# test plan) came back 35/66 false positives on real customer transcripts,
# 20/20 on meaningless placeholder text -- confirmed non-discriminating in
# its current prompt/model form, not a subtle miscalibration. False by
# design until that's revisited: `and` short-circuits, so
# _llm_classify_refusal() is never actually invoked (no LLM call, no latency
# cost) while this stays False. Function + all 4 call sites + the test suite
# stay intact so re-enabling later is a one-line flip, not a rebuild.
_LLM_REFUSAL_FALLBACK_ENABLED = False


def _get_groq_async_client() -> "AsyncGroq":
    # Lazy, not module-level: constructing eagerly at import time means any
    # bare `import webhook_reactivation` (every test file does this) raises
    # immediately if GROQ_API_KEY isn't in the process env yet -- production
    # is fine (webhook.py's load_dotenv() runs before this module is ever
    # imported), but tests don't go through that entry point.
    global _groq_async_client
    if _groq_async_client is None:
        _groq_async_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq_async_client


_REFUSAL_CLASSIFY_PROMPT = """Yeh ek customer ka jawab hai ek outbound sales call mein
(furniture store). Sirf ek sawaal ka jawab do: kya yeh jawab ek MANA/REFUSAL/DECLINE hai
— customer engage nahi karna chahta, chahe kisi bhi wajah se (umar, zaroorat nahi,
resource nahi, seedhe "nahi" ya koi bhi tarika)?

Customer ka jawab: "{utterance}"

Sirf ek word mein jawab do: "YES" (agar refusal/decline hai) ya "NO" (agar nahi)."""


async def _llm_classify_refusal(t: str, call_uuid: str) -> bool:
    """
    Fallback-only classifier — called by each handler ONLY when
    detect_intents() found nothing at all (intents == []) for a non-empty
    turn. Widens what can produce "not_interested" without adding new
    plumbing: every downstream consumer (check_hard_rejection(),
    route_objection(), each state chain, finalize_call()'s not_interested
    fallback) already keys off that exact string being present in intents,
    regardless of where it came from.

    Fails open (returns False = "not a refusal, continue normally") on any
    error or timeout — a missed classification just means the call continues
    exactly as it did before this function existed; it must never be able to
    force a false DNC via a broken API call.
    """
    try:
        resp = await asyncio.wait_for(
            _get_groq_async_client().chat.completions.create(
                model="groq/compound-mini",
                messages=[{"role": "user", "content": _REFUSAL_CLASSIFY_PROMPT.format(utterance=t)}],
                max_tokens=3,
                temperature=0,
            ),
            timeout=2.0,
        )
        answer = resp.choices[0].message.content.strip().upper()
        return answer.startswith("Y")
    except Exception as exc:
        logger.warning(f"[{call_uuid}] refusal-classify LLM call failed, treating as non-refusal: {exc}")
        return False


# ── Generative LLM fallback for genuinely unmatched turns ──────────────────
#
# Added 2026-08-13. Business decision: no finite keyword list covers natural
# speech -- every fix earlier this same day was the same shape (a real
# question worded a way the list didn't anticipate, matched nothing, got a
# generic reprompt/deflection instead of an answer). Confirmed across
# multiple real and test calls: "which furniture is the offer on", "what's
# your price range", "what's your name" (in English), etc. This replaces the
# blind "sorry, didn't understand" reprompt for turns detect_intents()
# couldn't place with an LLM call, grounded ONLY in the facts below, so it
# can actually answer novel phrasings instead of just re-asking.
#
# Cost/latency tradeoff, deliberate: this only fires when nothing else
# matched (the fast, free, ~5-10ms cached-audio path handles everything
# else unchanged). This path costs a real API round-trip (~1-3s) plus live
# TTS generation instead of instant cached audio -- accepted as the price of
# actually answering arbitrary questions instead of deflecting them.
#
# Lesson applied from _llm_classify_refusal() above, which is currently
# disabled after failing calibration (35/66 false positives on real
# transcripts). REDESIGNED 2026-08-13 after this function's own first
# version failed the same way on its own test pass: asked to classify
# in-scope-vs-not AND generate AND self-censor in one call, a small model
# under that much load got it wrong -- confirmed live, it fabricated "haan,
# offer online bhi hai" (yes, the offer's online too) for a fact that
# doesn't exist anywhere in FACTS, and separately glued a correct answer to
# the unclear-speech reprompt line in the same reply. Split into two
# narrower calls instead: classify first (ANSWERABLE / UNKNOWN / UNCLEAR,
# one word out), then only generate free text for the ANSWERABLE case,
# where real facts exist to ground it. UNKNOWN and UNCLEAR use fixed,
# pre-written strings -- never LLM-generated -- so neither failure mode
# observed above is structurally possible for those two cases anymore.
_REACT_LLM_FACTS = """STORE: Krishna Furniture. Priya (aap) ek existing/purane customer ko
personally call kar rahi hain.
OFFER: Purana furniture exchange karne par uski value milti hai, aur naye furniture par 25%
discount — total milakar 43 se 50% tak saving ho sakti hai. Koi fixed end-date nahi hai.
CATEGORIES COVERED BY THIS OFFER: sofa, bed, dining table, wardrobe, chair.
STARTING PRICES (sirf yeh, aur koi number kabhi mat bolo — OWNER-CONFIRMED price
sheet, Sep 2026, replaces the earlier website-observed figures used here; see
new_flows_pricing.py PRICE_LIST for the same numbers as structured data):
  - Sofa: per-seat pricing — 1 seater ₹7,000-8,000, 2 seater ₹15,000 se, 3 seater
    ₹21,000-24,000, sofa-cum-bed ₹35,000 se shuru
  - Bed: single ₹15,000 se, double ₹25,000 se shuru (no confirmed king/storage figure)
  - Dining set: sheesham 4 seater ₹30,000 se, 6 seater ~₹40,000 se (UNCONFIRMED --
    owner's own sheet flagged this one, do not state it with full confidence),
    8 seater ₹50,000 se; marble 4 seater ₹40,000 se, 6 seater ₹65,000 se,
    8 seater ₹80,000 se
  - Wardrobe: ₹25,000 se shuru, wooden wardrobe ₹15,000 se
  - Chair (lounge, part of sofa seating range): koi alag confirmed price nahi hai --
    per-seat sofa starting point (₹7,000-8,000) bolo, exact price confirm karke
    baad mein batao
TV units, coffee/center tables, cabinets, side tables, aur home décor: on request,
koi price mat bolo yeh sab ke liye.
SHOWROOMS: Sector 14 Gurgaon, Delhi, Noida — Monday se Sunday, subah 10 baje se raat 8 baje tak.
NOT COVERED (explicitly UNKNOWN, never answer these): EMI/installment, delivery cost ya time, warranty,
online ordering, cash on delivery, old furniture buyback/exchange terms, payment methods, discount codes,
GST/tax, refund/return policy."""

_REACT_LLM_REPROMPT_TEXT = "Oh, maaf kijiye ji — aapki awaaz thodi clear nahi aayi. Ek baar phir se bata dijiye please?"
# 2026-08-15 warm rewrite -- Agent_Replies_Warm.md's ★ "Random / can't-answer
# question" fallback (its own "big missing piece" callout): apologizes,
# stays honest (no fabricated answer), offers the Customer Relations Head
# callback instead of a flat "I don't have this detail." Same not-yet-backed
# promise as obj_escalate_generic/obj_want_human_generic above -- nothing
# captures or acts on the implied "theek rahega?" yes/no here either, this
# is a single fixed string same as before, just warmer and honest about
# needing to escalate rather than implying WhatsApp will have the answer.
_REACT_LLM_UNKNOWN_TEXT = "Ohh, yeh accha sawaal hai ji — sach kahun toh iska sahi jawab main abhi confirm kar ke dena chahungi, taaki aapko kuch galat na bataun. Agar aap kahein, toh main hamari Customer Relations Head se aapke liye ek call schedule karwa deti hoon — woh aapko poora aur sahi jawab de dengi. Theek rahega?"

# 2026-08-22 -- English versions, used only by fresh_cta's _try_fresh_llm_qa
# so far (threaded via the new `lang` param below) -- the rest of the LLM-
# fallback call sites (react_a/b/c/call2/call3) still default to lang="hi"
# unchanged, since only fresh_cta's English path has been verified live.
# Confirmed live 2026-08-22: an English-speaking caller's real question fell
# through this whole pipeline with lang hardcoded to "hi" throughout --
# generation prompt Hindi-only AND play_dynamic_text's TTS call Hindi-only
# regardless of who was speaking -- closing that gap for fresh_cta here.
_REACT_LLM_REPROMPT_TEXT_EN = "Oh, sorry — I didn't quite catch that clearly. Could you say that once more, please?"
_REACT_LLM_UNKNOWN_TEXT_EN = "That's a good question — honestly, I'd like to confirm the exact answer before I tell you something wrong. If you're okay with it, I'll set up a call with our Customer Relations Head — she'll give you the complete, correct answer. Does that work?"

# Added 2026-08-19 -- fresh_cta (product-follow-up campaign) audit found it
# had ZERO LLM-fallback coverage, unlike react_a/b/c/call2/call3. Couldn't
# just reuse _REACT_LLM_FACTS as-is: that block asserts "existing/purane
# customer" + "exchange offer, 25% discount" framing that doesn't apply here
# -- a fresh_cta lead is a NEW inquiry who asked about one specific product
# via WhatsApp, not an existing customer being offered an exchange, and
# nothing in FRESH_CTA_SCRIPT's own script text (fresh_price/fresh_trust/
# fresh_objection) asserts a specific discount percentage for this funnel.
# Deliberately conservative rather than assuming the same offer applies:
# kept to what's verifiably true regardless of campaign (the 3 real base
# prices, showroom locations/timings) and marked offer/discount specifics as
# explicitly UNKNOWN here, rather than risk the LLM asserting a discount
# figure never actually communicated to this lead.
_FRESH_LLM_FACTS = """STORE: Krishna Furniture. Priya (aap) ek lead ko follow-up call kar rahi hain jisne
WhatsApp par ek specific product mein interest dikhaya tha -- yeh call ab budget, timeline, aur
store-visit date poochhne ke liye hai, koi cold sales pitch nahi.
CATEGORIES (owner-confirmed price sheet, Sep 2026 -- see new_flows_pricing.py PRICE_LIST):
sofa/seating, bed, wardrobe, dining set, office table, office chair, mattress, recliner.
ON REQUEST (no confirmed price, never state a number, say "confirm karke batati hoon"):
TV unit, coffee/center table, cabinet, side table, home décor, ottoman/pouffe, bedroom chair.
Lounge/lobby chairs are part of the sofa seating range, not a separate priced category.
Interior design consultation bhi available hai -- agar koi is baare mein poochhe, unka budget poochho
aur bataao ki hamare manager unhe personally contact karenge (koi price/scope detail mat do, yeh sirf
handoff hai).
STARTING PRICES (sirf yeh, aur koi number kabhi mat bolo -- kisi bhi cheez ka jo yahan nahi hai).
Replaced 2026-09-14 with the OWNER-CONFIRMED price sheet (Sep 2026), which supersedes the
2026-08-23 figures and the 2026-09-14-morning website-catalog-verified figures used here
earlier the same day -- per the owner's own note, this sheet runs BELOW the website-listed
prices on purpose:
  - Sofa (per seat): 1 seater ₹7,000-8,000 se, 2 seater ₹15,000 se, 3 seater ₹21,000-24,000 se,
    sofa-cum-bed ₹35,000 se
  - Bed: single ₹15,000 se, double ₹25,000 se (no confirmed king/storage figure -- don't state one)
  - Wardrobe: ₹25,000 se, wooden wardrobe ₹15,000 se
  - Dining set: sheesham 4 seater ₹30,000 se, 6 seater ~₹40,000 se (UNCONFIRMED, flagged by the
    owner's own sheet -- hedge this one, e.g. "around ₹40,000, let me confirm exactly"),
    8 seater ₹50,000 se; marble 4 seater ₹40,000 se, 6 seater ₹65,000 se, 8 seater ₹80,000 se
  - Office table: ₹10,000-12,000 se
  - Office chair: ₹6,000 se
  - Mattress: single ₹10,000-12,000 se, double ₹20,000-25,000 se
  - Recliner: manual ₹25,000 se, power/recliner ₹35,000 se
  - Lounge/lobby chair: no distinct confirmed price -- use the sofa per-seat starting point
    (₹7,000-8,000) and offer to confirm the exact figure
SHOWROOMS (real 5-store list, 2026-08-23): do stores Gurgaon mein (Atul Kataria Chowk, Sector 14, Old
Delhi Road; aur Sector 69, Sohna Road, Vatika Chowk ke paas), ek Noida mein (A-2, Sector 10), ek
Faridabad mein (Sector 28 Metro Station ke saamne), ek Delhi mein (Ghitorni).
NOT COVERED (explicitly UNKNOWN, never answer these, chahe kitna bhi simple lage): koi bhi item jo
upar CATEGORIES mein nahi hai (agar poochha jaaye toh keh do "iska price abhi available nahi hai,
WhatsApp par confirm kar ke bataungi" -- kabhi number mat banao), koi bhi discount percentage ya
exchange-offer ke exact terms (is lead ko kaunsa offer specifically pitch hua tha, yeh yahan nahi diya
gaya hai), interior design ka price/scope, EMI/installment, delivery cost ya time, warranty, online
ordering, cash on delivery, old furniture buyback/exchange terms, payment methods, GST/tax,
refund/return policy, showroom timings (yeh yahan nahi diye gaye)."""


def _build_classify_prompt(facts: str, utterance: str) -> str:
    return f"""Neeche ek customer ka jawab hai ek outbound sales call mein (Krishna
Furniture). Aapke paas sirf yeh FACTS hain:

{facts}

Customer ne kaha: "{utterance}"

Is jawab ko EXACTLY teen categories mein se ek mein classify karo:
- ANSWERABLE: ek saaf, samajh aane wala sawaal/statement hai JISKA jawab upar diye FACTS se seedha mil sakta hai.
- UNKNOWN: ek saaf, samajh aane wala sawaal hai, lekin uska jawab FACTS mein kahin nahi hai (jaise EMI,
  delivery time, online availability, warranty, koi bhi cheez jo FACTS mein explicitly nahi likhi).
- UNCLEAR: garbled, adhoora, ya samajh na aane wala hai (STT ki galti ho sakti hai) — ek real sawaal ya
  statement nahi lagta.

IMPORTANT: Agar sawaal FACTS mein bilkul explicitly nahi likha hai, toh woh hamesha UNKNOWN hai — chahe
kitna bhi simple ya sambhavit lage. "Shayad haan hoga" jaisi soch mat karo, sirf yeh check karo ki FACTS
mein woh cheez LITERALLY likhi hai ya nahi.

EXAMPLES (in exact examples ko follow karo):
- "EMI milta hai kya?" -> UNKNOWN (FACTS mein EMI ka zikr kahin nahi hai)
- "online bhi milta hai kya offer?" -> UNKNOWN (FACTS mein online ka zikr nahi hai)
- "warranty kitne saal ki hai?" -> UNKNOWN (FACTS mein warranty ka zikr nahi hai)
- "delivery kitne din mein hoti hai?" -> UNKNOWN (FACTS mein delivery time ka zikr nahi hai)
- "sofa kitne ka hai?" -> ANSWERABLE (sofa price FACTS mein hai)
- "showroom kahan hai?" -> ANSWERABLE (locations FACTS mein hain)
- "आई वॉन्ट टू डिप यू आई रियली डिप" -> UNCLEAR (yeh koi samajh aane wala sawaal nahi hai)
- "नीचर के सोफा वोफा तू बहुत बड़ी ना मैं भी" -> UNCLEAR (garbled, koi clear matlab nahi banta)

Sirf ek word mein jawab do: "ANSWERABLE" ya "UNKNOWN" ya "UNCLEAR"."""


def _build_answer_prompt(facts: str, utterance: str, lang: str = "hi") -> str:
    # 2026-08-22 -- lang="en" branch added for fresh_cta's bilingual Q&A
    # fallback (see _REACT_LLM_UNKNOWN_TEXT_EN's comment). Only the
    # generated ANSWER needs to switch language -- the FACTS block itself
    # stays as-is (Hinglish facts read fine as grounding context regardless
    # of the output language instructed).
    if lang == "en":
        return f"""You are Priya, speaking on the phone on behalf of Krishna Furniture.
The customer asked a question whose answer is in the FACTS below.

FACTS:
{facts}

Customer asked: "{utterance}"

Based ONLY on these FACTS, in English, maximum 2 short sentences (20-25 words), like you're speaking
on the phone — answer. Don't say anything not in these FACTS (price, availability, any fact). Don't
be vague or generic (like "good rate" or "many options") if the exact fact isn't in FACTS — in that
case say EXACTLY this: "{_REACT_LLM_UNKNOWN_TEXT_EN}". No extra explanation or prefix, just the answer."""
    return f"""Aap Priya hain, Krishna Furniture ki taraf se phone par baat kar rahi hain.
Customer ne ek sawaal poocha hai jiska jawab neeche diye FACTS mein hai.

FACTS:
{facts}

Customer ne poocha: "{utterance}"

Sirf in FACTS ke aadhar par, Hindi/Hinglish mein, maximum 2 chhote vaakya (20-25 shabd), jaise phone par
bol rahe ho — jawab do. FACTS mein na ho aisi koi bhi cheez (price, availability, koi bhi fact) mat
kaho. Vague ya generic baat mat karo (jaise "achha rate hai" ya "bahut options hain") agar exact fact
FACTS mein nahi hai — is case mein EXACTLY yeh bolo: "{_REACT_LLM_UNKNOWN_TEXT}". Koi extra explanation
ya prefix mat do, sirf jawab bolo."""


# Shared across ALL campaigns' LLM-fallback answer generation (checked
# unconditionally in _llm_fallback_reply_impl, not scoped per campaign) --
# react_a/b/c/call2/call3's exchange-offer prices and fresh_cta's real
# furniture catalog prices both need to pass this same guard, so it's a
# union of both, not a replacement of one by the other.
_REACT_LLM_GROUNDED_PRICES = {
    # Owner-confirmed price sheet, Sep 2026 -- supersedes both the
    # 2026-08-23 figures and the 2026-09-14-morning website-catalog
    # figures. Mirrors new_flows_pricing.py's PRICE_LIST; keep both in sync
    # by hand. Deliberately does NOT include TV unit/coffee-center
    # table/cabinet/side table/home décor/ottoman/bedroom chair -- none of
    # those have a confirmed number on this sheet (on_request=True or
    # simply not covered), so they must never appear here even though
    # earlier versions of this set had numbers for some of them.
    "₹7,000", "₹8,000",     # sofa 1-seater
    "₹15,000",               # sofa 2-seater; also bed single, wardrobe wooden, garden swing
    "₹21,000", "₹24,000",   # sofa 3-seater
    "₹35,000",               # sofa-cum-bed; also recliner (power)
    "₹25,000",               # bed double; also wardrobe, recliner (manual), table+chair set
    "₹30,000",               # dining sheesham 4-seater
    "₹40,000",               # dining sheesham 6-seater (UNCONFIRMED -- see _FRESH_LLM_FACTS
                              # comment, hedge this one when spoken); also dining marble 4-seater
    "₹50,000",               # dining sheesham 8-seater
    "₹65,000",               # dining marble 6-seater
    "₹80,000",               # dining marble 8-seater
    "₹10,000", "₹12,000",   # office table; also mattress single
    "₹6,000",                # office chair
    "₹20,000",               # mattress double (low end); also center/coffee table (still
                              # excluded above -- kept here only because it coincides with a
                              # real mattress figure, not because center-table is grounded)
}

# Added 2026-08-14 -- confirmed live and reproduced directly (not a fluke):
# fed "और ये।" ("and this") straight to _react_llm_classify() and it came
# back ANSWERABLE every single time, then the generation step confidently
# hallucinated "Arre, yeh offer sirf sofa, bed... ke liye hai" -- a fluent,
# grounded-SOUNDING answer to something that was never a real question.
# llama-3.1-8b-instant (the model in use at the time) appeared biased toward
# forcing short, low-content fragments into ANSWERABLE rather than correctly
# recognizing them as UNCLEAR. That model was retired by Groq and swapped to
# groq/compound-mini 2026-08-18 (llama-3.1-8b-instant started 404ing --
# confirmed live, every classify call was silently falling to UNCLEAR) --
# this specific bias hasn't been re-verified against the new model, but the
# guard itself is cheap and model-agnostic so it's left in place regardless.
# Real short questions in this domain ("EMI?", "warranty?") still
# carry a real content word and are allowed through; this only catches
# utterances built ENTIRELY out of bare connective/filler words with no
# content word at all -- exactly the "और ये" shape, nothing broader.
_LOW_CONTENT_WORDS = {
    "aur", "और", "ye", "ये", "yeh", "यह", "woh", "वो", "toh", "तो",
    "bhi", "भी", "hi", "ही", "ki", "कि", "jo", "जो", "tha", "था",
    "thi", "थी", "the", "थे", "hai", "है",
}


def _is_low_content_fragment(t: str) -> bool:
    tokens = _tokenize(t)
    return bool(tokens) and all(tok in _LOW_CONTENT_WORDS for tok in tokens)


# Groq circuit breaker (2026-09-01). Groq's free tier has a hard daily token
# cap; once hit, EVERY call 429s for the rest of the day ("try again in
# 51m"). Without this, each mid-call question still paid the classify round-
# trip (~1s) AND fired a filler before falling back -- confirmed live, a
# whole test call of question turns each stalled ~5s on a filler then a
# static "noted" line. When a 429 / rate-limit / quota error is seen, skip
# Groq entirely for _GROQ_COOLDOWN_SECONDS: classify returns UNCLEAR
# instantly (no network, no filler), the caller goes straight to its static
# fallback. Self-heals when the cooldown lapses.
_GROQ_COOLDOWN_SECONDS = 180.0
_groq_cooldown_until = 0.0


def _groq_in_cooldown() -> bool:
    return time.monotonic() < _groq_cooldown_until


def _note_groq_error(exc: Exception, call_uuid: str) -> None:
    global _groq_cooldown_until
    s = str(exc).lower()
    if any(m in s for m in ("429", "rate_limit", "rate limit", "quota", "tokens per day")):
        _groq_cooldown_until = time.monotonic() + _GROQ_COOLDOWN_SECONDS
        logger.warning(
            f"[{call_uuid}] Groq rate-limited -- LLM Q&A disabled for "
            f"{_GROQ_COOLDOWN_SECONDS:.0f}s (falling back to static replies)"
        )


async def _react_llm_classify(t: str, call_uuid: str, facts: str = _REACT_LLM_FACTS) -> str:
    """Returns 'ANSWERABLE', 'UNKNOWN', or 'UNCLEAR' (defaults to UNCLEAR on any failure).

    `facts` added 2026-08-19 to support fresh_cta's own grounding
    (_FRESH_LLM_FACTS) -- defaults to _REACT_LLM_FACTS so every pre-existing
    call site (react_a/b/c/call2/call3) is unaffected."""
    if _groq_in_cooldown():
        return "UNCLEAR"
    try:
        resp = await asyncio.wait_for(
            _get_groq_async_client().chat.completions.create(
                model="groq/compound-mini",
                messages=[{"role": "user", "content": _build_classify_prompt(facts, t)}],
                max_tokens=5,
                temperature=0,
            ),
            timeout=1.5,
        )
        answer = resp.choices[0].message.content.strip().upper()
        for label in ("ANSWERABLE", "UNKNOWN", "UNCLEAR"):
            if label in answer:
                return label
        return "UNCLEAR"
    except Exception as exc:
        logger.warning(f"[{call_uuid}] LLM fallback classify failed, treating as UNCLEAR: {exc}")
        _note_groq_error(exc, call_uuid)
        return "UNCLEAR"


async def _llm_fallback_reply_impl(t: str, call_uuid: str, facts: str = _REACT_LLM_FACTS, lang: str = "hi") -> str | None:
    _reprompt_text = _REACT_LLM_REPROMPT_TEXT_EN if lang == "en" else _REACT_LLM_REPROMPT_TEXT
    _unknown_text  = _REACT_LLM_UNKNOWN_TEXT_EN if lang == "en" else _REACT_LLM_UNKNOWN_TEXT
    if _is_low_content_fragment(t):
        logger.info(f"[{call_uuid}] low-content fragment '{t}' -- skipping LLM classify entirely, treating as UNCLEAR")
        return _reprompt_text
    label = await _react_llm_classify(t, call_uuid, facts=facts)
    if label == "UNCLEAR":
        return _reprompt_text
    if label == "UNKNOWN":
        return _unknown_text

    try:
        resp = await asyncio.wait_for(
            _get_groq_async_client().chat.completions.create(
                model="groq/compound-mini",
                messages=[{"role": "user", "content": _build_answer_prompt(facts, t, lang=lang)}],
                max_tokens=80,
                temperature=0.2,
            ),
            timeout=2.0,
        )
        reply = resp.choices[0].message.content.strip()
        if not reply:
            return None
        found_prices = set(re.findall(r"₹\s*[\d,]+", reply))
        if found_prices - _REACT_LLM_GROUNDED_PRICES:
            logger.warning(f"[{call_uuid}] LLM fallback answer had an ungrounded price, discarding: {reply!r}")
            return None
        return reply
    except Exception as exc:
        logger.warning(f"[{call_uuid}] LLM fallback answer generation failed: {exc}")
        _note_groq_error(exc, call_uuid)
        return None


# Hard ceiling 2026-08-13: confirmed live, a real call hit 8.2s of dead
# silence on this fallback -- individual per-call budgets (classify + generate)
# summed higher than intended, and there was no cap on the combined total, so
# a slow moment on either call (or Groq's own internal retry-on-429, which
# runs inside the per-call wait_for and can itself eat most of that budget)
# could stack past what's acceptable on a live phone call. This wraps the
# WHOLE classify+generate sequence in one outer ceiling, independent of the
# tightened per-call budgets above (1.5s + 2.0s = 3.5s max normally) -- no
# matter what happens inside, the customer never waits past this before
# getting the static reprompt line instead.
_REACT_LLM_FALLBACK_HARD_TIMEOUT = 4.0


async def llm_fallback_reply(t: str, call_uuid: str, facts: str = _REACT_LLM_FACTS, lang: str = "hi") -> str | None:
    """
    Two-step fallback for a turn detect_intents() found nothing for.
    Classifies first; only ANSWERABLE ever reaches free-form generation
    (with the ₹ fabrication guard still applied as a second layer). UNKNOWN
    and UNCLEAR return fixed, pre-written strings -- never LLM output.
    Returns None if the overall pipeline exceeds _REACT_LLM_FALLBACK_HARD_TIMEOUT,
    or if the ANSWERABLE generation step itself fails or produces something
    ungrounded -- either way the caller falls back to the static reprompt line.

    `facts` added 2026-08-19 -- defaults to _REACT_LLM_FACTS (react_a/b/c/
    call2/call3's exchange-offer grounding); fresh_cta passes _FRESH_LLM_FACTS
    instead, since it's a different campaign context (see that constant's
    comment for why the two can't just share one block).

    `lang` added 2026-08-22 -- defaults to "hi" so every pre-existing call
    site is unaffected; fresh_cta's _try_fresh_llm_qa passes session.lang.
    """
    try:
        return await asyncio.wait_for(
            _llm_fallback_reply_impl(t, call_uuid, facts=facts, lang=lang),
            timeout=_REACT_LLM_FALLBACK_HARD_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[{call_uuid}] LLM fallback exceeded {_REACT_LLM_FALLBACK_HARD_TIMEOUT}s hard ceiling, aborting to static reprompt")
        return None


async def _resolve_dynamic_url(call_uuid: str, text: str, voice: str = "shreya", lang: str = "hi") -> tuple[str | None, bytes | None]:
    """
    Resolves arbitrary text to a playable Sarvam TTS URL WITHOUT playing it
    -- split out of play_dynamic_text 2026-08-23 so a dynamic answer and a
    following static reprompt key can be combined into ONE Vobiz Play
    request instead of two separate ones (see _play_dynamic_then_key()'s
    docstring for why that matters). Returns (audio_url, wav_bytes), or
    (None, None) on any failure/timeout -- caller decides what "no answer"
    means for its own transcript-logging and fallback behavior.
    """
    try:
        from tts_engine import get_speech
        # Timeout raised 3.0 -> 6.5s, 2026-08-22: confirmed live this was
        # firing routinely, not just on a slow outlier -- tts_engine.py's
        # own docstring documents fresh (uncached) Sarvam generation as
        # NORMALLY taking 3-6s ("Layer 3: Sarvam API — 3-6s"), so a 3.0s
        # ceiling sat at the very bottom of the documented normal range and
        # was structurally likely to abort on a large fraction of real
        # answers, not just unusually slow ones. 6.5s covers the top of that
        # documented range with a little margin. Tradeoff: worst-case dead
        # air before falling back to a generic reprompt is now longer, but
        # the prior alternative was silently discarding a real, already-
        # generated answer roughly as often as not.
        wav_bytes, audio_url, _ = await asyncio.wait_for(
            get_speech(text, lang=lang, static_key=None, speaker=voice), timeout=6.5
        )
        if audio_url:
            return audio_url, wav_bytes
    except asyncio.TimeoutError:
        logger.warning(f"[{call_uuid}] Dynamic TTS for LLM fallback exceeded 6.5s, aborting")
    except Exception as exc:
        logger.error(f"[{call_uuid}] Dynamic TTS for LLM fallback failed: {exc}")
    return None, None


async def play_dynamic_text(call_uuid: str, text: str, session=None, voice: str = "shreya", lang: str = "hi") -> bool:
    """
    Speaks arbitrary text live (Sarvam TTS, dynamic hash-keyed cache) rather
    than a pre-cached static key — for llm_fallback_reply()'s generated
    replies, which have no fixed key since the text itself is dynamic.
    Mirrors play_key()'s cache-miss branch.

    `voice` added 2026-08-13 -- every caller of this function already knows
    which campaign voice (ritu/shreya/simran) the rest of the call is using
    via PREFIX_VOICE_MAP, but it was never passed through, so get_speech()
    always fell back to tts_engine's hardcoded "shreya" default regardless.
    That produced an audible mid-call voice switch on every campaign except
    "rb" whenever a reply came from this fallback path -- confirmed live on
    the Pratham call (919911117660, campaign "ra"/"ritu"). Defaults to
    "shreya" only for any caller that genuinely doesn't have a campaign
    voice in scope.

    `lang` added 2026-08-22, defaults to "hi" (every pre-existing call site
    is unaffected) -- previously hardcoded unconditionally, so an English
    caller whose question fell through to this path got a Hindi-rendered
    reply regardless of what generated the text. fresh_cta's
    _try_fresh_llm_qa now passes session.lang alongside the matching
    English generation prompt (see _build_answer_prompt's lang branch) --
    passing lang="en" here alone, without also generating English text,
    would just mispronounce Hindi text in an English voice mode, so the two
    always need to move together.

    Single-URL callers only (7 pre-existing call sites across react_a/b/c/
    call2/call3) -- fresh_cta's answer-then-reprompt pattern uses
    _play_dynamic_then_key() instead, which combines both into one request.
    """
    # 2026-08-23 CONFIRMED-LIVE BUG: session.conversation used to get the
    # ("assistant", text) line appended HERE, unconditionally, before TTS
    # synthesis was even attempted -- so when get_speech() itself timed out
    # (confirmed live: the Pratham call's price-range answer, "Dynamic TTS
    # for LLM fallback exceeded 6.5s, aborting"), the stored transcript
    # recorded a reply the customer never actually heard a single word of.
    # Anyone reading call_summaries.full_transcript later sees a
    # conversation that doesn't match what was actually said on the call.
    # Moved to only append once get_speech() has actually produced a real
    # audio_url -- i.e., synthesis genuinely succeeded, not merely intended.
    # Note this still can't guarantee Vobiz's leg actually rendered the
    # audio end-to-end -- _vobiz_play() is deliberately fire-and-forget (see
    # its own docstring) and always returns True once called, by design, to
    # avoid adding dead air waiting on that HTTP round-trip. This fix closes
    # the gap that's actually fixable from here: never claim a line was said
    # when synthesis itself never completed.
    _turn = getattr(session, "turn_idx", None) if session else None
    if _turn is None:
        _turn = getattr(session, "turn_count", 0) if session else 0
    audio_url, wav_bytes = await _resolve_dynamic_url(call_uuid, text, voice, lang)
    if audio_url:
        if session is not None:
            if not hasattr(session, "conversation"):
                session.conversation = []
            session.conversation.append(("assistant", text))
            session.turn_audio_duration = getattr(session, "turn_audio_duration", 0.0) + _wav_bytes_duration(wav_bytes or b"")
        audit_event(call_uuid, "tts", turn=_turn, key="llm_fallback_dynamic", cached=False)
        return await _vobiz_play(call_uuid, audio_url, turn=_turn, kind="reply")
    return False


async def _play_dynamic_then_key(call_uuid: str, text: str, reprompt_key: str, session, voice: str, lang: str) -> bool:
    """
    Plays a dynamically-generated answer immediately followed by a static
    reprompt key, combined into ONE Vobiz Play request -- NOT two separate
    play_dynamic_text() + play_key() calls.

    2026-08-23 CONFIRMED-LIVE BUG (Pratham call): _vobiz_play()'s own
    docstring already documents that two separate Play requests fired in
    quick succession let the SECOND interrupt/replace the FIRST on the
    Vobiz leg -- confirmed back on 2026-08-13 for static-key pairs and
    fixed there via play_keys() (one combined multi-URL request). The new
    fresh_cta answer-then-reprompt pattern (_try_fresh_llm_qa and the
    equivalent inline block in handle_fresh_cta_turn) reintroduced the
    exact same bug shape by calling play_dynamic_text() then play_key() as
    two separate calls -- Pratham reported "unable to tell furniture
    categories" despite the answer being correctly generated and a Play
    request logged as sent; the reprompt line fired ~2s later almost
    certainly cut it off before he heard it. This combines both into one
    request the same way play_keys() already does for static-only pairs.
    """
    _turn = getattr(session, "turn_idx", None) if session else None
    if _turn is None:
        _turn = getattr(session, "turn_count", 0) if session else 0

    audio_url, wav_bytes = await _resolve_dynamic_url(call_uuid, text, voice, lang)
    if not audio_url:
        return False

    # log_transcript=False matches this reprompt's existing behavior at
    # every call site -- only the dynamic answer itself is logged as a real
    # reply, not the follow-up question re-ask.
    reprompt_url = await _resolve_key_url(call_uuid, reprompt_key, session, log_transcript=False)

    if session is not None:
        if not hasattr(session, "conversation"):
            session.conversation = []
        session.conversation.append(("assistant", text))
        session.turn_audio_duration = getattr(session, "turn_audio_duration", 0.0) + _wav_bytes_duration(wav_bytes or b"")
    audit_event(call_uuid, "tts", turn=_turn, key="llm_fallback_dynamic", cached=False)

    urls = [audio_url] + ([reprompt_url] if reprompt_url else [])
    return await _vobiz_play(call_uuid, urls, turn=_turn, kind="reply")


def _pick_llm_filler_key(t: str, voice: str) -> str:
    """
    Picks a topic-matched filler for the LLM fallback's real latency window
    (0.5-4s, vs ~5-10ms for the normal cached path) -- added 2026-08-13.
    Fast local keyword check only, no LLM call, adds no latency of its own.
    Reuses the same word sets ask_price_range/ask_offer_scope's proximity
    detectors already use, so "price-shaped" and "location-shaped" turns get
    a filler that actually matches what they asked instead of one generic
    line for everything.
    """
    tokens = set(_tokenize(t))
    if tokens & _PRICE_WORDS:
        return f"llm_filler_price_{voice}"
    if tokens & {"kahan", "कहां", "कहाँ", "location", "लोकेशन", "showroom", "शोरूम",
                 "store", "स्टोर", "address", "एड्रेस"}:
        return f"llm_filler_location_{voice}"
    return f"llm_filler_generic_{voice}"


async def _fire_llm_filler(call_uuid: str, t: str, session, voice: str) -> None:
    """Fire-and-forget: plays a topic-matched filler immediately."""
    key = _pick_llm_filler_key(t, voice)
    # Was hardcoded to lang="hi" (via _static_url()'s default) regardless of
    # session.lang -- confirmed live 2026-08-19: an English-speaking caller
    # whose question fell through to the LLM-fallback path heard a Hindi
    # filler ("Ek second ji, dekhti hoon...") mid-English-conversation,
    # twice in one call. SHARED_SCRIPT_EN already has English audio cached
    # for every one of these keys (generated 2026-08-18), so this was just a
    # missed lang= plumb-through, not missing content.
    lang = "en" if getattr(session, "lang", "hi") == "en" else "hi"
    url = _static_url(key, lang)
    if not url:
        return
    _turn = getattr(session, "turn_idx", None) if session else None
    if _turn is None:
        _turn = getattr(session, "turn_count", 0) if session else 0
    # Record when this filler clip is expected to finish so the real reply's
    # Play (via _vobiz_play, kind="reply") waits it out instead of cutting
    # it. +0.25s covers Vobiz's own start latency on the leg.
    try:
        _fdur = _wav_file_duration(_static_wav_path(key, lang))
    except Exception:
        _fdur = 0.0
    if _fdur > 0:
        _filler_finish_at[call_uuid] = time.monotonic() + _fdur + 0.25
    asyncio.create_task(_vobiz_play(call_uuid, url, turn=_turn, kind="filler"))


# How long to wait for the LLM fallback before committing to a filler --
# added 2026-08-13. Fillers are ~2-3s of spoken audio (measured: llm_filler_
# generic ~1.95s, llm_filler_price ~2.2s, llm_filler_location ~3.1s), but
# the classify-only UNCLEAR/UNKNOWN path (_react_llm_classify, 1.5s ceiling,
# 5 output tokens) routinely returns in well under a second on Groq. The old
# behavior fired the filler unconditionally and immediately, in parallel
# with the LLM call -- so on the (apparently common) fast path, the reply's
# Play request arrived at Vobiz while the filler was still mid-sentence, and
# _vobiz_play()'s docstring already documents that Vobiz REPLACES whatever's
# currently playing rather than queuing after it. Net effect: the filler
# audibly cut off mid-word, which is exactly the "fillers get cut, feels
# weird" behavior reported live. Fix: don't decide to play a filler until
# the LLM call has actually run long enough that skipping one would leave
# dead air. 0.45s is a judgment call, not measured against a real production
# latency distribution -- audit_event() already logs per-call "tts"/
# "play_result" elapsed times, so this is tunable later against real data if
# it turns out to fire too often or too rarely.
#
# 2026-09-01 -- raised 0.45 -> 0.75. At 0.45 the classify-only fast path
# (routinely sub-second on Groq) still lost the race often enough that the
# filler fired and then got chopped ~0.3s later by the real reply -- the
# exact "filler cut, sounds terrible" complaint, just moved slightly. 0.75
# lets almost every fast reply land BEFORE a filler is ever committed, so a
# filler now only plays when there's a genuine multi-second wait to cover.
# The filler-finish gate in _vobiz_play() then keeps the reply from cutting
# even that one short.
_FILLER_GRACE_SECONDS = 0.75

# call_uuid -> monotonic timestamp at which the last-fired filler clip on
# this leg is expected to finish playing. Set when a filler Play is issued
# (_fire_llm_filler); read once by _vobiz_play() before it sends a "reply"
# Play, so the reply waits out the filler instead of interrupting it on the
# Vobiz leg (Vobiz REPLACES current playback rather than queuing -- see
# _vobiz_play()'s docstring). Best-effort: a stale entry can only ever add a
# sub-3s wait, and it's cleared as soon as it's consumed or expires.
_filler_finish_at: dict[str, float] = {}


async def _llm_fallback_with_filler(call_uuid: str, t: str, session, voice: str,
                                     facts: str = _REACT_LLM_FACTS, lang: str = "hi") -> str | None:
    """
    Runs llm_fallback_reply() and only plays a filler if it's still pending
    past _FILLER_GRACE_SECONDS -- see that constant's docstring for why this
    replaced firing the filler unconditionally and immediately. Total worst-
    case reply latency is unchanged (the LLM task starts immediately either
    way, this only delays the DECISION to also play a filler); only the
    filler's start time moves later, past the point a fast reply would have
    already made it redundant.

    `facts` threaded through 2026-08-19 for fresh_cta's _FRESH_LLM_FACTS.
    `lang` threaded through 2026-08-22, defaults to "hi" (unchanged for
    every pre-existing caller); fresh_cta's _try_fresh_llm_qa passes
    session.lang so an English caller's answer generates in English.
    """
    llm_task = asyncio.create_task(llm_fallback_reply(t, call_uuid, facts=facts, lang=lang))
    done, _pending = await asyncio.wait({llm_task}, timeout=_FILLER_GRACE_SECONDS)
    if llm_task in done:
        return llm_task.result()
    await _fire_llm_filler(call_uuid, t, session, voice)
    return await llm_task


async def _reprompt_or_llm_fallback(call_uuid: str, t: str, session, voice: str,
                                     facts: str = _REACT_LLM_FACTS) -> None:
    """
    Shared by every "genuinely unmatched turn" branch across GREETING/
    PRESENT_OFFER/WHATSAPP_CTA/APPOINTMENT/call2's WA_CHECK/call3/fresh_cta:
    try the grounded LLM fallback first, fall back to the static
    obj_repeat_generic_{voice} reprompt line on any failure.
    """
    reply = await _llm_fallback_with_filler(call_uuid, t, session, voice, facts=facts)
    if reply and await play_dynamic_text(call_uuid, reply, session, voice=voice):
        return
    # Reached if there was no reply, or play_dynamic_text() itself failed/
    # timed out -- never leave the call silent either way.
    await play_key(call_uuid, f"obj_repeat_generic_{voice}", session)


# Standalone-token day-suffix check (e.g. "सैटर डे" written with a space) —
# replaces the old raw-substring "डे" in t check, which matched inside
# unrelated words like "स्टूडेंट" (student). Known transliterated day names
# without a space ("सैटरडे", "संडे", ...) are already exact keywords in
# SHARED_INTENTS["appointment_confirm"] and go through detect_intents instead.
def _has_standalone_day_suffix(t: str) -> bool:
    tokens = _tokenize(t)
    return "डे" in tokens and len(tokens) >= 2


# Deferral/hedge phrases that should block a date/appointment_confirm match
# even when a real date word is present in the same sentence — e.g. "कल बता
# सकेंगे" (I'll tell you tomorrow) uses the real word "कल" but is a deferral,
# not a confirmation. Sourced from the one confirmed real-world case found in
# the audit (call 85238e15) plus general Hindi/English deferral vocabulary
# consistent with this file's existing "busy"/"sochna_hai" intent keywords —
# a full-history scan of every confirmed appointment turned up no additional
# real deferral phrasings to generalize from, so treat this list as a
# starting point to extend if more surface later.
_APPOINTMENT_DEFERRAL_PHRASES = [
    "कल बता", "कल बताऊंगा", "कल बताऊंगी", "कल बता सकेंगे", "कल बता सकते",
    "बाद में बताऊंगा", "बाद में बताऊंगी", "बाद में बता", "फिर बताऊंगा", "फिर बताऊंगी",
    "अभी बता नहीं", "अभी नहीं बता", "सोच के बताऊंगा", "सोच के बताऊंगी",
    "बाहर जा रहा", "बाहर जा रहे", "अभी बाहर", "जा रहा हूं अभी", "जा रहे हैं अभी",
    "will tell tomorrow", "let me get back", "not sure yet",
    "cant confirm right now", "can't confirm right now", "will confirm later",
    "will let you know",
]


def _is_appointment_deferral(t: str) -> bool:
    tokens = _tokenize(t)
    boundary_text = f" {' '.join(tokens)} "
    return any(_phrase_in_tokens(p, boundary_text) for p in _APPOINTMENT_DEFERRAL_PHRASES)


# Words that make a digit token plausibly part of a DATE rather than an
# arbitrary number. Deliberately excludes generic quantity/duration words like
# "mahine"/"महीने" (months, as in "6 mahine ki EMI") and "percent"/"lakh" --
# those are common in price/EMI questions, not dates, and including them
# reopens the exact false-positive class this guard exists to close.
_DATE_CONTEXT_WORDS = {
    "तारीख", "tareek", "tarikh", "date", "को", "ko", "बजे", "baje",
    "जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त",
    "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
}
_ORDINAL_SUFFIX_RE = re.compile(r"^\d+(st|nd|rd|th)$", re.IGNORECASE)


def _has_date_context_digit(t: str) -> bool:
    """
    Replaces the old blind `any(ch.isdigit() for ch in t)` check -- confirmed
    via a 291-case regression audit (2026-07-15, test_reply_state_regression.py)
    that a bare digit ANYWHERE in the utterance ("office mein 5 log baithe the",
    "TV pe channel number 9", "1+1 kitna hota hai", "6 mahine ki EMI") false-
    confirmed a hot-lead appointment regardless of context. A full-history scan
    of every real outbound_leads.visit_date_status='confirmed' row found no
    production case of this exact class causing a fabricated visit yet, but
    it's the same shape of bug as the सर्कल/स्टूडेंट substring fix
    (see _has_standalone_day_suffix) and worth closing proactively.

    Now requires the digit token to be adjacent (previous or next token) to a
    real date-context word (तारीख/date/month name/ko/baje), or to carry an
    English ordinal suffix (20th/3rd) which is unambiguous on its own. Plain
    digit-bearing tokens with no such context ("5 log", "channel 9", "50000",
    "6 mahine") no longer count as a date.
    """
    tokens = _tokenize(t)
    for i, tok in enumerate(tokens):
        if not any(ch.isdigit() for ch in tok):
            continue
        if _ORDINAL_SUFFIX_RE.match(tok):
            return True
        prev_tok = tokens[i - 1] if i > 0 else ""
        next_tok = tokens[i + 1] if i + 1 < len(tokens) else ""
        if prev_tok in _DATE_CONTEXT_WORDS or next_tok in _DATE_CONTEXT_WORDS:
            return True
    return False


# Interrogative markers + "is it open/closed/what time" context words together
# mean the utterance is ASKING about store hours/availability, not confirming
# a visit -- e.g. "kitne baje khulta hai store" (what time do you open) uses
# the real appointment_confirm keyword "baje", and "Sunday ko khula rehta hai
# kya store" uses a real day-name keyword, but neither is a commitment to
# visit. Confirmed via the same regression audit as _has_date_context_digit;
# a full-history scan found no production case of this exact class yet either.
_TIMING_QUESTION_INTERROGATIVES = {
    "kya", "क्या", "kitne", "kitna", "कितने", "कितना", "kab", "कब",
}
_TIMING_QUESTION_CONTEXT_WORDS = {
    "baje", "बजे", "khula", "khulta", "khulti", "खुला", "खुलता", "खुलती",
    "band", "बंद", "available", "उपलब्ध", "timing", "टाइमिंग",
}


def _is_timing_question(t: str) -> bool:
    tokens = set(_tokenize(t))
    return bool(tokens & _TIMING_QUESTION_INTERROGATIVES) and bool(tokens & _TIMING_QUESTION_CONTEXT_WORDS)


# Vague relative-time words ("kal"/tomorrow, "raat"/tonight, ...) are real
# appointment_confirm keywords but, unlike a day-name ("saturday") or an
# actual digit-date, they're just as likely to show up in a sentence that has
# nothing to do with visiting the store ("cricket match kal hai", "movie
# dekhne jaana hai aaj raat" -- "raat" alone fires this). Day-names/month-
# names/digit-dates are left untouched here (they're unambiguous enough on
# their own); this guard only fires when a vague word is the SOLE reason
# appointment_confirm matched, and then requires an explicit visiting/coming
# verb ("aaunga"/"jaunga"/"showroom") in the same utterance. A bare one-word
# "kal" reply to "kab free honge?" would also get blocked by this and cost
# one extra re-ask turn -- an intentional trade-off: this codebase already
# treats a false CONFIRM (fabricated hot lead, see
# project_appointment_confirm_fabrication_fix) as far more costly than a
# false negative (one harmless re-ask, handled gracefully by the existing
# appt_reask_tried flow), so it's biased toward re-asking when unsure.
_VAGUE_TIME_WORDS = {"kal", "कल", "parso", "परसों", "subah", "सुबह", "shaam", "शाम", "raat", "रात"}
_VISIT_COMMITMENT_TOKENS = {
    "aaunga", "aaungi", "jaunga", "jaungi", "aaenge", "aayenge", "aaega", "aayega",
    "milunga", "milungi", "milenge", "aana", "aaonga", "free",
    "आऊंगा", "आऊँगी", "आएंगे", "आएगा", "मिलूंगा", "मिलूँगी", "मिलेंगे", "आना", "फ्री",
    "showroom", "store", "शोरूम", "स्टोर", "visit", "विजिट",
}


def _is_vague_time_without_commitment(t: str) -> bool:
    tokens = _tokenize(t)
    token_set = set(tokens)
    if not (token_set & _VAGUE_TIME_WORDS):
        return False  # no vague time word present -- guard doesn't apply
    if _has_date_context_digit(t) or _has_standalone_day_suffix(t):
        return False  # a stronger, unambiguous signal is already present
    # Does appointment_confirm still fire once the vague word(s) are removed?
    # If so, a stronger keyword (day-name/month-name/explicit commit phrase)
    # is independently responsible and this guard shouldn't interfere.
    stripped = " ".join(tok for tok in tokens if tok not in _VAGUE_TIME_WORDS)
    if "appointment_confirm" in detect_intents(stripped):
        return False
    return not bool(token_set & _VISIT_COMMITMENT_TOKENS)


# "I'm just browsing / I'll think about it / not right now" answers to the
# visit-date ask. Several of these (देख रहा हूँ, सोच कर बताता हूँ) match no
# detect_intents() category at all, so the fresh_cta VISIT_DATE handler needs
# an explicit phrase check or it would treat them as a date answer and
# fake-confirm a hot appointment. Substring match on a hyphen-normalised,
# lowercased transcript -- same lightweight style as _QUESTION_MARKERS.
_NONCOMMITTAL_VISIT_PHRASES = (
    "देख रहा", "देख रही", "देख रहे", "dekh raha", "dekh rahi", "dekh rahe",
    "बस देख", "सिर्फ देख", "केवल देख", "sirf dekh", "bas dekh", "just look",
    "just brows", "browsing", "सोच कर", "सोचकर", "सोच के बता", "soch kar",
    "soch ke bata", "sochkar", "think about", "let me think", "abhi nahi",
    "अभी नहीं", "abhi kuch nahi", "अभी कुछ नहीं", "pata nahi", "पता नहीं",
    "baad me", "बाद में", "later batata", "abhi decide nahi",
)


def _is_noncommittal_visit_reply(t: str) -> bool:
    tl = (t or "").lower().replace("-", " ")
    return any(p in tl for p in _NONCOMMITTAL_VISIT_PHRASES)


# A VAGUE date RANGE ("next weekend", "agle hafte", "kuch din mein") -- a
# real intent to visit, but no specific day. The fresh_cta flow should
# acknowledge (details -> WhatsApp) and pin the exact day before confirming
# an appointment against it, rather than booking "next weekend" as if it
# were "Saturday 3pm". Only treated as vague when NO concrete day/date is
# also named in the same utterance ("next weekend, Saturday" is specific).
_VAGUE_DATE_RANGE_PHRASES = (
    "weekend", "वीकेंड", "वीक एंड", "week end",
    "next week", "नेक्स्ट वीक", "coming week", "in a week", "within the week",
    "agle hafte", "अगले हफ्ते", "agla hafta", "अगला हफ्ता", "hafte bhar",
    "हफ्ते भर", "is hafte", "इस हफ्ते", "इस हफ़्ते",
    "next month", "agle mahine", "अगले महीने", "agle maheene",
    "kuch din", "कुछ दिन", "kuch dino", "कुछ दिनों", "few days",
    "couple of days", "couple days", "ek do din", "एक दो दिन",
)
_SPECIFIC_DAY_TOKENS = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "somvar", "mangalvar", "budhvar", "guruvar", "shukravar", "shanivar",
    "ravivar", "itvar", "itwar",
    "सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार",
    "इतवार", "सैटरडे", "संडे", "सन्डे", "मंडे", "मन्डे", "ट्यूज़डे", "ट्यूजडे",
    "वेडनेसडे", "थर्सडे", "फ्राइडे",
    "kal", "aaj", "parso", "kalh", "today", "tomorrow", "tmrw",
    "कल", "आज", "परसों",
}


def _is_vague_date_range(t: str) -> bool:
    tl = (t or "").lower().replace("-", " ")
    if not any(p in tl for p in _VAGUE_DATE_RANGE_PHRASES):
        return False
    toks = set(_tokenize(tl))
    if toks & _SPECIFIC_DAY_TOKENS or _has_date_context_digit(t):
        return False  # a concrete day/date is also present -> specific enough
    return True


async def handle_followup_wa_turn(session, transcript: str, call_uuid: str) -> bool:
    if not hasattr(session, "followup_played"):
        session.followup_played = False
    if not session.followup_played:
        session.followup_played = True
        session.turn_count = getattr(session, "turn_count", 0) + 1
        session.turn_audio_duration = 0.0
        p = get_prefix(getattr(session, "campaign", "react_a"))
        await play_key(call_uuid, f"{p}_wa_cta", session)
        await fire_whatsapp(session, call_uuid)
        await asyncio.sleep(12)
        # Already slept a fixed 12s here (comfortably covers this single
        # clip) -- zero this out so webhook.py's _hold_then_stop_speaking
        # doesn't add a second, redundant wait on top.
        session.turn_audio_duration = 0.0
        return False
    return False


# 2026-08-20 -- found live while testing the sequential step machine below:
# a genuine question asked mid-sequence ("aapke paas king size bed hai kya")
# has empty detect_intents() output, same as a plain data answer ("50 hazar
# tak") -- both are indistinguishable by intents alone. Without this check,
# the step machine silently swallowed real questions as if they were the
# answer to whatever it had just asked (confirmed: stored the literal
# question text as session.lead["budget"], then moved straight to asking
# urgency, never answering it). Cheap local marker-match, same
# Latin/Devanagari/phonetic-Devanagari triple-form convention as
# detect_intents()'s keyword lists -- imperfect (a phrasing with none of
# these markers still won't detour), but far better than swallowing every
# question that does happen to use one of them.
#
# Widened same day after user-directed verification against a batch of
# realistic product-detail phrasings ("kis tarah ke sofa hai aapke paas",
# "fabric options kya hai", "sofa kis kis colour mein milta hai") turned up
# 4/15 real questions the first pass missed entirely. Biased toward broader
# coverage over precision here deliberately: this function is only ever
# reached (see _try_fresh_llm_qa's callers) after the matching
# extract_budget()/extract_urgency()/product-match has ALREADY failed, so a
# false positive just costs one extra "let me check" LLM round-trip and a
# repeated question -- mildly redundant, not broken. A false negative means
# a real question gets silently swallowed as data, the worse failure mode.
_QUESTION_MARKERS = (
    "hai kya", "milta hai kya", "milte hai kya", "hota hai kya", "hote hain kya",
    "milta hai", "milte hain", "milti hai", "aata hai kya", "aate hain kya",
    "available hai", "available hain", "kaunsa", "kaunse", "kaunsi",
    "kis tarah", "kis type", "kis kism", "kis prakar", "kis colour", "kis rang",
    "kis size", "size kya", "colour kya", "color kya", "material kya",
    "kitne type", "kitni tarah", "kitne prakar", "kya kya", "options kya", "option kya",
    "kaun kaun", "kaun sa", "kaun se",
    "which size", "what size", "what kind", "what type", "do you have", "is there",
    "what colour", "what color", "what material", "what options",
    "है क्या", "मिलता है क्या", "मिलते है क्या", "होता है क्या", "होते हैं क्या",
    "मिलता है", "मिलते हैं", "मिलती है", "आता है क्या", "आते हैं क्या",
    "अवेलेबल है", "अवेलेबल हैं", "कौनसा", "कौनसे", "कौनसी", "कौन कौन", "कौन सा", "कौन से",
    "किस तरह", "किस टाइप", "किस किस्म", "किस प्रकार", "किस कलर", "किस रंग",
    "किस साइज", "साइज़ क्या", "साइज क्या", "कलर क्या", "मटेरियल क्या",
    "कितने टाइप", "कितनी तरह", "क्या क्या", "ऑप्शन क्या", "ऑप्शंस क्या",
    "व्हिच साइज", "व्हाट काइंड", "व्हाट टाइप", "डू यू हैव", "इज़ देयर",
    "व्हाट कलर", "व्हाट मटेरियल", "व्हाट ऑप्शंस",
)


# 2026-08-22 -- token-based fallback for _looks_like_question(), added after
# a real call where the exact-substring marker list missed "what will be
# the options in the bed I will be getting?" and "what are the options"
# (both have "what"..."options" separated by inserted words -- "will be
# the"/"are the" -- so no fixed-phrase marker matches word-for-word).
# Exact-phrase markers keep chasing every new insertion pattern
# indefinitely; checking word CO-OCCURRENCE instead (an interrogative word
# together with a noun it's plausibly asking about, regardless of what's
# between them) generalizes across insertions without enumerating them.
# English-only for now (English STT text tokenizes cleanly on whitespace;
# Hindi/Hinglish already has broad substring coverage above and its
# grammar doesn't insert words between question-word and noun the same way).
_QUESTION_WORDS_EN = {"what", "which", "kaunsa", "kaunse"}
_QUESTION_NOUNS_EN = {"options", "option", "kind", "kinds", "type", "types",
                      "colour", "colours", "color", "colors", "material",
                      "materials", "size", "sizes", "variety", "varieties"}


def _looks_like_question(t: str) -> bool:
    # Confirmed live 2026-08-22: STT sometimes renders a reduplicated word
    # ("kya kya" / "kaun kaun") with a hyphen instead of a space ("क्या-क्या",
    # "कौन-कौन") -- a real question slipped through undetected because the
    # marker list only had the space-separated form. Normalize hyphens to
    # spaces before matching instead of duplicating every marker twice.
    tl = t.lower().replace("-", " ")
    if any(m in tl for m in _QUESTION_MARKERS):
        return True
    tokens = set(_tokenize(tl))
    return bool(tokens & _QUESTION_WORDS_EN) and bool(tokens & _QUESTION_NOUNS_EN)


async def _try_fresh_llm_qa(call_uuid: str, t: str, session, reprompt_key: str) -> bool:
    """
    Fresh_cta's LLM Q&A fallback (grounded in _FRESH_LLM_FACTS), scoped for
    use INSIDE the sequential step machine below -- only fires when the text
    heuristically looks like a real question (see _looks_like_question),
    not merely because detect_intents() found nothing (that's the common
    case for a perfectly valid data answer too, e.g. a bare budget figure).
    Returns True if the turn was handled -- either it answered + reprompted,
    OR (2026-09-01) it played the fresh_qa_unavailable acknowledgment + the
    pending-question re-ask as one sequenced Play. Either way the caller
    should `return True` immediately. Returns False only when there was
    nothing to answer (not a question / bare filler) OR the LLM pipeline
    hiccuped in a way that isn't the customer's fault (_REACT_LLM_REPROMPT_
    TEXT) -- in both False cases nothing was played and the caller proceeds
    with its own default handling (e.g. capturing the text as a raw answer).
    """
    if _is_filler_continuer(t) or not _looks_like_question(t):
        return False
    _fresh_voice = PREFIX_VOICE_MAP.get("fresh", "simran")
    # 2026-08-22 -- bilingual: session.lang drives BOTH the generation
    # prompt's output language (_build_answer_prompt's lang branch, via
    # llm_fallback_reply) AND the TTS render language, so an English caller
    # gets an English-generated answer spoken in English, not a Hindi
    # answer or a Hindi-text-in-English-voice mismatch.
    _lang = "en" if getattr(session, "lang", "hi") == "en" else "hi"
    llm_answer = await _llm_fallback_with_filler(call_uuid, t, session, _fresh_voice, facts=_FRESH_LLM_FACTS, lang=_lang)
    # 2026-08-22 CONFIRMED-LIVE BUG: llm_fallback_reply() returns
    # _REACT_LLM_REPROMPT_TEXT (Hindi/English) not just when the customer's
    # speech was genuinely unclear, but ALSO whenever the classify step
    # itself throws (Groq API error/timeout/rate-limit) -- _react_llm_classify
    # defaults to "UNCLEAR" on any exception, same text either way. STT
    # already transcribed the turn correctly (that's what `t` is); an LLM-
    # pipeline hiccup is not evidence the customer wasn't understood, and
    # playing "I didn't catch that clearly" is an outright false claim.
    # Worse: treating this fallback text as a real "answer" made
    # _try_fresh_llm_qa return True, which skipped the caller's own
    # extract_budget()/extract_urgency() capture for that turn entirely --
    # confirmed live, a Groq 429 mid-call silently discarded a customer's
    # real stated budget range instead of just failing to answer their
    # question. Treat this specific fallback text as "no real answer" (same
    # as any other failure) so the caller still runs its own extraction/
    # capture on the turn instead of losing it.
    if llm_answer in (_REACT_LLM_REPROMPT_TEXT, _REACT_LLM_REPROMPT_TEXT_EN):
        return False
    # 2026-08-23 -- combined into one Play request (_play_dynamic_then_key)
    # instead of two separate play_dynamic_text() + play_key() calls -- see
    # that helper's docstring: two separate Play requests fired in quick
    # succession let the second cut off the first before the customer hears
    # it. Confirmed live: Pratham's furniture-categories answer was
    # correctly generated and "played" per the logs, but he never actually
    # heard it -- the reprompt fired ~2s later and silently interrupted it.
    if llm_answer and await _play_dynamic_then_key(call_uuid, llm_answer, reprompt_key, session, _fresh_voice, _lang):
        return True
    # Real question, no answer generated/played in time (Sarvam dynamic-TTS
    # latency or a Groq failure). fresh_qa_unavailable is a pre-cached STATIC
    # key so it plays instantly regardless of Groq/Sarvam state -- always
    # acknowledge before moving on, so the customer hears something
    # responsive rather than being ignored (confirmed live: silent fall-
    # through here FOUR turns running, then the customer hung up).
    #
    # 2026-09-01 -- acknowledgment + the pending-question re-ask now go out
    # as ONE sequenced Vobiz Play (play_keys) and this returns True, ending
    # the turn. It used to play only fresh_qa_unavailable and return False,
    # leaving the caller to fire a SECOND separate play_key() for the
    # re-ask -- that, plus the LLM filler already in flight, was three Plays
    # in ~4s each cutting the previous one mid-word (confirmed live on the
    # BUDGET/URGENCY steps). Trade-off: a turn that both asked a question
    # AND stated real data ("if my budget is 50k, what do I get") no longer
    # captures that data on this turn -- but the customer is being re-asked
    # the same question anyway and will normally restate it, and the old
    # chopped-audio behavior is exactly what was reported as broken.
    await play_keys(call_uuid, ["fresh_qa_unavailable", reprompt_key],
                    session, log_transcript=[False, False])
    return True


def _fresh_step_question_key(fresh_step: str | None) -> str:
    """
    Which key re-asks whatever question is currently pending in fresh_cta's
    sequential budget/urgency/visit-date step machine (see
    handle_fresh_cta_turn) — used by the LLM-fallback trailing reprompt and
    the generic catch-all reask so a customer who asks an unrelated question
    or says something unparseable mid-sequence gets steered back to the
    actual pending question, not always the same generic fresh_objection
    line. Falls back to "fresh_objection" for VISIT_DATE and None (the
    latter covers call_cycle 2/3, where the step machine never activates —
    same behavior as before this feature existed).
    """
    return {
        "AWAIT_FIRST_REPLY": "fresh_ask_budget",
        "BUDGET":            "fresh_ask_budget",
        "URGENCY":           "fresh_ask_urgency",
        "INTERIOR_BUDGET":   "fresh_interior_budget_ask",
    }.get(fresh_step, "fresh_objection")


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
    # Moved above the init-once block below so it's available for
    # session.fresh_step's initial value — purely reads session.fresh_product
    # (set once at call start via _session_meta), no session mutation, safe
    # to compute this early. Re-derives the same product key /answer-outbound
    # used to pick the initial greeting rather than trusting the raw
    # query-param string is one of the known values.
    _raw_product = getattr(session, "fresh_product", "") or ""
    _product_key = normalize_fresh_product_key(_raw_product)

    if not hasattr(session, "dnc"):
        session.dnc = False
        session.react_state = "APPOINTMENT"  # for call_summaries reporting only — no other state exists in this funnel

    # 2026-08-20 — deliberately separate guards from the dnc block above, not
    # folded into it: make_session() (test_objection_routing.py) always
    # pre-sets session.dnc, so a combined guard would silently skip
    # initializing these two for every test session (and any other caller
    # that pre-populates dnc but not these). Independent hasattr checks make
    # each safe regardless of how the session was constructed.
    #
    # session.lead is read unconditionally by finalize_call()
    # (supabase_calling.py) for every campaign already — populating it here
    # (product/budget/urgency below) feeds call_summaries.product_interest/
    # budget_mentioned/urgency_mentioned with zero new plumbing, same dict
    # shape react_a/b/c already use.
    if not hasattr(session, "lead"):
        session.lead = {"product": _product_key} if _product_key else {}

    if not hasattr(session, "fresh_step"):
        # New sequential budget/urgency/visit-date flow. Call-1 only:
        # call_cycle 2/3 keep their original single-purpose "just confirm a
        # date" flow (their own greeting already asks for a date directly —
        # see webhook.py's fresh_c2_greet_*/fresh_c3_greet_* dispatch)
        # rather than re-asking budget/urgency a lead may have already
        # answered, or that reads oddly as a second/third follow-up.
        # "AWAIT_FIRST_REPLY" (not "BUDGET") because turn 1's reply is
        # answering the greeting's open "what are you looking for / how can
        # I help" line, not yet a specific question — see the step-machine
        # dispatch further down for how this advances.
        #
        # 2026-08-22 CONFIRMED-LIVE BUG: this used to check `is None`, but a
        # real call_cycle 1 session has session.call_cycle == "" (empty
        # string, set at webhook.py:1839 via _meta.get("call_cycle", "")),
        # never Python None -- "" is None is False, so the step machine was
        # DISABLED on every real call-1 (the one case it needed to cover)
        # and every turn silently fell through to the old flat flow the
        # entire time this was live. Falsy-check instead, so "" and None
        # both correctly mean call 1; only a real "2"/"3" string disables it.
        session.fresh_step = "AWAIT_FIRST_REPLY" if not getattr(session, "call_cycle", None) else None

    session.turn_count = getattr(session, "turn_count", 0) + 1
    session.turn_audio_duration = 0.0
    t = transcript.strip() if transcript else ""

    if not hasattr(session, "conversation"):
        session.conversation = []

    _cap_reason = _hard_cap_reason(session)
    if _cap_reason:
        logger.info(f"[{call_uuid}] fresh_cta hard cap hit ({_cap_reason}, turn_count={session.turn_count}) — closing")
        if t:
            session.conversation.append(("user", t))
        await play_key(call_uuid, "fresh_no_date_close", session)
        await fire_whatsapp(session, call_uuid)
        return False

    if t and _is_ivr_fragment(t):
        logger.info(f"[{call_uuid}] fresh_cta IVR/voicemail fragment detected transcript='{t[:60]}' — withholding reply, marker=ivr_fragment_detected")
        _mark_ivr_fragment(session)
        session.conversation.append(("user", t))
        return True

    # 2026-08-29 CONFIRMED-LIVE BUG, severe: webhook.py's WS transcript
    # handler only increments session.turn_count_substantive for campaigns
    # that fall through to its generic tail -- fresh_cta's dispatch (like
    # followup_wa's) `return`s right after calling this handler, so that
    # shared increment code is NEVER reached. session.turn_count_substantive
    # therefore stayed permanently 0 for every fresh_cta call, no matter how
    # many real turns happened, which made _hard_cap_reason()'s
    # "duration_cap_close" branch (meant only for a genuinely dead/stuck
    # call with ZERO real speech) fire on EVERY fresh_cta call that simply
    # ran past 180 seconds -- confirmed live: a real test call with 12
    # substantive turns of active price/category/location Q&A got force-
    # closed at 212s with reason=duration_cap_close, turn_count=12. The
    # other 3 handlers (react_a/b/c, call2, call3) already increment this
    # counter themselves internally for the same reason -- fresh_cta and
    # followup_wa never did. Mirrors handle_reactivation_turn's placement:
    # after the empty/IVR-fragment early-returns, for any real remaining
    # speech.
    if t:
        session.turn_count_substantive = getattr(session, "turn_count_substantive", 0) + 1

    intents = detect_intents(t) if t else []

    logger.info(f"[{call_uuid}] fresh_cta transcript='{t[:60]}' intents={intents}")
    # Added 2026-08-19 -- the other 3 handlers (react_a/b/c, call2, call3) all
    # already emit this audit_event() record; fresh_cta never did, despite
    # being the only campaign with real product-specific greetings. Confirmed
    # during the keyword-matching audit: this meant fresh_cta turns were
    # invisible to scripts/no_match_report.py (see that file), the only
    # queryable record of which live turns matched no keyword at all.
    audit_event(call_uuid, "route", turn=getattr(session, "turn_idx", session.turn_count),
                state=session.react_state, campaign="fresh_cta", intents=intents, transcript=t)

    # 2026-08-20 — a turn where fresh_step is one of the new sequential
    # question-answer steps expects free-form speech (a budget figure, a
    # timeframe, a plain product name) that will very often match NONE of
    # detect_intents()'s keyword categories — that's normal, not a failure
    # to understand. Without this guard, a bare "50 hazar" or "next week"
    # answer would increment not_understood_streak/total same as genuine
    # gibberish, and 3 such answers in a row would incorrectly close the
    # call via the not_understood cap before the sequence ever finished.
    _expects_freeform_answer = getattr(session, "fresh_step", None) in (
        "AWAIT_FIRST_REPLY", "BUDGET", "URGENCY", "INTERIOR_BUDGET",
    )

    if t and not intents and not _expects_freeform_answer:
        if _LLM_REFUSAL_FALLBACK_ENABLED and await _llm_classify_refusal(t, call_uuid):
            logger.info(f"[{call_uuid}] fresh_cta LLM refusal-classify fired on unrecognized utterance '{t[:60]}' — treating as not_interested")
            intents = ["not_interested"]
        else:
            session.not_understood_streak = getattr(session, "not_understood_streak", 0) + 1
            session.not_understood_total  = getattr(session, "not_understood_total", 0) + 1
            if session.not_understood_streak >= 3 or session.not_understood_total >= 5:
                logger.info(f"[{call_uuid}] fresh_cta not_understood cap hit (streak={session.not_understood_streak}, total={session.not_understood_total}) — closing")
                session.conversation.append(("user", t))
                await play_key(call_uuid, "fresh_no_date_close", session)
                await fire_whatsapp(session, call_uuid)
                return False
    else:
        session.not_understood_streak = 0

    if t:
        session.conversation.append(("user", t))

    # Hard decline — "not_interested" per spec; "dnc" folded in too (same
    # top-priority hard-stop convention every other handler in this file uses).
    # Reuses react_a's cached DNC audio directly — no new fresh_dnc key, per spec.
    if await check_hard_rejection(session, call_uuid, intents, "ra_dnc", also_reject_on=("not_interested",)):
        return False

    # 2026-08-20 — interior-design branch: a distinct funnel exit, not a
    # furniture objection, so it's checked above route_objection() and
    # independent of session.fresh_step/call_cycle (a retry customer raising
    # this is just as real as a first-call one). Exactly one budget question,
    # then a manager handoff — no urgency/visit-date asks for this path, per
    # spec. Checked in two parts: continuation first (we already asked the
    # budget question last turn, so THIS turn's text is the answer,
    # regardless of what intents matched), then fresh entry.
    if getattr(session, "fresh_step", None) == "INTERIOR_BUDGET":
        from webhook import extract_budget
        _budget = extract_budget(t)
        _is_question = _looks_like_question(t)
        # 2026-08-22 CONFIRMED-LIVE BUG: `_budget is None` alone as the only
        # gate meant a genuine question containing a number that happens to
        # parse as a budget ("agar 50 hazar ka budget ho toh...") would get
        # silently accepted as the answer instead of detouring to answer it.
        # OR-ing in _looks_like_question(t) closes that regardless of
        # whether extraction succeeded.
        if (_budget is None or _is_question) and await _try_fresh_llm_qa(call_uuid, t, session, "fresh_interior_budget_ask"):
            return True
        # 2026-08-29 -- same fix as the BUDGET/URGENCY steps above, and even
        # more consequential here: falling through on a failed-to-answer
        # question wouldn't just record bad data, it would fire the
        # manager handoff (fresh_interior_handoff, lead_tier_override=hot)
        # on a question the customer never got an answer to. Re-ask instead.
        if _budget is None and _is_question:
            await play_key(call_uuid, "fresh_interior_budget_ask", session)
            return True
        session.lead["budget"] = _budget or t
        session.lead["interest_type"] = "interior_design"
        session.lead_tier_override = "hot"
        session.fresh_step = "INTERIOR_HANDOFF_DONE"
        await play_key(call_uuid, "fresh_interior_handoff", session)
        return False

    if "interior_design" in intents and getattr(session, "fresh_step", None) != "INTERIOR_HANDOFF_DONE":
        session.fresh_step = "INTERIOR_BUDGET"
        await play_key(call_uuid, "fresh_interior_budget_ask", session)
        return True

    _obj_result = await route_objection(session, call_uuid, "fresh", session.react_state, intents, t)
    if _obj_result is not None:
        return _obj_result

    # Same confirmation detection as the APPOINTMENT state in
    # handle_reactivation_turn, verbatim — mirrored, not reimplemented.
    _has_digit      = _has_date_context_digit(t)
    _has_day_suffix = _has_standalone_day_suffix(t)
    if ("appointment_confirm" in intents or _has_digit or _has_day_suffix) and not _is_appointment_deferral(t) and not _is_timing_question(t) and not _is_vague_time_without_commitment(t):
        # Vague range ("next weekend", "agle hafte") with no concrete day:
        # don't book against it -- acknowledge (details -> WhatsApp) and ask
        # for the exact day. The customer's NEXT reply is what gets
        # confirmed. Only once per call: a second vague answer is accepted
        # as-is rather than looping.
        if _is_vague_date_range(t) and not getattr(session, "visit_day_clarify_asked", False):
            session.visit_day_clarify_asked = True
            await play_key(call_uuid, "fresh_ask_visit_day", session)
            return True
        session.appointment_confirmed = True
        session.visit_date_raw_text   = t
        session.lead["visit_date"]    = t
        session.lead_tier_override    = "hot"
        session.lead_score_override   = 85
        await play_key(call_uuid, "fresh_appointment_confirmed", session)
        await asyncio.sleep(3.0)
        return False

    # Specific product named ("L-shape sofa", "recliner", "6 seater dining")
    # 2026-09-01. Krishna Furniture has no short category menu -- a named item
    # gets an instant "yes we have it" (fresh_have_{key}), and a price
    # question about it pivots straight to WhatsApp + a store visit
    # (fresh_price_wa), per explicit instruction. Checked before the generic
    # busy/price/categories branches; after appointment_confirm so
    # "L-shape sofa Saturday ko dekhne aaunga" still books.
    _fresh_prod = match_fresh_product(t)
    if _fresh_prod:
        session.lead["product_detail"] = _fresh_prod
        _bcat = _FRESH_PRODUCT_BROAD.get(_fresh_prod)
        if _bcat and not session.lead.get("product"):
            session.lead["product"] = _bcat
        _step = getattr(session, "fresh_step", None)
        if ("ask_price_range" in intents or "ask_valuation" in intents
                or _is_price_question(t)):
            await play_key(call_uuid, "fresh_price_wa", session)
            if _step in ("AWAIT_FIRST_REPLY", "BUDGET", "URGENCY", None):
                session.fresh_step = "VISIT_DATE"
            return True
        await play_key(call_uuid, f"fresh_have_{_fresh_prod}", session)
        # fresh_have_* ends with "aap kab tak lene ka plan kar rahe hain?"
        # (the urgency question) -- so the next reply is the urgency answer.
        if _step in ("AWAIT_FIRST_REPLY", None):
            session.fresh_step = "URGENCY"
        return True

    # Price question with NO product named this turn but a product named
    # EARLIER ("recliner sofa" ... then "iska price kya hai") -- carry the
    # context: WhatsApp price-list deflect, not the generic categories list.
    if (getattr(session, "lead", {}).get("product_detail")
            and ("ask_price_range" in intents or "ask_valuation" in intents or _is_price_question(t))
            and match_price_category(t) is None):
        await play_key(call_uuid, "fresh_price_wa", session)
        if getattr(session, "fresh_step", None) in ("AWAIT_FIRST_REPLY", "BUDGET", "URGENCY", None):
            session.fresh_step = "VISIT_DATE"
        return True

    # Broad category named as a "what/which do you have" question
    # ("konse sofa hain", "what beds do you have") -- no specific product, no
    # menu; the fresh_range_{cat} line names the real variants and asks which.
    # Below match_fresh_product so a specific item still wins. Skipped when
    # we're mid budget/urgency AND the turn carries a number -- that's a
    # budget answer that happens to also ask "which ones", and the step
    # machine below must still capture the figure (regression-guarded).
    _fresh_broad = match_fresh_broad_category(t)
    if _fresh_broad and getattr(session, "fresh_step", None) in ("BUDGET", "URGENCY") \
            and any(ch.isdigit() for ch in (t or "")):
        _fresh_broad = None
    if _fresh_broad:
        if not session.lead.get("product") and _fresh_broad in ("sofa", "bed", "dining", "wardrobe", "chair"):
            session.lead["product"] = _fresh_broad
        await play_key(call_uuid, f"fresh_range_{_fresh_broad}", session)
        return True

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

    # 2026-08-23 — location ask, rebuilt around the real 5-store list
    # (Gurgaon x2, Noida, Faridabad, Delhi). If they named a specific city,
    # answer with that city's exact store directly (match_store_city);
    # otherwise play the general list, which itself ends by asking which
    # city they want (fresh_location_info) -- matches the same
    # ask-if-unclear pattern the price/category branch below uses.
    #
    # `return True` (not False): confirmed live on the Pratham call that
    # hard-ending the call right after this answer read as an abrupt cutoff
    # -- he was still actively engaged (three questions in a row right up
    # to this exact point). Continuing lets the conversation carry on
    # naturally into whatever's next instead of hanging up on someone
    # mid-engagement; WhatsApp still fires either way so the address is
    # there in writing regardless of how the call itself ends.
    if "ask_location" in intents:
        _city = match_store_city(t)
        _key = f"fresh_store_{_city}" if _city else "fresh_location_info"
        await play_key(call_uuid, _key, session)
        await fire_whatsapp(session, call_uuid)
        return True

    # 2026-08-23 — category/price ask, built from the real 12-category
    # catalog. ask_offer_scope included as a synonym trigger here alongside
    # the dedicated ask_categories intent: confirmed live a real "what
    # categories do you have" question ("कौन सी कौन सी फर्नीचर कैटेगरीज
    # हैं?") matched ask_offer_scope's keywords, not a fresh-cta-specific
    # one (ask_offer_scope's actual meaning -- "which products does the
    # discount apply to" -- doesn't otherwise exist in fresh_cta, which has
    # no discount/exchange-offer framing at all, so there's no real
    # ambiguity in treating it as "what do you sell" here).
    #
    # Deliberately does NOT go through the dynamic LLM+TTS fallback at all
    # for a NAMED category -- this is a common, high-value question with a
    # small closed answer set, answered instantly from a pre-cached key
    # instead of depending on the slower, failure-prone dynamic path found
    # unreliable elsewhere today (TTS timeouts, Groq rate limits, the
    # Play-interruption bug). A specifically-named item not in the real
    # catalog honestly says so (fresh_price_unavailable) rather than falling
    # through to the LLM and risking a fabricated number.
    #
    # 2026-08-29 CONFIRMED-LIVE BUG (real test call): a fully vague price
    # question ("What is our starting price?", no item named at all) was
    # going to fresh_price_unavailable ("I don't have the exact price for
    # that, I'll confirm on WhatsApp") -- but the user's own spec for this
    # exact case ("agar clear nahi to hamare pass ye ye furniture hai,
    # aapko kiski price chahiye") calls for the categories-clarifying
    # question instead, which is what fresh_categories_list already says --
    # the branch just had the wrong key picked for "no category matched".
    # Now distinguishes "no item named" (-> ask which one) from "a real
    # non-catalog item was named" (-> honest unavailable) via
    # mentions_non_catalog_item().
    if "ask_price_range" in intents or "ask_categories" in intents or "ask_offer_scope" in intents:
        _category = match_price_category(t)
        if _category:
            _key = f"fresh_price_{_category}"
        elif "ask_price_range" in intents and mentions_non_catalog_item(t):
            # A specific, real item was named but it's genuinely outside
            # our 12-category catalog -- honest unavailable line, not a
            # guess at which of OUR categories they meant instead.
            _key = "fresh_price_unavailable"
        else:
            # No specific item named at all (vague price question), or
            # ask_categories/ask_offer_scope -- list everything, ends with
            # its own clarifying question ("aapko kis furniture ki price
            # janni hai?").
            _key = "fresh_categories_list"
        await play_key(call_uuid, _key, session)
        return True

    # 2026-08-20 — sequential budget/urgency/visit-date step machine (call-1
    # only: session.fresh_step is None for call_cycle 2/3, so this whole
    # block is a no-op for them and they fall through unchanged to the
    # LLM-fallback/generic-reask/close chain below, exactly as before this
    # change — see the fresh_step init comment above for why retries are
    # excluded).
    #
    # "VISIT_DATE" IS handled here now (added 2026-09-01). Previously it
    # fell through to the LLM-fallback/generic-reask/close chain, which
    # meant a date answer the appointment_confirm block above didn't happen
    # to parse (a phrasing not in its keyword list, an STT script the
    # matchers don't cover, ...) got no date-specific handling at all --
    # confirmed live twice: "next Saturday or Sunday" (mis-scripted by STT)
    # and a mid-step question both dropped straight to "fresh_objection" and
    # the call ended warm with no appointment, as if the answer was never
    # given. See the dedicated `session.fresh_step == "VISIT_DATE"` block
    # further down.
    if session.fresh_step == "AWAIT_FIRST_REPLY":
        # Product may already be known from outbound_leads.product_interest
        # (session.lead["product"] pre-populated at init) — only try to
        # extract it from what they just said if it isn't.
        #
        # 2026-08-22 CONFIRMED-LIVE BUG: mentioning a product name is NOT
        # mutually exclusive with asking a question about it -- "बेड में
        # क्या-क्या ऑप्शंस हैं आपके पास?" ("what bed options do you have?")
        # matched extract_product() -> "bed" successfully, so the old
        # `elif _try_fresh_llm_qa(...)` (only reachable when extraction
        # failed) never ran, and a real question got silently treated as
        # "customer wants a bed" while never being answered. Still capture
        # the product opportunistically either way (harmless, useful
        # signal), but check _looks_like_question independently of whether
        # extraction succeeded, same OR-pattern as the BUDGET/URGENCY/
        # INTERIOR_BUDGET steps below.
        if not session.lead.get("product"):
            from webhook import extract_product
            _stated_product = normalize_fresh_product_key(t) or extract_product(t)
            if _stated_product:
                session.lead["product"] = _stated_product
        if (not session.lead.get("product") or _looks_like_question(t)) and await _try_fresh_llm_qa(call_uuid, t, session, "fresh_ask_budget"):
            # Advance to BUDGET even on the detour -- the reprompt just
            # played WAS fresh_ask_budget, so the next turn's reply is
            # answering that, not re-stating what they're looking for.
            # Without this, fresh_step stays AWAIT_FIRST_REPLY and the next
            # turn redundantly re-runs this same block instead of capturing
            # their actual budget answer.
            session.fresh_step = "BUDGET"
            return True
        session.fresh_step = "BUDGET"
        await play_key(call_uuid, "fresh_ask_budget", session)
        return True

    if session.fresh_step == "BUDGET":
        from webhook import extract_budget
        _budget = extract_budget(t)
        _is_question = _looks_like_question(t)
        # OR-ing in _looks_like_question(t): a question that happens to
        # contain a number ("agar mera budget 50 hazar ho toh kya milega")
        # would otherwise "successfully" extract and get silently accepted
        # as the answer instead of being answered -- same bug class as
        # AWAIT_FIRST_REPLY above, found the same way (live verification).
        if (_budget is None or _is_question) and await _try_fresh_llm_qa(call_uuid, t, session, "fresh_ask_budget"):
            return True
        # 2026-08-29 CONFIRMED-LIVE BUG (real test call): _try_fresh_llm_qa
        # can legitimately return False for a genuine question too -- not
        # just when it wasn't a question -- whenever the LLM Q&A pipeline
        # itself fails (Groq/TTS hiccup); it already played
        # fresh_qa_unavailable acknowledging the question in that case. The
        # old code fell straight through to `_budget or t` regardless, which
        # stored the RAW QUESTION TEXT as the customer's budget (confirmed
        # live: call_summaries.budget_mentioned came back as
        # 'ओके, कौन-कौन सी कैटेगरीज़ हैं आपके पास?' after this exact path).
        # Re-ask the real pending question instead of fabricating budget
        # data and silently advancing past it.
        if _budget is None and _is_question:
            await play_key(call_uuid, "fresh_ask_budget", session)
            return True
        session.lead["budget"] = _budget or t
        session.fresh_step = "URGENCY"
        await play_key(call_uuid, "fresh_ask_urgency", session)
        return True

    if session.fresh_step == "URGENCY":
        from webhook import extract_urgency
        _urgency = extract_urgency(t)
        _is_question = _looks_like_question(t)
        if (_urgency is None or _is_question) and await _try_fresh_llm_qa(call_uuid, t, session, "fresh_ask_urgency"):
            return True
        # Same fix as BUDGET above -- a genuine question the LLM Q&A
        # pipeline failed to answer must not get recorded as "urgency" and
        # silently advance the call past it.
        if _urgency is None and _is_question:
            await play_key(call_uuid, "fresh_ask_urgency", session)
            return True
        session.lead["urgency"] = _urgency or t
        session.fresh_step = "VISIT_DATE"
        await play_key(call_uuid, "fresh_ask_visit_date", session)
        return True

    if session.fresh_step == "VISIT_DATE":
        # The bot's immediately-preceding line was "store visit ke liye aap
        # kab aa sakte hain?" -- so this turn IS the answer to that. The
        # shared appointment_confirm block ran above already; reaching here
        # means it didn't recognise the text as a date. Rather than drop to
        # the generic objection/close chain (which reads as ignoring the
        # answer -- confirmed live twice), resolve every case explicitly:
        #
        #   1. a real question           -> answer it + re-ask the date, ONE
        #                                   combined Play, stay on VISIT_DATE
        #   2. explicit deferral / "just -> soft close, no push, WhatsApp
        #      browsing" / busy
        #   3. near-empty / pure filler  -> ONE gentle re-ask of the date
        #   4. anything else with real   -> treat as the visit-date answer
        #      content                      and CONFIRM (this is the whole
        #                                    point of the funnel; at this
        #                                    step a non-question, non-
        #                                    objection reply is a date)
        if _looks_like_question(t):
            # Phrase-heuristic question. _try_fresh_llm_qa answers it, or on
            # a genuine failure plays fresh_qa_unavailable + the re-ask
            # itself and returns True. It returns False ONLY on the "LLM
            # hiccup, nothing played" path (Groq 429 / _REACT_LLM_REPROMPT_
            # TEXT) -- in that case WE must play a fallback or the turn ends
            # in dead air after the filler (confirmed live: 26s of silence,
            # then the customer hung up). A question is never the date
            # answer, so end the turn here either way, still on VISIT_DATE.
            if not await _try_fresh_llm_qa(call_uuid, t, session, "fresh_ask_visit_date"):
                await play_keys(
                    call_uuid, ["fresh_qa_unavailable", "fresh_ask_visit_date"],
                    session, log_transcript=[False, False],
                )
            return True

        _meaningful_q = set(intents) - {"positive"}
        if _meaningful_q and _meaningful_q <= _INFORMATIONAL_QA_INTENTS:
            # Recognised informational question by intent (ask_name/
            # ask_delivery/...) that the phrase heuristic above missed --
            # _try_fresh_llm_qa would no-op on it (it self-gates on
            # _looks_like_question), so acknowledge + re-ask the date as one
            # sequenced Play and stay on VISIT_DATE. Not a date answer.
            await play_keys(
                call_uuid, ["fresh_qa_unavailable", "fresh_ask_visit_date"],
                session, log_transcript=[False, False],
            )
            return True

        # Vague range ("next weekend", "agle hafte") with no concrete day --
        # acknowledge (details -> WhatsApp) and ask for the exact day once,
        # then accept whatever comes next. Checked before everything below so
        # a range never slips into confirm.
        if _is_vague_date_range(t) and not getattr(session, "visit_day_clarify_asked", False):
            session.visit_day_clarify_asked = True
            await play_key(call_uuid, "fresh_ask_visit_day", session)
            return True

        # Non-committal replies to "when can you come?" -- an explicit
        # deferral ("kal bataunga"), "busy"/"sochna_hai"/"uncertain" intents,
        # a "just browsing / I'll think about it" phrase, or "just send it to
        # me on WhatsApp" (wants info, not a booked slot). NOT a slot -- must
        # not fake-confirm a hot lead off it (confirmed live: "abhi bas dekh
        # raha hoon" landed as urgency text; "theek hai aap bhej do" would
        # land as visit_date). One gentle re-ask, then a soft no-push close.
        _wants_info_sent = any(
            p in t.lower().replace("-", " ")
            for p in ("bhej", "भेज", "send it", "send me", "just send", "whatsapp par bhej")
        )
        _noncommittal = (
            _is_appointment_deferral(t)
            or bool({"busy", "sochna_hai", "uncertain"} & set(intents))
            or _is_noncommittal_visit_reply(t)
            or _wants_info_sent
        )
        _real_content = bool(t) and not _is_filler_continuer(t)

        if _noncommittal or not _real_content:
            if not getattr(session, "visit_date_reask_tried", False):
                session.visit_date_reask_tried = True
                await play_key(call_uuid, "fresh_ask_visit_date", session)
                return True
            await play_key(call_uuid, "fresh_soft_defer" if _noncommittal else "fresh_no_date_close", session)
            await fire_whatsapp(session, call_uuid)
            return False

        _looks_dateish = (
            "appointment_confirm" in intents
            or _has_date_context_digit(t)
            or _has_standalone_day_suffix(t)
            or bool(set(_tokenize(t)) & _VISIT_COMMITMENT_TOKENS)
            or bool(set(_tokenize(t.lower().replace("-", " "))) & _SPECIFIC_DAY_TOKENS)
        )

        # Bare affirmative ("haan", "theek hai ji") with no day named --
        # agreement, but not a slot. Ask which day once; a positive that
        # comes AFTER we've already re-asked is taken as good enough.
        if ("positive" in intents and not _looks_dateish
                and not getattr(session, "visit_date_reask_tried", False)):
            session.visit_date_reask_tried = True
            await play_key(call_uuid, "fresh_ask_visit_date", session)
            return True

        # Confirm only on a real date/commitment signal, or a "yes" that
        # survived the re-ask above. Anything else with content but no such
        # signal (ambiguous chatter after some Q&A) gets one date re-ask,
        # then a soft close -- never a fabricated appointment.
        if not (_looks_dateish or "positive" in intents):
            if not getattr(session, "visit_date_reask_tried", False):
                session.visit_date_reask_tried = True
                await play_key(call_uuid, "fresh_ask_visit_date", session)
                return True
            await play_key(call_uuid, "fresh_no_date_close", session)
            await fire_whatsapp(session, call_uuid)
            return False

        # Real answer to "kab aa sakte hain?" -- confirm the appointment.
        session.appointment_confirmed = True
        session.visit_date_raw_text   = t
        session.lead["visit_date"]    = t
        session.lead_tier_override    = "hot"
        session.lead_score_override   = 85
        await play_key(call_uuid, "fresh_appointment_confirmed", session)
        await asyncio.sleep(3.0)
        return False

    # Added 2026-08-19 -- fresh_cta had ZERO LLM-fallback coverage (the only
    # one of the 4 flows with none at all): a genuine question this catch-all
    # didn't have a dedicated branch for (ask_price_range, ask_valuation,
    # ask_name, a novel phrasing entirely) previously just got the generic
    # "yeh accha design hai, kab aa sakte hain?" fresh_objection reask, which
    # doesn't acknowledge what was actually asked. Uses _FRESH_LLM_FACTS, NOT
    # _REACT_LLM_FACTS -- see that constant's comment for why fresh_cta needs
    # its own grounding (different campaign, no exchange-offer framing
    # established for this funnel). Gated the same way as call2/call3's
    # equivalent additions: fires on a genuinely empty match OR a recognized-
    # but-unanswered informational question, never on a bare "positive"-only
    # acknowledgment. Stays in the same single APPOINTMENT state either way
    # (fresh_cta has no sub-states to advance between).
    if _only_unanswered_qa_intents(intents) and not _is_filler_continuer(t):
        # 2026-08-23 CONFIRMED-LIVE GAP: this is the ORIGINAL LLM-fallback
        # call site (predates _try_fresh_llm_qa, still the only path once
        # fresh_step reaches VISIT_DATE or is None for call_cycle 2/3) --
        # it never got the same 2026-08-22 fixes (bilingual lang threading,
        # not treating the generic REPROMPT_TEXT as a real answer, the
        # fresh_qa_unavailable acknowledgment on failure). Confirmed live: a
        # real caller asked two clearly-recognized questions (ask_offer_scope,
        # ask_price_range) at this stage and got silently reprompted with no
        # acknowledgment either time -- same failure mode _try_fresh_llm_qa
        # was built to close, just unreached from here. Applying the same
        # three fixes here for consistency.
        _fresh_voice = PREFIX_VOICE_MAP.get("fresh", "simran")
        _lang = "en" if getattr(session, "lang", "hi") == "en" else "hi"
        llm_answer = await _llm_fallback_with_filler(call_uuid, t, session, _fresh_voice, facts=_FRESH_LLM_FACTS, lang=_lang)
        if llm_answer in (_REACT_LLM_REPROMPT_TEXT, _REACT_LLM_REPROMPT_TEXT_EN):
            llm_answer = None
        # 2026-08-23 — combined into one Play request (_play_dynamic_then_key),
        # same fix and same reason as _try_fresh_llm_qa: two separate Play
        # requests fired in quick succession let the second cut off the
        # first before the customer hears it (confirmed live, Pratham call).
        # Step-aware reprompt key unchanged: re-asks whatever question is
        # actually pending (budget/urgency) instead of always the generic
        # "come visit" line; resolves to "fresh_objection" for VISIT_DATE/
        # None (call_cycle 2/3), same as before this change.
        if llm_answer and await _play_dynamic_then_key(call_uuid, llm_answer, _fresh_step_question_key(session.fresh_step), session, _fresh_voice, _lang):
            return True
        # Real question, but no answer could be generated/played in time.
        # 2026-09-01 -- this used to play "fresh_qa_unavailable" here and
        # then FALL THROUGH to the catch-all below, which fired a SECOND
        # separate play_key() for the reask. Combined with the LLM filler
        # that had already fired, a real caller heard three Play requests in
        # ~4s, each cutting the previous one mid-word (confirmed live). Send
        # the acknowledgment + the pending-question reask as ONE sequenced
        # Vobiz request instead, and end the turn here -- do not also run
        # the catch-all.
        session.appt_reask_tried = True
        await play_keys(
            call_uuid,
            ["fresh_qa_unavailable", _fresh_step_question_key(session.fresh_step)],
            session, log_transcript=[False, False],
        )
        return True

    # General objection/hesitant/unclear catch-all (stock questions, "WhatsApp
    # options weren't great", expensive, online_cheaper, trust_issue, anything else
    # non-matching): exactly one reask, same appt_reask_tried pattern as the
    # APPOINTMENT state. Step-aware for the same reason as the LLM-fallback
    # reprompt above.
    if not getattr(session, "appt_reask_tried", False):
        session.appt_reask_tried = True
        await play_key(call_uuid, _fresh_step_question_key(session.fresh_step), session)
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
    # Excludes empty-STT (silence) turns from the latency aggregate — this
    # wrapper previously recorded every turn unconditionally, including
    # silence, which drags avg_response_latency/first_response_latency down
    # with near-zero "latencies" that aren't a real response time at all.
    # Matches webhook.py's fresh-lead pipeline, which only ever reaches its
    # own turn_latencies.append() past its own empty-STT early return.
    if transcript and transcript.strip():
        if not hasattr(session, "turn_latencies"):
            session.turn_latencies = []
        session.turn_latencies.append(_latency)
        if getattr(session, "first_reply_ts", None) is None:
            session.first_reply_ts = _latency
    logger.info(f"[{call_uuid}] React turn latency {_latency:.2f}s")
    audit_event(call_uuid, "turn_end", turn=getattr(session, "turn_idx", session.turn_count), latency_ms=round(_latency * 1000))
    return should_continue


async def _handle_reactivation_turn_impl(session, transcript: str, call_uuid: str) -> bool:
    if not hasattr(session, "react_state"):
        session.react_state   = "GREETING"
        session.silence_count = 0
        session.wa_sent       = False
        session.dnc           = False

    session.turn_count = getattr(session, "turn_count", 0) + 1
    session.turn_audio_duration = 0.0
    campaign = getattr(session, "campaign", "react_a")
    p        = get_prefix(campaign)
    state    = session.react_state
    t        = transcript.strip() if transcript else ""

    _cap_reason = _hard_cap_reason(session)
    if _cap_reason:
        logger.info(f"[{call_uuid}] react state={state} campaign={campaign} hard cap hit ({_cap_reason}, turn_count={session.turn_count}) — closing")
        if not hasattr(session, "conversation"):
            session.conversation = []
        if t:
            session.conversation.append(("user", t))
        await play_key(call_uuid, f"{p}_obj_busy", session)
        await fire_whatsapp(session, call_uuid)
        return False

    if t and _is_ivr_fragment(t):
        logger.info(f"[{call_uuid}] react state={state} campaign={campaign} IVR/voicemail fragment detected transcript='{t[:60]}' — withholding reply, marker=ivr_fragment_detected")
        _mark_ivr_fragment(session)
        if not hasattr(session, "conversation"):
            session.conversation = []
        session.conversation.append(("user", t))
        return True

    intents  = detect_intents(t) if t else []

    logger.info(f"[{call_uuid}] react state={state} campaign={campaign} transcript='{t[:60]}' intents={intents}")
    audit_event(call_uuid, "route", turn=getattr(session, "turn_idx", session.turn_count), state=state, campaign=campaign, intents=intents, transcript=t)

    if t and not intents:
        if _LLM_REFUSAL_FALLBACK_ENABLED and await _llm_classify_refusal(t, call_uuid):
            logger.info(f"[{call_uuid}] react state={state} campaign={campaign} LLM refusal-classify fired on unrecognized utterance '{t[:60]}' — treating as not_interested")
            intents = ["not_interested"]
        else:
            session.not_understood_streak = getattr(session, "not_understood_streak", 0) + 1
            session.not_understood_total  = getattr(session, "not_understood_total", 0) + 1
            if session.not_understood_streak >= 3 or session.not_understood_total >= 5:
                logger.info(f"[{call_uuid}] react state={state} campaign={campaign} not_understood cap hit (streak={session.not_understood_streak}, total={session.not_understood_total}) — closing")
                await play_key(call_uuid, f"{p}_obj_busy", session)
                await fire_whatsapp(session, call_uuid)
                return False
    else:
        session.not_understood_streak = 0

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
    # Mirrors webhook.py's fresh-lead pipeline, which only ever reaches its
    # own turn_latencies-recording code past its empty-STT early return —
    # this counter and the same substantive-only gate on turn_latencies
    # below give call_summaries an honest denominator for average latency.
    session.turn_count_substantive = getattr(session, "turn_count_substantive", 0) + 1
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
    if await check_hard_rejection(session, call_uuid, intents, f"{p}_dnc"):
        return False

    _obj_result = await route_objection(session, call_uuid, p, state, intents, t)
    if _obj_result is not None:
        return _obj_result

    # ── GREETING ──────────────────────────────────────────────────────────────
    if state == "GREETING":
        if "confusion_who" in intents:
            await play_keys(call_uuid, [f"{p}_greet_who", f"{p}_offer_main"], session)
            session.react_state = "PRESENT_OFFER"
            asyncio.create_task(fire_whatsapp(session, call_uuid))
            return True
        # Added 2026-08-13, same rollout as PRESENT_OFFER/WHATSAPP_CTA/
        # APPOINTMENT's ask_offer_scope/ask_price_range handling -- confirmed
        # live the same day this state was skipped: a customer asked "कौन से
        # फर्नीचर पे डिस्काउंट चल रहा है?" as their very first turn, before
        # ever hearing the pitch, and it fell through to the generic sale
        # pitch instead of being answered (only worked on their second,
        # reworded attempt once the call had reached PRESENT_OFFER).
        if "ask_offer_scope" in intents:
            # Confirmed live 2026-08-13: this used to also immediately play
            # {p}_offer_main right after -- but q_offer_scope's own text
            # already ends with "Ek aur achhi baat bataun?", so the customer
            # heard that exact question twice back to back, glued into one
            # message, followed by a redundant re-pitch of the same sale
            # they hadn't even responded to yet. Answer once, wait for them.
            await play_key(call_uuid, f"{p}_q_offer_scope", session)
            session.react_state = "PRESENT_OFFER"
            asyncio.create_task(fire_whatsapp(session, call_uuid))
            return True
        if "ask_price_range" in intents:
            # Same fix as ask_offer_scope above.
            await play_key(call_uuid, f"{p}_q_price_range", session)
            session.react_state = "PRESENT_OFFER"
            asyncio.create_task(fire_whatsapp(session, call_uuid))
            return True
        if "repeat" in intents:
            await play_keys(call_uuid, [f"{p}_greet_repeat", f"{p}_offer_main"], session, log_transcript=[True, False])
            session.react_state = "PRESENT_OFFER"
            asyncio.create_task(fire_whatsapp(session, call_uuid))
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
        if "already_purchased" in intents:
            await play_key(call_uuid, f"{p}_already_purchased", session)
            return False
        if not intents and getattr(session, "ivr_fragment_count", 0) > 0:
            # An IVR/hold-message fragment already matched earlier THIS call
            # (_is_ivr_fragment() above caught the complete phrase at least
            # once) -- confirmed live 2026-08-09: the same continuous carrier
            # loop gets chopped into turns by STT/VAD, and partial fragments
            # ("रही।", "लाइन पर।") don't match the exact-phrase list, so they
            # fell through here and reprompted a machine loop 3-4x in a row.
            # Once we've already confirmed this call looks like IVR, treat a
            # further unmatched turn as "probably the same loop continuing"
            # -- but never truly silent (2026-08-13): play the generic
            # WhatsApp-deflection line instead. Harmless to a real machine,
            # and means a real customer whose speech got misflagged (see
            # wa_fallback_deflect_{voice}'s comment) still gets acknowledged.
            # A real intent match (this check only runs when intents is
            # empty) still overrides this every time.
            voice = PREFIX_VOICE_MAP.get(p, "shreya")
            await play_key(call_uuid, f"wa_fallback_deflect_{voice}", session)
            await fire_whatsapp(session, call_uuid)
            logger.info(f"[{call_uuid}] react state={state} campaign={campaign} unmatched turn after prior IVR detection — deflecting to WhatsApp instead of staying silent")
            return True
        if not intents and not _is_filler_continuer(t):
            # Genuinely unmatched — try the grounded LLM fallback before
            # falling back to the static "didn't catch that" reprompt (see
            # _reprompt_or_llm_fallback's docstring). Stay in GREETING,
            # don't advance or fire WA. Filler ("hmm") deliberately skips
            # this branch and falls through to the Default below instead —
            # see _is_filler_continuer's docstring.
            voice = PREFIX_VOICE_MAP.get(p, "shreya")
            await _reprompt_or_llm_fallback(call_uuid, t, session, voice)
            return True
        # Default — fire WA immediately on first response, then present offer
        session.react_state = "PRESENT_OFFER"
        asyncio.create_task(fire_whatsapp(session, call_uuid))
        await play_key(call_uuid, f"{p}_offer_main", session)
        return True

    # ── PRESENT_OFFER ─────────────────────────────────────────────────────────
    if state == "PRESENT_OFFER":
        # Added 2026-08-13 -- this state previously had no Q&A handling at
        # all (unlike WHATSAPP_CTA/APPOINTMENT below, which already have
        # this same loop), so a real question landing here fell straight
        # through to the generic hook_cta pitch at the bottom regardless of
        # what was actually asked. Confirmed live: "कौन से फर्नीचर पे ऑफर है?"
        # (which furniture is the offer on?) landed in this exact state.
        # ask_offer_scope handled separately from the qa_keys loop below --
        # user feedback 2026-08-13: its answer ("sofa, bed, dining table...
        # ek aur achhi baat bataun?") is written to flow straight into
        # hook_cta next, the same two-line shape offer_main->hook_cta
        # already uses elsewhere, not the generic wa_cta hand-off every
        # other Q&A answer here gets.
        if "ask_offer_scope" in intents:
            await play_keys(call_uuid, [f"{p}_q_offer_scope", f"{p}_hook_cta"], session, log_transcript=[True, False])
            session.react_state = "WHATSAPP_CTA"
            asyncio.create_task(fire_whatsapp(session, call_uuid))
            return True
        qa_keys = {
            "confusion_who":   f"{p}_greet_who",
            "ask_location":    f"{p}_q_location",
            "ask_timings":     f"{p}_q_location",
            "ask_name":        f"{p}_q_name",
            "ask_valuation":   f"{p}_q_valuation",
            "ask_delivery":    f"{p}_q_valuation",
            "ask_price_range": f"{p}_q_price_range",
        }
        # Collect EVERY matched question's answer key, not just the first --
        # added 2026-08-13. The old "first match wins, return immediately"
        # shape meant a customer asking two things in one turn ("showroom
        # kahan hai aur price kya hai") only ever got the first one answered;
        # the second was silently dropped, not deferred -- nothing re-asks a
        # dropped question later, so it just never gets answered unless the
        # customer repeats it. Deduped so ask_location+ask_timings (which
        # share one answer key) don't play the same clip twice.
        matched_plan_keys = []
        for intent_name, plan_key in qa_keys.items():
            if intent_name in intents and plan_key not in matched_plan_keys:
                matched_plan_keys.append(plan_key)
        if matched_plan_keys:
            # Confirmed live 2026-08-13: two separate play_key() calls
            # here let the second interrupt the first before a real
            # customer heard it -- play_keys() sends both as one native
            # Vobiz sequence instead. See _vobiz_play()'s docstring.
            await play_keys(call_uuid, matched_plan_keys + [f"{p}_wa_cta"], session,
                             log_transcript=[True] * len(matched_plan_keys) + [False])
            session.react_state = "WHATSAPP_CTA"
            await fire_whatsapp(session, call_uuid)
            return True
        if "already_purchased" in intents:
            await play_key(call_uuid, f"{p}_already_purchased", session)
            return False
        if "offer_clarify" in intents:
            await play_key(call_uuid, f"{p}_offer_explain", session)
            return True
        if "trust_issue" in intents:
            await play_key(call_uuid, f"{p}_offer_trust", session)
            return True
        if "buying_signal" in intents:
            await play_keys(call_uuid, [f"{p}_offer_urgency", f"{p}_wa_cta"], session, log_transcript=[True, False])
            session.react_state = "WHATSAPP_CTA"
            await fire_whatsapp(session, call_uuid)
            return True
        # Added 2026-08-19 -- confirmed live: a customer volunteering a
        # date/time before being asked ("शाम को चार बजे") wasn't checked
        # anywhere in this state's chain, so it silently fell all the way
        # through to the generic {p}_hook_cta pitch at the bottom, which
        # doesn't acknowledge the time at all -- a real reply-quality bug,
        # not a keyword miss. Treated like buying_signal (strong positive
        # engagement) rather than trying to book the date right here -- the
        # date itself is NOT stored/reused; the customer will be asked again
        # once APPOINTMENT state is reached, same as if they'd said nothing.
        # Real early-date capture (skip the later re-ask) is a separate,
        # bigger piece of work -- flagged, not attempted here.
        if "appointment_confirm" in intents:
            await play_keys(call_uuid, [f"{p}_offer_urgency", f"{p}_wa_cta"], session, log_transcript=[True, False])
            session.react_state = "WHATSAPP_CTA"
            await fire_whatsapp(session, call_uuid)
            return True
        if "expensive" in intents:
            await play_keys(call_uuid, [f"{p}_obj_expensive", f"{p}_wa_cta"], session, log_transcript=[True, False])
            session.react_state = "WHATSAPP_CTA"
            await fire_whatsapp(session, call_uuid)
            return True
        if "online_cheaper" in intents:
            await play_keys(call_uuid, [f"{p}_obj_online", f"{p}_wa_cta"], session, log_transcript=[True, False])
            session.react_state = "WHATSAPP_CTA"
            await fire_whatsapp(session, call_uuid)
            return True
        if "not_interested" in intents:
            await play_key(call_uuid, f"{p}_obj_not_interested", session)
            await fire_whatsapp(session, call_uuid)
            return False
        if "busy" in intents:
            await play_keys(call_uuid, [f"{p}_obj_busy", f"{p}_wa_cta"], session, log_transcript=[True, False])
            session.react_state = "WHATSAPP_CTA"
            await fire_whatsapp(session, call_uuid)
            return True
        if not intents and getattr(session, "ivr_fragment_count", 0) > 0:
            # Same IVR-loop-continuation suppression as GREETING — see that
            # branch's comment for the full explanation. Never truly silent
            # (2026-08-13) -- see wa_fallback_deflect_{voice}'s comment.
            voice = PREFIX_VOICE_MAP.get(p, "shreya")
            await play_key(call_uuid, f"wa_fallback_deflect_{voice}", session)
            await fire_whatsapp(session, call_uuid)
            logger.info(f"[{call_uuid}] react state={state} campaign={campaign} unmatched turn after prior IVR detection — deflecting to WhatsApp instead of staying silent")
            return True
        if not intents and not _is_filler_continuer(t):
            # Genuinely unmatched — same pattern as GREETING/WA_CHECK/WHATSAPP_CTA.
            # Filler ("hmm") deliberately skips this branch and falls through to
            # the Default below instead — see _is_filler_continuer's docstring
            # (business decision 2026-08-04: let it proceed, don't reprompt, but
            # also don't score it -- intents stays empty either way).
            voice = PREFIX_VOICE_MAP.get(p, "shreya")
            await _reprompt_or_llm_fallback(call_uuid, t, session, voice)
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
        if "already_purchased" in intents:
            await play_key(call_uuid, f"{p}_already_purchased", session)
            return False
        if "busy" in intents or "sochna_hai" in intents:
            await play_keys(call_uuid, [f"{p}_obj_think", f"{p}_close"], session)
            session.react_state = "CLOSE"
            return False
        # Any question about who/location/name/valuation/delivery → answer + move to APPOINTMENT
        qa_keys = {
            "confusion_who":   f"{p}_greet_who",
            "ask_location":    f"{p}_q_location",
            "ask_timings":     f"{p}_q_location",
            "ask_name":        f"{p}_q_name",
            "ask_valuation":   f"{p}_q_valuation",
            "ask_delivery":    f"{p}_q_valuation",
            "ask_price_range": f"{p}_q_price_range",
            "ask_offer_scope": f"{p}_q_offer_scope",
        }
        # Collect every matched question's answer key instead of stopping at
        # the first -- see PRESENT_OFFER's identical fix above for the full
        # reasoning (2026-08-13). interest_signals credited once per turn
        # regardless of how many questions were asked, same as before.
        matched_plan_keys = []
        for intent_name, plan_key in qa_keys.items():
            if intent_name in intents and plan_key not in matched_plan_keys:
                matched_plan_keys.append(plan_key)
        if matched_plan_keys:
            session.interest_signals = getattr(session, "interest_signals", 0) + 1
            # Confirmed live 2026-08-13: this exact combination (answer
            # then appointment_ask as two separate play_key() calls) is
            # what proved the interrupt bug in the first place -- a real
            # customer's location question got no audible answer at all,
            # cut off by appointment_ask arriving milliseconds later. See
            # _vobiz_play()'s docstring.
            await play_keys(call_uuid, matched_plan_keys + [f"{p}_appointment_ask"], session,
                             log_transcript=[True] * len(matched_plan_keys) + [False])
            session.react_state = "APPOINTMENT"
            await fire_whatsapp(session, call_uuid)
            return True
        if not intents and getattr(session, "ivr_fragment_count", 0) > 0:
            # Same IVR-loop-continuation suppression as GREETING — see that
            # branch's comment for the full explanation. Never truly silent
            # (2026-08-13) -- see wa_fallback_deflect_{voice}'s comment.
            voice = PREFIX_VOICE_MAP.get(p, "shreya")
            await play_key(call_uuid, f"wa_fallback_deflect_{voice}", session)
            await fire_whatsapp(session, call_uuid)
            logger.info(f"[{call_uuid}] react state={state} campaign={campaign} unmatched turn after prior IVR detection — deflecting to WhatsApp instead of staying silent")
            return True
        if not intents and not _is_filler_continuer(t):
            # Genuinely unmatched — try the grounded LLM fallback first (see
            # _reprompt_or_llm_fallback's docstring); falls back to the same
            # "sending you the WhatsApp details" line as before if that
            # fails, no score inflation, no jump to APPOINTMENT either way.
            # Filler ("hmm") deliberately skips this branch and falls through to
            # the Default below instead — see _is_filler_continuer's docstring.
            _voice = PREFIX_VOICE_MAP.get(p, "shreya")
            reply = await _llm_fallback_with_filler(call_uuid, t, session, _voice)
            if not (reply and await play_dynamic_text(call_uuid, reply, session, voice=_voice)):
                await play_key(call_uuid, f"{p}_wa_cta", session)
            return True
        # Default: positive engagement → fire WA, move to APPOINTMENT, ask
        await fire_whatsapp(session, call_uuid)
        session.interest_signals = getattr(session, "interest_signals", 0) + 1
        session.react_state = "APPOINTMENT"
        await play_key(call_uuid, f"{p}_appointment_ask", session)
        return True

    # ── APPOINTMENT ───────────────────────────────────────────────────────────
    if state == "APPOINTMENT":
        if "already_purchased" in intents:
            await play_key(call_uuid, f"{p}_already_purchased", session)
            return False
        # Any question still gets answered FIRST, then re-ask for date (before any confirm check)
        qa_keys = {
            "confusion_who":   f"{p}_greet_who",
            "ask_location":    f"{p}_q_location",
            "ask_timings":     f"{p}_q_location",
            "ask_name":        f"{p}_q_name",
            "ask_valuation":   f"{p}_q_valuation",
            "ask_delivery":    f"{p}_q_valuation",
            "ask_price_range": f"{p}_q_price_range",
            "ask_offer_scope": f"{p}_q_offer_scope",
        }
        # Collect every matched question's answer key instead of stopping at
        # the first -- see PRESENT_OFFER's identical fix above for the full
        # reasoning (2026-08-13). If ANY matched question is valuation/
        # delivery, skip the trailing appointment_ask for the whole batch --
        # q_valuation's own script text already ends by asking for a date,
        # so appending appointment_ask after it would ask twice in one turn.
        matched_plan_keys = []
        skip_reask_append = False
        for intent_name, plan_key in qa_keys.items():
            if intent_name in intents and plan_key not in matched_plan_keys:
                matched_plan_keys.append(plan_key)
                if intent_name in ("ask_valuation", "ask_delivery"):
                    skip_reask_append = True
        if matched_plan_keys:
            if skip_reask_append:
                await play_keys(call_uuid, matched_plan_keys, session,
                                 log_transcript=[True] * len(matched_plan_keys))
                return True
            # Confirmed live 2026-08-13: appt_reask_tried is consumed once
            # by any unclear reply and never reset, so a legitimate
            # intervening question here (answered correctly) silently
            # spent the caller's only "unclear reply" allowance -- the
            # NEXT unclear reply, even turns later and unrelated to this
            # one, then fell straight through to give-up-and-close
            # instead of getting its own chance. This re-ask is a fresh
            # question, so it earns a fresh reask budget. Also confirmed
            # live the same day: answer+appointment_ask as two separate
            # play_key() calls let the second interrupt the first before
            # a real customer heard it -- play_keys() sends both as one
            # native Vobiz sequence instead. See _vobiz_play()'s docstring.
            session.appt_reask_tried = False
            await play_keys(call_uuid, matched_plan_keys + [f"{p}_appointment_ask"], session,
                             log_transcript=[True] * len(matched_plan_keys) + [False])
            return True
        if "not_interested" in intents or "busy" in intents:
            session.react_state = "CLOSE"
            await play_key(call_uuid, f"{p}_close", session)
            return False
        # Treat as confirmation if a concrete date/day keyword was used,
        # OR if the transcript contains a digit (e.g. "6 august", "15 tareek", "20 july")
        # since we are explicitly in the APPOINTMENT state asking for a date.
        # Plain "haan"/"positive" alone is NOT enough to confirm an appointment.
        _has_digit = _has_date_context_digit(t)
        _has_day_suffix = _has_standalone_day_suffix(t)
        if ("appointment_confirm" in intents or _has_digit or _has_day_suffix) and not _is_appointment_deferral(t) and not _is_timing_question(t) and not _is_vague_time_without_commitment(t):
            # HOT LEAD — appointment confirmed
            session.appointment_confirmed = True
            session.visit_date_raw_text = t
            session.lead_tier_override = "hot"
            session.lead_score_override = 85
            session.react_state = "CLOSE"
            await play_key(call_uuid, f"{p}_appointment_confirmed", session)
            await asyncio.sleep(3.0)
            return False
        # Not a date -- before treating this as a genuinely unclear reply,
        # see if it's actually an answerable question the qa_keys loop above
        # just doesn't have a keyword for (2026-08-13, same rollout as the
        # other states' reprompt branches). Gated on `not intents`, same as
        # every other state's LLM fallback call -- confirmed live the same
        # day this was missing here: "ठीक है, ओके" (already matched as
        # "positive", just not a date) fell through to the LLM anyway, and
        # burned 2.7s classifying something that was never going to be
        # ANSWERABLE (it isn't a question at all) before landing on the
        # exact same reask it would've gotten instantly otherwise. A real
        # grounded answer still doesn't spend the reask budget when this
        # does run -- it was a real exchange, not confusion.
        # Filler guard added 2026-08-13, matching GREETING/PRESENT_OFFER/
        # WHATSAPP_CTA above -- this was the one state that sent bare filler
        # ("हेलो" etc.) into the ungrounded LLM-answer path instead of
        # treating it as a check-in. See _FILLER_CONTINUER_WORDS' docstring.
        if not intents and not _is_filler_continuer(t):
            _voice = PREFIX_VOICE_MAP.get(p, "shreya")
            _llm_answer = await _llm_fallback_with_filler(call_uuid, t, session, _voice)
            # 2026-08-23 -- combined into one Play request (_play_dynamic_then_key)
            # instead of two separate calls -- see that helper's docstring:
            # confirmed live (Pratham, fresh_cta) that a second Play request
            # fired ~2s after the first cuts it off before the customer
            # hears it. Same shape here (react_a/b/c's APPOINTMENT state).
            if _llm_answer and await _play_dynamic_then_key(call_uuid, _llm_answer, f"{p}_appointment_ask", session, _voice, "hi"):
                return True
        # Unclear response — acknowledge + re-ask once with a different line.
        # log_transcript left at its default (True) as of 2026-08-13 -- this
        # is a standalone reply with no preceding logged half in this turn
        # (unlike the play_keys([True, False]) pairs elsewhere in this file),
        # so suppressing it made the stored transcript look like the agent
        # went silent. Confirmed live on the Pratham call: the customer's
        # final "haan ji" has no assistant turn after it in call_summaries.
        # full_transcript even though the agent did reply on the recording.
        if not getattr(session, "appt_reask_tried", False):
            session.appt_reask_tried = True
            await play_key(call_uuid, f"{p}_appointment_reask", session)
            return True
        # Confirmed live 2026-08-13: this used to reuse {p}_close ("Bilkul
        # sahi decision hai" -- that's absolutely the right decision), which
        # is wrong here -- the caller never confirmed anything, that's
        # exactly why this branch was reached. Honest neutral sign-off.
        session.react_state = "CLOSE"
        await play_key(call_uuid, f"{p}_close_no_response", session)
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
    session.turn_audio_duration = 0.0
    state   = session.c2_state
    t       = transcript.strip() if transcript else ""

    _cap_reason = _hard_cap_reason(session)
    if _cap_reason:
        logger.info(f"[{call_uuid}] call2 hard cap hit ({_cap_reason}, turn_count={session.turn_count}) — closing")
        if not hasattr(session, "conversation"):
            session.conversation = []
        if t:
            session.conversation.append(("user", t))
        await play_key(call_uuid, "c2_close_busy", session)
        await fire_whatsapp(session, call_uuid)
        return False

    if t and _is_ivr_fragment(t):
        logger.info(f"[{call_uuid}] call2 state={state} IVR/voicemail fragment detected transcript='{t[:60]}' — withholding reply, marker=ivr_fragment_detected")
        _mark_ivr_fragment(session)
        if not hasattr(session, "conversation"):
            session.conversation = []
        session.conversation.append(("user", t))
        return True

    intents = detect_intents(t) if t else []

    logger.info(f"[{call_uuid}] call2 state={state} transcript='{t[:60]}' intents={intents}")
    audit_event(call_uuid, "route", turn=getattr(session, "turn_idx", session.turn_count), state=state, campaign=getattr(session, "campaign", None), intents=intents, transcript=t)

    if t and not intents:
        if _LLM_REFUSAL_FALLBACK_ENABLED and await _llm_classify_refusal(t, call_uuid):
            logger.info(f"[{call_uuid}] call2 LLM refusal-classify fired on unrecognized utterance '{t[:60]}' — treating as not_interested")
            intents = ["not_interested"]
        else:
            session.not_understood_streak = getattr(session, "not_understood_streak", 0) + 1
            session.not_understood_total  = getattr(session, "not_understood_total", 0) + 1
            if session.not_understood_streak >= 3 or session.not_understood_total >= 5:
                logger.info(f"[{call_uuid}] call2 not_understood cap hit (streak={session.not_understood_streak}, total={session.not_understood_total}) — closing")
                await play_key(call_uuid, "c2_close_busy", session)
                await fire_whatsapp(session, call_uuid)
                return False
    else:
        session.not_understood_streak = 0

    # session.campaign stays react_a/b/c across a lead's whole call_cycle
    # (call2/call3 don't get their own campaign value), so feeding this
    # handler's intents into the SAME set _handle_reactivation_turn_impl
    # (Call1) already writes to is what makes call_summaries.intents_fired /
    # interest_signals / rejection_signals / offer_explained / cta_accepted
    # and finalize_call()'s not_interested/dnc detection actually reflect
    # call2 conversations, instead of reading as if nothing was ever said.
    if not hasattr(session, "react_intents_seen"):
        session.react_intents_seen = set()
    session.react_intents_seen.update(intents)

    # ── Silence ───────────────────────────────────────────────────────────────
    if not t:
        session.silence_count += 1
        if session.silence_count >= 3:
            await play_key(call_uuid, "c2_close_busy", session)
            await fire_whatsapp(session, call_uuid)
            return False
        return True

    session.silence_count = 0
    session.turn_count_substantive = getattr(session, "turn_count_substantive", 0) + 1
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
    if await check_hard_rejection(session, call_uuid, intents, "ra_dnc"):
        return False

    _obj_result = await route_objection(session, call_uuid, "c2", state, intents, t)
    if _obj_result is not None:
        return _obj_result

    # ── GREETING ──────────────────────────────────────────────────────────────
    if state == "GREETING":
        if "confusion_who" in intents:
            await play_keys(call_uuid, ["c2_greet_reorient", "c2_wa_check"], session, log_transcript=[True, False])
            session.c2_state = "WA_CHECK"
            return True
        if "busy" in intents:
            await play_key(call_uuid, "c2_close_busy", session)
            return False
        if "not_interested" in intents:
            # Two plays combined into one native Vobiz sequence -- see
            # _vobiz_play()'s docstring (confirmed live 2026-08-13: two
            # separate play_key() calls let the second interrupt the first).
            await play_keys(call_uuid, ["c2_obj_not_interested", "c2_close_declined"], session)
            return False
        # Added 2026-08-19 -- audit found call2's GREETING had no LLM-
        # fallback coverage (WA_CHECK below already had it); a genuine
        # unmatched question here previously went straight to WA_CHECK with
        # no attempt to answer it. Same _REACT_LLM_FACTS grounding as
        # react_a/b/c/call3/call2's own WA_CHECK. Stay in GREETING (don't
        # advance the state) on a successful answer, same convention as
        # react_a/b/c's GREETING fallback. Uses _only_unanswered_qa_intents()
        # rather than a bare "not intents" check -- see that helper's
        # docstring -- since this state has no qa_keys loop of its own.
        if _only_unanswered_qa_intents(intents) and not _is_filler_continuer(t):
            voice = PREFIX_VOICE_MAP.get("c2", "ritu")
            await _reprompt_or_llm_fallback(call_uuid, t, session, voice)
            return True
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
        if not intents and any(w in _tokenize(t) for w in (_OPTOUT_NEGATION_WORDS | {"नाही", "naahi"})):
            # Bare/near-bare negation with no other matched intent, directly
            # answering the yes/no "did you see the WhatsApp?" question just
            # asked -- e.g. "नाही." / "नहीं हमें नहीं किए।" (confirmed live,
            # call c51fc807..., 2026-08-01). Neither contains an exact
            # wa_no_whatsapp phrase or a receipt-word for _is_wa_not_received()
            # to anchor on -- there's nothing left to match on except "this is
            # a negation and nothing else fired." Treat the same as an
            # explicit wa_no_whatsapp match.
            await play_key(call_uuid, "c2_invite_resend", session)
            await fire_whatsapp(session, call_uuid)
            return True
        # Price objection raised before even confirming they saw the WhatsApp
        # (confirmed live on 8d46a889 — "बहुत रेट है, महंगे हैं" here was
        # silently ignored, agent proceeded to invite_seen as if nothing was
        # said). Reuse DATE_ASK's existing price-objection handling verbatim
        # rather than writing new copy — c2_state is already set to DATE_ASK
        # above, so the customer's reply next turn resolves through that
        # branch's c2_price_asked check as-is.
        if "expensive" in intents or "online_cheaper" in intents:
            await play_key(call_uuid, "c2_obj_price", session)
            session.c2_price_asked = True
            return True
        if not intents and getattr(session, "ivr_fragment_count", 0) > 0:
            # Same IVR-loop-continuation suppression as GREETING — see that
            # branch's comment for the full explanation. Still undo the state
            # advance set at the top of this block, same as the reprompt
            # branch below would. Never truly silent (2026-08-13) -- see
            # wa_fallback_deflect_{voice}'s comment.
            session.c2_state = "WA_CHECK"
            voice = PREFIX_VOICE_MAP.get("c2", "shreya")
            await play_key(call_uuid, f"wa_fallback_deflect_{voice}", session)
            await fire_whatsapp(session, call_uuid)
            logger.info(f"[{call_uuid}] call2 state={state} unmatched turn after prior IVR detection — deflecting to WhatsApp instead of staying silent")
            return True
        if not intents and not _is_filler_continuer(t):
            # Genuinely unmatched turn — the streak/total cap-closure already ran
            # above (before this handler dispatches to state), so don't
            # re-increment here. Just undo the state advance set at the top of
            # this block (we haven't actually confirmed they saw the WhatsApp)
            # and reprompt with the same honest "didn't catch that" line used
            # for this same ambiguity in GREETING/WHATSAPP_CTA.
            # Filler ("hmm") deliberately skips this branch and falls through to
            # the Default below instead — see _is_filler_continuer's docstring.
            session.c2_state = "WA_CHECK"
            voice = PREFIX_VOICE_MAP.get("c2", "shreya")
            await _reprompt_or_llm_fallback(call_uuid, t, session, voice)
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
            # Check for a date in THIS reply before falling back to a re-ask --
            # confirmed live via replay audit (call 8d46a889): a customer who
            # answers the price objection AND gives their date in the same
            # breath ("सैटरडे को फ्री रहेंगे") was unconditionally re-asked for
            # a date they'd already given, because this branch only ever
            # played c2_date_direct. Same detection block as DATE_ASK's own
            # confirmation check just below -- reused verbatim, not reimplemented.
            _has_digit      = _has_date_context_digit(t)
            _has_day_suffix = _has_standalone_day_suffix(t)
            if ("appointment_confirm" in intents or _has_digit or _has_day_suffix) and not _is_appointment_deferral(t) and not _is_timing_question(t) and not _is_vague_time_without_commitment(t):
                session.appointment_confirmed = True
                session.visit_date_raw_text   = t
                session.lead_tier_override    = "hot"
                session.lead_score_override   = 85
                await play_key(call_uuid, "c2_booked", session)
                await asyncio.sleep(3.0)
                return False
            await play_key(call_uuid, "c2_date_direct", session)
            return True

        if "not_interested" in intents:
            # Two plays combined into one native Vobiz sequence -- see
            # _vobiz_play()'s docstring (confirmed live 2026-08-13: two
            # separate play_key() calls let the second interrupt the first).
            await play_keys(call_uuid, ["c2_obj_not_interested", "c2_close_declined"], session)
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
        _has_digit      = _has_date_context_digit(t)
        _has_day_suffix = _has_standalone_day_suffix(t)
        if ("appointment_confirm" in intents or _has_digit or _has_day_suffix) and not _is_appointment_deferral(t) and not _is_timing_question(t) and not _is_vague_time_without_commitment(t):
            session.appointment_confirmed = True
            session.visit_date_raw_text   = t
            session.lead_tier_override    = "hot"
            session.lead_score_override   = 85
            await play_key(call_uuid, "c2_booked", session)
            await asyncio.sleep(3.0)
            return False

        # Added 2026-08-19, same audit -- a genuine unanswered question here
        # previously went straight into the vague-reask-then-close
        # fallthrough below, same treatment as an unclear non-answer. Try to
        # actually answer it first, same pattern as call3's DECISION_DATE
        # and react_a/b/c's APPOINTMENT state -- answer, then re-ask the
        # date in the same turn, doesn't consume the reask budget below. Uses
        # _only_unanswered_qa_intents() -- see that helper's docstring --
        # since DATE_ASK has no qa_keys loop of its own either.
        if _only_unanswered_qa_intents(intents) and not _is_filler_continuer(t):
            voice = PREFIX_VOICE_MAP.get("c2", "ritu")
            llm_answer = await _llm_fallback_with_filler(call_uuid, t, session, voice)
            # 2026-08-23 -- combined into one Play request, same fix/reason
            # as react_a/b/c's APPOINTMENT state above (call2's DATE_ASK).
            if llm_answer and await _play_dynamic_then_key(call_uuid, llm_answer, "c2_date_direct", session, voice, "hi"):
                return True

        # Vague (including busy/sochna_hai, which fall through to here for
        # this state) — one reask, then close. Deliberate, same as
        # DECISION_DATE's equivalent fallthrough in handle_call3_turn:
        # c2_date_reask doesn't punish a "busy"/"need to think" reply with a
        # hard close, and c2_close_thinking already reads as an appropriate
        # graceful exit for exactly that reply ("soch lijiye, WhatsApp bhej
        # deti hoon"). Left as-is on purpose, not wired into
        # route_objection() -- Call2 isn't the last attempt (Call3 is), so
        # staying slightly more persistent here than Call3's immediate
        # acknowledgment is intentional, not an oversight.
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
    session.turn_audio_duration = 0.0
    state   = session.c3_state
    t       = transcript.strip() if transcript else ""

    _cap_reason = _hard_cap_reason(session)
    if _cap_reason:
        logger.info(f"[{call_uuid}] call3 hard cap hit ({_cap_reason}, turn_count={session.turn_count}) — closing")
        if not hasattr(session, "conversation"):
            session.conversation = []
        if t:
            session.conversation.append(("user", t))
        await play_key(call_uuid, "c3_close_busy", session)
        await fire_whatsapp(session, call_uuid)
        return False

    if t and _is_ivr_fragment(t):
        logger.info(f"[{call_uuid}] call3 state={state} IVR/voicemail fragment detected transcript='{t[:60]}' — withholding reply, marker=ivr_fragment_detected")
        _mark_ivr_fragment(session)
        if not hasattr(session, "conversation"):
            session.conversation = []
        session.conversation.append(("user", t))
        return True

    intents = detect_intents(t) if t else []

    logger.info(f"[{call_uuid}] call3 state={state} transcript='{t[:60]}' intents={intents}")
    audit_event(call_uuid, "route", turn=getattr(session, "turn_idx", session.turn_count), state=state, campaign=getattr(session, "campaign", None), intents=intents, transcript=t)

    if t and not intents:
        if _LLM_REFUSAL_FALLBACK_ENABLED and await _llm_classify_refusal(t, call_uuid):
            logger.info(f"[{call_uuid}] call3 LLM refusal-classify fired on unrecognized utterance '{t[:60]}' — treating as not_interested")
            intents = ["not_interested"]
        else:
            session.not_understood_streak = getattr(session, "not_understood_streak", 0) + 1
            session.not_understood_total  = getattr(session, "not_understood_total", 0) + 1
            if session.not_understood_streak >= 3 or session.not_understood_total >= 5:
                logger.info(f"[{call_uuid}] call3 not_understood cap hit (streak={session.not_understood_streak}, total={session.not_understood_total}) — closing")
                await play_key(call_uuid, "c3_close_busy", session)
                await fire_whatsapp(session, call_uuid)
                return False
    else:
        session.not_understood_streak = 0

    # Same as handle_call2_turn above — feeds the shared react_intents_seen
    # set so call_summaries reflects call3 conversations too.
    if not hasattr(session, "react_intents_seen"):
        session.react_intents_seen = set()
    session.react_intents_seen.update(intents)

    # ── Silence ───────────────────────────────────────────────────────────────
    if not t:
        session.silence_count += 1
        if session.silence_count >= 3:
            await play_key(call_uuid, "c3_close_busy", session)
            await fire_whatsapp(session, call_uuid)
            return False
        return True

    session.silence_count = 0
    session.turn_count_substantive = getattr(session, "turn_count_substantive", 0) + 1
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
    if await check_hard_rejection(session, call_uuid, intents, "ra_dnc"):
        return False

    _obj_result = await route_objection(session, call_uuid, "c3", state, intents, t)
    if _obj_result is not None:
        return _obj_result

    # ── GREETING ──────────────────────────────────────────────────────────────
    if state == "GREETING":
        if "confusion_who" in intents:
            await play_keys(call_uuid, ["c3_greet_reorient", "c3_decision_date"], session, log_transcript=[True, False])
            session.c3_state = "DECISION_DATE"
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
        # Added 2026-08-19 -- audit found call3 had ZERO LLM-fallback coverage
        # anywhere in this handler (react_a/b/c and call2's WA_CHECK already
        # had it; call3 was simply never wired in). A genuine unmatched
        # question here ("EMI milta hai kya" etc.) previously just fell
        # straight through to c3_decision_date with no attempt to answer it.
        # Same _REACT_LLM_FACTS grounding as react_a/b/c/call2 applies
        # unchanged -- call3 is the same offer/campaign content, just the
        # 3rd attempt, so the facts are still accurate here. Stay in
        # GREETING (don't advance to DECISION_DATE) on a successful answer,
        # same convention as react_a/b/c's GREETING fallback. Uses
        # _only_unanswered_qa_intents() -- see that helper's docstring --
        # since this state has no qa_keys loop of its own.
        if _only_unanswered_qa_intents(intents) and not _is_filler_continuer(t):
            voice = PREFIX_VOICE_MAP.get("c3", "simran")
            await _reprompt_or_llm_fallback(call_uuid, t, session, voice)
            return True
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

        _has_digit      = _has_date_context_digit(t)
        _has_day_suffix = _has_standalone_day_suffix(t)
        if ("appointment_confirm" in intents or _has_digit or _has_day_suffix) and not _is_appointment_deferral(t) and not _is_timing_question(t) and not _is_vague_time_without_commitment(t):
            session.appointment_confirmed = True
            session.visit_date_raw_text   = t
            session.lead_tier_override    = "hot"
            session.lead_score_override   = 85
            await play_key(call_uuid, "c3_booked", session)
            await asyncio.sleep(3.0)
            return False

        # Added 2026-08-19, same audit -- a genuine unanswered question here
        # (not a date, not a matched objection) previously went straight to
        # the vague-reask-then-close fallthrough below, identical treatment
        # to a customer who just said something unclear. Try to actually
        # answer it first; only fall through to the reask/close logic below
        # if the fallback itself produced nothing (matches APPOINTMENT
        # state's pattern in handle_reactivation_turn -- answer, then
        # re-ask the date in the same turn, doesn't consume the reask budget).
        # Uses _only_unanswered_qa_intents() -- see that helper's docstring --
        # since DECISION_DATE has no qa_keys loop of its own either.
        if _only_unanswered_qa_intents(intents) and not _is_filler_continuer(t):
            voice = PREFIX_VOICE_MAP.get("c3", "simran")
            llm_answer = await _llm_fallback_with_filler(call_uuid, t, session, voice)
            # 2026-08-23 -- combined into one Play request, same fix/reason
            # as react_a/b/c's APPOINTMENT state above (call3's DECISION_DATE).
            if llm_answer and await _play_dynamic_then_key(call_uuid, llm_answer, "c3_decision_date", session, voice, "hi"):
                return True

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
