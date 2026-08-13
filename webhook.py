import os
import asyncio
import logging
import base64
import json
import audioop
import wave
import io
import time
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx
from dotenv import load_dotenv
from groq import Groq
from knowledge import get_response as kb_response, build_llm_context, match_faq_detour, reply_has_ungrounded_price
from audit_log import audit_event

load_dotenv("/home/voiceagent/voice-ai/.env")
from supabase_calling import insert_call_log, finalize_call, get_or_create_lead_id, mark_dnc_immediate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Persistent HTTP client for Vobiz Play API ────────────────────────────────
_vobiz_http_client: "httpx.AsyncClient | None" = None
_sarvam_http_client: "httpx.AsyncClient | None" = None

async def _get_sarvam_client() -> "httpx.AsyncClient":
    global _sarvam_http_client
    if _sarvam_http_client is None or _sarvam_http_client.is_closed:
        _sarvam_http_client = httpx.AsyncClient(timeout=15)
    return _sarvam_http_client

async def _get_vobiz_client() -> "httpx.AsyncClient":
    global _vobiz_http_client
    if _vobiz_http_client is None or _vobiz_http_client.is_closed:
        _vobiz_http_client = httpx.AsyncClient(timeout=8)
    return _vobiz_http_client

# ── Upgrade: Language-aware TTS + filler system ───────────────────────────────
from contextlib import asynccontextmanager
from lang_detect import detect_lang, get_lang_instruction
from tts_engine import get_speech, generate_static_cache, static_cache_stats
from filler_audio import generate_fillers, load_filler_cache
from respond_pipeline import build_multilingual_llm_system_prompt

# ─── TTS Cache Registry ───────────────────────────────────────────────────────
CACHE_DIR = "/home/voiceagent/voice-ai/tts-cache"

STATIC_CACHE: dict[str, str] = {
    "greeting_inbound":   f"{CACHE_DIR}/static_greeting_inbound.wav",
    "greeting_outbound":  f"{CACHE_DIR}/static_greeting_outbound.wav",
    "objection:expensive":     f"{CACHE_DIR}/static_obj_expensive.wav",
    "objection:think":         f"{CACHE_DIR}/static_obj_think.wav",
    "objection:online":        f"{CACHE_DIR}/static_obj_online.wav",
    "objection:busy":          f"{CACHE_DIR}/static_obj_busy.wav",
    "objection:competitor":    f"{CACHE_DIR}/static_obj_competitor.wav",
    "objection:not_interested":f"{CACHE_DIR}/static_obj_notinterested.wav",
    "faq:location":       f"{CACHE_DIR}/static_faq_location.wav",
    "faq:head_branch":    f"{CACHE_DIR}/static_faq_headbranch.wav",
    "faq:timing":         f"{CACHE_DIR}/static_faq_timing.wav",
    "faq:offer":          f"{CACHE_DIR}/static_faq_offer.wav",
    "faq:exchange":       f"{CACHE_DIR}/static_faq_exchange.wav",
    "faq:emi":            f"{CACHE_DIR}/static_faq_emi.wav",
    "faq:delivery":       f"{CACHE_DIR}/static_faq_delivery.wav",
    "faq:pan_india":      f"{CACHE_DIR}/static_faq_panindia.wav",
    "faq:manufacturing":  f"{CACHE_DIR}/static_faq_manufacturing.wav",
    "faq:quality":        f"{CACHE_DIR}/static_faq_quality.wav",
    "faq:warranty":       f"{CACHE_DIR}/static_faq_warranty.wav",
    "faq:sofa_general":   f"{CACHE_DIR}/static_faq_sofa.wav",
    "faq:sofa_lshape":    f"{CACHE_DIR}/static_faq_sofa_lshape.wav",
    "faq:sofa_cum_bed":   f"{CACHE_DIR}/static_faq_sofacumbed.wav",
    "faq:bed_general":    f"{CACHE_DIR}/static_faq_bed.wav",
    "faq:dining_general": f"{CACHE_DIR}/static_faq_dining.wav",
    "faq:wardrobe":       f"{CACHE_DIR}/static_faq_wardrobe.wav",
    "faq:office_general": f"{CACHE_DIR}/static_faq_office.wav",
    "faq:tv_unit":        f"{CACHE_DIR}/static_faq_tvunit.wav",
    "faq:price_general":  f"{CACHE_DIR}/static_faq_price.wav",
    "faq:products_general":f"{CACHE_DIR}/static_faq_products.wav",
    "faq:interior":       f"{CACHE_DIR}/static_faq_interior.wav",
    "faq:wholesale":      f"{CACHE_DIR}/static_faq_wholesale.wav",
    "faq:visit":          f"{CACHE_DIR}/static_faq_visit.wav",
    "faq:installation":   f"{CACHE_DIR}/static_faq_installation.wav",
    "product_only:sofa":     f"{CACHE_DIR}/static_slot_sofa.wav",
    "product_only:bed":      f"{CACHE_DIR}/static_slot_bed.wav",
    "product_only:dining":   f"{CACHE_DIR}/static_slot_dining.wav",
    "product_only:wardrobe": f"{CACHE_DIR}/static_slot_wardrobe.wav",
    "product_only:office":   f"{CACHE_DIR}/static_slot_office.wav",
    "fallback:0":  f"{CACHE_DIR}/static_fallback_1.wav",
    "fallback:1":  f"{CACHE_DIR}/static_fallback_2.wav",
    "fallback:2":  f"{CACHE_DIR}/static_fallback_3.wav",
    "fallback_llm":f"{CACHE_DIR}/static_fallback_llm.wav",
}

def get_static_audio(source: str) -> bytes | None:
    path = STATIC_CACHE.get(source)
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None

def get_dynamic_cache_path(text: str) -> str:
    import hashlib
    h = hashlib.md5(text.strip().encode("utf-8")).hexdigest()[:10]
    return f"{CACHE_DIR}/dyn_{h}.wav"

def get_dynamic_audio(text: str) -> bytes | None:
    path = get_dynamic_cache_path(text)
    if os.path.exists(path):
        logger.info(f"DYN CACHE HIT → {path}")
        with open(path, "rb") as f:
            return f.read()
    return None

def save_dynamic_audio(text: str, wav_bytes: bytes):
    path = get_dynamic_cache_path(text)
    with open(path, "wb") as f:
        f.write(wav_bytes)
    logger.info(f"DYN CACHE SAVED → {path}")

# ─── App & Clients ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    load_filler_cache()
    logger.info("Filler cache loaded")
    stats = static_cache_stats()
    logger.info(f"TTS static cache: {stats['static_cached']}/{stats['static_total']} ready")
    if not stats.get("static_ready"):
        logger.warning("Run generate_cache.py to pre-generate all static responses")
    yield
    logger.info("Shutting down...")

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/audio", StaticFiles(directory="/home/voiceagent/voice-ai/tts-cache"), name="audio")

groq_client    = Groq(api_key=os.getenv("GROQ_API_KEY"))
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
BASE_URL       = "https://voice.thesocialhood.in"
VOBIZ_ACCOUNT  = "MA_P0E0RLUU"
VOBIZ_AUTH_ID  = "MA_P0E0RLUU"
VOBIZ_AUTH_TOK = "XC5wQHlaTsNKltGHxoo4Ln5s14zQKzcDd31EQ2I4MEXOlDUBHWcuZ4Ja4dJh6JMY"

# 10:00 AM - 8:00/10:00 PM IST calling window — mirrors outbound_orchestrator.py's
# CALL_START_HOUR/CALL_END_HOUR_BY_CAMPAIGN (kept as separate constants, not a
# shared import, since the two processes are deployed/restarted independently).
# Enforced here too, not just in the orchestrator's tick() loop: /trigger-call
# previously had no window check of its own and trusted whichever caller hit
# it to have already gated on the window — same single-point-of-enforcement
# shape as the DNC bypass fixed 2026-07-15 (see mark_dnc_immediate), where
# calls turned out to be arriving through this endpoint from something other
# than the orchestrator's own filtered lead list.
#
# fresh_cta gets the wider 10-22 window (first-contact outreach); every
# reactivation variant (reactivation/react_a/b/c, and call_cycle 2/3 which
# reuse the same campaign value) is clamped tighter to 10-20 — these are
# repeat contacts with an existing customer, where a late-evening call reads
# as more intrusive than a first-touch fresh lead call.
IST             = ZoneInfo("Asia/Kolkata")
CALL_START_HOUR = 10   # 10:00 AM IST, all campaigns
CALL_END_HOUR_BY_CAMPAIGN = {
    "fresh_cta": 22,   # 10:00 PM IST
}
CALL_END_HOUR_DEFAULT = 20   # 8:00 PM IST — reactivation/react_a/b/c and anything else


def is_calling_window(campaign: str = "") -> bool:
    hour = datetime.now(IST).hour
    end_hour = CALL_END_HOUR_BY_CAMPAIGN.get(campaign, CALL_END_HOUR_DEFAULT)
    return CALL_START_HOUR <= hour < end_hour

# ─── STT Correction Map ───────────────────────────────────────────────────────
STT_CORRECTIONS = {
    r"\bso far\b":       "sofa",
    r"\bso fa\b":        "sofa",
    r"\bseufa\b":        "sofa",
    r"\bsofar\b":        "sofa",
    r"\bso pha\b":       "sofa",
    r"\bso far dear\b":  "sofa",
    r"\bdear leonard\b": "",
    r"\bleonard\b":      "",
    r"\bsochen ge\b":    "sochenge",
    r"\bsochen\b":       "sochenge",
    r"\bmehenga\b":      "mahanga",
    r"\bmehngi\b":       "mahanga",
    r"\bgurgoan\b":      "gurgaon",
    r"\bguru gaon\b":    "gurgaon",
    r"\be\.m\.i\b":      "emi",
    r"\balmari\b":       "almirah",
}

def correct_stt(text: str) -> str:
    corrected = text.lower()
    for pattern, replacement in STT_CORRECTIONS.items():
        corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
    corrected = re.sub(r'\s+', ' ', corrected).strip()
    if corrected != text.lower():
        logger.info(f"STT corrected: '{text}' → '{corrected}'")
    return corrected

# ─── VAD ─────────────────────────────────────────────────────────────────────
SILENCE_THRESHOLD = 400
MIN_SPEECH_FRAMES = 6    # 120ms minimum — filters out clicks and noise
TRAILING_SILENCE  = 18   # 360ms — enough for natural mid-sentence pauses
BARGE_IN_FRAMES   = 10  # raised from 4 — reduces false barge-in triggers from echo/noise on longer reactivation lines
SAMPLE_RATE       = 8000
REJECTION_GRACEFUL_DECLINE_THRESHOLD = 2  # rejection_signals count that forces a scripted, no-CTA exit

# ═════════════════════════════════════════════════════════════════════════════
# INTENT ENGINE
# ═════════════════════════════════════════════════════════════════════════════

OBJECTIONS = {
    "expensive": (
        ["mahanga","mehenga","mehngi","costly","bahut zyada","expensive","paisa nahi","budget nahi","zyada hai"],
        "सर, पहले से ४०% छूट शामिल है। EMI में कन्वर्ट करें तो सिर्फ ३-४ हज़ार प्रति महीना पड़ता है। बजट बताइए — उस रेंज में बेस्ट ऑप्शन ढूंढ लेती हूँ।"
    ),
    "think": (
        ["sochenge","soch lenge","soch ke","will think","baad mein batata","sochna hai"],
        "बिल्कुल सोचिए। बस यह ऑफर लिमिटेड टाइम का है। एक बार स्टोर आइए, क्वालिटी फील करिए — फिर डिसाइड करिए। कौन सा दिन सूट करेगा?"
    ),
    "online": (
        ["amazon","flipkart","online sasta","pepperfry","urban ladder","ikea","website pe sasta"],
        "सर, ऑनलाइन में डिलीवरी, असेंबली और क्वालिटी गारंटी अलग होती है। हमारे खुद के प्लांट्स हैं — क्वालिटी और आफ्टर-सेल्स दोनों हमारे हाथ में। एक बार देखने आइए, फर्क समझ आएगा।"
    ),
    "busy": (
        ["busy hoon","abhi nahi","baad mein call","call back karo","later","abhi time nahi"],
        "जी ज़रूर। तब तक मैं आपको WhatsApp पर कुछ ऑप्शन भेजती हूँ। नंबर कन्फर्म कर लूँ?"
    ),
    "competitor": (
        ["godrej","durian","nilkamal","zuari","hometown","wooden street","compare karna"],
        "बिल्कुल कंपेयर करिए सर। हमारे खुद के प्लांट्स हैं तो क्वालिटी और प्राइसिंग दोनों में एडवांटेज है। किस ब्रांड से कंपेयर कर रहे हैं?"
    ),
    "not_interested": (
        ["nahi chahiye","interest nahi","zaroorat nahi","wrong number","galat number","rehne do",
         # Added alongside the reactivation-funnel dnc fix (webhook_reactivation.py) —
         # same "call again" phrasing gap confirmed live there; this matcher is a
         # separate raw-substring system (not detect_intents), so ported as literal
         # phrases rather than the token-proximity check used in the other funnels.
         "call na karo","call na karein","dobara call na","call mat karna","phone mat karna",
         "list se hata","bilkul interested nahi",
         "कॉल ना करो","कॉल ना करें","दोबारा कॉल ना","कॉल मत करना","फोन मत करना",
         "लिस्ट से हटा","बिल्कुल इंटरेस्टेड नहीं"],
        "कोई बात नहीं सर। कभी ज़रूरत हो तो हम हैं। आपका दिन शुभ हो!"
    ),
}

FAQS = {
    "location":       (["location","address","kahan hai","where is","showroom kahan","store kahan","nearest store"],
                       "हमारे स्टोर गुड़गाँव, दिल्ली, फरीदाबाद और नोएडा में हैं। आप किस एरिया में हैं? नज़दीकी स्टोर की डिटेल देती हूँ।"),
    "head_branch":    (["head branch","head office","sector 14","atul kataria"],
                       "हेड ब्रांच सेक्टर चौदह गुरुग्राम में है, अतुल कटारिया चौक के पास। कब आना चाहेंगे?"),
    "timing":         (["timing","timings","open","close","kab khulta","hours","baje"],
                       "स्टोर टाइमिंग के लिए अपना एरिया बताइए — मैं WhatsApp पर exact टाइमिंग भेज देती हूँ।"),
    "offer":          (["offer","discount","chhoot","sale","deal","kya offer","koi offer"],
                       "अभी फ्लैट चालीस प्रतिशत छूट चल रही है MRP पर हर आइटम पे। और एक्सचेंज ऑफर में डबल सेविंग — पच्चीस प्रतिशत प्लस पच्चीस प्रतिशत!"),
    "exchange":       (["exchange","purana furniture","old furniture","badal","trade in"],
                       "एक्सचेंज ऑफर में पुराना फर्नीचर लाओ — पहले MRP पर पच्चीस प्रतिशत छूट, फिर बाकी पर और पच्चीस प्रतिशत छूट। डबल सेविंग! कौन सा फर्नीचर एक्सचेंज करना है?"),
    "emi":            (["emi","loan","installment","finance","kist","monthly","zero percent"],
                       "हाँ, EMI उपलब्ध है — ज़ीरो प्रतिशत भी मिलती है कुछ ऑप्शन में। कितनी मंथली बजट सोच रहे हैं?"),
    "delivery":       (["delivery","deliver","ghar pe","delivery charge","kab milega","shipping"],
                       "डिलीवरी चार्जेज़ लोकेशन पर निर्भर करते हैं। एड्रेस शेयर करिए — मैं exact चार्जेज़ कन्फर्म करती हूँ।"),
    "pan_india":      (["pan india","bahar deliver","other city","different state","poora india"],
                       "हाँ बिल्कुल, पूरे भारत में डिलीवरी करते हैं। वेबसाइट से भी ऑर्डर कर सकते हैं।"),
    "manufacturing":  (["manufacturing","factory","plant","banate kahan","import","made where"],
                       "हमारे खुद के प्लांट्स हैं — खेड़की दौला और बामडोली में। कोई इम्पोर्ट नहीं, सब इन-हाउस। क्वालिटी गारंटीड।"),
    "quality":        (["quality","toot jayega","durable","strong","material","kitne saal chalega"],
                       "सॉलिड वुड और प्रीमियम फैब्रिक यूज़ करते हैं — सब इन-हाउस बनता है। एक बार स्टोर में टच करके देखिए, कॉन्फिडेंस आ जाएगा।"),
    "warranty":       (["warranty","guarantee","repair","garanti"],
                       "वारंटी उपलब्ध है — exact टर्म्स प्रोडक्ट पर निर्भर करती हैं। स्टोर विज़िट में पूरी डिटेल मिल जाएगी। कब आना चाहेंगे?"),
    "sofa_general":   (["sofa","couch","settee","sofa set"],
                       "एक सीट से लेकर कॉर्नर सोफा तक सब उपलब्ध है — चौदह हज़ार से शुरू, चालीस प्रतिशत छूट के बाद। कौन सा साइज़ चाहिए — दो सीट, तीन सीट या कॉर्नर?"),
    "sofa_lshape":    (["l shape","l-shape","corner sofa","l type"],
                       "कॉर्नर सोफा छिहत्तर हज़ार से शुरू — Eagle, Opal, Zikara adjustable हेडरेस्ट वाले भी उपलब्ध। कितने लोगों के लिए चाहिए?"),
    "sofa_cum_bed":   (["sofa cum bed","sofa bed","diwan","cum bed","convertible sofa"],
                       "सोफा कम बेड चवालीस हज़ार से शुरू — Ace, Shine, Grace — कई डिज़ाइन। गेस्ट रूम के लिए है या डेली यूज़?"),
    "bed_general":    (["bed","palang","king size","bedroom","hydraulic bed","storage bed"],
                       "किंग साइज़ बेड विद स्टोरेज इकहत्तर हज़ार से शुरू — हाइड्रोलिक और पुलआउट दोनों। कौन सा स्टोरेज टाइप पसंद करेंगे?"),
    "dining_general": (["dining","dining table","dining set","marble dining"],
                       "छह सीट डाइनिंग सेट एक लाख उन्नीस हज़ार से शुरू — सॉलिड वुड और मार्बल दोनों। फैमिली कितने लोगों की है?"),
    "wardrobe":       (["wardrobe","almirah","almari","cupboard","2 door","3 door"],
                       "दो दरवाज़ा वार्डरोब सैंतीस हज़ार से, तीन दरवाज़ा अड़तालीस हज़ार से शुरू। बेडरूम में कितनी जगह है roughly?"),
    "office_general": (["office table","office chair","workstation","study table","reception"],
                       "ऑफिस टेबल बारह हज़ार से और कुर्सियाँ बीस हज़ार से शुरू। होम ऑफिस के लिए है या कमर्शियल स्पेस?"),
    "tv_unit":        (["tv unit","tv cabinet","entertainment unit","lcd unit","tv stand"],
                       "TV यूनिट अठारह हज़ार से शुरू — शीशम वुड भी उपलब्ध। कितने इंच का TV है?"),
    "price_general":  (["price","cost","kitna","rate","dam","kitne ka","how much","kya rate","rate batao","kitne mein"],
                       "फर्नीचर चौदह हज़ार से छह लाख तक — सभी में चालीस प्रतिशत छूट। कौन सा प्रोडक्ट और roughly कितनी रेंज सोच रहे हैं?"),
    "products_general":(["available","kya hai","kya milta","kya kuch","range","catalogue","sab kuch","konsa","products","show me","kya available"],
                        "हमारे पास सोफा, बेड, डाइनिंग सेट, वार्डरोब, ऑफिस फर्नीचर, पर्दे और गद्दे हैं — सभी में चालीस प्रतिशत छूट। किस कमरे के लिए ढूंढ रहे हैं?"),
    "interior":       (["interior","interior design","complete home","decor","curtain","poora ghar"],
                       "हाँ, इंटीरियर सर्विसेज़ भी देते हैं — फर्नीचर, लेआउट, पर्दे सब। नया घर है?"),
    "wholesale":      (["wholesale","bulk","reseller","dealer","distributor"],
                       "हाँ, होलसेल भी करते हैं। कौन सा प्रोडक्ट और कितनी क्वांटिटी? सेल्स टीम से कॉलबैक अरेंज करती हूँ।"),
    "visit":          (["visit","aana chahta","dekhne aana","appointment","kab aa sakta","store visit"],
                       "ज़रूर! कौन से दिन आना चाहेंगे — वीकडे या वीकएंड? मैं स्लॉट नोट कर लेती हूँ।"),
    "installation":   (["installation","install","lagana","setup","assemble"],
                       "फ्री इंस्टॉलेशन मिलती है डिलीवरी के साथ — हमारी टीम सब सेट अप कर देगी।"),
}

SLOT_PATTERNS = {
    "size": {
        "1 seater":  r"\b(1|ek|one).{0,8}(seater|seat)\b",
        "2 seater":  r"\b(2|do|two).{0,8}(seater|seat)\b",
        "3 seater":  r"\b(3|teen|three).{0,8}(seater|seat)\b",
        "6 seater":  r"\b(6|chhah|six).{0,8}(seater|seat)\b",
        "L-shape":   r"\b(l.?shape|l.?type|corner)\b",
        "king size": r"\b(king|king.?size)\b",
    },
    "product": {
        "sofa":     r"\b(sofa|couch|settee|sopha|sofar|so fa)\b",
        "bed":      r"\b(bed|palang)\b",
        "dining":   r"\b(dining)\b",
        "wardrobe": r"\b(wardrobe|almirah|almari|cupboard)\b",
        "office":   r"\b(office|study)\b",
    },
}

PRODUCT_PRICES = {
    ("sofa","1 seater"):  ("₹14,000","₹17,000"),
    ("sofa","2 seater"):  ("₹34,000","₹47,000"),
    ("sofa","3 seater"):  ("₹33,000","₹56,000"),
    ("sofa","L-shape"):   ("₹76,000","₹2,19,000"),
    ("sofa", None):       ("₹14,000","₹2,19,000"),
    ("bed","king size"):  ("₹71,000","₹91,000"),
    ("bed", None):        ("₹71,000","₹91,000"),
    ("dining","6 seater"):("₹1,19,000","₹6,39,000"),
    ("dining", None):     ("₹1,19,000","₹6,39,000"),
    ("wardrobe", None):   ("₹37,000","₹76,000"),
    ("office", None):     ("₹12,000","₹69,000"),
}

NEXT_QUESTIONS = {
    "sofa":    "फैब्रिक चाहिए या सॉलिड वुड फ्रेम?",
    "bed":     "हाइड्रोलिक स्टोरेज चाहिए या पुलआउट?",
    "dining":  "मार्बल टॉप चाहिए या सॉलिड वुड?",
    "wardrobe":"स्लाइडिंग दरवाज़ा चाहिए या hinged?",
    "office":  "कुर्सी भी चाहिए साथ में?",
}

FALLBACK_POOL = [
    "हाँ जी, मैं समझ रही हूँ। यह डिटेल मैं चेक करके आपको बताती हूँ — WhatsApp पर उपलब्ध हैं?",
    "अच्छा जी। मैं यह कन्फर्म करके WhatsApp पर भेजती हूँ। नंबर नोट कर लूँ?",
    "जी ज़रूर, एक सेकंड — मैं यह चेक करके अभी बताती हूँ।",
]
_fallback_idx = 0


def get_response(text: str, session) -> tuple[str, str]:
    global _fallback_idx
    lower = correct_stt(text)
    session.turn_count += 1

    for key, (kws, ans) in OBJECTIONS.items():
        if any(k in lower for k in kws):
            logger.info(f"OBJECTION:{key}")
            return ans, f"objection:{key}"

    for key, (kws, ans) in FAQS.items():
        if any(k in lower for k in kws):
            if key not in session.intents_fired:
                session.intents_fired.add(key)
                logger.info(f"FAQ:{key}")
                return ans, f"faq:{key}"

    found = {}
    for slot_type, patterns in SLOT_PATTERNS.items():
        for label, pattern in patterns.items():
            if re.search(pattern, lower):
                found[slot_type] = label
                break

    if found:
        product = found.get("product") or session.slots.get("product")
        size    = found.get("size")    or session.slots.get("size")
        if product:
            session.slots["product"] = product
        if size:
            session.slots["size"] = size
        price_key = (product, size) if (product, size) in PRODUCT_PRICES else (product, None)
        if price_key in PRODUCT_PRICES:
            lo, hi   = PRODUCT_PRICES[price_key]
            size_str = f"{size} " if size else ""
            pnames   = {"sofa":"सोफा","bed":"बेड","dining":"डाइनिंग सेट","wardrobe":"वार्डरोब","office":"ऑफिस फर्नीचर"}
            pname    = pnames.get(product, product)
            nq       = NEXT_QUESTIONS.get(product, "और कोई preference है?")
            resp     = f"अरे बढ़िया चॉइस! {size_str}{pname} {lo} से {hi} तक उपलब्ध है — ४०% छूट के बाद। {nq}"
            logger.info(f"SLOT:{found}")
            return resp, f"slot:{found}"

    if "product" in found:
        product = found["product"]
        if product == "sofa":
            resp = "सोफा में कई ऑप्शन हैं — २-सीटर ₹३४,००० से, ३-सीटर ₹३३,००० से, L-शेप ₹७६,००० से शुरू। कौन सा साइज़ चाहिए?"
        elif product == "bed":
            resp = "किंग साइज़ बेड विद स्टोरेज ₹७१,००० से शुरू — ४०% छूट के बाद। हाइड्रोलिक स्टोरेज चाहिए या पुलआउट?"
        elif product == "dining":
            resp = "६-सीटर डाइनिंग सेट ₹१,१९,००० से उपलब्ध है। मार्बल टॉप चाहिए या सॉलिड वुड?"
        elif product == "wardrobe":
            resp = "वार्डरोब २-दरवाज़ा ₹३७,००० से, ३-दरवाज़ा ₹४८,००० से। कितनी जगह है बेडरूम में?"
        elif product == "office":
            resp = "ऑफिस फर्नीचर में टेबल ₹१२,००० से और कुर्सी ₹२०,००० से। क्या चाहिए — टेबल, कुर्सी या दोनों?"
        else:
            resp = "यह उपलब्ध है। आपका बजट रेंज क्या है?"
        logger.info(f"PRODUCT_ONLY:{product}")
        return resp, f"product_only:{product}"

    resp = FALLBACK_POOL[_fallback_idx % len(FALLBACK_POOL)]
    _fallback_idx += 1
    logger.info("FALLBACK")
    return resp, "fallback"


# ═════════════════════════════════════════════════════════════════════════════
# CALL SESSION
# ═════════════════════════════════════════════════════════════════════════════

class CallSession:
    def __init__(self, call_uuid: str):
        self.call_uuid         = call_uuid
        self.stream_id         = ""
        self.turn_count        = 0
        self.intents_fired     = set()
        self.conversation      = []
        self.slots             = {}
        self.is_processing     = False
        self.is_priya_speaking = False
        self.barge_frames      = 0
        self.barge_in_pending  = False  # set True by ingest() when barge-in fires; ws_handler consumes it to actually stop playback
        self.audio_buffer      = bytearray()
        self.in_speech         = False
        self.speaking_frames   = 0
        self.silence_frames    = 0
        self.state             = "QUALIFY_PRODUCT"
        self.lead              = {"product": None, "budget": None, "urgency": None}
        self.faq_mode          = False
        self.last_reply        = ""
        self.empty_turns       = 0           # consecutive empty transcripts
        self.greeted           = False
        self.lead_id: str | None = None
        self.lang              = "hinglish"
        self.turn_timestamps   = []          # [(user_end_ts, priya_start_ts), ...]
        self.call_start_ts     = None        # set when first user speech detected
        self.first_reply_ts    = None        # set when Priya sends first audio
        self.user_audio_frames = 0           # total frames customer spoke
        self.priya_audio_frames= 0           # total frames Priya spoke
        self.lang_streak       = 0
        self.campaign          = ""
        self.customer_phone    = ""
        self.customer_name     = ""

    def ingest(self, mulaw_chunk: bytes) -> tuple[bool, bytes | None]:
        pcm       = audioop.ulaw2lin(mulaw_chunk, 2)
        rms       = audioop.rms(pcm, 2)
        is_speech = rms > SILENCE_THRESHOLD

        if self.is_priya_speaking:
            # KNOWN GAP: frames in this branch only ever count toward
            # barge_frames -- they're never appended to audio_buffer, and
            # _reset_vad() below clears whatever's there once BARGE-IN fires.
            # So the ~200ms of speech (BARGE_IN_FRAMES frames) that actually
            # triggers detection never reaches STT; only speech arriving
            # after is_priya_speaking goes back to False gets captured. If a
            # customer's entire utterance lands inside that detection window,
            # it's silently dropped -- confirmed live 2026-07-23 on a
            # reactivation-pilot call (barge-in fired before stt, stt came
            # back empty), though same-shape calls elsewhere in the same
            # pilot got real text, so this alone doesn't explain every empty
            # STT turn -- just a real, structural loss window worth knowing
            # about before touching this logic.
            if is_speech:
                self.barge_frames += 1
                if self.barge_frames >= BARGE_IN_FRAMES:
                    logger.info(f"[{self.call_uuid}] BARGE-IN")
                    self.is_priya_speaking = False
                    self.barge_frames      = 0
                    self.barge_in_pending  = True
                    self._reset_vad()
            else:
                self.barge_frames = max(0, self.barge_frames - 1)
            return False, None

        if is_speech:
            self.in_speech        = True
            self.speaking_frames += 1
            self.silence_frames   = 0
            self.audio_buffer.extend(mulaw_chunk)
        elif self.in_speech:
            self.silence_frames += 1
            self.audio_buffer.extend(mulaw_chunk)
            if self.silence_frames >= TRAILING_SILENCE:
                if self.speaking_frames >= MIN_SPEECH_FRAMES:
                    audio = bytes(self.audio_buffer)
                    self._reset_vad()
                    return True, audio
                else:
                    self._reset_vad()
        return False, None

    def _reset_vad(self):
        self.audio_buffer.clear()
        self.in_speech       = False
        self.speaking_frames = 0
        self.silence_frames  = 0

    def priya_starts_speaking(self, tts_wav: bytes) -> float:
        try:
            with wave.open(io.BytesIO(tts_wav), "rb") as wf:
                duration = wf.getnframes() / wf.getframerate() + 0.3
        except Exception:
            duration = 3.0
        self.is_priya_speaking = True
        self.barge_frames      = 0
        return duration

    def priya_stops_speaking(self):
        self.is_priya_speaking = False
        self.barge_frames      = 0


sessions: dict[str, CallSession] = {}
_session_meta: dict[str, dict] = {}  # tracks direction+to_phone per call


# ─── Audio ────────────────────────────────────────────────────────────────────
def normalize_tts_output(wav_bytes: bytes, target_peak: float = 0.75) -> bytes:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            params = wf.getparams()
            pcm = wf.readframes(wf.getnframes())
        peak = audioop.max(pcm, 2)
        if peak == 0:
            return wav_bytes
        target = int(32767 * target_peak)
        scale = target / peak
        if scale < 1.0:
            pcm = audioop.mul(pcm, 2, scale)
            logger.info(f"TTS normalize: peak={peak} → scaled {scale:.3f}")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setparams(params)
            wf.writeframes(pcm)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"normalize_tts_output error: {e}")
        return wav_bytes

def ulaw_to_wav(ulaw_bytes: bytes) -> bytes:
    pcm = audioop.ulaw2lin(ulaw_bytes, 2)
    pcm = audioop.bias(pcm, 2, 0)
    try:
        rms = audioop.rms(pcm, 2)
        if 0 < rms < 3000:
            pcm = audioop.mul(pcm, 2, min(3000 / rms, 4.0))
    except Exception:
        pass
    pcm, _ = audioop.ratecv(pcm, 2, 1, 8000, 16000, None)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(pcm)
    return buf.getvalue()


# ─── STT ─────────────────────────────────────────────────────────────────────
async def transcribe(wav_bytes: bytes, call_uuid: str = None, turn: int = 0) -> str:
    _t0 = time.time()
    try:
        client = await _get_sarvam_client()
        r = await client.post(
                "https://api.sarvam.ai/speech-to-text",
                headers={"API-Subscription-Key": SARVAM_API_KEY},
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                data={
                    "model": "saaras:v3",
                    "language_code": "hi-IN",
                    "with_timestamps": "false",
                    "with_disfluencies": "false",
                    "prompt": (
                        "Krishna Furniture Gurgaon. Sofa, chair, kursi, bed, palang, "
                        "dining table, wardrobe, almirah. EMI, delivery, offer, discount, "
                        "exchange. Kherki Daula, Bamdoli, Sector 14, Gurugram."
                    ),
                }
            )
        _duration_ms = round((time.time() - _t0) * 1000)
        if r.status_code == 200:
            text = r.json().get("transcript", "").strip()
            if not text:
                logger.info(f"[{call_uuid}] Saaras: empty transcript")
                audit_event(call_uuid, "stt", turn=turn, text="", lang="hi-IN", empty=True, duration_ms=_duration_ms)
                return ""
            logger.info(f"[{call_uuid}] STT → '{text}'")
            audit_event(call_uuid, "stt", turn=turn, text=text, lang="hi-IN", empty=False, duration_ms=_duration_ms)
            return text
        else:
            logger.error(f"[{call_uuid}] Saaras STT {r.status_code}: {r.text[:200]}")
            audit_event(call_uuid, "stt", turn=turn, text="", lang="hi-IN", empty=True, duration_ms=_duration_ms)
            return ""
    except Exception as e:
        logger.error(f"[{call_uuid}] STT error: {e}")
        audit_event(call_uuid, "stt", turn=turn, text="", lang="hi-IN", empty=True, duration_ms=round((time.time() - _t0) * 1000))
        return ""

# ─── TTS ─────────────────────────────────────────────────────────────────────
async def text_to_speech(text: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={
                    "API-Subscription-Key": SARVAM_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "inputs": [text],
                    "target_language_code": "hi-IN",
                    "speaker": "shreya",
                    "pace": 1.05,
                    "speech_sample_rate": 8000,
                    "model": "bulbul:v3"
                }
            )
        if r.status_code == 200:
            data = r.json()
            if data.get("audios"):
                raw_wav = base64.b64decode(data["audios"][0])
                return normalize_tts_output(raw_wav)
        logger.error(f"TTS HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"TTS error: {e}")
    return None

async def save_audio(text: str, filename: str) -> str | None:
    lang = "hi"
    from tts_engine import _make_static_path, _make_url
    greeting_key = "greeting_outbound" if "greeting_out" in filename else "greeting_inbound"
    static_path = _make_static_path(greeting_key, lang)
    if static_path.exists():
        logger.info(f"GREETING STATIC HIT → {static_path.name}")
        return _make_url(static_path)
    static_path_hl = _make_static_path(greeting_key, "hinglish")
    if static_path_hl.exists():
        logger.info(f"GREETING STATIC HIT (hinglish) → {static_path_hl.name}")
        return _make_url(static_path_hl)
    logger.warning("Static greeting missing — generating")
    audio = await text_to_speech(text)
    if audio:
        path = f"{CACHE_DIR}/{filename}.wav"
        with open(path, "wb") as f: f.write(audio)
        return f"{BASE_URL}/audio/{filename}.wav"
    return None


def get_static_audio(source: str) -> tuple[bytes | None, str]:
    path = STATIC_CACHE.get(source)
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read(), f"{BASE_URL}/audio/{os.path.basename(path)}"
    return None, ""


def get_dynamic_audio(reply: str) -> tuple[bytes | None, str]:
    import hashlib
    h = hashlib.md5(reply.strip().encode("utf-8")).hexdigest()[:10]
    path = f"{CACHE_DIR}/dyn_{h}.wav"
    if os.path.exists(path):
        logger.info(f"DYN CACHE HIT → dyn_{h}.wav")
        with open(path, "rb") as f:
            return f.read(), f"{BASE_URL}/audio/dyn_{h}.wav"
    return None, ""


def save_dynamic_audio(reply: str, wav_bytes: bytes) -> str:
    import hashlib
    h = hashlib.md5(reply.strip().encode("utf-8")).hexdigest()[:10]
    path = f"{CACHE_DIR}/dyn_{h}.wav"
    with open(path, "wb") as f:
        f.write(wav_bytes)
    logger.info(f"DYN CACHE SAVED → dyn_{h}.wav")
    return f"{BASE_URL}/audio/dyn_{h}.wav"


# ─── Lead Qualification State Machine ────────────────────────────────────────

PRODUCT_KEYWORDS = {
    "sofa","bed","chair","dining","table","wardrobe","almirah","office",
    "curtain","mattress","palang","kursi","mej","almari","furniture",
    "सोफा","बेड","कुर्सी","डाइनिंग","मेज","टेबल","वार्डरोब","अलमारी",
    "गद्दा","पर्दा","फर्नीचर","चेयर","शेयर",
}

BUDGET_KEYWORDS = {
    "hazaar","lakh","thousand","budget","price","kitna","rate","rupee",
    "50","20","30","40","10","15","25","1","2","3","4","5",
    "हज़ार","लाख","बजट","रुपये","कितने",
}

URGENCY_KEYWORDS = {
    "week","month","mahine","hafte","din","day","jaldi","abhi","asap",
    "urgent","kab","soon","kal","aaj","today","tomorrow","2 din","7 din",
    "हफ्ते","महीने","दिन","जल्दी","अभी","कल","आज","इसी हफ्ते",
}

def extract_product(text: str) -> str | None:
    tl = text.lower()
    for kw in PRODUCT_KEYWORDS:
        if kw in tl:
            deva_map = {
                "सोफा":"sofa","शेयर":"sofa","बेड":"bed","कुर्सी":"chair",
                "चेयर":"chair","डाइनिंग":"dining","मेज":"table","टेबल":"table",
                "वार्डरोब":"wardrobe","अलमारी":"wardrobe","गद्दा":"mattress",
                "पर्दा":"curtain","फर्नीचर":"furniture",
            }
            return deva_map.get(kw, kw)
    return None

def extract_budget(text: str) -> str | None:
    tl = text.lower()
    # Convert Hindi number words to digits before regex
    _WMAP = {
        "ek":"1","do":"2","teen":"3","char":"4","paanch":"5","chhe":"6",
        "saat":"7","aath":"8","nau":"9","das":"10","gyarah":"11","barah":"12",
        "terah":"13","chaudah":"14","pandrah":"15","solah":"16","satrah":"17",
        "atharah":"18","unnis":"19","bees":"20","tees":"30","chalis":"40",
        "pachaas":"50","saath":"60","sattar":"70","assi":"80","nabbe":"90",
        "एक":"1","दो":"2","तीन":"3","चार":"4","पाँच":"5","पांच":"5",
        "छह":"6","सात":"7","आठ":"8","नौ":"9","दस":"10","बीस":"20",
        "तीस":"30","चालीस":"40","पचास":"50","साठ":"60","सत्तर":"70",
        "सत्रह":"70","अस्सी":"80","नब्बे":"90","डेढ":"1.5","ढाई":"2.5","साढ़े":"1.5","sadhe":"1.5","dedh":"1.5","aadha":"0.5",
    }
    for w, d in _WMAP.items():
        tl = tl.replace(w, d)
    # Range: '60 se 70 hazaar', '1 se 2 lakh', '60 से 70 हजार' — take higher bound
    range_m = re.search(
        r'(\d[\d,]*)\s*(?:se|to|से|-)\s*(\d[\d,]*)\s*'
        r'(hazaar|hazar|हज़ार|हजार|lakh|लाख|k\b|thousand)?', tl)
    if range_m:
        num = range_m.group(2).replace(",","")
        unit = range_m.group(3) or ""
        if unit in ("hazaar","hazar","हज़ार","हजार","k","thousand"): return f"₹{num},000"
        elif unit in ("lakh","लाख"): return f"₹{num},00,000"
        elif len(num) >= 4: return f"₹{num}"
    # Single number
    m = re.search(r'(\d[\d,]*)\s*(hazaar|hazar|हज़ार|हजार|lakh|लाख|k\b|thousand)?', tl)
    if m:
        num = m.group(1).replace(",","")
        unit = m.group(2) or ""
        if unit in ("hazaar","hazar","हज़ार","हजार","k","thousand"): return f"₹{num},000"
        elif unit in ("lakh","लाख"): return f"₹{num},00,000"
        elif len(num) >= 4: return f"₹{num}"
    for kw in BUDGET_KEYWORDS:
        if kw in tl and kw not in {"kitna","rate","price","budget","बजट","कितने"}:
            return tl.strip()
    return None

def extract_urgency(text: str) -> str | None:
    tl = text.lower()
    for kw in URGENCY_KEYWORDS:
        if kw in tl:
            return text.strip()
    return None

def state_machine(text_fixed: str, text_raw: str, session, call_uuid: str) -> tuple[str | None, str]:
    session.turn_count += 1
    state = session.state

    # Absolute safety net, independent of not_understood_streak/_total and of
    # state — a call stuck looping any branch (faq_mode included) for 25 turns
    # forces the same DONE/goodbye/hangup path rather than running unbounded.
    if session.turn_count >= 25:
        session.state = "DONE"
        reply = "ठीक है सर, अभी के लिए इतना ही। मैं WhatsApp पर details भेज देती हूँ, आराम से देख लीजिएगा। धन्यवाद!"
        session.conversation.append(("user", text_raw))
        session.conversation.append(("assistant", reply))
        return reply, "turn_cap_close"

    # Second, independent safety net: >180s elapsed with zero real
    # (non-IVR-fragment) customer speech. Turn-count alone isn't reliable
    # when turns are short — the react_a "Rajni" call (919910566742,
    # 2026-07-25) ran 370 turns / 2731s against a carrier hold-loop before
    # any turn cap existed on that handler. turn_count_substantive is only
    # incremented on real (fragment-filtered) speech, so 0 here means every
    # turn so far was silence or an IVR fragment.
    if getattr(session, "turn_count_substantive", 0) == 0:
        _started = getattr(session, "started_at", None)
        if _started:
            try:
                _elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(_started)).total_seconds()
            except ValueError:
                _elapsed = 0
            if _elapsed > 180:
                session.state = "DONE"
                reply = "ठीक है सर, अभी के लिए इतना ही। मैं WhatsApp पर details भेज देती हूँ, आराम से देख लीजिएगा। धन्यवाद!"
                session.conversation.append(("user", text_raw))
                session.conversation.append(("assistant", reply))
                return reply, "duration_cap_close"

    # IVR/voicemail fragment check — same phonetic-Devanagari pattern match
    # every webhook_reactivation.py handler already uses, applied once per
    # turn ahead of state/faq_mode dispatch so it covers every state fresh_lead
    # can be in, not just QUALIFY_PRODUCT (where the one confirmed incident
    # happened, but nothing state-specific makes it QUALIFY_PRODUCT-only).
    # Withholds the reply (state_machine's equivalent of returning True to
    # keep listening) instead of attempting product/budget extraction or FAQ
    # matching against carrier-hold gibberish.
    from webhook_reactivation import _is_ivr_fragment
    if text_fixed and _is_ivr_fragment(text_fixed):
        logger.info(f"[{call_uuid}] state={state} IVR/voicemail fragment detected transcript='{text_fixed[:60]}' — withholding reply, marker=ivr_fragment_detected")
        session.ivr_fragment_count = getattr(session, "ivr_fragment_count", 0) + 1
        session.conversation.append(("user", text_raw))
        return None, "ivr_fragment_detected"

    if session.faq_mode:
        reply, source = kb_response(text_fixed, session)
        if source in ("noise", "ack"):
            return None, "noise"
        if source == "product" or reply is None:
            return llm_reply(text_fixed, session, call_uuid)
        if reply:
            session.conversation.append(("user", text_raw))
            session.conversation.append(("assistant", reply))
        return reply, source

    if state == "QUALIFY_PRODUCT":
        # If customer is just saying ack words (हाँ जी, हेलो) and we haven't asked product yet
        # proactively ask instead of staying silent
        tl_ack_check = text_fixed.lower().strip(".,!? ।")
        pure_greeting = tl_ack_check in {
            "हेलो","hello","हाँ","हां","जी","हाँ जी","हां जी","बोलिए",
            "हाँ बोलिए","हाँ जी बोलिए","ji","haan","han","ha","hello","hi"
        }
        if pure_greeting and session.turn_count <= 3:
            reply = "आप किस तरह का फर्नीचर देखना चाहते हैं — सोफा, बेड, डाइनिंग, वार्डरोब, या कुछ और?"
            session.conversation.append(("user", text_raw))
            session.conversation.append(("assistant", reply))
            return reply, "ask_product"
        # Early negative on outbound — customer says not interested before giving product
        tl_early = text_fixed.lower()
        early_exit = {"nahi chahiye","not interested","zaroorat nahi","mat karo","band karo",
                      "नहीं चाहिए","ज़रूरत नहीं","मत करो","बंद करो","no thanks","nope"}
        if any(s in tl_early for s in early_exit):
            already = getattr(session, "early_recovery_tried", False)
            if not already:
                session.early_recovery_tried = True
                reply = "जी समझ गई, कोई बात नहीं। बस एक बात — हम pan-India delivery करते हैं और installation भी free है। WhatsApp पर कुछ options भेज दूँ बस एक बार देखने के लिए?"
                session.conversation.append(("user", text_raw))
                session.conversation.append(("assistant", reply))
                return reply, "hook_negative_1"
            else:
                session.state = "DONE"
                reply = "बिल्कुल, आपका समय लेने के लिए माफ़ी। जब भी ज़रूरत हो — Krishna Furniture हमेशा यहाँ है। आपका दिन शुभ हो!"
                session.conversation.append(("user", text_raw))
                session.conversation.append(("assistant", reply))
                return reply, "hook_negative_2"
        product = extract_product(text_fixed) or extract_product(text_raw)
        if product:
            session.not_understood_streak = 0
            session.lead["product"] = product
            session.slots["product"] = product
            session.state = "QUALIFY_BUDGET"
            logger.info(f"[{call_uuid}] LEAD product={product}")
            # Set ack — specific for single product, generic for multiple
            _ack_map = {"sofa":"ack_sofa","bed":"ack_bed","dining":"ack_dining",
                        "wardrobe":"ack_wardrobe","office":"ack_office",
                        "chair":"ack_office","almirah":"ack_wardrobe",
                        "table":"ack_dining","mattress":"ack_bed"}
            _tl = text_fixed.lower()
            _multi = sum(1 for p in ["sofa","bed","dining","wardrobe","office",
                         "सोफा","बेड","डाइनिंग","वार्डरोब"] if p in _tl)
            session.pending_ack = "ack_general" if _multi > 1 else _ack_map.get(product, "ack_general")
            reply = "Budget में roughly कितना सोच रहे हैं — कोई idea हो तो बताइए?"
            session.conversation.append(("user", text_raw))
            session.conversation.append(("assistant", reply))
            return reply, "qualify_budget"
        else:
            # Off-script detour: try FAQ/intent match before treating this as
            # "product not understood". Doesn't touch state — qualification
            # resumes on the next turn as if this turn was a detour.
            faq_reply, faq_id = match_faq_detour(text_fixed, session)
            if faq_reply:
                session.not_understood_streak = 0
                session.conversation.append(("user", text_raw))
                session.conversation.append(("assistant", faq_reply))
                return faq_reply, f"faq:{faq_id}"
            # Product not understood — clarify warmly, re-ask once, then close.
            # Uncapped before this: a caller whose audio is never intelligible
            # (carrier hold/IVR bleed-through, background noise) would get the
            # same "not_understood" line forever with no escalation — confirmed
            # live as a 506s/51-turn call that never hung up. 3 consecutive
            # misses closes the call gracefully instead, via the same
            # state="DONE" auto-hangup hook WRAP_UP's goodbye already uses
            # (webhook.py respond(), ~1269) — not a new mechanism.
            already_asked = getattr(session, "product_ask_count", 0)
            session.product_ask_count = already_asked + 1
            session.not_understood_streak = getattr(session, "not_understood_streak", 0) + 1
            # not_understood_total mirrors the streak but is NEVER reset by the
            # match_faq_detour branches above — confirmed live (call
            # aa747696-c47a-4b9c-b2d4-4cfbd588a60e, 51 turns) that a caller
            # alternating between "not understood" and an FAQ-detour hit keeps
            # resetting the streak to 0 forever, so it never reaches 3. This
            # counter closes that gap independent of the streak.
            session.not_understood_total = getattr(session, "not_understood_total", 0) + 1
            if session.not_understood_streak >= 3 or session.not_understood_total >= 5:
                session.state = "DONE"
                reply = "ठीक है सर, लगता है अभी लाइन साफ़ नहीं आ रही। मैं WhatsApp पर details भेज देती हूँ, आराम से देख लीजिएगा। धन्यवाद!"
                source = "not_understood_close"
            elif already_asked >= 1:
                reply = "माफ़ करना, समझ नहीं पाई — sofa, bed, dining, wardrobe, कौन सा देखना है?"
                source = "not_understood"
            else:
                reply = "आप किस तरह का फर्नीचर देखना चाहते हैं — सोफा, बेड, डाइनिंग, वार्डरोब, या कुछ और?"
                source = "ask_product"
            session.conversation.append(("user", text_raw))
            session.conversation.append(("assistant", reply))
            return reply, source

    elif state == "QUALIFY_BUDGET":
        product = extract_product(text_fixed) or extract_product(text_raw)
        if product and not session.lead["product"]:
            session.lead["product"] = product
            session.slots["product"] = product
        elif product and product != session.lead.get("product"):
            # Caller switched product mid-flow — ack and update silently, don't break flow
            old_product = session.lead.get("product", "furniture")
            session.lead["product"] = product
            session.slots["product"] = product
            logger.info(f"[{call_uuid}] Product switched {old_product} → {product} during QUALIFY_BUDGET")
        budget = extract_budget(text_fixed) or extract_budget(text_raw)
        if not budget:
            # Off-script detour: try FAQ/intent match before treating this as a
            # vague/not-understood budget answer. State stays QUALIFY_BUDGET.
            faq_reply, faq_id = match_faq_detour(text_fixed, session)
            if faq_reply:
                session.not_understood_streak = 0
                session.conversation.append(("user", text_raw))
                session.conversation.append(("assistant", faq_reply))
                return faq_reply, f"faq:{faq_id}"
        if budget:
            session.not_understood_streak = 0
            session.lead["budget"] = budget.strip(".,!? ।")
            session.slots["budget"] = budget.strip(".,!? ।")
            session.state = "QUALIFY_URGENCY"
            logger.info(f"[{call_uuid}] LEAD budget={budget}")
            reply = "और कब तक चाहिए — कोई जल्दी है, या अभी देख रहे हैं बस?"
            session.urgency_lang_override = "hinglish"  # always use hinglish audio
        else:
            # Vague answer like "लगभग", "roughly" — apologise then re-ask, then
            # close. Same not_understood_streak cap as QUALIFY_PRODUCT above —
            # shared across states because it's tracking "can we understand
            # this caller at all right now", not a per-state count.
            vague_words = {"लगभग","lagbhag","roughly","almost","करीब","तकरीबन","शायद","pata nahi","nahi pata","hmm","hm","umm","uhh"}
            tl_check = text_fixed.lower().strip(".,!? ।")
            if any(v in tl_check for v in vague_words) or len(tl_check.split()) <= 1:
                session.not_understood_streak = getattr(session, "not_understood_streak", 0) + 1
                # not_understood_total — same never-reset counter as
                # QUALIFY_PRODUCT above, shared across states.
                session.not_understood_total = getattr(session, "not_understood_total", 0) + 1
                if session.not_understood_streak >= 3 or session.not_understood_total >= 5:
                    session.state = "DONE"
                    reply = "ठीक है सर, लगता है अभी लाइन साफ़ नहीं आ रही। मैं WhatsApp पर details भेज देती हूँ, आराम से देख लीजिएगा। धन्यवाद!"
                    source = "not_understood_close"
                else:
                    reply = "माफ़ करना, ठीक से समझ नहीं पाई — budget roughly कितना सोच रहे हैं?"
                    source = "not_understood_budget"
                session.conversation.append(("user", text_raw))
                session.conversation.append(("assistant", reply))
                return reply, source
            session.not_understood_streak = 0
            reply = "Budget rough idea भी चलेगा — जैसे ₹२०,००० से ₹५०,००० या इससे ऊपर?"
        session.conversation.append(("user", text_raw))
        session.conversation.append(("assistant", reply))
        return reply, "qualify_urgency" if budget else "ask_budget"

    elif state == "QUALIFY_URGENCY":
        urgency = extract_urgency(text_fixed) or extract_urgency(text_raw)
        if not urgency:
            # Off-script detour: try FAQ/intent match before falling back to
            # accepting the raw utterance as the urgency answer verbatim.
            faq_reply, faq_id = match_faq_detour(text_fixed, session)
            if faq_reply:
                session.conversation.append(("user", text_raw))
                session.conversation.append(("assistant", faq_reply))
                return faq_reply, f"faq:{faq_id}"
            urgency = text_raw.strip()
        session.lead["urgency"] = urgency.strip(".,!? ।")
        session.slots["urgency"] = urgency.strip(".,!? ।")
        session.state = "WRAP_UP"
        logger.info(f"[{call_uuid}] LEAD urgency={urgency} | LEAD COMPLETE: {session.lead}")
        product_raw = session.lead.get("product", "furniture")
        wrap_key_map = {
            "sofa":     "wrap_up_sofa",
            "bed":      "wrap_up_bed",
            "dining":   "wrap_up_dining",
            "office":   "wrap_up_office",
            "chair":    "wrap_up_office",
            "wardrobe": "wrap_up_general",
            "almirah":  "wrap_up_general",
            "table":    "wrap_up_dining",
            "curtain":  "wrap_up_general",
            "mattress": "wrap_up_bed",
        }
        wrap_key = wrap_key_map.get(product_raw, "wrap_up_general")
        from tts_engine import STATIC_RESPONSES
        lang = getattr(session, "lang", "hi")
        reply = STATIC_RESPONSES.get(wrap_key, {}).get(lang) or STATIC_RESPONSES.get(wrap_key, {}).get("hi", "बिल्कुल! WhatsApp पर options भेज रही हूँ।")
        logger.info(f"[{call_uuid}] WRAP_UP key={wrap_key} lang={lang}")
        session.conversation.append(("user", text_raw))
        session.conversation.append(("assistant", reply))
        return reply, wrap_key

    elif state == "WRAP_UP":
        tl = text_fixed.lower()

        # ── Objection: expensive / online cheaper ──────────────────────────
        expensive_signals = {"mehnga","costly","expensive","sasta","online","amazon","flipkart",
                             "महंगा","सस्ता","ऑनलाइन","कम budget","budget nahi"}
        if any(s in tl for s in expensive_signals):
            session.state = "FAQ_MODE"
            session.faq_mode = True
            reply = "सर, online में जो दिखता है वो quality और जो मिलता है वो quality — दोनों अलग होती हैं। हमारे अपने manufacturing plants हैं, आपको सीधे factory price देते हैं। Photos देखिए एक बार, फिर compare कीजिए खुद।"
            session.conversation.append(("user", text_raw))
            session.conversation.append(("assistant", reply))
            return reply, "obj_online_wrapup"

        # ── Objection: need to think / not sure ───────────────────────────
        think_signals = {"sochna","sochu","soch","think","zaroorat nahi","baad mein",
                         "sochenge","dekhenge","pata nahi","확인","सोचना","बाद में","ज़रूरत नहीं","देखेंगे"}
        if any(s in tl for s in think_signals):
            session.state = "FAQ_MODE"
            session.faq_mode = True
            reply = "बिल्कुल सोचिए! बस एक बात — यह sale महीने के अंत तक ही है और कुछ designs की limited pieces बची हैं। WhatsApp पर photos देख लीजिए, फिर decide करिए — कोई pressure नहीं!"
            session.conversation.append(("user", text_raw))
            session.conversation.append(("assistant", reply))
            return reply, "obj_think_wrapup"

        # ── Goodbye signals: first attempt → try recovery ─────────────────
        goodbye_signals = {"nahi","no","nope","shukriya","thanks","bye","band karo",
                          "नहीं","शुक्रिया","बस","bas","rehne do","theek hai","enough",
                          "ok thank you","okay thank you","oke thank you",
                          "ओके थैंक यू","ओके, थैंक यू","थैंक यू","thanks bye",
                          "thank you","shukriya","dhanyawad","धन्यवाद","शुक्रिया"}
        hard_exit = getattr(session, "recovery_tried", False)
        lead_complete = all(session.lead.get(k) for k in ["product","budget","urgency"])
        if any(g in tl for g in goodbye_signals) or len(tl.split()) <= 2:
            if lead_complete or hard_exit:
                # Lead complete or second goodbye → warm exit directly
                session.state = "DONE"
                reply = "बहुत बहुत शुक्रिया! आपसे बात करके अच्छा लगा। WhatsApp पर options भेज दिए हैं — ज़रूर देखिएगा। आपका दिन शानदार हो!"
                session.conversation.append(("user", text_raw))
                session.conversation.append(("assistant", reply))
                return reply, "goodbye_warm"
            else:
                # Lead incomplete, first goodbye → soft recovery
                session.recovery_tried = True
                reply = "जी समझ गई! बस WhatsApp पर कुछ options भेज देती हूँ — कभी भी देखिएगा, कोई pressure नहीं।"
                session.conversation.append(("user", text_raw))
                session.conversation.append(("assistant", reply))
                return reply, "obj_busy"

        # ── Positive / question → FAQ mode ────────────────────────────────
        session.faq_mode = True
        session.state = "FAQ_MODE"
        kb_reply, kb_source = kb_response(text_fixed, session)
        if kb_reply:
            reply = kb_reply
            source = kb_source
        else:
            reply, source = llm_reply(text_fixed, session, call_uuid)
            source = source or "llm"
        session.conversation.append(("user", text_raw))
        session.conversation.append(("assistant", reply or ""))
        return reply, source

    logger.warning(
        f"[{call_uuid}] STATE FALLTHROUGH — no branch produced a reply | "
        f"session={session.call_uuid} | state={state} | "
        f"text_raw={text_raw!r} | text_fixed={text_fixed!r}"
    )
    return llm_reply(text_fixed, session, call_uuid)


_LLM_SAFE_FALLBACK = "एक सेकंड, मैं चेक करके बताती हूँ।"

# Appended to the system prompt only on the retry after a grounding
# rejection — the base prompt's "NEVER make up prices" instruction alone did
# not stop the model (confirmed live: call 50845de5 fabricated "₹33,000" for
# a product not in the knowledge base). This is more forceful and names the
# exact failure mode, since a generic instruction wasn't enough on its own.
_LLM_GROUNDING_RETRY_SUFFIX = f"""

IMPORTANT: आपका पिछला जवाब एक ऐसी कीमत बता रहा था जो STORE KNOWLEDGE में कहीं नहीं है — यह गलत जानकारी है।
Is baar koi bhi specific ₹ price mat bolo jab tak woh EXACTLY STORE KNOWLEDGE section mein likhi na ho.
Agar exact price pata nahi hai, sirf yeh bolo: "{_LLM_SAFE_FALLBACK}" — koi number mat banao."""


def _call_groq(text: str, session, call_uuid: str, context: str) -> str:
    llm = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": context},
            *[{"role": r, "content": c} for r, c in session.conversation[-6:]],
            {"role": "user", "content": text}
        ],
        max_tokens=60,
        temperature=0.2,
    )
    return llm.choices[0].message.content.strip()


def llm_reply(text: str, session, call_uuid: str) -> tuple[str | None, str]:
    try:
        base_context = build_llm_context()
        context = build_multilingual_llm_system_prompt(session, base_context)
        if session.last_reply:
            context += f"\n\nमैंने अभी कहा: '{session.last_reply}'"

        reply = _call_groq(text, session, call_uuid, context)

        if reply_has_ungrounded_price(reply):
            logger.warning(f"[{call_uuid}] LLM GROUNDING REJECTED (attempt 1) — unverified price in: '{reply[:100]}' — retrying")
            retry_reply = _call_groq(text, session, call_uuid, context + _LLM_GROUNDING_RETRY_SUFFIX)
            if reply_has_ungrounded_price(retry_reply):
                logger.warning(f"[{call_uuid}] LLM GROUNDING REJECTED (attempt 2) — unverified price in: '{retry_reply[:100]}' — falling back to safe line")
                reply = _LLM_SAFE_FALLBACK
                session.conversation.append(("user", text))
                session.conversation.append(("assistant", reply))
                return reply, "fallback_ungrounded"
            reply = retry_reply
            logger.info(f"[{call_uuid}] LLM grounding retry passed → '{reply[:60]}'")

        session.conversation.append(("user", text))
        session.conversation.append(("assistant", reply))
        logger.info(f"[{call_uuid}] LLM → '{reply[:60]}'")
        return reply, "llm"
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return _LLM_SAFE_FALLBACK, "fallback_llm"


# ─── Play Audio Helper ────────────────────────────────────────────────────────
async def _fire_followup_wa(call_uuid: str, name: str, phone: str):
    """Fire WhatsApp for followup_wa campaign after short delay for audio to play."""
    await asyncio.sleep(15)  # wait for message to finish playing
    try:
        phone_clean = phone.replace("+", "").strip()
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                "https://n8n-production-aed7.up.railway.app/webhook/voice-call-complete",
                json={"phone": phone_clean, "name": name, "campaign": "followup_wa"}
            )
        logger.info(f"[{call_uuid}] Followup WA fired → {r.status_code} phone={phone_clean}")
    except Exception as e:
        logger.error(f"[{call_uuid}] Followup WA error: {e}")

async def play_audio_url(call_uuid: str, audio_url: str, turn: int = 0, kind: str = "reply") -> bool:
    _t0 = time.time()
    audit_event(call_uuid, "play_issue", turn=turn, audio_url=audio_url, kind=kind)
    try:
        client = await _get_vobiz_client()
        r = await asyncio.wait_for(
            client.post(
                f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/Play/",
                headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK,
                         "Content-Type": "application/json"},
                json={"urls": [audio_url], "legs": "aleg", "mix": False}
            ),
            timeout=3.0
        )
        _elapsed = time.time() - _t0
        logger.info(f"[{call_uuid}] Play → {r.status_code} | {_elapsed:.2f}s | {audio_url}")
        audit_event(call_uuid, "play_result", turn=turn, status_code=r.status_code, elapsed_ms=round(_elapsed * 1000), kind=kind)
        return r.status_code in (200, 202)
    except asyncio.TimeoutError:
        _elapsed = time.time() - _t0
        logger.warning(f"[{call_uuid}] Play TIMEOUT after {_elapsed:.2f}s → {audio_url}")
        audit_event(call_uuid, "play_timeout", turn=turn, elapsed_ms=round(_elapsed * 1000), kind=kind, audio_url=audio_url)
        return True
    except Exception as e:
        logger.error(f"[{call_uuid}] play_audio_url error: {type(e).__name__}: {e}")
        _elapsed = time.time() - _t0
        audit_event(call_uuid, "play_result", turn=turn, status_code=None, elapsed_ms=round(_elapsed * 1000), kind=kind, error=type(e).__name__)
        global _vobiz_http_client
        if isinstance(e, (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
            logger.warning(f"[{call_uuid}] resetting vobiz client due to {type(e).__name__}")
            _vobiz_http_client = None
        return False


async def _hold_then_stop_speaking(session: "CallSession") -> None:
    """
    react_a/b/c, call2/3, followup_wa and fresh_cta turns play their
    reply/replies as fire-and-forget background POSTs (see webhook_reactivation
    ._vobiz_play) rather than the fresh-lead pipeline's awaited
    play_audio_url + asyncio.sleep(duration) + priya_stops_speaking(). Without
    this, is_priya_speaking flipped back to False the instant the turn handler
    returned control -- near-instantly, since nothing awaits the actual
    playback anymore -- while the real clip could still be playing for
    several more seconds (ra_offer_main alone is 15.4s), leaving barge-in
    detection off for nearly the whole reply. play_key() accumulates the real
    duration of every clip it plays onto session.turn_audio_duration each
    turn; this holds is_priya_speaking True for that long before clearing it,
    same protection window the fresh-lead pipeline gets from awaiting its own
    play + sleep(duration).
    """
    hold = getattr(session, "turn_audio_duration", 0.0)
    if hold > 0:
        await asyncio.sleep(hold + 0.3)
    session.is_priya_speaking = False


# ─── Core Respond Pipeline ────────────────────────────────────────────────────
async def respond(ws: WebSocket, session: CallSession, audio: bytes, call_uuid: str):
    session.is_processing = True
    t0 = time.time()
    # Captured once per turn so every audit_event this respond() call emits
    # (stt/play_issue/play_result here, plus route/tts/turn_end inside
    # whichever handler this dispatches to) reports the SAME turn number —
    # session.turn_count itself isn't incremented until inside state_machine()
    # or the react handlers, well after some of these events already fired.
    session.turn_idx = getattr(session, "turn_count", 0) + 1
    try:
        # ── Fire filler PRE-STT for reactivation — customer hears instantly
        # (skipped for call_cycle 2/3 — those use their own script regardless
        # of what session.campaign says, and this filler is keyed off campaign)
        if session.campaign in ("reactivation", "react_a", "react_b", "react_c") and getattr(session, "call_cycle", None) not in ("2", "3"):
            import random as _random
            _react_st = getattr(session, "react_state", "GREETING")
            _filler_map = {"GREETING": [2, 6], "PRESENT_OFFER": [3, 4], "WHATSAPP_CTA": [1, 5], "CLOSE": [3, 6]}
            _filler_n = _random.choice(_filler_map.get(_react_st, [1, 2, 3]))
            if session.campaign in ("react_a", "react_b", "react_c"):
                from knowledge_react_abc import get_prefix as _get_prefix
                _filler_prefix = _get_prefix(session.campaign)
                _filler_url = f"{BASE_URL}/audio/static/{_filler_prefix}_filler_{_filler_n}_hi.wav"
            else:
                _filler_url = f"{BASE_URL}/audio/static/react_filler_{_filler_n}_hi.wav"
            asyncio.create_task(play_audio_url(call_uuid, _filler_url, turn=session.turn_idx, kind="filler"))
            session.is_priya_speaking = True
            logger.info(f"[{call_uuid}] PRE-STT filler fired → {_filler_url}")
        text = await transcribe(ulaw_to_wav(audio), call_uuid=call_uuid, turn=session.turn_idx)

        # ── call_cycle 2/3 override — takes priority over campaign routing ─────
        # fresh_cta is the one exception: it has its own call_cycle-aware
        # greeting (see /answer-outbound) but IDENTICAL turn logic across all
        # 3 cycles (handle_fresh_cta_turn) — so it deliberately skips this
        # override and falls through to the campaign=="fresh_cta" dispatch
        # below, same as call_cycle 1. Every other campaign is unaffected.
        if getattr(session, "call_cycle", None) == "2" and session.campaign != "fresh_cta":
            from webhook_reactivation import handle_call2_turn
            should_continue = await handle_call2_turn(session, text or "", call_uuid)
            await _hold_then_stop_speaking(session)
            if not should_continue:
                try:
                    async with httpx.AsyncClient(timeout=8) as hc:
                        await hc.delete(
                            f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/",
                            headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK},
                        )
                    logger.info(f"[{call_uuid}] Call2 hangup sent")
                except Exception as he:
                    logger.error(f"[{call_uuid}] Call2 hangup error: {he}")
            return
        elif getattr(session, "call_cycle", None) == "3" and session.campaign != "fresh_cta":
            from webhook_reactivation import handle_call3_turn
            should_continue = await handle_call3_turn(session, text or "", call_uuid)
            await _hold_then_stop_speaking(session)
            if not should_continue:
                try:
                    async with httpx.AsyncClient(timeout=8) as hc:
                        await hc.delete(
                            f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/",
                            headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK},
                        )
                    logger.info(f"[{call_uuid}] Call3 hangup sent")
                except Exception as he:
                    logger.error(f"[{call_uuid}] Call3 hangup error: {he}")
            return

        # ── Reactivation campaign: all turn logic lives in the engine ──────────
        if session.campaign == "followup_wa":
            from webhook_reactivation import handle_followup_wa_turn
            should_continue = await handle_followup_wa_turn(session, text or "", call_uuid)
            await _hold_then_stop_speaking(session)
            if not should_continue:
                try:
                    async with httpx.AsyncClient(timeout=8) as hc:
                        await hc.delete(
                            f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/",
                            headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK},
                        )
                except Exception as he:
                    logger.error(f"[{call_uuid}] Followup hangup error: {he}")
            return
        if session.campaign in ("reactivation", "react_a", "react_b", "react_c"):
            from webhook_reactivation import handle_reactivation_turn, play_key
            should_continue = await handle_reactivation_turn(session, text or "", call_uuid)
            await _hold_then_stop_speaking(session)
            if not should_continue:
                try:
                    async with httpx.AsyncClient(timeout=8) as hc:
                        await hc.delete(
                            f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/",
                            headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK},
                        )
                    logger.info(f"[{call_uuid}] React hangup sent")
                except Exception as he:
                    logger.error(f"[{call_uuid}] React hangup error: {he}")
            return
        if session.campaign == "fresh_cta":
            from webhook_reactivation import handle_fresh_cta_turn
            should_continue = await handle_fresh_cta_turn(session, text or "", call_uuid)
            await _hold_then_stop_speaking(session)
            if not should_continue:
                try:
                    async with httpx.AsyncClient(timeout=8) as hc:
                        await hc.delete(
                            f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/",
                            headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK},
                        )
                    logger.info(f"[{call_uuid}] Fresh CTA hangup sent")
                except Exception as he:
                    logger.error(f"[{call_uuid}] Fresh CTA hangup error: {he}")
            return
        # ── End reactivation routing ────────────────────────────────────────────

        if not text or len(text.strip()) < 2:
            session.empty_turns += 1
            logger.info(f"[{call_uuid}] Empty transcript — skip (#{session.empty_turns})")
            if session.empty_turns >= 3 and session.state in ("WRAP_UP", "DONE"):
                logger.info(f"[{call_uuid}] 3 empty turns in {session.state} — auto-hangup")
                try:
                    async with httpx.AsyncClient(timeout=8) as hc:
                        r = await hc.delete(
                            f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/",
                            headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK}
                        )
                    logger.info(f"[{call_uuid}] Silence auto-hangup → {r.status_code}")
                except Exception as he:
                    logger.error(f"[{call_uuid}] Silence auto-hangup error: {he}")
            return
            return

        session.empty_turns = 0  # reset on real speech

        # Keep turn_count_substantive fragment-aware — same phonetic-Devanagari
        # IVR/voicemail pattern check every webhook_reactivation.py handler
        # already uses. fresh_lead never had this: the +919262102426
        # 51-turn/506s incident (2026-07-12) ran entirely in QUALIFY_PRODUCT
        # because carrier hold-loop fragments occasionally matched
        # extract_product()/FAQ-detour keywords, resetting not_understood_streak
        # turn after turn. Only skips this counter here — the actual
        # withhold-reply behavior lives in state_machine() (checked there,
        # right after the turn/duration caps, so it still applies to every
        # state and can't let a pure fragment loop dodge either cap by never
        # reaching state_machine() at all).
        from webhook_reactivation import _is_ivr_fragment
        if not _is_ivr_fragment(text):
            session.turn_count_substantive = getattr(session, "turn_count_substantive", 0) + 1
        turn_lang = detect_lang(text)
        if not hasattr(session, "lang"):
            session.lang = turn_lang
            session.lang_streak = 1
        elif turn_lang == session.lang:
            session.lang_streak = getattr(session, "lang_streak", 0) + 1
        else:
            session.lang = turn_lang
            session.lang_streak = 1

        logger.info(f"[{call_uuid}] STT [{session.lang}] → '{text}'")

        from knowledge import ACK_WORDS, is_noise, fix_stt
        if is_noise(text):
            logger.info(f"[{call_uuid}] NOISE — skip")
            return
        stripped = text.strip(".,!? \u0964")
        if stripped.lower() in ACK_WORDS or stripped in ACK_WORDS:
            if session.state == "WRAP_UP":
                # ACK after wrap-up = caller is done — play goodbye and hang up
                logger.info(f"[{call_uuid}] ACK after WRAP_UP → goodbye_warm + auto-hangup")
                session.state = "DONE"
                from tts_engine import STATIC_RESPONSES
                lang = getattr(session, "lang", "hi")
                reply = STATIC_RESPONSES.get("goodbye_warm", {}).get(lang) or "बहुत बहुत शुक्रिया! आपका दिन शानदार हो!"
                wav, audio_url, was_cached = await get_speech(reply, lang, "goodbye_warm")
                if audio_url:
                    await play_audio_url(call_uuid, audio_url, turn=session.turn_idx)
                    dur = session.priya_starts_speaking(wav) if wav else 2.0
                    await asyncio.sleep(dur + 1.0)
                    session.priya_stops_speaking()
                    try:
                        async with httpx.AsyncClient(timeout=8) as hc:
                            r = await hc.delete(
                                f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/",
                                headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK}
                            )
                        logger.info(f"[{call_uuid}] Auto-hangup → {r.status_code}")
                    except Exception as he:
                        logger.error(f"[{call_uuid}] Auto-hangup error: {he}")
                return
            from tts_engine import STATIC_RESPONSES
            audio_lang = getattr(session, "lang", "hi")
            reask_key = None
            if session.state == "QUALIFY_PRODUCT":
                reask_key = "qualify_product"
            elif session.state == "QUALIFY_BUDGET":
                reask_key = "qualify_budget"
            elif session.state == "QUALIFY_URGENCY":
                reask_key = "qualify_urgency"
                audio_lang = "hinglish"  # always hinglish for urgency
            if reask_key:
                logger.info(f"[{call_uuid}] ACK in {session.state} → re-ask {reask_key}")
                reply = STATIC_RESPONSES.get(reask_key, {}).get(audio_lang) or STATIC_RESPONSES.get(reask_key, {}).get("hi", "")
                wav, audio_url, was_cached = await get_speech(reply, audio_lang, reask_key)
                if audio_url:
                    await play_audio_url(call_uuid, audio_url, turn=session.turn_idx)
                return
            logger.info(f"[{call_uuid}] ACK — silent")
            return

        text_fixed = fix_stt(text)
        # ── Sentiment tracking ──────────────────────────────────────────
        # This list is intentionally loose (bare "nahi"/"nhi"/"busy" match) —
        # it only ever fed a post-call lead score, where noise doesn't matter.
        # Do NOT use it to decide whether to end the call — see
        # _hard_rejection_kw below for that.
        _interest_kw  = ["kitna","kab","offer","discount","aana","dekhna","chahiye","dikhao","kitne","exchange","कितना","कब","ऑफर","आना","देखना","चाहिए","दिखाओ"]
        _rejection_kw = ["nahin","nahi","nhi","busy","mat karo","band karo","nahin chahiye","नहीं","बिज़ी","मत करो","बंद करो","नहीं चाहिए"]
        _tl = text.lower()
        if not hasattr(session, "interest_signals"): session.interest_signals = 0
        if not hasattr(session, "rejection_signals"): session.rejection_signals = 0
        if any(k in _tl for k in _interest_kw):  session.interest_signals  += 1
        if any(k in _tl for k in _rejection_kw): session.rejection_signals += 1

        # ── Explicit DNC / hard-rejection override ────────────────────────
        # Deliberately a SEPARATE, stricter list/counter from rejection_signals
        # above — that list matches bare "nahi"/"nhi"/"busy", which show up
        # constantly in normal engaged turns ("budget abhi nahi pata",
        # "sofa nahi bed chahiye", "thoda busy hoon do minute mein baat karta
        # hoon" all matched it in testing). Fine for a soft post-call score;
        # not safe as a hard "end the call" trigger — two such turns would
        # hang up on a customer who's still willing to talk. This list only
        # counts phrases that express actual terminal/end-of-call intent.
        _hard_rejection_kw = ["nahin chahiye","नहीं चाहिए","mat karo","मत करो","band karo","बंद करो",
                              "phone kaat","call kaat","kaat diya","phone rakh diya","call rakh diya",
                              "फोन काट","फ़ोन काट","कॉल काट","काट दिया","फोन रख दिया","फ़ोन रख दिया","कॉल रख दिया"]
        if not hasattr(session, "hard_rejection_signals"): session.hard_rejection_signals = 0
        if any(k in _tl for k in _hard_rejection_kw): session.hard_rejection_signals += 1

        # Detection existed (rejection_signals) but was never wired to
        # behavior — the agent kept pushing for a date/CTA even after a
        # clear rejection or an explicit "don't call me again". Both exits
        # below are fully scripted/pre-cached (STATIC_RESPONSES →
        # get_speech's static-cache layer), never a live LLM/TTS round trip.
        from webhook_reactivation import detect_intents
        is_explicit_dnc = session.state != "DONE" and "dnc" in detect_intents(text)
        hit_rejection_threshold = (
            session.state != "DONE"
            and not is_explicit_dnc
            and session.hard_rejection_signals >= REJECTION_GRACEFUL_DECLINE_THRESHOLD
        )
        if is_explicit_dnc or hit_rejection_threshold:
            session.dnc = True if is_explicit_dnc else getattr(session, "dnc", False)
            session.state = "DONE"
            from tts_engine import STATIC_RESPONSES
            audio_lang = getattr(session, "lang", "hi")
            reply = STATIC_RESPONSES.get("graceful_decline", {}).get(audio_lang) \
                or STATIC_RESPONSES.get("graceful_decline", {}).get("hi")
            source = "graceful_decline"
            session.conversation.append(("user", text))
            session.conversation.append(("assistant", reply))
            if is_explicit_dnc:
                phone = getattr(session, "customer_phone", "")
                if phone:
                    asyncio.create_task(mark_dnc_immediate(phone, call_uuid))
                logger.info(f"[{call_uuid}] Explicit DNC mid-call → graceful decline + immediate outbound_leads write")
            else:
                logger.info(f"[{call_uuid}] Hard rejection threshold hit ({session.hard_rejection_signals}) → graceful decline")
        else:
            reply, source = state_machine(text_fixed, text, session, call_uuid)
        if not reply:
            return

        session.last_reply = reply
        logger.info(f"[{call_uuid}] [{session.state}] {source} → '{reply[:60]}'")

        lang = getattr(session, "lang", "hinglish")
        # Some responses always use a fixed language for audio regardless of caller lang
        audio_lang = getattr(session, "urgency_lang_override", None) if source == "qualify_urgency" else None
        audio_lang = audio_lang or lang
        from respond_pipeline import _source_to_static_key
        static_key = _source_to_static_key(source, audio_lang)

        # ── Filler-first: check cache sync, play filler WHILE TTS generates ──
        from tts_engine import get_static_audio, get_dynamic_audio
        from filler_audio import get_filler_for_context

        is_cached = (
            get_static_audio(static_key, audio_lang) is not None
            if static_key else False
        ) or (get_dynamic_audio(reply, audio_lang) is not None)

        if not is_cached:
            filler_url = get_filler_for_context(source, lang)
            if filler_url:
                logger.info(f"[{call_uuid}] FILLER → {filler_url}")
                asyncio.create_task(play_audio_url(call_uuid, filler_url, turn=session.turn_idx, kind="filler"))

        wav, audio_url, was_cached = await get_speech(reply, audio_lang, static_key)

        if not audio_url:
            logger.error(f"[{call_uuid}] TTS failed entirely")
            return

        duration = session.priya_starts_speaking(wav) if wav else 2.0
        _latency = round(time.time() - t0, 3)
        logger.info(f"[{call_uuid}] Pipeline {_latency:.2f}s | cached={was_cached}")
        if not hasattr(session, "turn_latencies"): session.turn_latencies = []
        session.turn_latencies.append(_latency)
        if session.first_reply_ts is None: session.first_reply_ts = _latency

        await play_audio_url(call_uuid, audio_url, turn=session.turn_idx)
        await asyncio.sleep(duration)
        session.priya_stops_speaking()

        # Auto-hangup after goodbye plays
        if session.state == "DONE":
            await asyncio.sleep(1.2)
            logger.info(f"[{call_uuid}] DONE — auto-hangup")
            try:
                async with httpx.AsyncClient(timeout=8) as hc:
                    r = await hc.delete(
                        f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/",
                        headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK}
                    )
                logger.info(f"[{call_uuid}] Auto-hangup → {r.status_code}")
            except Exception as he:
                logger.error(f"[{call_uuid}] Auto-hangup error: {he}")

    except Exception as e:
        logger.error(f"[{call_uuid}] respond error: {e}")
        session.priya_stops_speaking()
    finally:
        session.is_processing = False


async def stop_audio(call_uuid: str, turn: int = 0):
    # This DELETE has never actually run in production — the barge-in trigger
    # that calls it was dead code until this fix (see ws_handler). status_code
    # and elapsed_ms are logged/audited specifically so it's known whether
    # Vobiz honours it and how fast, the first time real traffic hits it.
    _t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.delete(
                f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/Play/",
                headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK}
            )
        _elapsed = time.time() - _t0
        logger.info(f"[{call_uuid}] stop_audio (barge-in) → {r.status_code} | {_elapsed:.2f}s")
        audit_event(call_uuid, "barge_in", turn=turn, status_code=r.status_code, elapsed_ms=round(_elapsed * 1000))
    except Exception as e:
        _elapsed = time.time() - _t0
        logger.error(f"[{call_uuid}] stop_audio error: {e}")
        audit_event(call_uuid, "barge_in", turn=turn, status_code=None, elapsed_ms=round(_elapsed * 1000))


# No real speech turn within this long after the Stream opens → hang up.
# Confirmed live 2026-07-15: ~250 outbound calls/week connect (NORMAL_CLEARING,
# status=answered) but produce zero conversation turns. Audio analysis of a
# 124s sample showed ~20s of greeting then 100s of pure silence — no voice,
# no beep, nothing — consistent with a "ghost answer" (line connects, no one
# actually engages) rather than a live person the STT failed on. Longest
# current greeting (rb_greet_combined) is ~23.5s, so 35s gives that room to
# finish plus a few seconds for the customer to start responding, while
# cutting the ~100s dead-air waste down to ~35s and freeing the dialer's
# concurrency slot sooner.
SILENCE_CUTOFF_SECONDS = 35

async def _hangup_if_silent(call_uuid: str, session: "CallSession"):
    await asyncio.sleep(SILENCE_CUTOFF_SECONDS)
    if sessions.get(call_uuid) is not session:
        return  # call already ended naturally (or session was replaced)
    if session.turn_count > 0:
        return  # real conversation happened — leave it alone
    logger.info(f"[{call_uuid}] No speech within {SILENCE_CUTOFF_SECONDS}s of stream open — auto-hangup (likely ghost-answer/dead air)")
    try:
        async with httpx.AsyncClient(timeout=8) as hc:
            r = await hc.delete(
                f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/{call_uuid}/",
                headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK}
            )
        logger.info(f"[{call_uuid}] Silence auto-hangup → {r.status_code}")
    except Exception as e:
        logger.error(f"[{call_uuid}] Silence auto-hangup error: {e}")


# ─── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws/{call_uuid}")
async def ws_handler(websocket: WebSocket, call_uuid: str):
    await websocket.accept()
    session = CallSession(call_uuid)
    sessions[call_uuid] = session

    # Attach campaign info set by /answer-outbound before WS opened
    _meta = _session_meta.get(call_uuid, {})
    session.campaign       = _meta.get("campaign", "")
    session.customer_phone = _meta.get("to_phone", "")
    session.customer_name  = _meta.get("name", "")
    session.wa_decline_confirm = _meta.get("wa_decline_confirm", False)
    session.fresh_product   = _meta.get("product", "")
    session.call_cycle      = _meta.get("call_cycle", "")
    session.started_at     = datetime.now(timezone.utc).isoformat()
    if session.campaign:
        logger.info(f"[{call_uuid}] Campaign: {session.campaign}")

    async def _attach_lead_id():
        sb_url = os.getenv("SUPABASE_URL")
        sb_key = os.getenv("SUPABASE_SERVICE_KEY")
        if not sb_url or not sb_key:
            return
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(
                    f"{sb_url}/rest/v1/call_logs",
                    headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
                    params={"call_uuid": f"eq.{call_uuid}", "select": "lead_id", "limit": "1"},
                )
                if r.status_code == 200 and r.json():
                    session.lead_id = r.json()[0].get("lead_id")
                    logger.info(f"[{call_uuid}] lead_id attached: {session.lead_id}")
        except Exception as e:
            logger.error(f"_attach_lead_id error: {e}")

    asyncio.create_task(_attach_lead_id())
    asyncio.create_task(_hangup_if_silent(call_uuid, session))
    logger.info(f"[{call_uuid}] WS open")

    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive(), timeout=30.0)
            except asyncio.TimeoutError:
                break
            if msg.get("type") == "websocket.disconnect":
                break
            if "text" not in msg:
                continue
            try:
                data  = json.loads(msg["text"])
                event = data.get("event", "")
                if event == "start":
                    session.stream_id = data.get("start", {}).get("streamId", "")
                    logger.info(f"[{call_uuid}] Stream start | {session.stream_id}")
                elif event == "stop":
                    break
                elif event == "media":
                    payload = data.get("media", {}).get("payload", "")
                    if not payload: continue
                    chunk = base64.b64decode(payload)
                    should_process, audio = session.ingest(chunk)
                    if session.barge_in_pending:
                        asyncio.create_task(stop_audio(call_uuid, turn=getattr(session, "turn_idx", session.turn_count)))
                        session.barge_in_pending = False
                    if should_process and not session.is_processing:
                        logger.info(f"[{call_uuid}] Audio ready → sending to STT")
                        asyncio.create_task(respond(websocket, session, audio, call_uuid))
            except (json.JSONDecodeError, KeyError):
                pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[{call_uuid}] ws error: {e}")
    finally:
        logger.info(f"[{call_uuid}] WS closed")


# ─── HTTP Endpoints ───────────────────────────────────────────────────────────
INBOUND_GREETING  = "नमस्कार! कृष्णा फर्नीचर में आपका स्वागत है — मैं प्रिया बोल रही हूँ। आपकी कैसे मदद कर सकती हूँ?"
OUTBOUND_GREETING = "नमस्कार! क्या मैं {name} जी से बात कर रही हूँ? मैं प्रिया हूँ, कृष्णा फर्नीचर से। अभी २ मिनट बात कर सकते हैं?"

@app.post("/answer")
async def answer_call(request: Request):
    form      = await request.form()
    call_uuid = form.get("CallUUID", "unknown")
    from_num  = form.get("From", "")
    to_num    = form.get("To", "")

    # Detect outbound: check if To number is in outbound_leads
    is_outbound = False
    lead_name   = ""
    if to_num:
        try:
            sb_url = os.getenv("SUPABASE_URL")
            sb_key = os.getenv("SUPABASE_SERVICE_KEY")
            _hdrs  = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
            async with httpx.AsyncClient(timeout=3) as _c:
                _r = await _c.get(
                    f"{sb_url}/rest/v1/outbound_leads"
                    f"?phone=eq.{to_num}&tenant_id=eq.krishna_furniture"
                    f"&select=id,name,status,campaign_type&limit=1",
                    headers=_hdrs,
                )
                if _r.status_code == 200 and _r.json():
                    row = _r.json()[0]
                    if row.get("status") in ("pending", "in_progress"):
                        is_outbound   = True
                        lead_name     = row.get("name") or ""
                        lead_campaign = row.get("campaign_type") or "fresh_lead"
        except Exception as _e:
            logger.error(f"outbound detect error: {_e}")

    if is_outbound:
        logger.info(f"[{call_uuid}] Outbound detected → {to_num} | name={lead_name}")
        _session_meta[call_uuid] = {"direction": "outbound", "to_phone": to_num, "campaign": lead_campaign}
        lead_id = await get_or_create_lead_id(to_num, lead_name)
        asyncio.create_task(insert_call_log(
            call_uuid   = call_uuid,
            from_number = from_num,
            to_number   = to_num,
            direction   = "outbound",
            caller_name = lead_name,
            lead_id     = lead_id,
        ))
        greeting  = OUTBOUND_GREETING.format(name=lead_name) if lead_name else OUTBOUND_GREETING.format(name="")
        audio_url = await save_audio(greeting, f"greeting_out_{call_uuid}")
        play_tag  = f"<Play>{audio_url}</Play>" if audio_url else "<Speak>Namaskar! Main Priya hun.</Speak>"
        return PlainTextResponse(
            f'<?xml version="1.0" encoding="UTF-8"?><Response><Record recordSession="true" maxLength="3600" fileFormat="mp3" redirect="false" '
            f'action="https://voice.thesocialhood.in/recording-done"/>'
            f'{play_tag}'
            f'<Stream keepCallAlive="true" bidirectional="true" contentType="audio/x-mulaw;rate=8000" streamTimeout="86400">'
            f'wss://voice.thesocialhood.in/ws/{call_uuid}</Stream>'
            f'</Response>',
            media_type="application/xml"
        )

    # Inbound call
    logger.info(f"[{call_uuid}] Inbound from {from_num}")

    # Check if the caller is a known lead in EITHER funnel — if so, skip the
    # generic inbound greeting and drop straight into their already-assigned
    # plan's existing GREETING state (same audio/script as the matching
    # outbound flow, just entered inbound). Originally this only checked
    # funnel_type=reactivation_customer, so fresh_cta leads calling back
    # fell through to the generic/unknown-caller branch below with no
    # campaign, no product, no name attached (confirmed live: this is what
    # produced an 8m26s/51-turn stuck call for a fresh_cta lead that called
    # back inbound). Numbers stored in outbound_leads.phone always carry a
    # '+' prefix, but Vobiz's inbound "From" field does not — so match both
    # forms.
    matched_lead = None
    if from_num:
        try:
            _from_variants = {from_num, from_num[1:] if from_num.startswith("+") else f"+{from_num}"}
            _phone_or = ",".join(f"phone.eq.{v}" for v in _from_variants)
            sb_url = os.getenv("SUPABASE_URL")
            sb_key = os.getenv("SUPABASE_SERVICE_KEY")
            _hdrs  = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
            async with httpx.AsyncClient(timeout=3) as _c:
                _r = await _c.get(
                    f"{sb_url}/rest/v1/outbound_leads",
                    headers=_hdrs,
                    params={
                        "or":          f"({_phone_or})",
                        "funnel_type": "in.(reactivation_customer,fresh_cta)",
                        "tenant_id":   "eq.krishna_furniture",
                        "select":      "id,name,campaign_type,funnel_type,product_interest",
                        "limit":       "1",
                    },
                )
                if _r.status_code == 200 and _r.json():
                    matched_lead = _r.json()[0]
        except Exception as _e:
            logger.error(f"[{call_uuid}] inbound lead lookup error: {_e}")

    _name = ""
    if matched_lead and matched_lead.get("funnel_type") == "fresh_cta":
        from knowledge_react_abc import normalize_fresh_product_key
        _name    = matched_lead.get("name") or ""
        _product = matched_lead.get("product_interest") or ""
        _product_key = normalize_fresh_product_key(_product)
        logger.info(f"[{call_uuid}] Inbound fresh_cta lead → {from_num} | name={_name} | product={_product or '-'}")
        _session_meta[call_uuid] = {
            "direction": "inbound",
            "to_phone":  from_num,
            "campaign":  "fresh_cta",
            "name":      _name,
            "product":   _product,
        }
        greet_key = f"fresh_greet_{_product_key}" if _product_key else "fresh_greet_generic"
        play_tag  = f"<Play>{BASE_URL}/audio/static/{greet_key}_hi.wav</Play>"

    elif matched_lead:  # reactivation_customer
        _react_campaign = matched_lead.get("campaign_type") or "reactivation"
        _name           = matched_lead.get("name") or ""
        logger.info(f"[{call_uuid}] Inbound reactivation lead → {from_num} | name={_name} | campaign={_react_campaign}")
        _session_meta[call_uuid] = {
            "direction": "inbound",
            "to_phone":  from_num,
            "campaign":  _react_campaign,
            "name":      _name,
        }

        if _react_campaign in ("react_a", "react_b", "react_c"):
            # Single combined clip — same fix as the outbound reactivation
            # branch in /answer-outbound (2026-07-15). This branch was
            # "copied, not reinvented" from that one's PRE-fix two-<Play>-tag
            # form and never got the merge applied, leaving a real ~7s
            # dead-air gap between the two file fetches on inbound
            # reactivation callbacks (confirmed live via call 3088c2c5's
            # nginx log, 2026-07-17 — two separate GETs, universal_greeting_rc
            # then rc_greet_main, 7s apart).
            _p = {"react_a": "ra", "react_b": "rb", "react_c": "rc"}[_react_campaign]
            audio_url = f"{BASE_URL}/audio/static/{_p}_greet_combined_hi.wav"
            play_tag  = f"<Play>{audio_url}</Play>"
        else:
            greet_key = "react_greet_main"
            universal_greeting_url = f"{BASE_URL}/audio/static/universal_greeting_hi.wav"
            audio_url = f"{BASE_URL}/audio/static/{greet_key}_hi.wav"
            play_tag  = f"<Play>{universal_greeting_url}</Play><Play>{audio_url}</Play>"

    else:
        # Generic inbound — unknown caller, or a lead never assigned to
        # either funnel. Unchanged from prior behavior.
        _session_meta[call_uuid] = {"direction": "inbound", "to_phone": ""}
        audio_url = await save_audio(INBOUND_GREETING, f"greeting_{call_uuid}")
        play_tag  = f"<Play>{audio_url}</Play>" if audio_url else "<Speak>Namaskar! Main Priya hun.</Speak>"

    lead_id = await get_or_create_lead_id(from_num, _name)
    asyncio.create_task(insert_call_log(
        call_uuid   = call_uuid,
        from_number = from_num,
        to_number   = "+919262102426",
        direction   = "inbound",
        caller_name = _name,
        lead_id     = lead_id,
    ))
    return PlainTextResponse(
        f'<?xml version="1.0" encoding="UTF-8"?><Response><Record recordSession="true" maxLength="3600" fileFormat="mp3" redirect="false" '
        f'action="https://voice.thesocialhood.in/recording-done"/>'
        f'{play_tag}'
        f'<Stream keepCallAlive="true" bidirectional="true" contentType="audio/x-mulaw;rate=8000" streamTimeout="86400">'
        f'wss://voice.thesocialhood.in/ws/{call_uuid}</Stream>'
        f'</Response>',
        media_type="application/xml"
    )


@app.api_route("/answer-outbound", methods=["GET","POST"])
async def answer_outbound(request: Request):
    form      = await request.form()
    call_uuid = form.get("CallUUID", "unknown")
    name      = request.query_params.get("name", "")
    to_phone  = form.get("To", "")
    campaign  = request.query_params.get("campaign", "")
    product   = request.query_params.get("product", "")
    call_cycle = request.query_params.get("call_cycle", "")
    # Used by fresh_cta's greeting selection across all 3 call cycles below —
    # computed once here rather than re-derived per cycle.
    from knowledge_react_abc import normalize_fresh_product_key
    _product_key = normalize_fresh_product_key(product)
    wa_decline_confirm = request.query_params.get("wa_decline_confirm", "") in ("1", "true", "True")
    logger.info(f"[{call_uuid}] Outbound to {to_phone} | name={name} | campaign={campaign or 'generic'} | call_cycle={call_cycle or '1'} | wa_decline_confirm={wa_decline_confirm} | product={product or '-'}")

    # Store for ws_handler (campaign, phone, name all needed before WS opens)
    _session_meta[call_uuid] = {
        "direction": "outbound",
        "to_phone":  to_phone,
        "campaign":  campaign,
        "name":      name,
        "wa_decline_confirm": wa_decline_confirm,
        "product":   product,
        "call_cycle": call_cycle,
    }

    lead_id = await get_or_create_lead_id(to_phone, name)
    asyncio.create_task(insert_call_log(
        call_uuid   = call_uuid,
        from_number = "+919262102426",
        to_number   = to_phone,
        direction   = "outbound",
        caller_name = name,
        lead_id     = lead_id,
        call_cycle  = call_cycle,
    ))

    if call_cycle == "2" and campaign != "fresh_cta":
        # Call 2 (Ritu) — second real conversation with this lead, no date yet.
        # Overrides campaign_type entirely, per call_cycle routing.
        audio_url = f"{BASE_URL}/audio/static/c2_greet_main_hi.wav"
        play_tag  = f"<Play>{audio_url}</Play>"
    elif call_cycle == "3" and campaign != "fresh_cta":
        # Call 3 (Simran) — third real conversation, last attempt before the
        # existing answered_no_date_count>=3 cadence exit.
        audio_url = f"{BASE_URL}/audio/static/c3_greet_main_hi.wav"
        play_tag  = f"<Play>{audio_url}</Play>"
    elif call_cycle == "2" and campaign == "fresh_cta":
        # fresh_cta Call 2 — same Simran voice as Call 1, product-aware
        # follow-up greeting. Turn logic afterward is unchanged: it falls
        # through to the same campaign=="fresh_cta" dispatch in respond()
        # that Call 1 and Call 3 both use — handle_fresh_cta_turn doesn't
        # vary by call_cycle, only the opening line does.
        greet_key = f"fresh_c2_greet_{_product_key}" if _product_key else "fresh_c2_greet_generic"
        audio_url = f"{BASE_URL}/audio/static/{greet_key}_hi.wav"
        play_tag  = f"<Play>{audio_url}</Play>"
    elif call_cycle == "3" and campaign == "fresh_cta":
        # fresh_cta Call 3 — same pattern as Call 2 above, final-attempt tone.
        greet_key = f"fresh_c3_greet_{_product_key}" if _product_key else "fresh_c3_greet_generic"
        audio_url = f"{BASE_URL}/audio/static/{greet_key}_hi.wav"
        play_tag  = f"<Play>{audio_url}</Play>"
    elif campaign == "followup_wa":
        audio_url = f"{BASE_URL}/audio/static/react_followup_wa_hi.wav"
        # Fire WA immediately — no stream needed for followup
        asyncio.create_task(_fire_followup_wa(call_uuid, name, to_phone))
        return PlainTextResponse(
            f'<?xml version="1.0" encoding="UTF-8"?><Response>'
            f'<Record recordSession="true" maxLength="3600" fileFormat="mp3" redirect="false" '
            f'action="https://voice.thesocialhood.in/recording-done"/>'
            f'<Play>{audio_url}</Play>'
            f'<Hangup/>'
            f'</Response>',
            media_type="application/xml"
        )
    elif campaign in ("reactivation", "react_a", "react_b", "react_c"):
        prefix = {"react_a": "ra", "react_b": "rb", "react_c": "rc"}.get(campaign, "ra")
        if wa_decline_confirm:
            # WA-decline-confirm lane: play the confirm line instead of the
            # plan's usual opener, then fall straight into this same plan's
            # existing GREETING state — handle_reactivation_turn is unchanged,
            # it just receives a different opening line to react to.
            greet_key = "wa_decline_confirm_greet"
            audio_url = f"{BASE_URL}/audio/static/{greet_key}_hi.wav"
            universal_greeting_url = f"{BASE_URL}/audio/static/universal_greeting_hi.wav"
            play_tag = f"<Play>{universal_greeting_url}</Play><Play>{audio_url}</Play>"
        elif campaign in ("react_a", "react_b", "react_c"):
            # Single combined clip (universal_greeting + {prefix}_greet_main
            # concatenated, same text, no re-TTS) instead of two sequential
            # <Play> tags. Confirmed live 2026-07-15: 253 outbound calls had
            # 0 conversation turns despite connecting — 82% were react_a/b/c,
            # clustered at 6-15s, matching exactly the two-clip greeting's
            # playback length (customers hanging up before the Stream ever
            # got a chance to listen). Total spoken content is unchanged;
            # this only removes the inter-clip gap between the two Plays.
            audio_url = f"{BASE_URL}/audio/static/{prefix}_greet_combined_hi.wav"
            play_tag = f"<Play>{audio_url}</Play>"
        else:
            greet_key = "react_greet_main"
            audio_url = f"{BASE_URL}/audio/static/{greet_key}_hi.wav"
            universal_greeting_url = f"{BASE_URL}/audio/static/universal_greeting_hi.wav"
            play_tag = f"<Play>{universal_greeting_url}</Play><Play>{audio_url}</Play>"
    elif campaign == "fresh_cta":
        # No universal-greeting prefix line — fresh_greet_* already opens with
        # its own "Namaste ji". Product comes from the promoted outbound_leads
        # row's product_interest, threaded through /trigger-call -> query param.
        # This is call_cycle 1/None only — 2/3 are handled above.
        greet_key = f"fresh_greet_{_product_key}" if _product_key else "fresh_greet_generic"
        audio_url = f"{BASE_URL}/audio/static/{greet_key}_hi.wav"
        play_tag = f"<Play>{audio_url}</Play>"
    else:
        greeting  = OUTBOUND_GREETING.format(name=name) if name else INBOUND_GREETING
        audio_url = await save_audio(greeting, f"greeting_out_{call_uuid}")
        play_tag  = f"<Play>{audio_url}</Play>" if audio_url else "<Speak>Namaskar! Main Priya hun.</Speak>"

    return PlainTextResponse(
        f'<?xml version="1.0" encoding="UTF-8"?><Response><Record recordSession="true" maxLength="3600" fileFormat="mp3" redirect="false" '
        f'action="https://voice.thesocialhood.in/recording-done"/>'
        f'{play_tag}'
        f'<Stream keepCallAlive="true" bidirectional="true" contentType="audio/x-mulaw;rate=8000" streamTimeout="86400">'
        f'wss://voice.thesocialhood.in/ws/{call_uuid}</Stream>'
        f'</Response>',
        media_type="application/xml"
    )



@app.get("/recording/{recording_id}")
async def proxy_recording(recording_id: str):
    """Proxy Vobiz recording with auth headers so browser can play it."""
    url = f"https://media.vobiz.ai/v1/Account/{VOBIZ_ACCOUNT}/Recording/{recording_id}.mp3"
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(url, headers={
                "X-Auth-ID":    VOBIZ_AUTH_ID,
                "X-Auth-Token": VOBIZ_AUTH_TOK,
            })
        if r.status_code == 200:
            from fastapi.responses import Response
            return Response(
                content=r.content,
                media_type="audio/mpeg",
                headers={"Content-Disposition": f"inline; filename={recording_id}.mp3"}
            )
        return {"error": f"Vobiz returned {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/recording-done")
async def recording_done(request: Request):
    """Vobiz calls this when a recording is ready. Save URL to Supabase."""
    form         = await request.form()
    all_fields   = dict(form)
    call_uuid    = form.get("CallUUID", "")
    logger.info(f"[{call_uuid}] /recording-done full payload: {all_fields}")
    recording_url = form.get("RecordFile") or form.get("RecordUrl", "")
    recording_id  = form.get("RecordingID", "")
    proxied_url   = f"{BASE_URL}/recording/{recording_id}" if recording_id else recording_url
    duration     = form.get("RecordingDuration", "0")
    logger.info(f"[{call_uuid}] Recording ready | url={recording_url} | duration={duration}s")

    if call_uuid and recording_url:
        try:
            sb_url = os.getenv("SUPABASE_URL")
            sb_key = os.getenv("SUPABASE_SERVICE_KEY")
            hdrs   = {
                "apikey": sb_key,
                "Authorization": f"Bearer {sb_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            async with httpx.AsyncClient(timeout=5) as c:
                await c.patch(
                    f"{sb_url}/rest/v1/call_logs?call_uuid=eq.{call_uuid}",
                    headers=hdrs,
                    json={"recording_url": recording_url, "recording_duration": int(duration)}
                )
            # call_summaries row may not exist yet (it's only INSERTed at hangup,
            # and real calls routinely run past the old fixed 20s delay) — poll
            # until the row appears, then patch the recording_url onto it.
            async def _save_recording_to_summary(uuid, url, surl, skey):
                h = {"apikey": skey, "Authorization": f"Bearer {skey}", "Content-Type": "application/json", "Prefer": "return=minimal"}
                poll_interval = 10
                max_wait      = 180
                waited        = 0
                try:
                    async with httpx.AsyncClient(timeout=5) as c2:
                        while waited < max_wait:
                            await asyncio.sleep(poll_interval)
                            waited += poll_interval
                            r_check = await c2.get(
                                f"{surl}/rest/v1/call_summaries",
                                headers=h,
                                params={"call_uuid": f"eq.{uuid}", "select": "call_uuid", "limit": "1"},
                            )
                            if r_check.status_code == 200 and r_check.json():
                                await c2.patch(f"{surl}/rest/v1/call_summaries?call_uuid=eq.{uuid}", headers=h, json={"recording_url": url})
                                logger.info(f"[{uuid}] Recording URL saved to call_summaries (delayed, after {waited}s)")
                                return
                        logger.error(
                            f"[{uuid}] call_summaries row never appeared within {max_wait}s — "
                            f"recording_url NOT copied to call_summaries (still safe in call_logs.recording_url)"
                        )
                except Exception as ex:
                    logger.error(f"[{uuid}] Failed delayed recording save: {ex}")
            asyncio.create_task(_save_recording_to_summary(call_uuid, proxied_url, sb_url, sb_key))
            logger.info(f"[{call_uuid}] Recording URL saved to Supabase")
        except Exception as e:
            logger.error(f"[{call_uuid}] Failed to save recording URL: {e}")

    return PlainTextResponse("OK")

async def _is_dnc(to: str) -> bool:
    """
    Checked by /trigger-call before dialing — this endpoint previously had
    NO dnc check at all, dialing immediately regardless of outbound_leads
    status. Confirmed live: a team testing number (+918799712556) was
    already marked dnc=true in outbound_leads yet kept getting called,
    because every one of those calls came through this endpoint, which never
    looked the flag up. Same phone.eq OR-match pattern (+ and bare digits)
    used elsewhere in this codebase for outbound_leads lookups, since the
    column is stored inconsistently across write paths.
    """
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not sb_url:
        return False
    to_clean = to.strip()
    to_bare  = to_clean.lstrip("+")
    phone_or = ",".join(f"phone.eq.{v}" for v in {to_clean, f"+{to_bare}", to_bare})
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{sb_url}/rest/v1/outbound_leads",
                headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
                params={"or": f"({phone_or})", "select": "dnc", "limit": "1"},
            )
        rows = r.json()
        return bool(rows and rows[0].get("dnc"))
    except Exception as exc:
        logger.error(f"/trigger-call dnc check failed for {to}: {exc}")
        return False  # fail open on lookup errors — don't block calls on a transient DB hiccup


@app.post("/trigger-call")
async def trigger_call(request: Request):
    body     = await request.json()
    to       = body.get("to", "")
    name     = body.get("name", "")
    campaign = body.get("campaign", "")
    product  = body.get("product", "")
    call_cycle = body.get("call_cycle")
    wa_decline_confirm = body.get("wa_decline_confirm", False)
    if not to:
        return {"error": "Missing 'to'"}

    if await _is_dnc(to):
        logger.warning(f"/trigger-call BLOCKED — {to} is marked dnc in outbound_leads")
        return {"status": "blocked", "reason": "dnc", "to": to}

    if not is_calling_window(campaign):
        now_ist = datetime.now(IST).strftime("%H:%M")
        end_hour = CALL_END_HOUR_BY_CAMPAIGN.get(campaign, CALL_END_HOUR_DEFAULT)
        logger.warning(f"/trigger-call BLOCKED — {to} campaign={campaign or 'generic'} outside {CALL_START_HOUR}:00-{end_hour}:00 IST window (now {now_ist} IST)")
        return {"status": "blocked", "reason": "outside_calling_window", "to": to}

    campaign_param   = f"&campaign={campaign}" if campaign else ""
    decline_param    = "&wa_decline_confirm=1" if wa_decline_confirm else ""
    product_param    = f"&product={product}" if product else ""
    call_cycle_param = f"&call_cycle={call_cycle}" if call_cycle else ""
    answer_url = f"{BASE_URL}/answer-outbound?name={name}{campaign_param}{decline_param}{product_param}{call_cycle_param}"

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"https://api.vobiz.ai/api/v1/Account/{VOBIZ_ACCOUNT}/Call/",
            headers={"X-Auth-ID": VOBIZ_AUTH_ID, "X-Auth-Token": VOBIZ_AUTH_TOK, "Content-Type": "application/json"},
            json={"from": "+919262102426", "to": to,
                  "answer_url": answer_url,
                  "hangup_url": f"{BASE_URL}/hangup", "hangup_url_method": "POST"}
        )
    logger.info(f"Trigger call {to} campaign={campaign or 'generic'} → {r.status_code}")
    return {"status": "triggered", "to": to, "campaign": campaign, "vobiz": r.json()}


# ─── HANGUP — patched with outbound_leads status update ──────────────────────
@app.post("/hangup")
async def hangup(request: Request):
    form      = await request.form()
    call_uuid = form.get("CallUUID", "unknown")
    duration  = form.get("Duration", "0")
    cause     = form.get("HangupCause", "")
    _meta     = _session_meta.pop(call_uuid, {})
    direction = form.get("Direction", _meta.get("direction", "inbound"))
    to_phone  = form.get("To", "") if direction == "outbound" else form.get("From", "")

    logger.info(f"[{call_uuid}] Hangup after {duration}s | cause={cause} | ALL_FIELDS={dict(form)}")

    session = sessions.get(call_uuid) or CallSession(call_uuid)

    # ── For reactivation/followup_wa: restore campaign context from _session_meta
    #    so finalize_call writes correct campaign_type, phone, name to call_summaries
    if not session.campaign:
        session.campaign       = _meta.get("campaign", "")
        session.customer_phone = _meta.get("to_phone", "")
        session.customer_name  = _meta.get("name", "")
        session.wa_decline_confirm = _meta.get("wa_decline_confirm", False)
        session.fresh_product = _meta.get("product", "")
        # call_cycle also only ever gets set in the WS handler (webhook.py's
        # /ws/{call_uuid}) — for calls where the Stream never connects (the
        # session falls back to a bare CallSession above), it must be
        # restored here too or _resolve_call_number() defaults it to 1
        # regardless of what call_cycle the greeting actually used.
        session.call_cycle = _meta.get("call_cycle", "")
        if session.campaign:
            logger.info(f"[{call_uuid}] Hangup: restored campaign={session.campaign} call_cycle={session.call_cycle or '1'} from meta")

    logger.info(
        f"[{call_uuid}] Session at hangup → "
        f"campaign={session.campaign} | "
        f"lead={session.lead} | "
        f"state={session.state} | "
        f"react_state={getattr(session, 'react_state', '-')} | "
        f"turns={session.turn_count} | "
        f"wa_sent={getattr(session, 'wa_sent', False)} | "
        f"transcript_len={len(getattr(session, 'conversation', []))}"
    )
    audit_event(
        call_uuid, "call_end", turn=session.turn_count,
        final_state=getattr(session, "react_state", None) or session.state,
        turn_count=session.turn_count,
        wa_sent=getattr(session, "wa_sent", False),
    )

    # Write call summary to Supabase (existing logic — unchanged)
    await finalize_call(
        call_uuid    = call_uuid,
        session      = session,
        from_number  = to_phone if to_phone else form.get("From", "+919262102426"),
        duration_str = duration,
        hangup_cause = cause,
    )

    sessions.pop(call_uuid, None)
    return PlainTextResponse("", status_code=200)


@app.post("/stream-end")
async def stream_end(request: Request):
    form = await request.form()
    sessions.pop(form.get("CallUUID",""), None)
    return PlainTextResponse("", status_code=200)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active_calls": len(sessions),
        "sessions": list(sessions.keys())
    }

@app.get("/lead-followup-status")
async def lead_followup_status(phones: str):
    """
    Read-only CRM-facing lookup — current call_cycle, campaign_type, last
    call outcome, next_retry_at, and visit_date/visit_date_status for one
    or more leads. `phones` is a comma-separated list (a single phone works
    the same way, just one element). No writes; does not affect dispatch or
    eligibility. See supabase_calling.get_followup_status() for the query.
    """
    from supabase_calling import get_followup_status
    phone_list = [p.strip() for p in phones.split(",") if p.strip()]
    if not phone_list:
        raise HTTPException(status_code=400, detail="phones query param required")
    results = await get_followup_status(phone_list)
    return {"results": results}


@app.get("/lead-call-history")
async def lead_call_history(phones: str):
    """
    Read-only CRM-facing lookup — outbound call-attempt history (called_count,
    answered_count, pickup_rate) for one or more leads. `phones` is a
    comma-separated list, same convention as /lead-followup-status. Outbound
    calls only (see supabase_calling.get_call_history() docstring for why).
    Phones with no matching call_logs rows are still returned with
    called_count=0 / pickup_rate=None; phones whose leads row is dnc=true are
    omitted entirely. No writes; does not affect dispatch or eligibility.
    """
    from supabase_calling import get_call_history
    phone_list = [p.strip() for p in phones.split(",") if p.strip()]
    if not phone_list:
        raise HTTPException(status_code=400, detail="phones query param required")
    results = await get_call_history(phone_list)
    return {"results": results}


@app.post("/walkin-followup/{walkin_id}")
async def walkin_followup(walkin_id: str):
    """
    Queues one follow-up call for a walk-in visit (walkins table). No
    auto-fire timing — caller (CRM button, or manual) decides when to hit
    this. Capped at 3 total per walk-in; see walkin_followup.py.
    """
    from walkin_followup import schedule_next_walkin_followup_call
    result = await schedule_next_walkin_followup_call(walkin_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info",
                ws_ping_interval=20, ws_ping_timeout=30)