import asyncio
# ─────────────────────────────────────────────────────────────────
# supabase_calling.py
# Drop this file into /home/voiceagent/voice-ai/
# ─────────────────────────────────────────────────────────────────

import os
import logging
from datetime import date, datetime, timezone
from typing import Optional
import httpx

from groq_normalize import ai_normalize_lead_fields, ai_normalize_visit_date
# Pure function, no I/O — safe to import from webhook.py's process even though
# outbound_orchestrator.py's own tick() loop runs in a separate systemd unit
# (guarded by `if __name__ == "__main__":`, never triggered by this import).
from outbound_orchestrator import compute_retry_schedule

logger = logging.getLogger(__name__)

SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
TENANT_ID            = os.getenv("TENANT_ID", "krishna_furniture")

# n8n webhook — fires after every call to trigger WhatsApp follow-up
N8N_WEBHOOK_URL = "https://n8n-production-aed7.up.railway.app/webhook/voice-call-complete"

DEVANAGARI_DIGITS = {
    '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
    '५': '5', '६': '6', '७': '7', '८': '8', '९': '9',
}

DEVANAGARI_WORDS = {
    'एक': 1, 'दो': 2, 'तीन': 3, 'चार': 4, 'पाँच': 5,
    'पांच': 5, 'छह': 6, 'सात': 7, 'आठ': 8, 'नौ': 9, 'दस': 10,
    'बीस': 20, 'तीस': 30, 'चालीस': 40, 'पचास': 50,
    'साठ': 60, 'सत्तर': 70, 'अस्सी': 80, 'नब्बे': 90,
    'सौ': 100, 'हज़ार': 1000, 'हजार': 1000,
    'लाख': 100000, 'lac': 100000, 'lakh': 100000,
    'करोड़': 10000000,
}


def _format_inr(amount: int) -> str:
    if amount >= 10000000:
        return f"₹{amount/10000000:.1f} Cr"
    elif amount >= 100000:
        lakh = amount / 100000
        return f"₹{lakh:.1f} L" if lakh != int(lakh) else f"₹{int(lakh)} L"
    elif amount >= 1000:
        s = str(amount)
        if len(s) > 3:
            s = s[:-3] + ',' + s[-3:]
        return f"₹{s}"
    return f"₹{amount}"


def _parse_hindi_words(text: str) -> int:
    total = 0
    current = 0
    words = text.split()
    for word in words:
        val = DEVANAGARI_WORDS.get(word)
        if val is None:
            continue
        if val >= 100000:
            current = current or 1
            total += current * val
            current = 0
        elif val >= 1000:
            current = current or 1
            total += current * val
            current = 0
        elif val == 100:
            current = (current or 1) * 100
        else:
            current += val
    total += current
    return total


def normalize_budget(raw: str) -> str:
    if not raw:
        return raw

    import re

    normalized = ''.join(DEVANAGARI_DIGITS.get(c, c) for c in raw)
    normalized = normalized.lower().strip('.,!? ।')

    # Range like "1 se 2 lakh", "ek se do lakh" — take HIGHER bound (must run before _parse_hindi_words)
    WMAP = {'ek':'1','do':'2','teen':'3','char':'4','paanch':'5','chhe':'6',
            'saat':'7','aath':'8','nau':'9','das':'10','dedh':'1.5','dhai':'2.5',
            'एक':'1','दो':'2','तीन':'3','चार':'4','पाँच':'5','पांच':'5',
            'छह':'6','सात':'7','आठ':'8','नौ':'9','दस':'10','डेढ':'1.5','ढाई':'2.5'}
    import re as _r
    norm2 = normalized
    for w, d in WMAP.items():
        norm2 = norm2.replace(w, d)
    range_m = _r.search(
        r'(\d+(?:\.\d+)?)\s*(?:se|to|से|-)\s*(\d+(?:\.\d+)?)\s*(lakh|lac|लाख|hazaar|hazar|हज़ार|हजार|k|thousand)?',
        norm2, _r.IGNORECASE)
    if range_m:
        higher = float(range_m.group(2))
        u = (range_m.group(3) or '').lower().strip()
        if u in ('lakh','lac','लाख'):     return _format_inr(int(higher * 100000))
        if u in ('hazaar','hazar','हज़ार','हजार','k','thousand'): return _format_inr(int(higher * 1000))
        if higher >= 1000: return _format_inr(int(higher))

    amount = _parse_hindi_words(normalized)
    if amount:
        return _format_inr(amount)
    # old range block below — skip "1 se 2 lakh", "ek se do lakh" — take higher bound
    import re as _re2
    WMAP = {
        'ek':'1','do':'2','teen':'3','char':'4','paanch':'5','chhe':'6',
        'saat':'7','aath':'8','nau':'9','das':'10','dedh':'1.5','dhai':'2.5',
        'एक':'1','दो':'2','तीन':'3','चार':'4','पाँच':'5','पांच':'5',
        'छह':'6','सात':'7','आठ':'8','नौ':'9','दस':'10','डेढ':'1.5','ढाई':'2.5',
    }
    norm2 = normalized
    for w, d in WMAP.items():
        norm2 = _re2.sub(r'(?<![\w])' + _re2.escape(w) + r'(?![\w])', d, norm2)
    range_m = _re2.search(
        r'(\d+(?:\.\d+)?)\s*(?:se|to|से|-)\s*(\d+(?:\.\d+)?)\s*'
        r'(lakh|lac|लाख|hazaar|hazar|हज़ार|हजार|k|thousand)?',
        norm2, _re2.IGNORECASE
    )
    if range_m:
        higher = float(range_m.group(2))
        u = (range_m.group(3) or '').lower().strip()
        if u in ('lakh','lac','लाख'):     return _format_inr(int(higher * 100000))
        if u in ('hazaar','hazar','हज़ार','हजार','k','thousand'): return _format_inr(int(higher * 1000))
        if higher >= 1000:                return _format_inr(int(higher))

    m = re.search(
        r'[₹]?\s*(\d+(?:\.\d+)?)\s*'
        r'(hazaar|hazar|हज़ार|हजार|lakh|lac|लाख|k\b|thousand|cr|crore)?',
        normalized
    )
    if m:
        num = float(m.group(1))
        unit = (m.group(2) or '').strip()
        if unit in ('hazaar', 'hazar', 'हज़ार', 'हजार', 'k', 'thousand'):
            amount = int(num * 1000)
        elif unit in ('lakh', 'lac', 'लाख'):
            amount = num * 100000
        elif unit in ('cr', 'crore'):
            amount = int(num * 10000000)
        elif num >= 1000:
            amount = int(num)
        else:
            return f"~₹{int(num):,} (approx)"
        return _format_inr(amount)

    return normalized


URGENCY_MAP = [
    (['कल', 'kal', 'tomorrow'], 'Tomorrow'),
    (['आज', 'aaj', 'today'], 'Today'),
    (['जल्दी', 'jaldi', 'urgent', 'urge'], 'ASAP'),
    (['इसी हफ्ते', 'is hfte', 'this week', 'hafte'], 'This Week'),
    (['अगले हफ्ते', 'agle hafte', 'next week'], 'Next Week'),
    (['महीने', 'mahine', 'month', 'months'], 'Within Month'),
]


def normalize_urgency(raw: str) -> str:
    if not raw:
        return raw

    import re

    if re.match(r'^[A-Za-z\s/₹\d]+$', raw.strip()):
        return raw.strip()

    text = raw.lower().strip('.,!? ।')

    for keywords, label in URGENCY_MAP:
        if any(k.lower() in text for k in keywords):
            return label

    return text.strip()


def _score_budget(budget_raw: str, intents_fired: set) -> int:
    if budget_raw:
        normalized = normalize_budget(budget_raw)
        nl = normalized.lower()

        import re
        lakh_m = re.search(r'(\d+(?:\.\d+)?)\s*l\b', nl)
        thou_m = re.search(r'₹[\d,]+', nl)

        if lakh_m:
            lakhs = float(lakh_m.group(1))
            if lakhs >= 2:    return 30
            if lakhs >= 1:    return 25
            return 18

        if thou_m:
            num = int(thou_m.group(0).replace('₹','').replace(',',''))
            if num >= 100000: return 30
            if num >= 50000:  return 22
            if num >= 20000:  return 14
            return 8

        return 10

    if 'faq:emi' in intents_fired:             return 20
    if 'faq:offer' in intents_fired:           return 12
    if 'faq:exchange' in intents_fired:        return 12
    if 'objection:expensive' in intents_fired: return 6
    return 0


def _headers() -> dict:
    return {
        "apikey":        SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }


def _clean_phone(phone: str) -> str:
    """Keep + prefix, strip spaces and dashes only"""
    p = phone.replace(" ", "").replace("-", "").strip()
    return p if p.startswith("+") else f"+{p}"


async def mark_dnc_immediate(phone: str, call_uuid: str = "") -> None:
    """
    Marks outbound_leads.dnc=true for this phone the moment an explicit
    opt-out is detected mid-call, rather than waiting for finalize_call() at
    /hangup. finalize_call() already re-derives and writes the same dnc=true
    from session.dnc at hangup, so this is a redundant safety write, not a
    replacement — it just closes the window where a dropped connection or a
    crash between the opt-out turn and the hangup webhook would otherwise
    leave the lead's row unmarked and eligible for the next dispatch tick.
    outbound_leads.phone is stored inconsistently across write paths (some
    rows with '+91', some bare) — match all variants, same pattern used
    elsewhere in this codebase (finalize_call, _mark_wa_sent).
    """
    if not phone or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    bare = phone.lstrip("+")
    phone_or = ",".join(f"phone.eq.{v}" for v in {phone, bare, f"+{bare}"})
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.patch(
                f"{SUPABASE_URL}/rest/v1/outbound_leads",
                headers=_headers(),
                params={"or": f"({phone_or})", "tenant_id": f"eq.{TENANT_ID}"},
                json={"status": "dnc", "dnc": True, "cooldown_until": None},
            )
        if r.status_code not in (200, 204):
            logger.error(f"[{call_uuid}] mark_dnc_immediate failed {r.status_code}: {r.text[:200]}")
        else:
            logger.info(f"[{call_uuid}] outbound_lead → dnc (immediate, explicit opt-out) phone={phone}")
    except Exception as e:
        logger.error(f"[{call_uuid}] mark_dnc_immediate error: {e}")


def normalize_phone(raw: str | None) -> str:
    """
    Canonical bare-digits form for phone matching — last 10 digits, no '+',
    no country-code duplication. outbound_leads.phone (and several other
    tables) store the same number inconsistently across write paths — some
    rows with '+91', some with a bare '91', some with neither — and existing
    code works around this per-call-site with ad-hoc OR-filters (finalize_call,
    sync_whatsapp_visit_dates, webhook.py's inbound lookup). This sidesteps
    that by always comparing the same last-10-digit suffix regardless of
    storage format. Scoped to the get_followup_status() reporting feature
    below — existing phone-matching call sites are unchanged, not refactored
    onto this.
    """
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


async def get_followup_status(phones: list[str]) -> list[dict]:
    """
    Read-only CRM-facing lookup — no writes, no effect on dispatch/
    eligibility. For each phone (matched via normalize_phone()'s last-10-
    digit suffix, one OR'd query for the whole batch rather than a round
    trip per number), returns:
      - call_cycle: 1/2/3 — the SAME derivation fire_call() uses
        (outbound_orchestrator.py: min(answered_no_date_count + 1, 3)) —
        this is "what cycle the next call would be", not the cycle of the
        last completed call.
      - campaign_type, last call outcome (outbound_leads.status),
        next_retry_at (cooldown_until), visit_date, visit_date_status.
    Leads with no matching outbound_leads row are simply absent from the
    result list — not an error.
    """
    normalized = [normalize_phone(p) for p in phones]
    normalized = [n for n in normalized if n]
    if not normalized:
        return []

    or_filter = ",".join(f"phone.like.*{n}" for n in normalized)
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/outbound_leads",
                headers=_headers(),
                params={
                    "or":     f"({or_filter})",
                    "select": "phone,campaign_type,status,answered_no_date_count,"
                              "cooldown_until,visit_date,visit_date_status",
                },
            )
    except Exception as e:
        logger.error(f"get_followup_status error: {e}")
        return []

    if r.status_code != 200:
        logger.error(f"get_followup_status failed: {r.status_code} {r.text[:200]}")
        return []

    results = []
    for row in r.json():
        no_date_count = row.get("answered_no_date_count") or 0
        results.append({
            "phone":             normalize_phone(row.get("phone")),
            "call_cycle":        min(no_date_count + 1, 3),
            "campaign_type":     row.get("campaign_type"),
            "last_call_outcome": row.get("status"),
            "next_retry_at":     row.get("cooldown_until"),
            "visit_date":        row.get("visit_date"),
            "visit_date_status": row.get("visit_date_status"),
        })
    return results


async def get_call_history(phones: list[str]) -> list[dict]:
    """
    Read-only CRM-facing lookup — outbound call-attempt history per phone:
    called_count (total call_logs rows), answered_count (status=='answered',
    the SAME turn_count>=1-based 3-way definition finalize_call() writes to
    call_logs.status — NOT call_stats_daily, which deliberately still uses a
    simpler duration-only 2-way rule, unchanged), and pickup_rate
    (answered/called, None if called==0 rather than 0.0, so the CRM can tell
    "never called" apart from "called but 0% picked up").

    Deliberately outbound-only: this measures the outbound calling effort's
    effectiveness (did WE reach THEM), not inbound volume (customer calling
    in is a different thing and would muddy pickup-rate as a metric).
    outbound_leads.pickup_attempt_count was checked as a candidate source
    and rejected -- confirmed live to undercount vs. actual call_logs rows
    (e.g. one real lead: pickup_attempt_count=1, actual call_logs rows=4).

    Phones matched via normalize_phone()'s last-10-digit suffix, same as
    get_followup_status(). Phones whose leads row is dnc=true are excluded
    entirely (not returned) -- same "absent = no data" convention
    get_followup_status() uses for no-outbound_leads-row phones, and covers
    the known synthetic QA test leads (+919999900003/04) the same way it
    would cover any future dnc'd number, rather than a special-cased filter.
    """
    normalized = [normalize_phone(p) for p in phones]
    normalized = list({n for n in normalized if n})
    if not normalized:
        return []

    # leads.phone vs call_logs.to_number -- different column names, so this
    # needs two separate OR filters, not one shared string.
    leads_or_filter = ",".join(f"phone.like.*{n}" for n in normalized)
    calls_or_filter = ",".join(f"to_number.like.*{n}" for n in normalized)

    try:
        async with httpx.AsyncClient(timeout=8) as c:
            dnc_r, calls_r = await asyncio.gather(
                c.get(
                    f"{SUPABASE_URL}/rest/v1/leads",
                    headers=_headers(),
                    params={"or": f"({leads_or_filter})", "select": "phone,dnc"},
                ),
                c.get(
                    f"{SUPABASE_URL}/rest/v1/call_logs",
                    headers=_headers(),
                    params={
                        "or":        f"({calls_or_filter})",
                        "direction": "eq.outbound",
                        "select":    "to_number,status",
                    },
                ),
            )
    except Exception as e:
        logger.error(f"get_call_history error: {e}")
        return []

    if dnc_r.status_code != 200 or calls_r.status_code != 200:
        logger.error(f"get_call_history failed: leads={dnc_r.status_code} call_logs={calls_r.status_code}")
        return []

    dnc_phones = {normalize_phone(row.get("phone")) for row in dnc_r.json() if row.get("dnc")}

    statuses_by_phone: dict[str, list[str]] = {}
    for row in calls_r.json():
        n = normalize_phone(row.get("to_number"))
        if n:
            statuses_by_phone.setdefault(n, []).append(row.get("status"))

    results = []
    for n in normalized:
        if n in dnc_phones:
            continue
        statuses = statuses_by_phone.get(n, [])
        called   = len(statuses)
        answered = sum(1 for s in statuses if s == "answered")
        results.append({
            "phone":          n,
            "called_count":   called,
            "answered_count": answered,
            "pickup_rate":    round(answered / called, 3) if called else None,
        })
    return results


# ── Step 1: resolve or create lead by phone ───────────────────────
async def get_or_create_lead_id(phone: str, name: str = "") -> Optional[str]:
    if not phone or not SUPABASE_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/leads",
                headers=_headers(),
                params={"phone": f"eq.{phone}", "select": "id", "limit": "1"},
            )
            if r.status_code == 200 and r.json():
                lead_id = r.json()[0]["id"]
                logger.info(f"Lead found: {lead_id} for {phone}")
                return lead_id

            # Cross-funnel check — before creating a NEW leads row, check
            # whether this phone already has an outbound_leads row (the
            # separate campaign-calling pipeline's own table, keyed
            # independently of `leads`). A match here means this person is
            # already known to the outbound funnel and a brand-new,
            # disconnected leads row would fragment their identity across
            # the two systems. Diagnostic only — log a structured warning,
            # don't block or alter creation. Same phone-format OR-matching
            # every other outbound_leads lookup in this codebase uses,
            # since storage is inconsistent across write paths.
            bare = phone.lstrip("+")
            _phone_or = ",".join(f"phone.eq.{v}" for v in {phone, bare, f"+{bare}"})
            try:
                _ol_r = await client.get(
                    f"{SUPABASE_URL}/rest/v1/outbound_leads",
                    headers=_headers(),
                    params={"or": f"({_phone_or})", "select": "id,campaign_type,funnel_type,status", "limit": "1"},
                )
                if _ol_r.status_code == 200 and _ol_r.json():
                    _match = _ol_r.json()[0]
                    logger.warning(
                        f"CROSS_FUNNEL_MATCH phone={phone} outbound_leads_id={_match.get('id')} "
                        f"campaign_type={_match.get('campaign_type')} funnel_type={_match.get('funnel_type')} "
                        f"status={_match.get('status')} — about to create a new leads row for a phone "
                        f"already tracked in outbound_leads, identity may fragment across the two tables"
                    )
            except Exception as _e:
                logger.error(f"cross-funnel outbound_leads check error for {phone}: {_e}")

            payload = {
                "phone":       phone,
                "source":      "ai_call",
                "status":      "new",
                "lead_status": "cold",
            }
            if name:
                payload["name"] = name

            r2 = await client.post(
                f"{SUPABASE_URL}/rest/v1/leads",
                headers={**_headers(), "Prefer": "return=representation"},
                json=payload,
            )
            if r2.status_code in (200, 201):
                lead_id = r2.json()[0]["id"]
                logger.info(f"Lead created: {lead_id} for {phone}")
                return lead_id

            logger.error(f"Lead create failed {r2.status_code}: {r2.text[:200]}")
    except Exception as e:
        logger.error(f"get_or_create_lead_id error: {e}")
    return None


# ── Step 2: INSERT call_log on call start ─────────────────────────
def _resolve_call_number(call_cycle) -> int:
    """
    session.call_cycle / the /answer-outbound query param is a string ("",
    "1", "2", "3") — never persisted anywhere before this. Defaults to 1 for
    Call 1, inbound calls, and any funnel that doesn't use the call-cycle
    system at all (call_cycle absent/blank).
    """
    if call_cycle in ("2", "3"):
        return int(call_cycle)
    return 1


async def insert_call_log(
    call_uuid:   str,
    from_number: str,
    to_number:   str,
    direction:   str,
    caller_name: str = "",
    lead_id:     Optional[str] = None,
    call_cycle:  str = "",
):
    if not SUPABASE_URL:
        return
    payload = {
        "call_uuid":   call_uuid,
        "from_number": from_number,
        "to_number":   to_number,
        "direction":   direction,
        "status":      "answered",
        "tenant_id":   TENANT_ID,
        "started_at":  datetime.now(timezone.utc).isoformat(),
        "call_number": _resolve_call_number(call_cycle),
    }
    if caller_name:
        payload["caller_name"] = caller_name
    if lead_id:
        payload["lead_id"] = lead_id

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(
                f"{SUPABASE_URL}/rest/v1/call_logs",
                headers=_headers(),
                json=payload,
            )
        if r.status_code not in (200, 201):
            logger.error(f"insert_call_log failed {r.status_code}: {r.text[:200]}")
        else:
            logger.info(f"[{call_uuid}] call_log inserted")
    except Exception as e:
        logger.error(f"insert_call_log error: {e}")


# ── Step 3: UPDATE call_log + INSERT summary + upsert stats ───────
def _compute_reactivation_score(session) -> tuple[int, str]:
    """Score a reactivation call based on engagement signals."""
    intents = getattr(session, "react_intents_seen", set())
    turns   = getattr(session, "turn_count", 0)
    wa_sent = getattr(session, "wa_sent", False)
    state   = getattr(session, "react_state", "GREETING")

    score = 0

    # WA accepted — strongest signal
    if "wa_ok" in intents or "wa_prefers" in intents:
        score += 40
    elif wa_sent:
        score += 20  # WA sent even without explicit yes

    # Buying intent
    if "buying_signal" in intents:
        score += 30

    # Asked about exchange — genuinely curious
    if "offer_clarify" in intents or "offer_maths_challenge" in intents:
        score += 20

    # Product specific interest
    if any(i in intents for i in ["product_sofa","product_bed","product_wardrobe","product_dining"]):
        score += 15

    # Positive engagement
    if "positive" in intents and turns >= 2:
        score += 10

    # Trust issue but stayed on call
    if "trust_issue" in intents and turns >= 3:
        score += 10

    # Soft objections — still a warm lead
    if "sochna_hai" in intents:
        score += 8
    if "busy" in intents:
        score += 5

    # Hard rejections — zero out
    if "dnc" in intents or "not_interested" in intents:
        score = 0

    # IVR-fragment caution: a carrier/voicemail fragment matched somewhere in
    # this call (webhook_reactivation._is_ivr_fragment) but didn't clear the
    # turn_count<=1 / >=3 bar that flags the whole call ivr_flag=True (a real
    # human can legitimately keep talking after a hold/transfer message, so
    # that flag stays conservative on purpose). The gap this leaves: a single
    # bare filler turn ("haan"/"ji") right after the fragment gets read as
    # genuine wa_ok/positive engagement with nothing to weigh it against.
    # Confirmed live 2026-08-11 (hot_warm_leads_conversations.docx audit):
    # "स्टे ऑन द लाइन" (IVR hold message) followed by only "हां" scored
    # warm=30 off that one token. Don't let a fragment-adjacent call reach
    # warm+ unless it earned score from something beyond bare wa_ok/positive.
    ivr_fragment_count = getattr(session, "ivr_fragment_count", 0)
    if ivr_fragment_count >= 1 and not (intents - {"wa_ok", "positive"}):
        score = min(score, 20)

    score = min(score, 100)
    tier  = "hot" if score >= 60 else "warm" if score >= 25 else "cold"
    return score, tier


def _resolve_call_state(session, default: str) -> str:
    """
    Progress for a react_a/b/c/reactivation call is tracked in different
    session attributes depending on which call-cycle handler ran it:
    session.react_state for Call 1 (webhook_reactivation.handle_reactivation_turn,
    and fresh_cta, which sets react_state itself), but session.c2_state /
    session.c3_state for Call 2 / Call 3 (handle_call2_turn / handle_call3_turn
    never touch react_state at all). Reading only react_state — as this used
    to — silently fell back to the unrelated main-funnel session.state default
    for every single call2/3 conversation, mislabeling final_state/deepest_state
    as "QUALIFY_PRODUCT" in call_summaries regardless of how far the call
    actually progressed (confirmed live: calls that reached DATE_ASK/
    DECISION_DATE and booked a hot appointment were recorded as still sitting
    at QUALIFY_PRODUCT).
    """
    call_cycle = getattr(session, "call_cycle", None)
    if call_cycle == "2":
        return getattr(session, "c2_state", None) or default
    if call_cycle == "3":
        return getattr(session, "c3_state", None) or default
    return getattr(session, "react_state", None) or getattr(session, "state", default)


async def finalize_call(
    call_uuid:    str,
    session,
    from_number:  str,
    duration_str: str,
    hangup_cause: str = "",
):
    if not SUPABASE_URL:
        return

    # Wait for insert_call_log background task to complete before writing call_summaries
    await asyncio.sleep(1.5)

    try:
        duration = int(duration_str)
    except (ValueError, TypeError):
        duration = 0

    # call_stats_daily-facing status (upsert_call_stat RPC below) — kept on
    # the ORIGINAL 2-way duration-only logic deliberately. call_stats_daily
    # has no mid_answered_calls column (confirmed live 2026-07-15: total_calls
    # == answered_calls + no_answer_calls + failed_calls on every sampled
    # row, so the RPC's branching is exhaustive on today's 2 known values) —
    # passing a 3rd status through would either silently drop these calls
    # from every bucket or hit an unhandled case in the RPC. Do not change
    # this without confirming the RPC's own handling first.
    rpc_status = "answered" if duration > 0 else "no_answer"

    # call_logs-facing status — 3-way. 'answered' now requires a real
    # conversational turn, not just a connected duration. Confirmed live
    # 2026-07-15: 253+ outbound calls connected (Vobiz NORMAL_CLEARING,
    # duration up to 125s) with zero turns — greeting played into dead air/
    # a ghost pickup, never a real exchange — and were being counted as
    # 'answered' on duration alone.
    turn_count = getattr(session, "turn_count", 0)
    # Shared with the answered_no_date_count/pickup_attempt_count split
    # below and the call_summaries payload further down — computed once
    # here so both sites use the identical threshold, not two copies of it.
    #
    # >=3 alone only catches a repeating hold-loop (the machine's message
    # replays, so _is_ivr_fragment matches multiple separate turns). A
    # one-shot voicemail/answering-machine greeting plays exactly once, then
    # goes to a silent recording tone until natural hangup -- ivr_fragment_count
    # can structurally never exceed 1 for that shape, so >=3 could never fire
    # regardless of how long the call sat open. Confirmed live 2026-07-28:
    # 23/23 historical turn_count<=1 calls with a fragment match (all 100-166s,
    # single voicemail-prompt-shaped turn) were sitting at ivr_flag=False
    # forever under the old threshold; 0 false positives against the full
    # turn_count<=1 sample when adding this second, narrower OR-condition.
    _ivr_flag = getattr(session, "ivr_fragment_count", 0) >= 3 or (
        getattr(session, "ivr_fragment_count", 0) >= 1 and getattr(session, "turn_count", 0) <= 1
    )
    if duration <= 0:
        status = "no_answer"
    elif turn_count >= 1:
        status = "answered"
    else:
        status = "mid_answered"

    lead  = getattr(session, "lead", {})
    slots = getattr(session, "slots", {})

    product_interest = lead.get("product") or slots.get("product")
    budget_raw  = lead.get("budget") or slots.get("budget")
    urgency_raw = lead.get("urgency") or slots.get("urgency")

    # Only call Groq if we actually have data to normalize
    if budget_raw or urgency_raw:
        normalized = await ai_normalize_lead_fields(
            product     = product_interest,
            budget_raw  = budget_raw,
            urgency_raw = urgency_raw,
        )
        product_interest  = normalized.get("product") or product_interest
        budget_mentioned  = normalized.get("budget")
        urgency_mentioned = normalized.get("urgency")
        budget_numeric    = normalized.get("budget_numeric")
    else:
        # No lead data collected — skip Groq entirely
        budget_mentioned  = None
        urgency_mentioned = None
        budget_numeric    = None

    intents_fired = set(getattr(session, "intents_fired", []))
    # Use reactivation scoring for reactivation campaign (incl. A/B/C test plans)
    if getattr(session, "campaign", "") in ("reactivation", "react_a", "react_b", "react_c"):
        # react_a/b/c (and call2/call3, which share the same campaign value
        # across their whole call_cycle) track detected intents in
        # session.react_intents_seen, not session.intents_fired — the latter
        # is the fresh-lead funnel's own attribute and is essentially always
        # empty here. Folded in so call_summaries.intents_fired reflects what
        # actually happened on these calls instead of reading as [] always.
        intents_fired = intents_fired | getattr(session, "react_intents_seen", set())
        score, tier = _compute_reactivation_score(session)
        # Appointment confirmed → hard override to HOT regardless of computed score
        if getattr(session, "lead_score_override", None) is not None:
            score = session.lead_score_override
            tier  = getattr(session, "lead_tier_override", tier)
        score_breakdown = {}
    else:
        score, score_breakdown = _compute_score_from_normalized(
            product        = product_interest,
            budget         = budget_mentioned,
            urgency        = urgency_mentioned,
            budget_numeric = budget_numeric or 0,
            final_state    = getattr(session, "react_state", None) or getattr(session, "state", "QUALIFY_PRODUCT"),
            turn_count     = getattr(session, "turn_count", 0),
            intents_fired  = intents_fired,
            slots          = slots,
        )
        tier = "hot" if score >= 65 else "warm" if score >= 35 else "cold"
    transcript = getattr(session, "conversation", [])

    # Detect mid_answered: picked up but did not complete conversation
    call_was_answered = duration > 5
    if getattr(session, "campaign", "") in ("reactivation", "react_a", "react_b", "react_c"):
        # For reactivation (incl. A/B/C): answered = WA sent OR buying signal OR score >= 25
        react_intents = getattr(session, "react_intents_seen", set())
        all_slots_filled = (
            getattr(session, "wa_sent", False) or
            "buying_signal" in react_intents or
            "wa_ok" in react_intents or
            score >= 25
        )
    else:
        has_product      = bool(product_interest)
        has_budget       = bool(budget_mentioned)
        has_urgency      = bool(urgency_mentioned)
        all_slots_filled = has_product and has_budget and has_urgency

    # Clean phone for n8n — strip + and spaces
    phone_clean = _clean_phone(from_number)

    async with httpx.AsyncClient(timeout=8) as client:

        # 1. UPDATE call_logs
        try:
            r = await client.patch(
                f"{SUPABASE_URL}/rest/v1/call_logs",
                headers=_headers(),
                params={"call_uuid": f"eq.{call_uuid}"},
                json={
                    "status":           status,
                    "duration_seconds": duration,
                    "ended_at":         "now()",
                    "hangup_cause":     hangup_cause,
                },
            )
            if r.status_code not in (200, 201, 204):
                logger.error(f"update call_log failed {r.status_code}: {r.text[:200]}")
            else:
                logger.info(f"[{call_uuid}] call_log updated")
        except Exception as e:
            logger.error(f"update call_log error: {e}")

        # 2. Ensure call_logs row exists (unanswered calls never hit /answer-outbound)
        try:
            r_check = await client.get(
                f"{SUPABASE_URL}/rest/v1/call_logs?call_uuid=eq.{call_uuid}&select=call_uuid",
                headers=_headers(),
            )
            if r_check.status_code == 200 and r_check.json() == []:
                # No call_logs row — insert minimal one so FK constraint passes
                r_ins = await client.post(
                    f"{SUPABASE_URL}/rest/v1/call_logs",
                    headers=_headers(),
                    json={
                        "call_uuid":        call_uuid,
                        "tenant_id":        TENANT_ID,
                        "to_number":        phone_clean.replace("+", ""),
                        "from_number":      "+919262102426",
                        "direction":        "outbound",
                        "caller_name":      getattr(session, "customer_name", None),
                        "status":           "no_answer",
                        "duration_seconds": 0,
                        "hangup_cause":     hangup_cause,
                        "call_number":      _resolve_call_number(getattr(session, "call_cycle", "")),
                    },
                )
                if r_ins.status_code not in (200, 201):
                    logger.error(f"[{call_uuid}] minimal call_log insert failed {r_ins.status_code}: {r_ins.text[:200]}")
                logger.info(f"[{call_uuid}] minimal call_log inserted for unanswered call")
        except Exception as e:
            logger.error(f"call_log pre-check error: {e}")

        # 3. INSERT call_summaries  ← phone column added here
        try:
            summary_payload = {
                "call_uuid":         call_uuid,
                "lead_id":           getattr(session, "lead_id", None),
                "phone":             phone_clean.replace("+", ""),          # ← customer phone without + prefix
                "call_number":       _resolve_call_number(getattr(session, "call_cycle", "")),
                "product_interest":  product_interest,
                "budget_mentioned":  budget_mentioned,
                "urgency_mentioned": urgency_mentioned,
                "final_state":       _resolve_call_state(session, ""),
                "turn_count":             getattr(session, "turn_count", 0),
                # turn_count_substantive is tracked on the session (webhook.py /
                # webhook_reactivation.py) but deliberately NOT written here yet —
                # call_summaries.turn_count_substantive doesn't exist in the DB
                # and no schema migration has been approved. Re-add this line
                # (see supabase_migration_call_summaries_turn_count_substantive.sql)
                # once that column exists — writing it now would 400 every insert.
                "intents_fired":     list(intents_fired),
                "ivr_flag":          _ivr_flag,
                "slots":             slots,
                "full_transcript":   transcript,
                "duration_seconds":  duration,
                "caller_name":       getattr(session, "customer_name", None) or None,
                "started_at":        getattr(session, "started_at", None),
                "lead_score":        score,
                "lead_tier":         tier,
                "tenant_id":         TENANT_ID,
                "budget_numeric":    budget_numeric,
                "campaign_type":     getattr(session, "campaign", "fresh_lead") or "fresh_lead",
                "first_response_latency": getattr(session, "first_reply_ts", None),
                "avg_response_latency":   round(sum(getattr(session, "turn_latencies", [0])) / max(len(getattr(session, "turn_latencies", [1])), 1), 3),
                "interest_signals":       len([i for i in getattr(session, "react_intents_seen", set())
                                          if i in ("positive","buying_signal","wa_ok","offer_clarify","product_sofa","product_bed","product_wardrobe","product_dining","wa_prefers")])
                                          if getattr(session, "campaign", "") in ("reactivation", "react_a", "react_b", "react_c")
                                          else getattr(session, "interest_signals", 0),
                "rejection_signals":      len([i for i in getattr(session, "react_intents_seen", set())
                                          if i in ("not_interested","dnc","busy","sochna_hai","expensive","online_cheaper")])
                                          if getattr(session, "campaign", "") in ("reactivation", "react_a", "react_b", "react_c")
                                          else getattr(session, "rejection_signals", 0),
                "deepest_state":          _resolve_call_state(session, "GREETING"),
                # session.wa_accepted is never set anywhere in the codebase —
                # cta_accepted always read False for every campaign. For the
                # react family, "wa_ok"/"wa_prefers" in react_intents_seen is
                # the same explicit-acceptance signal _compute_reactivation_score()
                # already uses (see its "WA accepted" branch above) — reused
                # here rather than inventing a second signal. Non-react
                # campaigns keep the prior (dead) fallback unchanged; fixing
                # CTA tracking for the fresh-lead funnel is out of scope here.
                "cta_accepted":           (
                                          any(i in getattr(session, "react_intents_seen", set()) for i in ("wa_ok", "wa_prefers"))
                                          if getattr(session, "campaign", "") in ("reactivation", "react_a", "react_b", "react_c")
                                          else getattr(session, "wa_accepted", False)
                                          ),
                "wa_triggered":           getattr(session, "wa_sent", False),
                # offer_explained previously only checked for the "offer_clarify"
                # intent (customer asking us to clarify) -- true whenever the
                # actual offer content (*_offer_main / *_offer_explain) was
                # played, which is when the offer was explained regardless of
                # whether the customer asked a follow-up question about it.
                "offer_explained":        getattr(session, "offer_explained", False)
                                          or "offer_clarify" in getattr(session, "react_intents_seen", set()),
                "customer_response":      "positive" if "wa_ok" in getattr(session, "react_intents_seen", set()) else "negative" if "not_interested" in getattr(session, "react_intents_seen", set()) else None,
            }
            r2 = await client.post(
                f"{SUPABASE_URL}/rest/v1/call_summaries",
                headers=_headers(),
                json=summary_payload,
            )
            if r2.status_code == 409 or "23503" in r2.text:
                # FK violation — call_logs row for this call_uuid isn't committed yet
                # (can happen on very short/unanswered calls). Retry once after a beat.
                logger.warning(f"[{call_uuid}] call_summary insert hit FK violation — retrying in 1s")
                await asyncio.sleep(1)
                r2 = await client.post(
                    f"{SUPABASE_URL}/rest/v1/call_summaries",
                    headers=_headers(),
                    json=summary_payload,
                )
            if r2.status_code not in (200, 201):
                logger.error(f"insert call_summary failed {r2.status_code}: {r2.text[:200]}")
            else:
                logger.info(f"[{call_uuid}] call_summary inserted | score={score} tier={tier}")
        except Exception as e:
            logger.error(f"insert call_summary error: {e}")

        # 3. Upsert daily stats
        try:
            r3 = await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/upsert_call_stat",
                headers=_headers(),
                json={
                    "p_date":        str(date.today()),
                    "p_from_number": from_number,
                    "p_status":      rpc_status,
                    "p_duration":    duration if rpc_status == "answered" else None,
                    "p_tenant_id":   TENANT_ID,
                },
            )
            if r3.status_code not in (200, 201, 204):
                logger.error(f"upsert_call_stat failed {r3.status_code}: {r3.text[:200]}")
            else:
                logger.info(f"[{call_uuid}] call_stat upserted for {from_number}")
        except Exception as e:
            logger.error(f"upsert_call_stat error: {e}")

    # Update lead score on shared leads table
    lead_id = getattr(session, "lead_id", None)
    if lead_id:
        await _update_lead_score(lead_id, score, tier)

    # ── Update outbound_leads with correct final status ─────────
    # This runs AFTER finalize_call so we have all slot data
    if phone_clean:
        from datetime import timedelta

        _campaign              = getattr(session, "campaign", "")
        # Checks not_interested OR dnc intent OR the session.dnc flag itself —
        # previously only checked not_interested, so a call where ONLY the
        # separate "dnc" intent fired (e.g. an explicit "don't call again")
        # correctly ended the call live but was never marked dnc in
        # outbound_leads afterward, leaving the lead eligible to be called
        # again despite the explicit opt-out. Confirmed live on calls that
        # hit the top-priority dnc branch in handle_reactivation_turn /
        # handle_call2_turn / handle_call3_turn without also tripping
        # not_interested.
        _react_intents_seen    = getattr(session, "react_intents_seen", set())
        _not_interested        = (
            "not_interested" in _react_intents_seen
            or "dnc" in _react_intents_seen
            or getattr(session, "dnc", False)
        )
        _machine_detected      = getattr(session, "machine_detected", False)
        _appointment_confirmed = getattr(session, "appointment_confirmed", False)
        _wa_decline_confirm    = getattr(session, "wa_decline_confirm", False)

        _ol_payload = None  # None = leave outbound_leads untouched this call

        if _not_interested:
            # A "no" is always final — hard DNC regardless of any other signal.
            _ol_payload = {"status": "dnc", "dnc": True, "cooldown_until": None}
            logger.info(f"[{call_uuid}] outbound_lead → dnc (not_interested)")

        elif _machine_detected:
            # IVR/voicemail pickup — not a rejection, not a real conversation.
            # Excluded from future selection but NOT marked dnc.
            _ol_payload = {"status": "ivr_detected"}
            logger.info(f"[{call_uuid}] outbound_lead → ivr_detected")

        elif _campaign == "followup_wa":
            # One-shot static-audio nudge call — no conversation, no appointment
            # logic, no slot data collected. Deliberately NOT routed through
            # visit_date_status or answered_no_date_count; left untouched here.
            pass

        elif _appointment_confirmed:
            # Visit date confirmed during the call — authoritative for
            # react_a/b/c/reactivation, independent of the wa_sent-based
            # all_slots_filled heuristic below.
            _ol_payload = {"status": "answered", "visit_date_status": "confirmed"}

            _raw_date_text = getattr(session, "visit_date_raw_text", None)
            if _raw_date_text:
                _reference_dt = getattr(session, "started_at", None) or datetime.now(timezone.utc).isoformat()
                try:
                    _parsed_date = await ai_normalize_visit_date(_raw_date_text, _reference_dt)
                except Exception as e:
                    logger.error(f"[{call_uuid}] visit_date parse error: {e} | raw='{_raw_date_text}'")
                    _parsed_date = None

                if _parsed_date:
                    _ol_payload["visit_date"] = _parsed_date
                else:
                    logger.warning(
                        f"[{call_uuid}] visit_date_raw_text='{_raw_date_text}' could not be "
                        f"resolved confidently — visit_date left null, visit_date_status still 'confirmed'"
                    )
            else:
                logger.warning(f"[{call_uuid}] appointment_confirmed but no visit_date_raw_text on session")

            logger.info(
                f"[{call_uuid}] outbound_lead → answered (appointment_confirmed, "
                f"visit_date={_ol_payload.get('visit_date', 'unresolved')})"
            )

        elif getattr(session, "call_cycle", None) == "3" and call_was_answered and _campaign != "fresh_cta":
            # Call 3 (handle_call3_turn) is the last scripted attempt in the
            # call2/3 cadence — every non-conversion ending (decline, price
            # objection, vague/"thinking", busy, hostile, or plain silence)
            # must permanently stop outbound calling to this number, not just
            # exit this campaign's own selection query. Before this branch
            # existed, a call3 that didn't hit the explicit "dnc" intent (or
            # not_interested via react_intents_seen, which handle_call3_turn
            # never populates — only handle_reactivation_turn does) fell
            # through to the generic call_was_answered/answered_no_date_count
            # logic below, which for non-fresh_cta campaigns only ever reached
            # 'answered' or 'no_date_stalled' — no dnc write, and (confirmed
            # live) 'no_date_stalled' isn't even a valid value for this
            # column (check constraint outbound_leads_status_check), so that
            # write was silently failing with a 400 on every occurrence,
            # leaving the row's prior status untouched. Audit: 15/15 leads at
            # call_number=3 had dnc still false. fresh_cta is excluded here
            # deliberately — session.call_cycle is set for every campaign
            # (not just call2/3), so without this guard a fresh_cta call3
            # would also hit this branch and skip its own already-correct,
            # independent answered_no_date_count>=3 → dnc handling below.
            _ol_payload = {"status": "dnc", "dnc": True, "cooldown_until": None}
            logger.info(f"[{call_uuid}] outbound_lead → dnc (call3 hard stop, non-conversion)")

        elif call_was_answered:
            # For react_a/b/c, 'answered' must ONLY come from the
            # appointment_confirmed branch above — wa_sent fires on nearly
            # every turn of these scripts, so the generic all_slots_filled
            # fallback would otherwise mark almost any answered call
            # 'answered' even with no date confirmed. Gate it out here so
            # these three fall through to the answered_no_date_count path
            # instead. Not applied to any other campaign (reactivation,
            # fresh_lead, etc. keep the original fallback behavior).
            if all_slots_filled and _campaign not in ("react_a", "react_b", "react_c"):
                _ol_payload = {"status": "answered"}
            elif turn_count > 0 and not _ivr_flag:
                # Answered, no visit date confirmed, AND a real conversation
                # actually happened — turn_count>0 rules out a 0-turn
                # mid_answered pickup, and _ivr_flag rules out a call that
                # only "conversed" with a carrier IVR/voicemail loop.
                # Track via answered_no_date_count, capped at 3. Requires a
                # read-then-write since PostgREST PATCH can't express
                # "column = column + 1" without an RPC.
                _current_count = 0
                try:
                    async with httpx.AsyncClient(timeout=5) as _c:
                        # outbound_leads.phone is stored inconsistently across write
                        # paths — some rows have '+', some don't (promote_due_scheduled_actions()
                        # never adds it; detect_and_schedule_fresh_leads() always does).
                        # Match both so this lookup doesn't silently miss rows lacking '+'.
                        _phone_or = ",".join(f"phone.eq.{v}" for v in {phone_clean, phone_clean.lstrip("+")})
                        _r = await _c.get(
                            f"{SUPABASE_URL}/rest/v1/outbound_leads",
                            headers=_headers(),
                            params={
                                "or":        f"({_phone_or})",
                                "tenant_id": f"eq.{TENANT_ID}",
                                "select":    "answered_no_date_count",
                                "limit":     "1",
                            },
                        )
                        if _r.status_code == 200 and _r.json():
                            _current_count = _r.json()[0].get("answered_no_date_count") or 0
                except Exception as e:
                    logger.error(f"[{call_uuid}] answered_no_date_count lookup error: {e}")

                _new_count = _current_count + 1
                if _new_count >= 3:
                    if _campaign == "fresh_cta":
                        # fresh_cta diverges intentionally from reactivation's
                        # softer terminal state — 3 answered-no-date calls on
                        # a fresh lead goes straight to dnc, not a WA-only lane.
                        _ol_payload = {
                            "status":                 "dnc",
                            "dnc":                    True,
                            "answered_no_date_count": _new_count,
                        }
                        logger.info(f"[{call_uuid}] outbound_lead → dnc (fresh_cta, {_new_count}/3 no-date)")
                    else:
                        # Stop scheduling calls — NOT a rejection, so dnc stays false.
                        # Still eligible for WhatsApp-only follow-up outside this pipeline.
                        # This write itself was never wrong — 'no_date_stalled' silently
                        # 400'd for months only because it was missing from
                        # outbound_leads_status_check, not because this value is
                        # incorrect. Fixed by supabase_migration_outbound_leads_status_values.sql
                        # (adds it to the constraint) — no code change needed here once
                        # that migration has been run.
                        _ol_payload = {
                            "status":                 "no_date_stalled",
                            "answered_no_date_count": _new_count,
                        }
                        logger.info(f"[{call_uuid}] outbound_lead → no_date_stalled ({_new_count}/3)")
                else:
                    # Business decision 2026-08-11: this gap was a flat 24h regardless
                    # of what the customer actually said on the call. Confirmed too
                    # tight via hot_warm_leads_conversations.docx audit — real
                    # customers who explicitly deferred (sochna_hai/busy) or even
                    # outright declined were redialed on the same generic 24h clock
                    # as a genuinely engaged lead; several ground-truth outcomes
                    # (blocked-number reports) trace back to this compression.
                    # Widened to a 2.5-day baseline, 3.5 days when the call carried
                    # a sochna_hai/busy deferral signal — real room to think before
                    # the next touch instead of one fixed clock for every outcome.
                    _soft_deferral = bool({"sochna_hai", "busy"} & intents_fired)
                    _gap_hours = 84 if _soft_deferral else 60
                    _ol_payload = {
                        "status":                 "mid_answered",
                        "answered_no_date_count": _new_count,
                        "cooldown_until":         (datetime.now(timezone.utc) + timedelta(hours=_gap_hours)).isoformat(),
                    }
                    logger.info(f"[{call_uuid}] outbound_lead → mid_answered ({_new_count}/3 no-date, gap={_gap_hours}h, soft_deferral={_soft_deferral})")
            else:
                # Picked up (duration>5) but turn_count==0 or IVR-tainted --
                # functionally "never reached a real human," same as a true
                # no_answer, so it's tracked via pickup_attempt_count instead
                # of answered_no_date_count rather than falling through
                # untracked by either counter. Without this, a lead whose
                # entire history is 0-turn/IVR-tainted "answered" calls would
                # never hit any cap and could be redialed indefinitely --
                # confirmed live pattern, not hypothetical: 3 of a 20-lead
                # fresh_cta audit sample (2026-07-27) were 100% 0-turn
                # "answered" calls with zero true no_answer calls among them.
                # Capped at 4, matching get_due_leads()/get_due_fresh_leads()'s
                # own pickup_attempt_count<4 selection backstop, and writes
                # the same max_retries_exhausted terminal status
                # schedule_retry_or_dnc() writes for a true no-answer lead
                # that hits the same threshold — same outcome, same
                # visibility, regardless of which path got it there.
                _current_pickup_count = 0
                try:
                    async with httpx.AsyncClient(timeout=5) as _c:
                        _phone_or = ",".join(f"phone.eq.{v}" for v in {phone_clean, phone_clean.lstrip("+")})
                        _r = await _c.get(
                            f"{SUPABASE_URL}/rest/v1/outbound_leads",
                            headers=_headers(),
                            params={
                                "or":        f"({_phone_or})",
                                "tenant_id": f"eq.{TENANT_ID}",
                                "select":    "pickup_attempt_count",
                                "limit":     "1",
                            },
                        )
                        if _r.status_code == 200 and _r.json():
                            _current_pickup_count = _r.json()[0].get("pickup_attempt_count") or 0
                except Exception as e:
                    logger.error(f"[{call_uuid}] pickup_attempt_count lookup error (0-turn/IVR answered call): {e}")

                # Business decision 2026-08-10: this path now shares the exact same
                # cadence math as schedule_retry_or_dnc() (outbound_orchestrator.py)
                # instead of the flat 24h stopgap patched in 2026-08-09 -- that stopgap
                # fixed the immediate-redial bug but didn't match the intended "4h,
                # max 2/day, then growing 1/2/3-day pair gaps" design. funnel_type
                # derived from campaign the same way DEFAULT_PICKUP_CADENCE's fallback
                # already implies: fresh_cta gets its own cadence entry, every react_a/
                # b/c campaign maps to "reactivation".
                _cadence_funnel = "fresh_cta" if _campaign == "fresh_cta" else "reactivation"
                _schedule = compute_retry_schedule(_current_pickup_count, funnel_type=_cadence_funnel)
                _new_pickup_count = _schedule["pickup_attempt_count"]
                if _schedule["max_attempts_hit"]:
                    _ol_payload = {
                        "status":                 "max_retries_exhausted",
                        "pickup_attempt_count": _new_pickup_count,
                    }
                    logger.info(f"[{call_uuid}] outbound_lead → max_retries_exhausted (0-turn/IVR answered, {_new_pickup_count})")
                else:
                    _ol_payload = {
                        "status":                 "mid_answered",
                        "pickup_attempt_count": _new_pickup_count,
                        "cooldown_until":         _schedule["cooldown_until"],
                    }
                    logger.info(f"[{call_uuid}] outbound_lead → mid_answered (0-turn/IVR answered, pickup_attempt_count={_new_pickup_count}, retry at {_schedule['cooldown_until']})")
        # If not answered and none of the above fired: leave outbound_leads untouched —
        # the true no-answer path is handled by outbound_orchestrator.py's
        # cleanup_stuck_leads() / schedule_retry_or_dnc(), same as before.

        if _wa_decline_confirm and call_was_answered and _ol_payload is not None:
            # The one confirmatory call has now genuinely happened (a real
            # conversation, not just a ring) — consume it regardless of
            # outcome. A repeated "not interested" already hit the dnc branch
            # above; anything else falls through to the normal
            # appointment_confirmed / answered_no_date_count handling above,
            # unchanged — this just also marks the confirm call as used.
            _ol_payload["confirm_call_attempted"] = True
            logger.info(f"[{call_uuid}] outbound_lead → confirm_call_attempted=True (wa_decline_confirm lane)")

        if _ol_payload is not None:
            try:
                async with httpx.AsyncClient(timeout=5) as _c:
                    # Compare-and-swap on status='in_progress': cleanup_stuck_leads()
                    # in outbound_orchestrator.py runs on its own poll loop and can
                    # decide this same call is "stuck" (and call schedule_retry_or_dnc,
                    # incrementing pickup_attempt_count) while this coroutine is still
                    # mid-flight — the sleep+sequential-awaits above easily take long
                    # enough to straddle that sweep's 5-minute staleness check. Scoping
                    # this PATCH to status=eq.in_progress makes the two writers mutually
                    # exclusive: Postgres serializes concurrent UPDATEs on the same row,
                    # so whichever write commits first flips status away from
                    # in_progress and the other's WHERE clause matches zero rows —
                    # never both a pickup_attempt_count AND answered_no_date_count bump
                    # for the same call outcome.
                    # Match phone with or without '+' — outbound_leads.phone is stored
                    # inconsistently across write paths (see the lookup above); without
                    # this, rows lacking '+' never match here at all and this PATCH
                    # silently no-ops on every call outcome for them (confirmed live:
                    # this was masking as false "race-guard" skips for 6/7 leads in one
                    # 30-minute window, all of which had no '+' on their stored phone).
                    # Built via params= (not spliced into the URL string) so httpx
                    # percent-encodes the '+' as %2B — a raw '+' left in a query
                    # string is parsed as a space by PostgREST, which silently
                    # zero-matched every row here (all stored phones have a '+').
                    _phone_or_patch = ",".join(f"phone.eq.{v}" for v in {phone_clean, phone_clean.lstrip("+")})
                    _guard_r = await _c.patch(
                        f"{SUPABASE_URL}/rest/v1/outbound_leads",
                        headers={**_headers(), "Prefer": "return=representation"},
                        params={
                            "or":        f"({_phone_or_patch})",
                            "tenant_id": f"eq.{TENANT_ID}",
                            "status":    "eq.in_progress",
                        },
                        json=_ol_payload,
                    )
                    if _guard_r.status_code == 200 and not _guard_r.json():
                        logger.warning(
                            f"[{call_uuid}] outbound_lead update skipped — no row matched "
                            f"phone={phone_clean} (or without '+') AND status='in_progress'. "
                            f"Either another writer (e.g. cleanup_stuck_leads) already "
                            f"claimed this call, or no matching outbound_leads row exists "
                            f"at all — NOT applying {_ol_payload}"
                        )
            except Exception as e:
                logger.error(f'outbound_lead status update error: {e}')

    # ── Fire n8n webhook → triggers WhatsApp follow-up ────────────
    # Only fire if call was actually answered (duration > 0)
    if duration > 0 and phone_clean and getattr(session, "campaign", "") != "reactivation":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r_n8n = await client.post(
                    N8N_WEBHOOK_URL,
                    json={"phone": phone_clean.replace("+", "")},
                )
            logger.info(
                f"[{call_uuid}] n8n webhook fired → {phone_clean} "
                f"| status={r_n8n.status_code}"
            )
        except Exception as e:
            logger.error(f"[{call_uuid}] n8n webhook failed (non-critical): {e}")
    else:
        logger.info(f"[{call_uuid}] n8n webhook skipped — call not answered (duration={duration}s)")


async def _update_lead_score(lead_id: str, score: int, tier: str):
    # Writes call_lead_score/call_lead_status/call_last_contact/
    # call_interaction_count — NOT lead_score/lead_status/last_contact/
    # interaction_count. `leads` is the shared CRM table the WhatsApp side
    # also owns (and get_or_create_lead_id() attaches to an existing row by
    # phone rather than creating a separate one), so writing the voice
    # pipeline's own activity data into those shared columns was bleeding
    # call-only score AND contact/interaction data onto leads with zero
    # WhatsApp activity (confirmed live 2026-07-12 on 919582622123 —
    # interaction_count=1, last_contact set, zero WhatsApp messages).
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            # Read-then-write for the increment — PostgREST PATCH can't
            # express "column = column + 1" directly (same pattern as
            # answered_no_date_count elsewhere in this file). The previous
            # version hardcoded interaction_count=1 on every call instead of
            # incrementing — flagged as a known bug, fixed here in the same
            # pass rather than carried over under the new column name.
            _current_count = 0
            try:
                _r = await c.get(
                    f"{SUPABASE_URL}/rest/v1/leads",
                    headers=_headers(),
                    params={"id": f"eq.{lead_id}", "select": "call_interaction_count", "limit": "1"},
                )
                if _r.status_code == 200 and _r.json():
                    _current_count = _r.json()[0].get("call_interaction_count") or 0
            except Exception as e:
                logger.error(f"_update_lead_score count lookup error: {e}")

            await c.patch(
                f"{SUPABASE_URL}/rest/v1/leads",
                headers=_headers(),
                params={"id": f"eq.{lead_id}"},
                json={
                    "call_lead_score":        str(score),
                    "call_lead_status":       tier,
                    "call_last_contact":      "now()",
                    "call_interaction_count": _current_count + 1,
                },
            )
    except Exception as e:
        logger.error(f"_update_lead_score error: {e}")



def _days_until_urgency(urgency_str: str) -> int | None:
    """Return approximate days until the urgency, based on today's date.
    Returns None if we can't determine it."""
    from datetime import date
    import re
    u = urgency_str.lower()
    today = date.today()
    weekday_today = today.weekday()  # Monday=0, Sunday=6

    day_map = {
        "monday":    0, "सोमवार": 0, "somvar":  0, "मंडे":   0,
        "tuesday":   1, "मंगलवार":1, "mangalvar":1,"ट्यूजडे":1,
        "wednesday": 2, "बुधवार": 2, "budhvar": 2, "वेडनसडे":2,
        "thursday":  3, "गुरुवार": 3, "guruvar": 3, "थर्सडे": 3,
        "friday":    4, "शुक्रवार":4, "shukravar":4,"फ्राइडे":4,
        "saturday":  5, "शनिवार": 5, "shanivar": 5,"सैटरडे": 5,
        "sunday":    6, "रविवार": 6, "ravivar":  6, "संडे":   6,
    }
    for name, target_wd in day_map.items():
        if name in u:
            days = (target_wd - weekday_today) % 7
            if days == 0:
                days = 7  # same day next week
            return days

    # Numeric day patterns
    m = re.search(r"in (\d+)[- ](\d+) days?", u)
    if m:
        return int(m.group(2))  # take higher bound
    m = re.search(r"in (\d+) days?", u)
    if m:
        return int(m.group(1))
    if "tomorrow" in u or "kal" in u:
        return 1
    if "today" in u or "aaj" in u:
        return 0
    if "this week" in u or "is hafte" in u or "इस हफ्ते" in u:
        return 5
    if "next week" in u or "agle hafte" in u or "अगले हफ्ते" in u:
        return 10
    if "this month" in u or "is mahine" in u:
        return 20
    if "next month" in u or "agle mahine" in u:
        return 40
    return None

def _compute_score_from_normalized(
    product:        str,
    budget:         str,
    urgency:        str,
    budget_numeric: int,
    final_state:    str,
    turn_count:     int,
    intents_fired:  set,
    slots:          dict,
) -> tuple[int, dict]:
    breakdown = {"product": 0, "budget": 0, "urgency": 0, "engagement": 0}

    size = slots.get("size")
    if product and product != "other":
        breakdown["product"] = 25 if size else 18
    elif _infer_product_from_intents(intents_fired):
        breakdown["product"] = 10

    if budget_numeric:
        if budget_numeric >= 200000:   breakdown["budget"] = 30
        elif budget_numeric >= 100000: breakdown["budget"] = 26
        elif budget_numeric >= 50000:  breakdown["budget"] = 22
        elif budget_numeric >= 20000:  breakdown["budget"] = 15
        else:                          breakdown["budget"] = 8
    elif budget and budget not in (None, "null"):
        breakdown["budget"] = 10
    elif intents_fired:
        if "faq:emi" in intents_fired:               breakdown["budget"] = 20
        elif "faq:offer" in intents_fired:           breakdown["budget"] = 12
        elif "objection:expensive" in intents_fired: breakdown["budget"] = 6

    if urgency and urgency != "Not specified":
        days = _days_until_urgency(urgency)
        if days is not None:
            if days <= 1:
                breakdown["urgency"] = 25
            elif days <= 4:
                breakdown["urgency"] = 22
            elif days <= 7:
                breakdown["urgency"] = 16
            elif days <= 30:
                breakdown["urgency"] = 10
            elif days <= 90:
                breakdown["urgency"] = 6
            else:
                breakdown["urgency"] = 4
        else:
            breakdown["urgency"] = 4
    elif "faq:visit" in intents_fired:
        breakdown["urgency"] = 18
        breakdown["urgency"] = 18

    state_pts = {
        "DONE": 20, "FAQ_MODE": 18, "WRAP_UP": 16,
        "QUALIFY_URGENCY": 12, "QUALIFY_BUDGET": 8, "QUALIFY_PRODUCT": 4,
    }.get(final_state, 2)
    breakdown["engagement"] = min(state_pts + min(turn_count, 5), 20)

    total = min(sum(breakdown.values()), 100)
    logger.info(
        f"Score → product={breakdown['product']} budget={breakdown['budget']} "
        f"urgency={breakdown['urgency']} engagement={breakdown['engagement']} "
        f"TOTAL={total}"
    )
    return total, breakdown


def _infer_product_from_intents(intents: set):
    mapping = {
        "faq:sofa_general":  "sofa",
        "faq:sofa_lshape":   "sofa",
        "faq:sofa_cum_bed":  "sofa",
        "faq:bed_general":   "bed",
        "faq:dining_general":"dining",
        "faq:wardrobe":      "wardrobe",
        "faq:office_general":"office",
        "faq:tv_unit":       "tv_unit",
    }
    for intent, product in mapping.items():
        if intent in intents:
            return product
    return None