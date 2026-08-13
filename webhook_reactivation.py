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
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from groq import AsyncGroq

from knowledge_react_abc import REACT_ABC_INTENTS, get_script, get_prefix, SHARED_INTENTS, SHARED_SCRIPT, PREFIX_VOICE_MAP, CALL2_SCRIPT, CALL3_SCRIPT, normalize_fresh_product_key
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
    # Verified removing it still catches the real IVR message this list was
    # built for -- "मैसेज"/"लीव" match the very next turn of the same
    # greeting regardless.
    "मैसेज", "लीव",
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


def _static_wav_path(key: str) -> str:
    return os.path.join(STATIC_DIR, f"{key}_hi.wav")

def _static_url(key: str) -> str | None:
    path = _static_wav_path(key)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return f"{BASE_URL}/audio/static/{key}_hi.wav"
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

IST = ZoneInfo("Asia/Kolkata")
# Independence Day flash sale: flat 50% off, 2026-08-11 through 2026-08-16
# IST. play_key() swaps to each key's "_sale" variant (knowledge_react_abc.py)
# while this is true, leaving the original exchange-offer keys and their
# cached audio untouched — the Aug 17 revert is just this window closing,
# no code change or re-cache pass needed.
_SALE_END = datetime(2026, 8, 16, 23, 59, 59, tzinfo=IST)


def _sale_active() -> bool:
    return datetime.now(IST) <= _SALE_END


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
    call_cycle = getattr(session, "call_cycle", None) if session else None
    if call_cycle == "2":
        script = CALL2_SCRIPT
    elif call_cycle == "3":
        script = CALL3_SCRIPT
    else:
        campaign = getattr(session, "campaign", "react_a") if session else "react_a"
        script   = get_script(campaign)

    # Checked against the base key on purpose, before the sale-variant swap
    # below — offer_explained tracks the semantic slot (was the offer
    # pitched/explained this call), which holds regardless of which offer
    # copy is currently live.
    if session is not None and (key.endswith("_offer_main") or key.endswith("_offer_explain")):
        session.offer_explained = True

    if _sale_active():
        _sale_key = f"{key}_sale"
        if script.get(_sale_key) is not None:
            key = _sale_key

    if session is not None and log_transcript:
        if not hasattr(session, "conversation"):
            session.conversation = []
        # Falls back to SHARED_SCRIPT for keys not in the active flow's own
        # script (e.g. route_objection()'s obj_repeat_generic, which is
        # flow-agnostic and deliberately not duplicated into every per-plan
        # dict). Existing keys are unaffected -- they're always found in
        # their primary script, so this fallback never triggers for them.
        text = script.get(key) or SHARED_SCRIPT.get(key) or key
        session.conversation.append(("assistant", text))

    _turn = getattr(session, "turn_idx", None) if session else None
    if _turn is None:
        _turn = getattr(session, "turn_count", 0) if session else 0

    url = _static_url(key)
    if url:
        logger.info(f"[{call_uuid}] CACHE HIT → {key}")
        audit_event(call_uuid, "tts", turn=_turn, key=key, cached=True)
        if session is not None:
            session.turn_audio_duration = getattr(session, "turn_audio_duration", 0.0) + _wav_file_duration(_static_wav_path(key))
        return url

    logger.warning(f"[{call_uuid}] CACHE MISS → {key} — generating live")
    audit_event(call_uuid, "tts", turn=_turn, key=key, cached=False)
    text = script.get(key) or SHARED_SCRIPT.get(key)
    if not text:
        logger.error(f"[{call_uuid}] No text for key: {key}")
        return None
    try:
        from tts_engine import get_speech
        wav_bytes, audio_url, _ = await get_speech(text, lang="hi", static_key=key)
        if audio_url:
            if session is not None:
                session.turn_audio_duration = getattr(session, "turn_audio_duration", 0.0) + _wav_bytes_duration(wav_bytes or b"")
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
    # Global switch, not sale-window-gated like play_key()'s key swap --
    # fire_whatsapp() is idempotent per lead (wa_sent guard above), so an
    # in-flight lead who already got their WhatsApp keeps that message;
    # this only affects sends that haven't happened yet, which from
    # 2026-08-11 onward are overwhelmingly new leads pitched the sale.
    _offer_label = "Independence Day Sale — Flat 50% off till 16th August" if _sale_active() else "25+25% exchange offer"
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

    Priority order below is the FULL intended routing order for the
    eventual redesign. Right now only category 2 (repeat/didn't-understand)
    is live -- every other category is a stub (commented out, matching the
    intended condition/shape) and always falls through, so this function has
    zero effect on price/trust/not-interested/timing turns today. Those get
    wired in Phase 2 once new cache content exists for them.

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
            voice = PREFIX_VOICE_MAP.get(prefix, "shreya")
            await play_key(call_uuid, f"obj_timing_greet_generic_{voice}", session)
            if prefix in ("ra", "rb", "rc"):
                session.react_state = "PRESENT_OFFER"
                asyncio.create_task(fire_whatsapp(session, call_uuid))
                await play_key(call_uuid, f"{prefix}_offer_main", session, log_transcript=False)
            elif prefix == "c2":
                session.c2_state = "WA_CHECK"
                await play_key(call_uuid, "c2_wa_check", session, log_transcript=False)
            elif prefix == "c3":
                session.c3_state = "DECISION_DATE"
                await play_key(call_uuid, "c3_decision_date", session, log_transcript=False)
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

    return None


_TOKEN_EDGE_PUNCT = ".,!?;:'\"()[]{}—-–।॥*"


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
    tokens = []
    for raw in text.lower().split():
        tok = raw.strip(_TOKEN_EDGE_PUNCT)
        if tok:
            tokens.append(tok)
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
_FILLER_CONTINUER_WORDS = {"hmm", "hmmm", "हम्म", "हम्म्म"}


def _is_filler_continuer(text: str) -> bool:
    tokens = _tokenize(text)
    return bool(tokens) and all(tok in _FILLER_CONTINUER_WORDS for tok in tokens)


_BRIDGING_FILLERS = {"bhi", "भी", "mein", "में", "hi", "ही", "toh", "तो"}


def _phrase_in_tokens(keyword: str, boundary_text: str) -> bool:
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
    return False


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
        if keywords and any(_phrase_in_tokens(kw, boundary_text) for kw in keywords):
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
    return matched


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
                model="llama-3.1-8b-instant",
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
OFFER: Independence Day Sale — flat 50% off, sirf 16 August 2026 tak valid.
CATEGORIES COVERED BY THIS OFFER: sofa, bed, dining table, wardrobe, chair.
STARTING PRICES (sirf yeh, aur koi number kabhi mat bolo — wardrobe/chair ka koi price yahan
NAHI diya gaya hai, agar koi wardrobe ya chair ka exact price poochhe toh yeh UNKNOWN hai, kabhi
vague ya generic jawab mat do jaise "achha rate hai"):
  - Sofa: ₹33,000 se shuru
  - Bed: ₹71,000 se shuru
  - Dining set: ₹1,19,000 se shuru
SHOWROOMS: Sector 14 Gurgaon, Delhi, Noida — Monday se Sunday, subah 10 baje se raat 8 baje tak.
NOT COVERED (explicitly UNKNOWN, never answer these): EMI/installment, delivery cost ya time, warranty,
online ordering, cash on delivery, old furniture buyback/exchange terms, payment methods, discount codes,
GST/tax, refund/return policy."""

_REACT_LLM_REPROMPT_TEXT = "Maaf kijiye, thik se sun nahi paayi. Kya aap phir se bata sakte hain?"
_REACT_LLM_UNKNOWN_TEXT = "Yeh detail abhi mere paas nahi hai — main confirm karke WhatsApp par bhej deti hoon."

_REACT_LLM_CLASSIFY_PROMPT = f"""Neeche ek customer ka jawab hai ek outbound sales call mein (Krishna
Furniture, Independence Day sale). Aapke paas sirf yeh FACTS hain:

{_REACT_LLM_FACTS}

Customer ne kaha: "{{utterance}}"

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

_REACT_LLM_ANSWER_PROMPT = f"""Aap Priya hain, Krishna Furniture ki taraf se phone par baat kar rahi hain.
Customer ne ek sawaal poocha hai jiska jawab neeche diye FACTS mein hai.

FACTS:
{_REACT_LLM_FACTS}

Customer ne poocha: "{{utterance}}"

Sirf in FACTS ke aadhar par, Hindi/Hinglish mein, maximum 2 chhote vaakya (20-25 shabd), jaise phone par
bol rahe ho — jawab do. FACTS mein na ho aisi koi bhi cheez (price, availability, koi bhi fact) mat
kaho. Vague ya generic baat mat karo (jaise "achha rate hai" ya "bahut options hain") agar exact fact
FACTS mein nahi hai — is case mein EXACTLY yeh bolo: "{_REACT_LLM_UNKNOWN_TEXT}". Koi extra explanation
ya prefix mat do, sirf jawab bolo."""

_REACT_LLM_GROUNDED_PRICES = {"₹33,000", "₹71,000", "₹1,19,000"}


async def _react_llm_classify(t: str, call_uuid: str) -> str:
    """Returns 'ANSWERABLE', 'UNKNOWN', or 'UNCLEAR' (defaults to UNCLEAR on any failure)."""
    try:
        resp = await asyncio.wait_for(
            _get_groq_async_client().chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": _REACT_LLM_CLASSIFY_PROMPT.format(utterance=t)}],
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
        return "UNCLEAR"


async def _llm_fallback_reply_impl(t: str, call_uuid: str) -> str | None:
    label = await _react_llm_classify(t, call_uuid)
    if label == "UNCLEAR":
        return _REACT_LLM_REPROMPT_TEXT
    if label == "UNKNOWN":
        return _REACT_LLM_UNKNOWN_TEXT

    try:
        resp = await asyncio.wait_for(
            _get_groq_async_client().chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": _REACT_LLM_ANSWER_PROMPT.format(utterance=t)}],
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


async def llm_fallback_reply(t: str, call_uuid: str) -> str | None:
    """
    Two-step fallback for a turn detect_intents() found nothing for.
    Classifies first; only ANSWERABLE ever reaches free-form generation
    (with the ₹ fabrication guard still applied as a second layer). UNKNOWN
    and UNCLEAR return fixed, pre-written strings -- never LLM output.
    Returns None if the overall pipeline exceeds _REACT_LLM_FALLBACK_HARD_TIMEOUT,
    or if the ANSWERABLE generation step itself fails or produces something
    ungrounded -- either way the caller falls back to the static reprompt line.
    """
    try:
        return await asyncio.wait_for(
            _llm_fallback_reply_impl(t, call_uuid),
            timeout=_REACT_LLM_FALLBACK_HARD_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[{call_uuid}] LLM fallback exceeded {_REACT_LLM_FALLBACK_HARD_TIMEOUT}s hard ceiling, aborting to static reprompt")
        return None


async def play_dynamic_text(call_uuid: str, text: str, session=None) -> bool:
    """
    Speaks arbitrary text live (Sarvam TTS, dynamic hash-keyed cache) rather
    than a pre-cached static key — for llm_fallback_reply()'s generated
    replies, which have no fixed key since the text itself is dynamic.
    Mirrors play_key()'s cache-miss branch.
    """
    if session is not None:
        if not hasattr(session, "conversation"):
            session.conversation = []
        session.conversation.append(("assistant", text))
    _turn = getattr(session, "turn_idx", None) if session else None
    if _turn is None:
        _turn = getattr(session, "turn_count", 0) if session else 0
    try:
        from tts_engine import get_speech
        wav_bytes, audio_url, _ = await asyncio.wait_for(
            get_speech(text, lang="hi", static_key=None), timeout=3.0
        )
        if audio_url:
            if session is not None:
                session.turn_audio_duration = getattr(session, "turn_audio_duration", 0.0) + _wav_bytes_duration(wav_bytes or b"")
            audit_event(call_uuid, "tts", turn=_turn, key="llm_fallback_dynamic", cached=False)
            return await _vobiz_play(call_uuid, audio_url, turn=_turn, kind="reply")
    except asyncio.TimeoutError:
        logger.warning(f"[{call_uuid}] Dynamic TTS for LLM fallback exceeded 3.0s, aborting")
    except Exception as exc:
        logger.error(f"[{call_uuid}] Dynamic TTS for LLM fallback failed: {exc}")
    return False


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
    """Fire-and-forget: plays a topic-matched filler immediately, in parallel with the LLM call that follows."""
    key = _pick_llm_filler_key(t, voice)
    url = _static_url(key)
    if not url:
        return
    _turn = getattr(session, "turn_idx", None) if session else None
    if _turn is None:
        _turn = getattr(session, "turn_count", 0) if session else 0
    asyncio.create_task(_vobiz_play(call_uuid, url, turn=_turn, kind="filler"))


async def _reprompt_or_llm_fallback(call_uuid: str, t: str, session, voice: str) -> None:
    """
    Shared by every "genuinely unmatched turn" branch across GREETING/
    PRESENT_OFFER/WHATSAPP_CTA/APPOINTMENT/call2's WA_CHECK: try the grounded
    LLM fallback first, fall back to the static obj_repeat_generic_{voice}
    reprompt line on any failure.
    """
    await _fire_llm_filler(call_uuid, t, session, voice)
    reply = await llm_fallback_reply(t, call_uuid)
    if reply and await play_dynamic_text(call_uuid, reply, session):
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

    intents = detect_intents(t) if t else []

    logger.info(f"[{call_uuid}] fresh_cta transcript='{t[:60]}' intents={intents}")

    if t and not intents:
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

    # Same product-key derivation /answer-outbound uses to pick the initial
    # greeting (session.fresh_product is the raw query-param string threaded
    # through via _session_meta — not pre-validated, so re-check it here
    # exactly the same way rather than trusting it's one of the 4 known values).
    _raw_product = getattr(session, "fresh_product", "") or ""
    _product_key = normalize_fresh_product_key(_raw_product)

    # Hard decline — "not_interested" per spec; "dnc" folded in too (same
    # top-priority hard-stop convention every other handler in this file uses).
    # Reuses react_a's cached DNC audio directly — no new fresh_dnc key, per spec.
    if await check_hard_rejection(session, call_uuid, intents, "ra_dnc", also_reject_on=("not_interested",)):
        return False

    _obj_result = await route_objection(session, call_uuid, "fresh", session.react_state, intents, t)
    if _obj_result is not None:
        return _obj_result

    # Same confirmation detection as the APPOINTMENT state in
    # handle_reactivation_turn, verbatim — mirrored, not reimplemented.
    _has_digit      = _has_date_context_digit(t)
    _has_day_suffix = _has_standalone_day_suffix(t)
    if ("appointment_confirm" in intents or _has_digit or _has_day_suffix) and not _is_appointment_deferral(t) and not _is_timing_question(t) and not _is_vague_time_without_commitment(t):
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
        for intent_name, plan_key in qa_keys.items():
            if intent_name in intents:
                # Confirmed live 2026-08-13: two separate play_key() calls
                # here let the second interrupt the first before a real
                # customer heard it -- play_keys() sends both as one native
                # Vobiz sequence instead. See _vobiz_play()'s docstring.
                await play_keys(call_uuid, [plan_key, f"{p}_wa_cta"], session, log_transcript=[True, False])
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
        for intent_name, plan_key in qa_keys.items():
            if intent_name in intents:
                session.interest_signals = getattr(session, "interest_signals", 0) + 1
                # Confirmed live 2026-08-13: this exact combination (answer
                # then appointment_ask as two separate play_key() calls) is
                # what proved the interrupt bug in the first place -- a real
                # customer's location question got no audible answer at all,
                # cut off by appointment_ask arriving milliseconds later. See
                # _vobiz_play()'s docstring.
                await play_keys(call_uuid, [plan_key, f"{p}_appointment_ask"], session, log_transcript=[True, False])
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
            await _fire_llm_filler(call_uuid, t, session, PREFIX_VOICE_MAP.get(p, "shreya"))
            reply = await llm_fallback_reply(t, call_uuid)
            if not (reply and await play_dynamic_text(call_uuid, reply, session)):
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
        for intent_name, plan_key in qa_keys.items():
            if intent_name in intents:
                if intent_name in ("ask_valuation", "ask_delivery"):
                    # q_valuation already ends by asking for a date — don't re-ask via appointment_ask
                    await play_key(call_uuid, plan_key, session)
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
                await play_keys(call_uuid, [plan_key, f"{p}_appointment_ask"], session, log_transcript=[True, False])
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
        if not intents:
            await _fire_llm_filler(call_uuid, t, session, PREFIX_VOICE_MAP.get(p, "shreya"))
            _llm_answer = await llm_fallback_reply(t, call_uuid)
            if _llm_answer and await play_dynamic_text(call_uuid, _llm_answer, session):
                await play_key(call_uuid, f"{p}_appointment_ask", session, log_transcript=False)
                return True
        # Unclear response — acknowledge + re-ask once with a different line
        if not getattr(session, "appt_reask_tried", False):
            session.appt_reask_tried = True
            await play_key(call_uuid, f"{p}_appointment_reask", session, log_transcript=False)
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
