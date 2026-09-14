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
    r"\bchahiye\b":       "चाहिए",   # Roman → Devanagari
    r"\bchahie\b":        "चाहिए",
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
    "वॉर्डरोब":    "wardrobe",
    "वार्डरोब":    "wardrobe",
    "वार्ड रोब":   "wardrobe",
    "वॉर्ड रोब":   "wardrobe",
    "रब":           "wardrobe",
    "डाइनिंग":      "dining",
    "डाइनिंग टेबल": "dining",
    "बेड":           "bed",
    "अल्मारी":      "almirah",
    "अलमारी":       "almirah",
    "चेहरे":  "chair",
    "सोफ़ा":   "sofa",
    "सो फा":      "sofa",    # Saaras splits sofa
    "सो फ़ा":     "sofa",
    "सो फ":      "sofa",
    "वॉर्डरोब":  "wardrobe", # Devanagari wardrobe
    "वार्डरोब":  "wardrobe",
    "वार्ड रोब": "wardrobe", # split
    "वॉर्ड रोब": "wardrobe", # split
    "रब":         "wardrobe", # tail-end split of wardrobe
    "डाइनिंग":   "dining",   # Devanagari dining
    "डाइनिंग टेबल": "dining",
    "बेड":        "bed",      # Devanagari bed
    "सोफ़ा":      "sofa",
    "अल्मारी":   "almirah",
    "अलमारी":    "almirah",

    "सत्रह":  "sattar",
    "सतरह":  "sattar",

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
    # Greetings used as ACK (caller checking if agent is there)
    "हेलो","हेलो।","hello","hello?","हैलो","हैलो।",
    "हां बोलो","बोलो","बोलो।","हां बोलो।","जी बताइए","जी बताइए।",
    "यह।","ये।","यह","ये",  # pickup sounds

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
    "khula":             "timing_hours",
    "sunday":            "timing_hours",
    "sunday open":       "timing_hours",
    "kab khulta":        "timing_hours",
    "kab aun":           "timing_hours",
    "टाइमिंग":           "timing_hours",
    "कब खुलता":          "timing_hours",
    "कब आऊं":            "timing_hours",
    "खुला":              "timing_hours",
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

    # ── Product-specific — bare noun direct match ─────────────────────────────
    # Added 2026-09-14: matcher.match()'s confidence formula divides by
    # cat["priority"] (7 for every product_specific_* category), so a single
    # primary-keyword hit ("wardrobe" in "do you have a wardrobe?") only ever
    # scores confidence ~0.14 -- far under MIN_CONFIDENCE=0.65. That means
    # these product categories could never fire via the fuzzy matcher for an
    # ordinary one-word product question, regardless of gating order. Direct
    # match has no confidence threshold, so bare product nouns are routed
    # here instead. Longest-keyword-wins ordering in get_direct_match() means
    # a more specific phrase ("office chair", "sofa cum bed") still resolves
    # to its own category ahead of the generic noun below it.
    "office chair":      "product_specific_office",
    "office chairs":     "product_specific_office",
    "office table":      "product_specific_office",
    "office tables":     "product_specific_office",
    "study table":       "product_specific_office",
    "study tables":      "product_specific_office",
    "sofa cum bed":      "product_specific_sofa",
    "diwan cum bed":     "product_specific_sofa",
    "sofa":              "product_specific_sofa",
    "sofas":             "product_specific_sofa",
    "couch":             "product_specific_sofa",
    "couches":           "product_specific_sofa",
    "bunk bed":          "product_specific_bed",
    "bunk beds":         "product_specific_bed",
    "bed":               "product_specific_bed",
    "beds":              "product_specific_bed",
    "palang":            "product_specific_bed",
    "dining table":      "product_specific_dining",
    "dining tables":     "product_specific_dining",
    "dining set":        "product_specific_dining",
    "dining sets":       "product_specific_dining",
    "wardrobe":          "product_specific_wardrobe",
    "wardrobes":         "product_specific_wardrobe",
    "almirah":           "product_specific_wardrobe",
    "almari":            "product_specific_wardrobe",
    "lobby chair":       "product_specific_chair",
    "lobby chairs":      "product_specific_chair",
    "lounge chair":      "product_specific_chair",
    "lounge chairs":     "product_specific_chair",
    "chair":             "product_specific_chair",
    "chairs":            "product_specific_chair",
    "kursi":             "product_specific_chair",
    "सोफा":              "product_specific_sofa",
    "सोफ़ा":              "product_specific_sofa",
    "बेड":                "product_specific_bed",
    "पलंग":               "product_specific_bed",
    "डाइनिंग":            "product_specific_dining",
    "वार्डरोब":           "product_specific_wardrobe",
    "अलमारी":             "product_specific_wardrobe",
    "कुर्सी":             "product_specific_chair",
    "mattress":          "product_specific_mattress",
    "mattresses":        "product_specific_mattress",
    "gadda":             "product_specific_mattress",
    "गद्दा":              "product_specific_mattress",
    "recliner":          "product_specific_recliner",
    "recliners":         "product_specific_recliner",
    "recliner sofa":     "product_specific_recliner",
    "रिक्लाइनर":          "product_specific_recliner",
}

# Added 2026-08-19 -- fresh-lead-flow audit (same pass that hardened
# webhook_reactivation.py's matcher earlier the same day). get_direct_match()
# is pure substring matching with no negation awareness at all -- confirmed
# live via direct testing: "warranty nahi chahiye" (I don't want the
# warranty) still matched "warranty" -> warranty_quality and got the FAQ
# pitch explaining warranty terms; "exchange nahi karna mujhe" (I don't want
# to do the exchange) matched "exchange" -> exchange_offer and got the
# exchange pitch. Same failure shape as the reactivation engine's
# _is_explicit_optout()/windowed-matcher negation guard, just never built
# here. Word-proximity (not "negation appears anywhere in the utterance") --
# a genuine multi-topic turn like "sofa nahi bed chahiye, EMI hai kya" must
# still match EMI correctly; only a negation sitting near THIS keyword
# should suppress THIS match.
_DIRECT_MATCH_NEGATION_WORDS = {"nahi", "nahin", "nhi", "mat", "na",
                                 "नहीं", "नही", "ना", "मत"}
_DIRECT_MATCH_NEGATION_WINDOW = 3
# Same clause-boundary discipline as webhook_reactivation.py's
# _is_explicit_optout() -- confirmed via testing here too: without splitting
# on punctuation first, "sofa nahi bed chahiye, EMI hai kya" (I don't want a
# sofa, I want a bed -- EMI available?) suppressed the correct EMI match,
# because "nahi" from the earlier, unrelated clause fell inside EMI's word
# window. Real STT transcripts don't always include the comma, so this is a
# partial mitigation (same acknowledged limitation as _is_explicit_optout's
# own docstring), not a complete fix -- narrows the false-suppression surface
# without eliminating it.
_DIRECT_MATCH_CLAUSE_SPLIT_RE = re.compile(r"[,।;.!?]+")

# Added 2026-08-19, same audit pass -- get_direct_match() previously checked
# `kw in text_lower` as a raw SUBSTRING of the whole string, with no word-
# boundary awareness at all (unlike webhook_reactivation.py's _tokenize(),
# which deliberately avoids \b/\w+ for Devanagari-virama reasons but still
# enforces word boundaries via explicit split()-based tokens). Confirmed live
# via direct testing: "main purana customer hoon" (I'm a returning customer)
# matched the bare keyword "custom" -- sitting inside "customer" -- and
# routed to the customization FAQ instead of acknowledging the customer
# statement; "resale value kya hoga" matched "sale" inside "resale" and
# routed to the discount-offer pitch instead of the actual resale/valuation
# question. Fixed the same way as get_direct_match: pad both the keyword and
# the transcript with a leading/trailing space and require the padded
# keyword to appear as a substring of the padded, whitespace-tokenized
# transcript -- this is exactly _phrase_in_tokens()'s own exact-match tier
# in webhook_reactivation.py, reused here rather than reinvented.
_TOKEN_EDGE_PUNCT = ".,!?;:'\"()[]{}—-–।॥*"


def _tokenize_words(text: str) -> list[str]:
    return [w.strip(_TOKEN_EDGE_PUNCT) for w in text.split() if w.strip(_TOKEN_EDGE_PUNCT)]


def _is_negated_nearby(tokens: list[str], kw_tokens: list[str]) -> bool:
    """True only if EVERY occurrence of the keyword's first token in `tokens`
    has a negation word nearby -- not just any one of them. Matches
    webhook_reactivation.py's _phrase_in_tokens() negation-guard semantics
    (all(), not any()) -- found during a 2026-08-19 code review that this
    function originally used any()-across-occurrences, an inconsistency with
    its sibling implementation that could false-suppress a legitimate match
    if the same keyword-starting word happens to appear twice in one clause,
    once negated and once not (e.g. a real, non-negated question stated
    alongside an unrelated negated mention of the same word)."""
    if not kw_tokens:
        return False
    kw_first = kw_tokens[0]
    positions = [i for i, tok in enumerate(tokens) if tok == kw_first]
    if not positions:
        return False

    def _negated_at(i: int) -> bool:
        lo = max(0, i - _DIRECT_MATCH_NEGATION_WINDOW)
        hi = min(len(tokens), i + _DIRECT_MATCH_NEGATION_WINDOW + 1)
        return any(w in _DIRECT_MATCH_NEGATION_WORDS for w in tokens[lo:hi])

    return all(_negated_at(i) for i in positions)


def get_direct_match(text: str) -> str | None:
    text_lower = text.lower()
    # Clause-split and tokenize the transcript ONCE, not once per keyword --
    # found during a 2026-08-19 code review: this work was being redone
    # inside the per-keyword loop below (~174 keywords), pure wasted work for
    # the same fixed input text. Hoisted out; behavior is unchanged.
    clauses = [_tokenize_words(c) for c in _DIRECT_MATCH_CLAUSE_SPLIT_RE.split(text_lower)]
    boundary_clauses = [f" {' '.join(c)} " for c in clauses]
    for kw in sorted(DIRECT_KEYWORD_MAP, key=len, reverse=True):
        kw_tokens = kw.split()
        boundary_kw = f" {' '.join(kw_tokens)} "
        for clause_tokens, boundary_clause in zip(clauses, boundary_clauses):
            if boundary_kw in boundary_clause and not _is_negated_nearby(clause_tokens, kw_tokens):
                return DIRECT_KEYWORD_MAP[kw]
    return None

def is_product_query(text: str) -> bool:
    product_keywords = [
        # Roman
        "sofa", "bed", "table", "chair", "dining", "wardrobe",
        "almirah", "almari", "furniture", "office", "curtain",
        "mattress", "palang", "mej", "kursi", "dekhna chahiye",
        "dekhna hai", "dikhao", "recliner",
        # Devanagari (Saaras output)
        "सोफा", "सोफ़ा", "बेड", "पलंग", "कुर्सी", "शेयर", "चेयर",
        "डाइनिंग", "वार्डरोब", "अलमारी", "फर्नीचर", "देखना", "देखने",
        "चाहिए", "दिखाओ", "मेज", "टेबल", "ऑफिस", "गद्दा", "पर्दा",
        "रिक्लाइनर",
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
    # Prices below replaced 2026-09-14 with the OWNER-CONFIRMED price sheet
    # (Sep 2026 — see new_flows_pricing.py, PRICE_LIST), which supersedes
    # the website-observed figures used here earlier the same day. Per the
    # owner's own note, these run below the website-listed prices —
    # new_flows_pricing.py is the single source of truth going forward; keep
    # both in sync by hand until/unless this file is refactored to import it.
    "product_specific_sofa":    "सोफा पर-सीट प्राइसिंग है — १ सीटर ₹७,००० से ₹८,००० तक, २ सीटर ₹१५,००० से, ३ सीटर ₹२१,००० से ₹२४,००० तक, और सोफा-कम-बेड ₹३५,००० से शुरू। कौन सा साइज़ चाहिए?",
    "product_specific_bed":     "सिंगल बेड ₹१५,००० से, डबल बेड ₹२५,००० से शुरू। कौन सा साइज़ चाहिए?",
    "product_specific_dining":  "डाइनिंग सेट में शीशम वुड ४ सीटर ₹३०,००० से, ६ सीटर करीब ₹४०,००० से (कन्फर्म करना बाकी है), ८ सीटर ₹५०,००० से; मार्बल में ४ सीटर ₹४०,००० से, ६ सीटर ₹६५,००० से, ८ सीटर ₹८०,००० से शुरू। कौन सा मटेरियल और साइज़ चाहिए?",
    "product_specific_office":  "ऑफिस चेयर ₹६,००० से और ऑफिस टेबल ₹१०,००० से ₹१२,००० तक शुरू। क्या चाहिए — टेबल, कुर्सी या दोनों?",
    "product_specific_wardrobe":"वार्डरोब ₹२५,००० से शुरू, और वुडन वार्डरोब ₹१५,००० से। कौन सा टाइप चाहिए?",
    "product_specific_chair":   "लाउंज चेयर हमारी सोफा सीटिंग रेंज में आती हैं — करीब ₹७,००० से ₹८,००० प्रति सीट से शुरू, एग्ज़ैक्ट प्राइस मैं कन्फर्म करके बताती हूँ। किस जगह के लिए चाहिए?",
    "product_specific_mattress":"गद्दे में सिंगल ₹१०,००० से ₹१२,००० तक, और डबल ₹२०,००० से ₹२५,००० तक शुरू। कौन सा साइज़ चाहिए?",
    "product_specific_recliner":"मैनुअल रिक्लाइनर ₹२५,००० से, और पावर रिक्लाइनर ₹३५,००० से शुरू। कौन सा टाइप चाहिए?",

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

# ─── English response override ────────────────────────────────────────────────
# Added 2026-09-14: DEVANAGARI_OVERRIDES (and the FAQ scripts it shadows) had
# NO English variant at all — get_response()/match_faq_detour() returned this
# Hindi text unconditionally regardless of session.lang. That's a real,
# confirmed cause of "agent replies in Hindi to an English caller": the
# state_machine()'s own scripted turns are already language-aware (separate
# _hi/_en cached audio), but any turn that detoured into this FAQ layer (off-
# script questions about delivery/location/pricing/product availability, or a
# direct keyword hit) got Hindi text no matter what language the caller was
# using. Same 21+2 keys as DEVANAGARI_OVERRIDES, same short-phone-call tone
# (see lang_detect.get_lang_instruction's "en" rule: clear Indian English,
# no Hindi words). Picked via _pick_override() below, keyed off session.lang;
# "hinglish" (the default/unknown-signal bucket) intentionally still gets the
# Hindi/Hinglish text, unchanged from current behavior — only a confident
# "en" session.lang switches to this dict.
ENGLISH_OVERRIDES: dict[str, str] = {
    "greeting":                 "Hi! Welcome to Krishna Furniture. How can I help you?",

    "delivery_delay":           "For delivery status, please check the salesperson's name on your bill and contact them directly — they'll have the exact update.",
    "delivery_charges":         "Delivery charges depend on your location. Share your address and I'll confirm the exact charges.",
    "pan_india_delivery":       "Yes, absolutely — we deliver pan-India. You can also order directly from our website.",

    "store_location":           "We have stores in Gurgaon, Delhi, Faridabad and Noida. Which area are you in? I'll share the nearest store's details.",
    "store_address_request":    "Sure — just share your area and number, I'll WhatsApp you the nearest showroom's address and Google Maps link.",
    "head_branch":              "Our head branch is in Sector 14, Gurugram, near Atul Kataria Chowk. When would you like to visit?",

    "general_discount_offer":   "We currently have a flat 40% off on MRP on every item. Which product would you like to see?",
    "exchange_offer":           "With our exchange offer, bring your old furniture — get 25% off first, then another 25% off on the rest. Double savings! Which piece would you like to exchange?",

    "furniture_types_pricing":  "We have sofas, beds, dining sets, wardrobes, office furniture, curtains and mattresses — all with 40% off. Which room are you shopping for?",
    "product_specific_sofa":    "Our sofas are priced per seat — 1 seater from ₹7,000-8,000, 2 seater from ₹15,000, 3 seater from ₹21,000-24,000, and sofa-cum-bed from ₹35,000. Which size would you like?",
    "product_specific_bed":     "Single beds start from ₹15,000, double beds from ₹25,000. Which size would you like?",
    "product_specific_dining":  "Dining sets — sheesham wood: 4 seater from ₹30,000, 6 seater around ₹40,000 (still confirming that one), 8 seater from ₹50,000; marble: 4 seater from ₹40,000, 6 seater from ₹65,000, 8 seater from ₹80,000. Which material and size would you like?",
    "product_specific_office":  "Office chairs start from ₹6,000, and office tables from ₹10,000-12,000. What do you need — a table, a chair, or both?",
    "product_specific_wardrobe":"Wardrobes start from ₹25,000, and wooden wardrobes from ₹15,000. Which type would you like?",
    "product_specific_chair":   "Lounge chairs fall under our sofa seating range — starting around ₹7,000-8,000 per seat, I'll confirm the exact price for you. Which space is this for?",
    "product_specific_mattress":"Mattresses — single from ₹10,000-12,000, double from ₹20,000-25,000. Which size would you like?",
    "product_specific_recliner":"Manual recliners start from ₹25,000, and power recliners from ₹35,000. Which type would you like?",

    "manufacturing":            "We have our own manufacturing plants in Kherki Daula and Bamdoli — nothing imported, all in-house. Quality guaranteed.",
    "interior_design":          "Yes, we also offer interior design services — furniture, layout, curtains, everything. Is this for a new home?",
    "wholesale_bulk":           "Yes, we do wholesale as well. Which product and what quantity? I'll arrange a callback from our sales team.",
    "installation_assembly":    "Installation is free with delivery — our team will set everything up for you.",
    "customization":            "Yes, size, colour and fabric can be customized. Which product would you like to change?",

    "warranty_quality":         "Warranty is available — exact terms depend on the product. Replacement is also covered for manufacturing defects.",
    "payment_methods":          "We accept cash, card and UPI — EMI is also available on select banks. Which option would you prefer?",
    "timing_hours":             "The store is open Monday to Sunday, 10 AM to 8 PM.",
}


def _pick_override(cid: str, session=None) -> str | None:
    """
    Language-aware lookup replacing direct DEVANAGARI_OVERRIDES[...] access.
    "en" session.lang -> ENGLISH_OVERRIDES; everything else (hi/hinglish/
    unset) -> DEVANAGARI_OVERRIDES, matching prior behavior exactly for
    non-English callers.
    """
    lang = getattr(session, "lang", "hinglish") if session is not None else "hinglish"
    if lang == "en":
        text = ENGLISH_OVERRIDES.get(cid)
        if text:
            return text
    return DEVANAGARI_OVERRIDES.get(cid)


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

    def greeting_response(self, session=None) -> str:
        return _pick_override("greeting", session) or \
               "नमस्कार! कृष्णा फर्नीचर में आपका स्वागत है। आपकी कैसे मदद कर सकती हूँ?"


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
        return matcher.greeting_response(session), "greeting"

    # Direct keyword match — bypasses fuzzy scorer entirely
    direct_cat_id = get_direct_match(text)
    if direct_cat_id:
        fired = getattr(session, "intents_fired", set()) if session else set()
        if direct_cat_id not in fired:
            if session and hasattr(session, "intents_fired"):
                session.intents_fired.add(direct_cat_id)
            response = _pick_override(direct_cat_id, session)
            if response:
                logger.info(f"DIRECT MATCH:{direct_cat_id} | '{text[:40]}'")
                return response, f"faq:{direct_cat_id}"

    # Dedup: skip FAQs already answered this call
    fired = getattr(session, "intents_fired", set()) if session else set()

    # Fuzzy/category match — checked BEFORE the blanket is_product_query()
    # cutoff below. Fixed 2026-09-14: this used to run AFTER is_product_query(),
    # so any text containing a bare product word ("sofa", "bed", ...) short-
    # circuited straight to the "product" tag and never reached here — which
    # meant the rich product_specific_sofa/bed/dining/office/wardrobe/chair
    # categories (with real prices) were unreachable dead weight for exactly
    # the queries they exist to answer (e.g. "do you have a sofa?", "bunk
    # beds available?"). Confirmed live 2026-09-14 on test call
    # 461818cf-...: "do you have bunk beds?" / "do you have a sofa?" both got
    # intents=[] and fell through to an ungrounded LLM call (or the not-
    # understood cap) instead of this answer.
    result = matcher.match(text)

    if result is not None:
        cat = result["category"]
        cid = cat["id"]
        confidence = result["confidence"]
        if cid not in fired:
            if session and hasattr(session, "intents_fired"):
                session.intents_fired.add(cid)
            override = _pick_override(cid, session)
            if override is not None:
                logger.info(f"FAQ:{cid} ({confidence:.0%}) | '{text[:40]}'")
                return override, f"faq:{cid}"
            # No override (Hindi or English) for this category — fall through
            # to the JSON script below rather than dropping the match.
            script = cat["response"]["script"]
            cond = cat["response"].get("conditional_responses", {})
            if cond:
                for key, alt in cond.items():
                    if key.lower() in text:
                        script = alt
                        break
            logger.warning(f"NO OVERRIDE for '{cid}' — using Roman from JSON")
            logger.info(f"FAQ:{cid} ({confidence:.0%}) | '{text[:40]}'")
            return script, f"faq:{cid}"
        # else: already fired this call — fall through to product/LLM below

    # Product detection — no specific FAQ category matched (or already fired
    # this call) but the utterance does contain a product word. Send to
    # webhook slot engine / LLM rather than answering generically here.
    if is_product_query(text):
        logger.info(f"PRODUCT query: '{text[:40]}'")
        return None, "product"

    if result is None:
        logger.info(f"NO MATCH ({text[:40]!r}) → LLM")
        return None, "needs_llm"

    # result matched but cid already fired this call
    cid = result["category"]["id"]
    logger.info(f"FAQ {cid} already fired → LLM")
    return None, "needs_llm"


def match_faq_detour(text: str, session=None) -> tuple[str | None, str | None]:
    """
    Direct-keyword + fuzzy FAQ match only — no noise/greeting/product gates.
    Used by state_machine() to answer off-script questions asked mid-qualification
    (QUALIFY_PRODUCT/BUDGET/URGENCY) without derailing the funnel state.
    Returns (response_text, faq_id) or (None, None) if nothing matches.
    """
    fired = getattr(session, "intents_fired", set()) if session else set()

    direct_cat_id = get_direct_match(text)
    if direct_cat_id and direct_cat_id not in fired:
        response = _pick_override(direct_cat_id, session)
        if response:
            if session and hasattr(session, "intents_fired"):
                session.intents_fired.add(direct_cat_id)
            logger.info(f"DETOUR DIRECT MATCH:{direct_cat_id} | '{text[:40]}'")
            return response, direct_cat_id

    matcher = _get_matcher()
    result = matcher.match(text)
    if result is None:
        return None, None

    cat = result["category"]
    cid = cat["id"]
    if cid in fired:
        return None, None

    if session and hasattr(session, "intents_fired"):
        session.intents_fired.add(cid)

    override = _pick_override(cid, session)
    if override is not None:
        script = override
    else:
        script = cat["response"]["script"]
        cond = cat["response"].get("conditional_responses", {})
        if cond:
            for key, alt in cond.items():
                if key.lower() in text:
                    script = alt
                    break

    logger.info(f"DETOUR FAQ:{cid} ({result['confidence']:.0%}) | '{text[:40]}'")
    return script, cid


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
NEVER put a hyphen directly between a number and the next word (e.g. "1-seater",
"1‑सीटर", "4-seater") — this gets read aloud letter-by-letter by the phone
system instead of as a word. Always use a space instead: "1 seater", "1 सीटर",
"4 seater". This applies in both Hindi and English replies.

STORE KNOWLEDGE:
{context}

Current offers: Flat 40% off. Exchange: 25%+25% off.
Plants: Kherki Daula & Bamdoli. Pan India delivery.
Head branch: Sector 14, Gurugram. Mon–Sun 10am–8pm."""


_PRICE_RE = re.compile(r"₹\s*([\d,]+)")

# Added 2026-09-14: abbreviated "₹N हज़ार" / "₹N-M हज़ार" / "₹Nk" shorthand.
# Confirmed live on call b2845df0-...: the LLM answered "1‑सीटर ₹7‑8 हज़ार,
# 2‑सीटर ₹15 हज़ार, 3‑सीटर ₹21‑24 हज़ार" -- a 100% correct, grounded answer
# (₹7,000-8,000 / ₹15,000 / ₹21,000-24,000 really are the sofa prices) that
# got REJECTED TWICE as "ungrounded" and replaced with a generic "let me
# check" fallback, because _PRICE_RE only understands full-digit ₹ figures
# ("₹15,000") -- it read "₹15 हज़ार" as the bare, ungrounded number 15. Same
# risk for "₹Nk"/"₹N thousand" shorthand in English replies. One or two
# numbers (a range) followed by a thousand-unit word, each multiplied by
# 1000 before being checked against/added to the grounded set.
_ABBREV_THOUSAND_RE = re.compile(
    r"₹\s*(\d+(?:\.\d+)?)\s*(?:[-‑–]\s*(\d+(?:\.\d+)?))?\s*"
    r"(?:हज़ार|हजार|hazaar|hazar|k\b|thousand)",
    re.IGNORECASE,
)


def _iter_prices(text: str):
    """Yield every rupee figure stated in `text`, full-digit (₹15,000) and
    abbreviated-thousand (₹15 हज़ार, ₹7-8 हज़ार, ₹15k) forms alike, all
    normalized to whole rupees. Shared by _grounded_prices() (building the
    allowed set) and reply_has_ungrounded_price() (checking a reply against
    it) so both sides parse the same shorthand the same way."""
    for m in _ABBREV_THOUSAND_RE.finditer(text):
        yield int(float(m.group(1)) * 1000)
        if m.group(2):
            yield int(float(m.group(2)) * 1000)
    # Full-digit ₹ figures NOT immediately followed by a thousand/lakh unit
    # word (those are handled above, or are ₹-figure-times-लाख which this
    # codebase doesn't otherwise use) -- avoids double-counting "₹15" out of
    # "₹15 हज़ार" as the bare, wrong value 15.
    for m in _PRICE_RE.finditer(text):
        tail = text[m.end():m.end() + 12]
        if re.match(r"\s*(?:[-‑–]\s*\d+(?:\.\d+)?)?\s*(?:हज़ार|हजार|hazaar|hazar|k\b|thousand)", tail, re.IGNORECASE):
            continue
        yield int(m.group(1).replace(",", ""))


# Hardcoded offer figures from build_llm_context()'s "Current offers" line —
# not present in faq_database.json, so listed here explicitly rather than
# scanned. Kept in sync by hand with the string above.
_HARDCODED_GROUNDED_PRICES = set()


def _grounded_prices() -> set[int]:
    """
    Every ₹ figure that actually appears in the FAQ knowledge base — category
    scripts, price_ranges, follow_up_questions, all of it — walked
    recursively rather than re-parsing build_llm_context()'s already-truncated
    (script[:120]) summary, so this stays correct even for figures that get
    cut off the LLM's actual prompt. This is the full set of prices the LLM
    is allowed to state as fact; anything else it quotes is unverified.

    Also scans DEVANAGARI_OVERRIDES -- confirmed via regression audit
    (2026-07-15) that this was previously missing: build_llm_context() shows
    the LLM DEVANAGARI_OVERRIDES text (via `DEVANAGARI_OVERRIDES.get(cid,
    cat["response"]["script"])`) as the ground truth for what it's allowed to
    say, but this function only ever scanned matcher.categories (the raw
    faq_database.json). Real prices that only live in DEVANAGARI_OVERRIDES
    (₹34,000/₹33,000/₹76,000 sofa, ₹71,000 bed, ₹1,19,000 dining, ₹12,000/
    ₹20,000 office) were never in the grounded set, so a 100%-correct,
    script-verbatim reply quoting them was wrongly flagged as fabricated.
    Live-reproduced: reply_has_ungrounded_price() on the verbatim
    product_specific_sofa override returned True before this fix.
    """
    def _scan(obj, prices):
        if isinstance(obj, str):
            prices.update(_iter_prices(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                _scan(v, prices)
        elif isinstance(obj, list):
            for v in obj:
                _scan(v, prices)

    prices = set(_HARDCODED_GROUNDED_PRICES)
    _scan(_get_matcher().categories, prices)
    _scan(DEVANAGARI_OVERRIDES, prices)
    _scan(ENGLISH_OVERRIDES, prices)
    return prices


def reply_has_ungrounded_price(reply: str) -> bool:
    """
    True if `reply` states a specific rupee figure that isn't anywhere in the
    real knowledge base — i.e. the LLM invented it. Confirmed live: on call
    50845de5 (2026-06-09) the LLM fabricated "₹33,000 से शुरू होती है" for a
    "lobby chair set" that doesn't exist anywhere in faq_database.json — its
    own system prompt's "NEVER make up prices" instruction did not stop it.
    Caller (webhook.llm_reply) should reject/regenerate on True, not play the
    reply as-is.
    """
    grounded = _grounded_prices()
    for price in _iter_prices(reply):
        if price not in grounded:
            return True
    return False