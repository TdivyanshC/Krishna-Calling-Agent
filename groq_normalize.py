import os, json, logging
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
