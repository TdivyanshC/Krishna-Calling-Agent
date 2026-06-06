# ─────────────────────────────────────────────────────────────────
# supabase_calling.py
# Drop this file into /home/voiceagent/voice-ai/
# ─────────────────────────────────────────────────────────────────

import os
import logging
from datetime import date, datetime, timezone
from typing import Optional
import httpx

from groq_normalize import ai_normalize_lead_fields

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
async def insert_call_log(
    call_uuid:   str,
    from_number: str,
    to_number:   str,
    direction:   str,
    caller_name: str = "",
    lead_id:     Optional[str] = None,
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
async def finalize_call(
    call_uuid:    str,
    session,
    from_number:  str,
    duration_str: str,
    hangup_cause: str = "",
):
    if not SUPABASE_URL:
        return

    try:
        duration = int(duration_str)
    except (ValueError, TypeError):
        duration = 0

    status = "answered" if duration > 0 else "no_answer"

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
    score, score_breakdown = _compute_score_from_normalized(
        product        = product_interest,
        budget         = budget_mentioned,
        urgency        = urgency_mentioned,
        budget_numeric = budget_numeric or 0,
        final_state    = getattr(session, "state", "QUALIFY_PRODUCT"),
        turn_count     = getattr(session, "turn_count", 0),
        intents_fired  = intents_fired,
        slots          = slots,
    )
    tier       = "hot" if score >= 65 else "warm" if score >= 35 else "cold"
    transcript = getattr(session, "conversation", [])

    # Detect mid_answered: picked up but did not complete all 3 slots
    has_product      = bool(product_interest)
    has_budget       = bool(budget_mentioned)
    has_urgency      = bool(urgency_mentioned)
    all_slots_filled = has_product and has_budget and has_urgency
    call_was_answered = duration > 5

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

        # 2. INSERT call_summaries  ← phone column added here
        try:
            summary_payload = {
                "call_uuid":         call_uuid,
                "lead_id":           getattr(session, "lead_id", None),
                "phone":             phone_clean.replace("+", ""),          # ← customer phone without + prefix
                "product_interest":  product_interest,
                "budget_mentioned":  budget_mentioned,
                "urgency_mentioned": urgency_mentioned,
                "final_state":       getattr(session, "state", ""),
                "turn_count":        getattr(session, "turn_count", 0),
                "intents_fired":     list(intents_fired),
                "slots":             slots,
                "full_transcript":   transcript,
                "lead_score":        score,
                "lead_tier":         tier,
                "tenant_id":         TENANT_ID,
                "budget_numeric":    budget_numeric,
            }
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
                    "p_status":      status,
                    "p_duration":    duration if status == "answered" else None,
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
        _ol_status = 'pending'  # default
        _ol_next   = None
        _ol_retry  = None
        if call_was_answered:
            if all_slots_filled:
                _ol_status = 'answered'
            else:
                # Picked up but incomplete — mid_answered, retry after 1 day
                _ol_status = 'mid_answered'
                from datetime import timedelta
                _ol_next  = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
                _ol_retry = 0  # reset retry count, fresh attempt
        # If not answered: hangup handler in webhook.py already sets unanswered/dnc
        if _ol_status in ('answered', 'mid_answered'):
            try:
                async with httpx.AsyncClient(timeout=5) as _c:
                    _payload = {'status': _ol_status}
                    if _ol_next:  _payload['next_call_at'] = _ol_next
                    if _ol_retry is not None: _payload['retry_count'] = _ol_retry
                    await _c.patch(
                        f"{SUPABASE_URL}/rest/v1/outbound_leads?phone=eq.{phone_clean.replace("+", "%2B")}&tenant_id=eq.{TENANT_ID}",
                        headers=_headers(),
                        json=_payload,
                    )
                logger.info(f'[{call_uuid}] outbound_lead → {_ol_status}')
            except Exception as e:
                logger.error(f'outbound_lead status update error: {e}')

    # ── Fire n8n webhook → triggers WhatsApp follow-up ────────────
    # Only fire if call was actually answered (duration > 0)
    if duration > 0 and phone_clean:
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
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.patch(
                f"{SUPABASE_URL}/rest/v1/leads",
                headers=_headers(),
                params={"id": f"eq.{lead_id}"},
                json={
                    "lead_score":        str(score),
                    "lead_status":       tier,
                    "last_contact":      "now()",
                    "interaction_count": 1,
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