import os, json, logging
from datetime import datetime
from zoneinfo import ZoneInfo
from groq import AsyncGroq

logger = logging.getLogger(__name__)
_groq_client = None

def _get_groq():
    global _groq_client
    if not _groq_client:
        _groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq_client

async def ai_normalize_lead_fields(product, budget_raw, urgency_raw):
    if not budget_raw and not urgency_raw:
        return {"product": product, "budget": budget_raw, "urgency": urgency_raw, "budget_numeric": None}

    prompt = f"""Convert to JSON. No explanation. Raw JSON only.

product="{product or ''}" budget="{budget_raw or ''}" urgency="{urgency_raw or ''}"

urgency examples: "दो से तीन दिन में"→"In 2-3 days", "कल"→"Tomorrow", "अगले हफ्ते"→"Next week", "इसी हफ्ते"→"This week", "म्हणजे"→"Not specified"
budget: single "₹25,000" or range "₹70,000 - ₹90,000"
budget_numeric: if range given take the HIGHER bound as integer (e.g. "1 se 2 lakh" = 200000, "ek lakh" = 100000, "50 hazaar" = 50000), or null only if completely unclear

{{"product":"...","budget":"...","urgency":"...","budget_numeric":0}}"""

    try:
        resp = await _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        logger.info(f"Groq raw response: '{raw}'")
        raw = raw.replace("```json","").replace("```","").strip()
        if not raw:
            logger.error("Groq returned empty body")
            return _fallback(product, budget_raw, urgency_raw)
        result = json.loads(raw)
        logger.info(f"Groq normalize → {result}")
        return result
    except Exception as e:
        logger.error(f"Groq normalize error: {e} | raw was: '{raw if 'raw' in dir() else 'N/A'}'")
        return _fallback(product, budget_raw, urgency_raw)

def _fallback(product, budget_raw, urgency_raw):
    return {"product": product, "budget": budget_raw, "urgency": urgency_raw, "budget_numeric": None}


async def ai_normalize_visit_date(raw_text: str, reference_iso_utc: str) -> str | None:
    """
    Resolve a spoken visit-date utterance (e.g. "kal", "is weekend", "6 august",
    "15 tareek") into an absolute YYYY-MM-DD date, relative to the call's own
    date — converted to IST, since relative references are spoken in the
    customer's local calendar day, not UTC.

    Returns None if parsing fails or the utterance isn't specific enough to
    resolve confidently. Never guesses — callers should treat None as "leave
    visit_date null" and log it, not as an error to retry.
    """
    if not raw_text:
        return None

    try:
        ref_dt = datetime.fromisoformat(reference_iso_utc.replace("Z", "+00:00"))
        ref_ist_date = ref_dt.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()
    except Exception:
        ref_ist_date = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()

    prompt = f"""Today's date is {ref_ist_date} (India, IST). A customer said this when asked to confirm a furniture store visit date: "{raw_text}"

Resolve it to an absolute date, handling relative references ("kal"/tomorrow, "is weekend"/nearest upcoming Saturday-or-Sunday, weekday names, "is hafte"/this week, etc.) relative to today's date above.
If the utterance does not contain enough information to confidently resolve an actual date, return null — do not guess.

Reply with JSON only, no explanation: {{"date": "YYYY-MM-DD or null"}}"""

    try:
        resp = await _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        logger.info(f"Groq visit-date raw response: '{raw}'")
        raw = raw.replace("```json", "").replace("```", "").strip()
        if not raw:
            logger.error("Groq visit-date normalize returned empty body")
            return None
        result = json.loads(raw)
        date_str = result.get("date")
        if not date_str:
            logger.info(f"Groq visit-date normalize → no confident date for '{raw_text}'")
            return None
        datetime.fromisoformat(date_str)  # sanity-check it's a real date, raises if not
        logger.info(f"Groq visit-date normalize → '{raw_text}' resolved to {date_str}")
        return date_str
    except Exception as e:
        logger.error(f"Groq visit-date normalize error: {e} | raw_text='{raw_text}'")
        return None
