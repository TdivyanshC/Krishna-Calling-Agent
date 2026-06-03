"""
Krishna Furniture - Knowledge Engine
Wraps IntentMatcher + FAQ for clean integration with webhook.py
Returns (response_text, source) or (None, "needs_llm")
"""

import json
import re
import random
import logging
from difflib import SequenceMatcher
from collections import defaultdict

logger = logging.getLogger(__name__)

FAQ_PATH = "/home/voiceagent/voice-ai/faq_database.json"

# ─── STT Correction ───────────────────────────────────────────────────────────
STT_FIXES = {
    r"\bso far\b":        "sofa",
    r"\bsofa\b":          "sofa",
    r"\bsofer\b":         "sofa",
    r"\bsopha\b":         "sofa",
    r"\bto offer\b":      "sofa",
    r"\boffers\b":        "sofa",
    r"\bso fa\b":         "sofa",
    r"\bsocha\b":         "sofa",
    r"\bso pha\b":        "sofa",
    r"\bsofar\b":         "sofa",
    r"\bkukha\b":         "sofa",      # ← NEW: "kukha" = mishear of sofa/kursi
    r"\bchayar\b":        "chair",     # ← NEW: "chayar" = chair
    r"\bkirsten\b":       "",          # ← NEW: hallucination noise word
    r"\bobirah\b":        "",          # ← NEW: hallucination noise word
    r"\bjoin frozen\b":   "",          # ← NEW: hallucination
    r"\belchiev\b":       "l shape",
    r"\bel chiev\b":      "l shape",
    r"\bel shaped\b":     "l shape",
    r"\bpalang\b":        "bed",
    r"\balmari\b":        "almirah",
    r"\bmej\b":           "table",
    r"\bkursi\b":         "chair",
    r"\bparda\b":         "curtain",
    r"\bgadda\b":         "mattress",
    r"\bmehenga\b":       "mahanga",
    r"\bmehngi\b":        "mahanga",
    r"\bgurgoan\b":       "gurgaon",
    r"\bguru gaon\b":     "gurgaon",
    r"\be\.m\.i\b":       "emi",
    r"\bnhi\b":           "nahi",
    r"\bni\b":            "nahi",
    r"\bdlvry\b":         "delivery",
    r"\bdilvery\b":       "delivery",
    # ── Saaras Devanagari corrections ──────────────────────────────────────
    # Saaras transcribes Hindi phonetically — English furniture words get
    # written as their Hindi sound. Map them back to English for matching.
    "शेयर":    "chair",      # "chair" sounds like "share" in Hindi
    "छेड़":    "chair",      # another mishearing of chair
    "चेयर":   "chair",
    "चेहरे":  "chair",
    "सोफ़ा":   "sofa",
    "तोफा":   "sofa",
    "तोफ़ा":  "sofa",
    "सोफा":   "sofa",
    "बेड":    "bed",
    "पलंग":   "bed",
    "डाइनिंग": "dining",
    "वार्डरोब": "wardrobe",
    "अलमारी": "almirah",
    "कुर्सी":  "chair",
    "मेज":    "table",
    "देखना":  "dekhna chahiye",
    "देखने":  "dekhna chahiye",
    "चाहिए":  "chahiye",
    "कितने":  "kitne",
    "कितना":  "kitna",
    "डिलीवरी": "delivery",
    "ऑफर":   "offer",
    "छूट":   "discount",
    "वारंटी": "warranty",
    "इंस्टॉलेशन": "installation",
    r"\bdekhna hai\b":    "dekhna chahiye",
    r"\bdikhao\b":        "dekhna chahiye",
    r"\bdikhaiye\b":      "dekhna chahiye",
    r"\bking siege\b":    "king size",
    r"\bkink size\b":     "king size",
    r"\b6 cedar\b":       "6 seater",
    r"\bsix cedar\b":     "6 seater",
}

# Words that are pure noise — if transcript is ONLY these, skip
JUNK_WORDS = {
    # Audio artifacts
    "um","uh","ah","err","hmm","beep","bip","ding","wena",
    "excuse me","yuz mi","yuse me","sorry","pardon",
    # Whisper hallucinations on phone noise
    "kirsten","obirah","frozen","leonard","partner","walter",
    "thanks","thank","bye","goodbye","music","silence",
    # Single Hindi filler words that carry no intent
    "haan","han","ha","ji","okay","ok","achha","acha","theek",
    "hm","hmm","arre","oh","wah","nice","great","sure",
}

# Single-word responses that are acknowledgements, not queries
ACK_WORDS = {
    # Roman
    "haan","han","ha","ji","okay","ok","achha","acha","theek","bilkul",
    "zaroor","sahi","got it","alright","samjha","samjhi","understood",
    "haan ji","ok ji","theek hai","ji haan","yes","yep","yup",
    "ok thank you","okay thank you","thanks bye","ok thanks","thank you",
    # Devanagari (Saaras output)
    "हाँ","हाँ जी","हां","हां जी","जी","ठीक है","बिल्कुल","ज़रूर",
    "अच्छा","ओके","यस","हाँ जी।","जी।","यस।","ओके।","ठीक।",
    "हाँ जी बोलिए","हाँ बोलिए","हाँ जी बोलिए।","हाँ बोलिए।",
    "बोलिए","बोलिए।","जी बोलिए","जी बोलिए।","हाँ जी बताइए",
    "ओके, थैंक यू।","ओके थैंक यू","थैंक यू।","थैंक्स।","शुक्रिया।",
    "बहुत शुक्रिया।","धन्यवाद।","ठीक है जी।","अच्छा जी।",
}

def fix_stt(text: str) -> str:
    t = text.lower()
    for pat, rep in STT_FIXES.items():
        if pat.startswith("\b") or pat.startswith("r"):
            # Regex pattern
            try:
                t = re.sub(pat, rep, t, flags=re.IGNORECASE)
            except Exception:
                pass
        else:
            # Plain Devanagari string replacement
            t = t.replace(pat, rep)
    return re.sub(r"\s+", " ", t).strip()

def is_noise(text: str) -> bool:
    cleaned = text.strip(".,!? ।")
    words = [w.strip(".,!? ।") for w in cleaned.split()]
    real  = [w for w in words if w and len(w) > 1 and w not in JUNK_WORDS]
    if len(real) < 1:
        return True
    if len(real) == 1:
        w = real[0]
        # Short Devanagari fillers alone = incomplete utterance
        devanagari_fillers = {"मुझे","मैं","आप","वो","यह","इसे","उसे","क्या","कोई","एक","मेरे","मेरा",
                                  "करीब","तकरीबन"}
        if w in devanagari_fillers:
            return True
        # Single English name/hallucination = noise
        if w.istitle() and w.lower() not in {
            "sofa","bed","beg","chair","table","wardrobe","almirah","curtain","dining",
            "delivery","offer","emi","gurgaon","delhi","noida","faridabad",
            "exchange","warranty","installation","wholesale","interior",
        }:
            return True
    return False

def is_acknowledgement(text: str) -> bool:
    """Short filler — agent should stay silent or give tiny nudge."""
    stripped = text.lower().strip(".,!? ")
    return stripped in ACK_WORDS or (len(stripped.split()) == 1 and stripped in JUNK_WORDS)

DIRECT_KEYWORD_MAP: dict[str, str] = {
    # ── Manufacturing / Factory ───────────────────────────────────────────────
    "kherki daula":      "manufacturing",
    "kherki":            "manufacturing",
    "bamdoli":           "manufacturing",
    "manufacturing":     "manufacturing",
    "factory":           "manufacturing",
    "khud ka":           "manufacturing",
    "apna plant":        "manufacturing",
    "खेड़की":            "manufacturing",
    "खेड़की दौला":       "manufacturing",
    "बामडोली":           "manufacturing",
    "फैक्ट्री":          "manufacturing",
    "प्लांट":            "manufacturing",
    "खुद का":            "manufacturing",

    # ── Store Location ────────────────────────────────────────────────────────
    "kahan hai":         "store_location",
    "kahan hain":        "store_location",
    "kahan par":         "store_location",
    "shop kahan":        "store_location",
    "store kahan":       "store_location",
    "showroom kahan":    "store_location",
    "address":           "store_location",
    "location":          "store_location",
    "kahan milega":      "store_location",
    "nearest":           "store_location",
    "nazdik":            "store_location",
    # Devanagari location
    "कहाँ है":           "store_location",
    "कहाँ हैं":          "store_location",
    "कहाँ पर":           "store_location",
    "शॉप कहाँ":          "store_location",
    "स्टोर कहाँ":         "store_location",
    "शोरूम कहाँ":         "store_location",
    "एड्रेस":            "store_location",
    "पता":               "store_location",
    "नज़दीक":            "store_location",
    "नज़दीकी":           "store_location",
    "कहां":              "store_location",

    # ── Head Branch ───────────────────────────────────────────────────────────
    "sector 14":         "head_branch",
    "atul kataria":      "head_branch",
    "head branch":       "head_branch",
    "head office":       "head_branch",
    "सेक्टर 14":         "head_branch",
    "सेक्टर चौदह":       "head_branch",
    "अतुल कटारिया":      "head_branch",

    # ── Delivery ─────────────────────────────────────────────────────────────
    "pan india":         "pan_india_delivery",
    "delivery kitne":    "delivery_charges",
    "delivery kab":      "delivery_delay",
    "kitne din":         "delivery_charges",
    "delivery charges":  "delivery_charges",
    "delivery free":     "delivery_charges",
    "free delivery":     "delivery_charges",
    "कितने दिन":         "delivery_charges",
    "डिलीवरी कब":        "delivery_delay",
    "डिलीवरी कितने":     "delivery_charges",
    "डिलीवरी चार्ज":     "delivery_charges",
    "फ्री डिलीवरी":      "delivery_charges",
    "डिलीवरी टाइम":      "delivery_charges",
    "कब मिलेगा":         "delivery_delay",
    "कब आएगा":           "delivery_delay",

    # ── Offers / Discount ─────────────────────────────────────────────────────
    "discount":          "general_discount_offer",
    "offer":             "general_discount_offer",
    "chhoot":            "general_discount_offer",
    "sale":              "general_discount_offer",
    "kitna discount":    "general_discount_offer",
    "koi offer":         "general_discount_offer",
    "exchange":          "exchange_offer",
    "purana furniture":  "exchange_offer",
    "old furniture":     "exchange_offer",
    "छूट":               "general_discount_offer",
    "ऑफर":               "general_discount_offer",
    "सेल":               "general_discount_offer",
    "कितनी छूट":         "general_discount_offer",
    "कोई ऑफर":           "general_discount_offer",
    "डिस्काउंट":         "general_discount_offer",
    "एक्सचेंज":          "exchange_offer",
    "पुराना फर्नीचर":    "exchange_offer",

    # ── EMI / Payment ─────────────────────────────────────────────────────────
    "emi":               "payment_methods",
    "installment":       "payment_methods",
    "kist":              "payment_methods",
    "finance":           "payment_methods",
    "loan":              "payment_methods",
    "no cost emi":       "payment_methods",
    "payment":           "payment_methods",
    "upi":               "payment_methods",
    "cash":              "payment_methods",
    "किस्त":             "payment_methods",
    "ईएमआई":            "payment_methods",
    "किश्त":             "payment_methods",
    "फाइनेंस":           "payment_methods",
    "लोन":               "payment_methods",
    "नो कॉस्ट":          "payment_methods",

    # ── Warranty / Quality ────────────────────────────────────────────────────
    "warranty":          "warranty_quality",
    "guarantee":         "warranty_quality",
    "kitne saal":        "warranty_quality",
    "quality":           "warranty_quality",
    "toot jayega":       "warranty_quality",
    "टूट":               "warranty_quality",
    "वारंटी":            "warranty_quality",
    "गारंटी":            "warranty_quality",
    "क्वालिटी":          "warranty_quality",
    "कितने साल":         "warranty_quality",
    "मज़बूत":            "warranty_quality",
    "टिकाऊ":             "warranty_quality",

    # ── Timing / Hours ────────────────────────────────────────────────────────
    "timing":            "timing_hours",
    "time":              "timing_hours",
    "khula":             "timing_hours",
    "band":              "timing_hours",
    "sunday":            "timing_hours",
    "sunday open":       "timing_hours",
    "kab khulta":        "timing_hours",
    "kab aun":           "timing_hours",
    "टाइमिंग":           "timing_hours",
    "कब खुलता":          "timing_hours",
    "कब आऊं":            "timing_hours",
    "खुला":              "timing_hours",
    "बंद":               "timing_hours",
    "रविवार":            "timing_hours",
    "संडे":              "timing_hours",
    "सुबह":              "timing_hours",
    "शाम":               "timing_hours",

    # ── Installation / Assembly ───────────────────────────────────────────────
    "installation":      "installation_assembly",
    "assembly":          "installation_assembly",
    "fit karega":        "installation_assembly",
    "lagega kaun":       "installation_assembly",
    "इंस्टॉलेशन":        "installation_assembly",
    "फिटिंग":            "installation_assembly",
    "लगाएगा":            "installation_assembly",
    "सेटअप":             "installation_assembly",

    # ── Customisation ─────────────────────────────────────────────────────────
    "customize":         "customization",
    "customise":         "customization",
    "custom":            "customization",
    "change color":      "customization",
    "color change":      "customization",
    "size change":       "customization",
    "apna design":       "customization",
    "कस्टम":             "customization",
    "कस्टमाइज़":         "customization",
    "रंग बदल":           "customization",
    "साइज़ बदल":         "customization",
    "अपना डिज़ाइन":      "customization",

    # ── City responses (after "which area?" question) ────────────────────────
    "noida":             "store_address_request",
    "gurgaon":           "store_address_request",
    "gurugram":          "store_address_request",
    "delhi":             "store_address_request",
    "faridabad":         "store_address_request",
    "dwarka":            "store_address_request",
    "नोएडा":             "store_address_request",
    "गुड़गाँव":           "store_address_request",
    "गुरुग्राम":          "store_address_request",
    "दिल्ली":            "store_address_request",
    "फरीदाबाद":          "store_address_request",
    "द्वारका":            "store_address_request",

    # ── Goodbye / closing ─────────────────────────────────────────────────────
    "thank you":         "goodbye",
    "thanks":            "goodbye",
    "shukriya":          "goodbye",
    "dhanyawad":         "goodbye",
    "bye":               "goodbye",
    "alvida":            "goodbye",
    "theek hai":         "goodbye",
    "ok bye":            "goodbye",
    "thik hai":          "goodbye",
    "थैंक यू":           "goodbye",
    "शुक्रिया":          "goodbye",
    "धन्यवाद":           "goodbye",
    "अलविदा":            "goodbye",
    "बाय":               "goodbye",
    "ओके बाय":           "goodbye",
    "ठीक है बाय":        "goodbye",

    # ── Wholesale ─────────────────────────────────────────────────────────────
    "wholesale":         "wholesale_bulk",
    "bulk":              "wholesale_bulk",
    "bulk order":        "wholesale_bulk",
    "होलसेल":            "wholesale_bulk",
    "बल्क":              "wholesale_bulk",

    # ── Interior Design ───────────────────────────────────────────────────────
    "interior":          "interior_design",
    "interior design":   "interior_design",
    "ghar sajana":       "interior_design",
    "इंटीरियर":          "interior_design",
    "घर सजाना":          "interior_design",
    "डेकोर":             "interior_design",
}

def get_direct_match(text: str) -> str | None:
    text_lower = text.lower()
    for kw in sorted(DIRECT_KEYWORD_MAP, key=len, reverse=True):
        if kw in text_lower:
            return DIRECT_KEYWORD_MAP[kw]
    return None

def is_product_query(text: str) -> bool:
    product_keywords = [
        # Roman
        "sofa", "bed", "table", "chair", "dining", "wardrobe",
        "almirah", "almari", "furniture", "office", "curtain",
        "mattress", "palang", "mej", "kursi", "dekhna chahiye",
        "dekhna hai", "dikhao",
        # Devanagari (Saaras output)
        "सोफा", "सोफ़ा", "बेड", "पलंग", "कुर्सी", "शेयर", "चेयर",
        "डाइनिंग", "वार्डरोब", "अलमारी", "फर्नीचर", "देखना", "देखने",
        "चाहिए", "दिखाओ", "मेज", "टेबल", "ऑफिस", "गद्दा", "पर्दा",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in product_keywords)


# ─── Devanagari response override ─────────────────────────────────────────────
# ALL 21 categories from faq_database.json covered here.
# Key = exact category "id" field from JSON.
DEVANAGARI_OVERRIDES: dict[str, str] = {
    # Greeting
    "greeting":                 "नमस्कार! कृष्णा फर्नीचर में आपका स्वागत है। आपकी कैसे मदद कर सकती हूँ?",

    # Delivery
    "delivery_delay":           "डिलीवरी के लिए बिल में सेल्सपर्सन का नाम देखिए और उनसे संपर्क करिए — वो exact अपडेट देंगे।",
    "delivery_charges":         "डिलीवरी चार्जेज़ लोकेशन पर निर्भर करते हैं। एड्रेस शेयर करिए — मैं exact चार्जेज़ कन्फर्म करती हूँ।",
    "pan_india_delivery":       "हाँ बिल्कुल, पूरे भारत में डिलीवरी करते हैं। वेबसाइट से भी ऑर्डर कर सकते हैं।",

    # Location
    "store_location":           "हमारे स्टोर गुड़गाँव, दिल्ली, फरीदाबाद और नोएडा में हैं। आप किस एरिया में हैं? नज़दीकी स्टोर की डिटेल देती हूँ।",
    "store_address_request":    "ज़रूर — अपना एरिया और नंबर बताइए, मैं WhatsApp पर nearest शोरूम का address और Google Maps link भेज देती हूँ।",
    "head_branch":              "हेड ब्रांच सेक्टर चौदह गुरुग्राम में है, अतुल कटारिया चौक के पास। कब आना चाहेंगे?",

    # Offers
    "general_discount_offer":   "अभी फ्लैट चालीस प्रतिशत छूट चल रही है MRP पर हर आइटम पे। कौन सा प्रोडक्ट देखना है?",
    "exchange_offer":           "एक्सचेंज ऑफर में पुराना फर्नीचर लाओ — पहले पच्चीस प्रतिशत छूट, फिर बाकी पर और पच्चीस प्रतिशत। डबल सेविंग! कौन सा फर्नीचर एक्सचेंज करना है?",

    # Products
    "furniture_types_pricing":  "हमारे पास सोफा, बेड, डाइनिंग सेट, वार्डरोब, ऑफिस फर्नीचर, पर्दे और गद्दे हैं — सभी में चालीस प्रतिशत छूट। किस कमरे के लिए ढूंढ रहे हैं?",
    "product_specific_sofa":    "सोफा में कई ऑप्शन हैं — २-सीटर ₹३४,००० से, ३-सीटर ₹३३,००० से, L-शेप ₹७६,००० से शुरू। कौन सा साइज़ चाहिए?",
    "product_specific_bed":     "किंग साइज़ बेड विद स्टोरेज ₹७१,००० से शुरू — हाइड्रोलिक और पुलआउट दोनों। कौन सा स्टोरेज टाइप पसंद करेंगे?",
    "product_specific_dining":  "छह सीट डाइनिंग सेट एक लाख उन्नीस हज़ार से शुरू — सॉलिड वुड और मार्बल दोनों। फैमिली कितने लोगों की है?",
    "product_specific_office":  "ऑफिस फर्नीचर में टेबल बारह हज़ार से और कुर्सियाँ बीस हज़ार से शुरू। क्या चाहिए — टेबल, कुर्सी या दोनों?",

    # Services
    "manufacturing":            "हमारे खुद के प्लांट्स हैं — खेड़की दौला और बामडोली में। कोई इम्पोर्ट नहीं, सब इन-हाउस। क्वालिटी गारंटीड।",
    "interior_design":          "हाँ, इंटीरियर सर्विसेज़ भी देते हैं — फर्नीचर, लेआउट, पर्दे सब। नया घर है?",
    "wholesale_bulk":           "हाँ, होलसेल भी करते हैं। कौन सा प्रोडक्ट और कितनी क्वांटिटी? सेल्स टीम से कॉलबैक अरेंज करती हूँ।",
    "installation_assembly":    "फ्री इंस्टॉलेशन मिलती है डिलीवरी के साथ — हमारी टीम सब सेट अप कर देगी।",
    "customization":            "हाँ, साइज़, कलर और फैब्रिक customize हो सकता है। किस प्रोडक्ट में बदलाव चाहिए?",

    # Quality / Payment / Timing
    "warranty_quality":         "वारंटी उपलब्ध है — exact टर्म्स प्रोडक्ट पर निर्भर। Manufacturing defect पर replacement भी मिलती है।",
    "payment_methods":          "Cash, Card, UPI सब accept करते हैं — EMI भी उपलब्ध है selected banks पर। कौन सा ऑप्शन prefer करेंगे?",
    "timing_hours":             "स्टोर सोमवार से रविवार, सुबह दस बजे से रात आठ बजे तक खुला रहता है।",
}

# Minimum confidence to fire a FAQ — RAISED from 0.35 to 0.65
# Below this = NO MATCH → LLM, not a wrong FAQ
MIN_CONFIDENCE = 0.65


# ─── Intent Matcher ───────────────────────────────────────────────────────────
class IntentMatcher:
    def __init__(self, faq_path: str):
        with open(faq_path, encoding="utf-8") as f:
            data = json.load(f)["faq_system"]
        self.categories   = data["categories"]
        # Use our raised threshold, ignore whatever is in the JSON
        self.confidence_threshold = MIN_CONFIDENCE
        self.fallbacks    = data["fallback_responses"]
        self.greetings_pool = data["conversation_starters"]["greeting_responses"]
        self._index       = self._build_index()

    def _build_index(self):
        idx = defaultdict(list)
        for cat in self.categories:
            for ktype in ["primary", "variations", "fuzzy_match",
                          "city_specific", "product_specific"]:
                for kw in cat.get("keywords", {}).get(ktype, []):
                    idx[kw.lower()].append(cat["id"])
        return idx

    @staticmethod
    def _fuzzy(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def _score(self, text: str, cat: dict) -> float:
        score = 0.0
        kws   = cat.get("keywords", {})
        for ktype, weight in [("primary", 1.0), ("variations", 0.8),
                               ("city_specific", 0.9), ("product_specific", 0.9),
                               ("fuzzy_match", 0.5)]:
            for kw in kws.get(ktype, []):
                kl = kw.lower()
                # Skip very short keywords in fuzzy_match — too many false positives
                if ktype == "fuzzy_match" and len(kl) < 5:
                    continue
                if kl in text:
                    score += weight * 10
                # Fuzzy only for multi-word or long keywords
                elif len(kl) > 5 and any(self._fuzzy(w, kl) >= 0.85
                         for w in text.split() if len(w) > 4):
                    score += weight * 3   # conservative score for fuzzy
        return score / cat["priority"]

    def match(self, text: str) -> dict | None:
        best_score = 0.0
        best_cat   = None
        for cat in self.categories:
            s = self._score(text, cat)
            if s > best_score:
                best_score = s
                best_cat   = cat
        confidence = min(best_score / 10.0, 1.0)
        if confidence < self.confidence_threshold or best_cat is None:
            return None
        return {"category": best_cat, "confidence": confidence}

    def is_greeting(self, text: str) -> bool:
        greet_words = {"hi","hello","hey","namaste","namaskar","hii","hlo",
                       "good morning","good evening","good afternoon","salam"}
        words = set(text.lower().strip(".,!? ").split())
        # Must be ONLY greeting words — no furniture/price words mixed in
        furniture_words = {"sofa","bed","chair","table","wardrobe","almirah",
                           "dining","office","price","kitna","dekhna","chahiye",
                           "delivery","emi","offer","discount","kherki","daula"}
        if words & furniture_words:
            return False  # has furniture intent — not a greeting
        return bool(words & greet_words)

    def greeting_response(self) -> str:
        return DEVANAGARI_OVERRIDES.get("greeting",
               "नमस्कार! कृष्णा फर्नीचर में आपका स्वागत है। आपकी कैसे मदद कर सकती हूँ?")


# ─── Singleton ────────────────────────────────────────────────────────────────
_matcher: IntentMatcher | None = None

def _get_matcher() -> IntentMatcher:
    global _matcher
    if _matcher is None:
        _matcher = IntentMatcher(FAQ_PATH)
        logger.info("IntentMatcher loaded")
    return _matcher


# ─── Public API ───────────────────────────────────────────────────────────────
def get_response(raw_text: str, session=None) -> tuple[str | None, str]:
    """
    Returns (response_text, source_tag).
    response_text is None → caller should use LLM.
    source_tag: "greeting" | "faq:<id>" | "product" | "noise" | "needs_llm"
    """
    # Noise gate
    if is_noise(raw_text):
        logger.info(f"NOISE filtered: '{raw_text}'")
        return None, "noise"

    # Acknowledgement gate — short filler, no intent
    stripped = raw_text.strip(".,!? ").lower()
    if stripped in ACK_WORDS or raw_text.strip(".,!? ") in ACK_WORDS:
        logger.info(f"ACK filtered: '{raw_text}'")
        return None, "ack"

    text = fix_stt(raw_text)

    # After STT fix, check again — hallucinations get wiped to empty
    if not text.strip() or is_noise(text):
        logger.info(f"POST-FIX NOISE: '{raw_text}' → '{text}'")
        return None, "noise"

    matcher = _get_matcher()

    # Greeting shortcut
    if matcher.is_greeting(text):
        return matcher.greeting_response(), "greeting"

    # Product detection — send to webhook slot engine
    if is_product_query(text):
        logger.info(f"PRODUCT query: '{text[:40]}'")
        return None, "product"

    # Direct keyword match — bypasses fuzzy scorer entirely
    direct_cat_id = get_direct_match(text)
    if direct_cat_id:
        fired = getattr(session, "intents_fired", set()) if session else set()
        if direct_cat_id not in fired:
            if session and hasattr(session, "intents_fired"):
                session.intents_fired.add(direct_cat_id)
            response = DEVANAGARI_OVERRIDES.get(direct_cat_id)
            if response:
                logger.info(f"DIRECT MATCH:{direct_cat_id} | '{text[:40]}'")
                return response, f"faq:{direct_cat_id}"

    # Dedup: skip FAQs already answered this call
    fired = getattr(session, "intents_fired", set()) if session else set()

    result = matcher.match(text)

    if result is None:
        logger.info(f"NO MATCH ({text[:40]!r}) → LLM")
        return None, "needs_llm"

    cat = result["category"]
    cid = cat["id"]
    confidence = result["confidence"]

    if cid in fired:
        logger.info(f"FAQ {cid} already fired → LLM")
        return None, "needs_llm"

    if session and hasattr(session, "intents_fired"):
        session.intents_fired.add(cid)

    # Use Devanagari override if available, else fall back to JSON script
    if cid in DEVANAGARI_OVERRIDES:
        script = DEVANAGARI_OVERRIDES[cid]
    else:
        # Check conditional responses first
        script = cat["response"]["script"]
        cond   = cat["response"].get("conditional_responses", {})
        if cond:
            for key, alt in cond.items():
                if key.lower() in text:
                    script = alt
                    break
        # Log warning so you know to add Devanagari override for this category
        logger.warning(f"NO DEVANAGARI OVERRIDE for '{cid}' — using Roman from JSON")

    logger.info(f"FAQ:{cid} ({confidence:.0%}) | '{text[:40]}'")
    return script, f"faq:{cid}"


def build_llm_context() -> str:
    """Return a compact system prompt for LLM fallback."""
    matcher = _get_matcher()
    lines   = []
    for cat in matcher.categories:
        cid  = cat["id"]
        # Use Devanagari if available for context
        script = DEVANAGARI_OVERRIDES.get(cid, cat["response"]["script"])
        kws  = ", ".join(cat["keywords"].get("primary", [])[:5])
        lines.append(f"- {cid} [{kws}]: {script[:120]}")

    context = "\n".join(lines)
    return f"""आप प्रिया हैं — कृष्णा फर्नीचर, गुड़गाँव की sales agent।
केवल हिंदी या Hinglish में जवाब दें। अधिकतम २ वाक्य, २० शब्द।
केवल furniture, price, delivery, EMI, showroom के बारे में बात करें।
Off-topic पर: "आपके लिए कौन सा फर्नीचर चाहिए?"

STORE KNOWLEDGE:
{context}

Current offers: Flat 40% off. Exchange: 25%+25% off.
Plants: Kherki Daula & Bamdoli. Pan India delivery.
Head branch: Sector 14, Gurugram. Mon–Sun 10am–8pm."""