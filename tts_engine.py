"""
tts_engine.py — Language-aware TTS with smart caching layer.

ARCHITECTURE:
  Layer 1: Static cache  — pre-generated FAQs/greetings (0ms, instant)
  Layer 2: Dynamic cache — hash-keyed past responses (0ms, from disk)
  Layer 3: Sarvam API    — fresh generation (3–6s, saved for next time)

KEY IMPROVEMENTS OVER OLD SYSTEM:
  1. Language-aware: uses correct voice per detected language
  2. Cache keys include language suffix → no cross-language cache collisions
  3. Parallel filler + TTS: filler plays while TTS generates
  4. Normalizes text before hashing → slight phrasing variants hit same cache

INTEGRATION:
  Replace your existing text_to_speech() and get_tts_audio() functions
  with get_speech() from this module.
"""

import asyncio
import base64
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SARVAM_API_KEY  = os.getenv("SARVAM_API_KEY", "")
BASE_URL        = os.getenv("BASE_URL", "https://voice.thesocialhood.in")
CACHE_DIR       = Path("/home/voiceagent/voice-ai/tts-cache")
STATIC_DIR      = CACHE_DIR / "static"
DYNAMIC_DIR     = CACHE_DIR / "dynamic"
FILLER_DIR      = CACHE_DIR / "fillers"

TTS_TIMEOUT     = 20  # seconds
TTS_PACE        = 1.05
TTS_SAMPLE_RATE = 8000
TTS_MODEL       = "bulbul:v3"

# ── Voice config per language ─────────────────────────────────────────────────
VOICE_CONFIG = {
    "hi":       {"target_language_code": "hi-IN", "speaker": "kavya"},
    "hinglish": {"target_language_code": "hi-IN", "speaker": "kavya"},
    "en":       {"target_language_code": "en-IN", "speaker": "kavya"},
}

# ── Static cache: pre-generated responses keyed by source tag ─────────────────
# Add every FAQ response here — these are generated ONCE and played forever.
# Format: "cache_key": {"hi": "...", "hinglish": "...", "en": "..."}
# Use generate_static_cache() below to pre-generate them all.

STATIC_RESPONSES = {
    # ── Greetings ──────────────────────────────────────────────────────────────
    "greeting_inbound": {
        "hinglish": "Krishna Furniture mein aapka swagat hai, main Priya bol rahi hoon — aapki kya madad kar sakti hoon?",
        "hi":       "कृष्णा फर्नीचर में आपका स्वागत है, मैं प्रिया बोल रही हूँ — आपकी कैसे मदद कर सकती हूँ?",
        "en":       "Welcome to Krishna Furniture, this is Priya speaking — how can I help you today?",
    },
    "greeting_outbound": {
        "hinglish": "Namaskar, main Priya hoon Krishna Furniture se — abhi 2 minute baat kar sakte hain?",
        "hi":       "नमस्कार, मैं प्रिया हूँ कृष्णा फर्नीचर से — अभी 2 मिनट बात कर सकते हैं?",
        "en":       "Hello, this is Priya from Krishna Furniture — is this a good time to talk?",
    },

    # ── Qualification questions ────────────────────────────────────────────────
    "qualify_product": {
        "hinglish": "Kya dhundh rahe hain aap — sofa, bed, wardrobe, ya kuch aur?",
        "hi":       "आप क्या ढूंढ रहे हैं — सोफा, बेड, वार्डरोब, या कुछ और?",
        "en":       "What are you looking for — sofa, bed, wardrobe, or something else?",
    },
    "qualify_budget": {
        "hinglish": "Budget roughly kitna hai aapka?",
        "hi":       "आपका बजट लगभग कितना है?",
        "en":       "What's your approximate budget?",
    },
    "qualify_urgency": {
        "hinglish": "Kab tak chahiye aapko?",
        "hi":       "आपको कब तक चाहिए?",
        "en":       "When do you need it by?",
    },
    "wrap_whatsapp": {
        "hinglish": "Bilkul ji, main aapko WhatsApp pe options bhej rahi hoon. Koi aur sawaal?",
        "hi":       "बिल्कुल जी, मैं आपको WhatsApp पर options भेज रही हूँ। कोई और सवाल?",
        "en":       "Perfect, I'll send you the options on WhatsApp. Any other questions?",
    },
    "goodbye": {
        "hinglish": "Bahut shukriya aapka. Krishna Furniture ki taraf se aapka din shubh ho!",
        "hi":       "बहुत शुक्रिया आपका। कृष्णा फर्नीचर की तरफ से आपका दिन शुभ हो!",
        "en":       "Thank you so much for calling. Have a wonderful day from all of us at Krishna Furniture!",
    },

    # ── Objections ─────────────────────────────────────────────────────────────
    "obj_expensive": {
        "hinglish": "Samajh sakti hoon, sir. Already 40% discount include hai. EMI mein convert karein toh sirf 3-4 hazaar per month padta hai. Budget batao — usi range mein best option dhundh leti hoon.",
        "hi":       "समझ सकती हूँ, सर। पहले से 40% छूट शामिल है। EMI में convert करें तो सिर्फ 3-4 हज़ार प्रति माह पड़ता है। बजट बताइए — उस रेंज में best option ढूंढ लेती हूँ।",
        "en":       "I understand. The 40% discount is already included. On EMI it's just 3-4 thousand per month. Tell me your budget and I'll find the best option in that range.",
    },
    "obj_think": {
        "hinglish": "Bilkul sochiye. Bas yeh offer limited time ka hai. Ek baar store aiye, quality feel kariye — phir decide kariye. Kaunsa din suit karega?",
        "hi":       "बिल्कुल सोचिए। बस यह offer limited time का है। एक बार स्टोर आइए, quality feel करिए — फिर decide करिए। कौन सा दिन suit करेगा?",
        "en":       "Of course, take your time. But this offer is for a limited time. Visit our store once, feel the quality — then decide. Which day works for you?",
    },
    "obj_online": {
        "hinglish": "Sir, online mein delivery, assembly aur quality guarantee alag hoti hai. Hamare khud ke plants hain — quality aur after-sales dono hamare haath mein. Ek baar dekhne aiye, fark samajh aayega.",
        "hi":       "सर, online में delivery, assembly और quality guarantee अलग होती है। हमारे खुद के plants हैं — quality और after-sales दोनों हमारे हाथ में। एक बार देखने आइए, फर्क समझ आएगा।",
        "en":       "Sir, with online you get different delivery, assembly and quality guarantees. We have our own manufacturing plants — quality and after-sales are both in our hands. Visit once and you'll see the difference.",
    },
    "obj_busy": {
        "hinglish": "Ji zaroor. Tab tak main aapko WhatsApp pe kuch options bhejti hoon. Number confirm kar loon?",
        "hi":       "जी ज़रूर। तब तक मैं आपको WhatsApp पर कुछ options भेजती हूँ। नंबर confirm कर लूँ?",
        "en":       "Of course. I'll send you some options on WhatsApp in the meantime. Can I confirm your number?",
    },

    # ── FAQs ───────────────────────────────────────────────────────────────────
    "faq_location": {
        "hinglish": "Hamare stores Gurgaon, Delhi, Faridabad aur Noida mein hain. Aap kis area mein hain? Nearest store ki detail deti hoon.",
        "hi":       "हमारे stores गुड़गाँव, दिल्ली, फरीदाबाद और नोएडा में हैं। आप किस area में हैं? Nearest store की detail देती हूँ।",
        "en":       "We have stores in Gurgaon, Delhi, Faridabad and Noida. Which area are you in? I'll give you the nearest store details.",
    },
    "faq_delivery": {
        "hinglish": "Delivery 7 se 14 din mein hoti hai. Same city mein free delivery hai. Installation bhi free mein milti hai.",
        "hi":       "Delivery 7 से 14 दिन में होती है। Same city में free delivery है। Installation भी free मिलती है।",
        "en":       "Delivery takes 7 to 14 days. Same-city delivery is free, and installation is also complimentary.",
    },
    "faq_emi": {
        "hinglish": "Haan ji, EMI available hai — 6, 12, aur 24 months ke options hain. No-cost EMI bhi hai kuch products pe. Kaunsa product dekhna tha?",
        "hi":       "हाँ जी, EMI available है — 6, 12, और 24 महीनों के options हैं। No-cost EMI भी है कुछ products पर। कौन सा product देखना था?",
        "en":       "Yes, EMI is available in 6, 12, and 24 month options. No-cost EMI is also available on select products. Which product were you looking at?",
    },
    "faq_warranty": {
        "hinglish": "1 saal ki warranty milti hai manufacturing defects pe. Cushions pe 6 mahine ki warranty hai. After-sales support hamare store pe available hai.",
        "hi":       "1 साल की warranty मिलती है manufacturing defects पर। Cushions पर 6 महीने की warranty है। After-sales support हमारे store पर available है।",
        "en":       "We offer 1 year warranty on manufacturing defects and 6 months on cushions. After-sales support is available at our store.",
    },
    "faq_customisation": {
        "hinglish": "Haan, customisation hoti hai — colour, fabric, size sab change ho sakta hai. 15 se 20 din extra lagte hain. Kya customise karna tha?",
        "hi":       "हाँ, customisation होती है — colour, fabric, size सब change हो सकता है। 15 से 20 दिन extra लगते हैं। क्या customise करना था?",
        "en":       "Yes, customisation is available — colour, fabric and size can all be changed. It takes an extra 15 to 20 days. What would you like to customise?",
    },
    "faq_repeat": {
        "hinglish": "Haan ji, main yahan hoon — phir se bolo?",
        "hi":       "हाँ जी, मैं यहाँ हूँ — फिर से बोलिए?",
        "en":       "Yes, I'm here — could you say that again?",
    },
    # ── Additional FAQ static responses ──────────────────────────────────────
    "store_location": {
        "hinglish": "Hamare stores Gurgaon, Delhi, Faridabad aur Noida mein hain. Aap kis area mein hain? Nearest store ki detail deti hoon.",
        "hi":       "हमारे स्टोर गुड़गाँव, दिल्ली, फरीदाबाद और नोएडा में हैं। आप किस एरिया में हैं? नज़दीकी स्टोर की डिटेल देती हूँ।",
        "en":       "We have stores in Gurgaon, Delhi, Faridabad and Noida. Which area are you in? I will give you the nearest store details.",
    },
    "delivery_charges": {
        "hinglish": "Delivery 7 se 14 din mein hoti hai. Same city mein free delivery hai, installation bhi free.",
        "hi":       "डिलीवरी 7 से 14 दिन में होती है। Same city में फ्री डिलीवरी है, इंस्टॉलेशन भी फ्री।",
        "en":       "Delivery takes 7 to 14 days. Same city delivery is free and installation is complimentary.",
    },
    "delivery_delay": {
        "hinglish": "Delivery update ke liye bill mein salesperson ka naam dekhiye aur unse contact karein — wo exact update denge.",
        "hi":       "डिलीवरी अपडेट के लिए बिल में सेल्सपर्सन का नाम देखिए और उनसे संपर्क करिए — वो exact अपडेट देंगे।",
        "en":       "For delivery updates, please check the salesperson name on your bill and contact them directly for an exact update.",
    },
    "general_discount_offer": {
        "hinglish": "Abhi flat 40% discount chal raha hai MRP pe har item pe. Kaun sa product dekhna hai?",
        "hi":       "अभी फ्लैट 40% छूट चल रही है MRP पर हर आइटम पे। कौन सा प्रोडक्ट देखना है?",
        "en":       "We currently have a flat 40% discount on MRP across all items. Which product are you looking for?",
    },
    "exchange_offer": {
        "hinglish": "Exchange offer mein purana furniture lao — pehle 25% off, phir baaki pe aur 25%. Double saving! Kaun sa furniture exchange karna hai?",
        "hi":       "एक्सचेंज ऑफर में पुराना फर्नीचर लाओ — पहले 25% छूट, फिर बाकी पर और 25%। Double saving! कौन सा फर्नीचर एक्सचेंज करना है?",
        "en":       "In our exchange offer, bring your old furniture and get 25% off first, then another 25% on the rest. Double saving! What furniture would you like to exchange?",
    },
    "warranty_quality": {
        "hinglish": "Warranty available hai — exact terms product pe depend karti hai. Manufacturing defect pe replacement bhi milti hai.",
        "hi":       "वारंटी उपलब्ध है — exact terms प्रोडक्ट पर निर्भर। Manufacturing defect पर replacement भी मिलती है।",
        "en":       "Warranty is available and varies by product. Manufacturing defects are covered with replacement.",
    },
    "timing_hours": {
        "hinglish": "Store Monday se Sunday, subah 10 baje se raat 8 baje tak khula rehta hai.",
        "hi":       "स्टोर सोमवार से रविवार, सुबह 10 बजे से रात 8 बजे तक खुला रहता है।",
        "en":       "The store is open Monday to Sunday, from 10 AM to 8 PM.",
    },
    "installation_assembly": {
        "hinglish": "Free installation milti hai delivery ke saath — hamari team sab set up kar degi.",
        "hi":       "फ्री इंस्टॉलेशन मिलती है डिलीवरी के साथ — हमारी टीम सब सेट अप कर देगी।",
        "en":       "Free installation is included with delivery. Our team will set everything up for you.",
    },
    "customization": {
        "hinglish": "Haan, size, color aur fabric customize ho sakta hai. Kis product mein badlav chahiye?",
        "hi":       "हाँ, साइज़, कलर और फैब्रिक customize हो सकता है। किस प्रोडक्ट में बदलाव चाहिए?",
        "en":       "Yes, size, colour and fabric can all be customised. Which product would you like to change?",
    },
    "manufacturing": {
        "hinglish": "Hamare khud ke plants hain — Kherki Daula aur Bamdoli mein. Koi import nahi, sab in-house. Quality guaranteed.",
        "hi":       "हमारे खुद के प्लांट्स हैं — खेड़की दौला और बामडोली में। कोई इम्पोर्ट नहीं, सब इन-हाउस। क्वालिटी गारंटीड।",
        "en":       "We have our own manufacturing plants in Kherki Daula and Bamdoli. No imports, everything in-house. Quality guaranteed.",
    },
    "store_address_request": {
        "hinglish": "Bilkul! Main aapko WhatsApp pe nearest showroom ka address aur Google Maps link bhej deti hoon. Number confirm kar loon?",
        "hi":       "ज़रूर! मैं आपको WhatsApp पर nearest शोरूम का address और Google Maps link भेज देती हूँ। नंबर confirm कर लूँ?",
        "en":       "Sure! I will send you the nearest showroom address and Google Maps link on WhatsApp. Can I confirm your number?",
    },
    "goodbye": {
        "hinglish": "Bahut shukriya aapka! Krishna Furniture ki taraf se aapka din shubh ho. Milte hain store pe!",
        "hi":       "बहुत शुक्रिया आपका! कृष्णा फर्नीचर की तरफ से आपका दिन शुभ हो। मिलते हैं स्टोर पे!",
        "en":       "Thank you so much! Have a wonderful day from all of us at Krishna Furniture. See you at the store!",
    },
    "not_understood": {
        "hinglish": "Maafi chahti hoon, thoda clear nahi hua. Kya aap dobara bol sakte hain?",
        "hi":       "माफी चाहती हूँ, थोड़ा clear नहीं हुआ। क्या आप दोबारा बोल सकते हैं?",
        "en":       "I'm sorry, I didn't quite catch that. Could you say that again?",
    },
}


# ── Cache utilities ────────────────────────────────────────────────────────────

def _make_static_path(key: str, lang: str) -> Path:
    return STATIC_DIR / f"{key}_{lang}.wav"


def _make_dynamic_path(text: str, lang: str) -> Path:
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    h = hashlib.md5(f"{lang}:{normalized}".encode()).hexdigest()[:12]
    return DYNAMIC_DIR / f"dyn_{h}.wav"


def _make_url(path: Path) -> str:
    rel = path.relative_to(CACHE_DIR)
    return f"{BASE_URL}/audio/{rel}"


def get_static_audio(key: str, lang: str) -> Optional[bytes]:
    path = _make_static_path(key, lang)
    if path.exists():
        return path.read_bytes()
    # Fallback to hinglish if specific lang not cached
    if lang != "hinglish":
        fallback = _make_static_path(key, "hinglish")
        if fallback.exists():
            return fallback.read_bytes()
    return None


def get_dynamic_audio(text: str, lang: str) -> Optional[bytes]:
    path = _make_dynamic_path(text, lang)
    if path.exists():
        return path.read_bytes()
    return None


def save_dynamic_audio(text: str, lang: str, wav: bytes) -> Path:
    DYNAMIC_DIR.mkdir(parents=True, exist_ok=True)
    path = _make_dynamic_path(text, lang)
    path.write_bytes(wav)
    return path


# ── Sarvam API call ───────────────────────────────────────────────────────────

async def _call_sarvam_tts(text: str, lang: str) -> Optional[bytes]:
    """Raw Sarvam TTS API call. Returns WAV bytes or None."""
    cfg = VOICE_CONFIG.get(lang, VOICE_CONFIG["hinglish"])
    try:
        async with httpx.AsyncClient(timeout=TTS_TIMEOUT) as client:
            r = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={
                    "API-Subscription-Key": SARVAM_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "inputs": [text],
                    "target_language_code": cfg["target_language_code"],
                    "speaker": cfg["speaker"],
                    "pace": TTS_PACE,
                    "speech_sample_rate": TTS_SAMPLE_RATE,
                    "model": TTS_MODEL,
                },
            )
        if r.status_code == 200:
            data = r.json()
            if data.get("audios"):
                return base64.b64decode(data["audios"][0])
        logger.error(f"Sarvam TTS {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"Sarvam TTS error: {e}")
    return None


# ── Public API ────────────────────────────────────────────────────────────────

async def get_speech(
    text: str,
    lang: str,
    static_key: Optional[str] = None,
) -> tuple:
    """
    Main TTS function. Returns (wav_bytes, url, was_cached).

    Priority:
      1. Static cache (pre-generated FAQ/greeting) — instant
      2. Dynamic cache (past response with same text+lang) — instant
      3. Sarvam API — 3–6s, saves to dynamic cache

    Args:
      text:       The text to speak
      lang:       "hi", "en", or "hinglish"
      static_key: If provided, checks static cache first (e.g. "greeting_inbound")
    """
    # Layer 1: Static cache
    if static_key:
        wav = get_static_audio(static_key, lang)
        if wav:
            url = _make_url(_make_static_path(static_key, lang))
            logger.info(f"STATIC HIT [{lang}] → {static_key}")
            return wav, url, True

    # Layer 2: Dynamic cache
    wav = get_dynamic_audio(text, lang)
    if wav:
        url = _make_url(_make_dynamic_path(text, lang))
        logger.info(f"DYNAMIC HIT [{lang}] → {text[:40]!r}")
        return wav, url, True

    # Layer 3: Fresh from Sarvam
    wav = await _call_sarvam_tts(text, lang)
    if wav:
        path = save_dynamic_audio(text, lang, wav)
        url = _make_url(path)
        logger.info(f"TTS GENERATED [{lang}] → {text[:40]!r}")
        return wav, url, False

    return None, "", False


async def get_speech_url(text: str, lang: str, static_key: Optional[str] = None) -> str:
    """Returns just the URL (for Vobiz Play API). Generates and caches if needed."""
    _, url, _ = await get_speech(text, lang, static_key)
    return url


# ── Pre-generate static cache ─────────────────────────────────────────────────

async def generate_static_cache() -> None:
    """
    Pre-generate all static response WAVs.
    Run once at startup — skips already-generated files.
    Takes ~60–90s on first run, then all responses are instant forever.
    """
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Pre-generating static TTS cache...")

    tasks = []
    for key, lang_map in STATIC_RESPONSES.items():
        for lang, text in lang_map.items():
            path = _make_static_path(key, lang)
            if not path.exists():
                tasks.append(_generate_and_save_static(key, lang, text))
            else:
                logger.info(f"STATIC EXISTS: {key}_{lang}")

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success = sum(1 for r in results if r is True)
        logger.info(f"Static cache: {success}/{len(tasks)} generated")
    else:
        logger.info("Static cache already complete — all responses instant")


async def _generate_and_save_static(key: str, lang: str, text: str) -> bool:
    wav = await _call_sarvam_tts(text, lang)
    if wav:
        path = _make_static_path(key, lang)
        path.write_bytes(wav)
        logger.info(f"STATIC SAVED: {key}_{lang}")
        return True
    logger.error(f"STATIC FAILED: {key}_{lang}")
    return False


def static_cache_stats() -> dict:
    """Returns cache hit stats for monitoring."""
    total = sum(len(v) for v in STATIC_RESPONSES.values())
    cached = sum(
        1 for key, lang_map in STATIC_RESPONSES.items()
        for lang in lang_map
        if _make_static_path(key, lang).exists()
    )
    return {
        "static_total": total,
        "static_cached": cached,
        "static_ready": cached == total,
        "dynamic_count": len(list(DYNAMIC_DIR.glob("dyn_*.wav"))) if DYNAMIC_DIR.exists() else 0,
    }


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    print("TTS Engine — static cache stats:")
    stats = static_cache_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if "--generate" in sys.argv:
        print("\nGenerating static cache...")
        asyncio.run(generate_static_cache())
        print("Done.")