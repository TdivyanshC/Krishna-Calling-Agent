"""
lang_detect.py — Lightweight language detector for voice agent.

Detects whether caller is speaking:
  - "hi"       → Pure Hindi / Devanagari heavy
  - "en"       → Pure English
  - "hinglish" → Mixed Hindi+English (most common)

No external ML needed. Uses script + keyword heuristics.
Fast: <1ms per call, runs before LLM/TTS.

Usage:
    from lang_detect import detect_lang
    lang = detect_lang("sofa dekhna tha mujhe")  # → "hinglish"
    lang = detect_lang("I want to see the sofa")  # → "en"
    lang = detect_lang("सोफा दिखाइए")              # → "hi"
"""

import re

# ── Hindi word list (romanised, common in Hinglish speech) ───────────────────
# "to", "the", "do", "what", "so", "he", "she", "we" intentionally excluded — ambiguous
HINDI_ROMAN_WORDS = {
    # Pronouns / question words
    "main", "mujhe", "mera", "meri", "mere", "hum", "hamare",
    "aap", "aapka", "aapki", "aapke", "aapko",
    "yeh", "woh", "isko", "usko", "inko", "unko",
    "kya", "kaun", "kahan", "kab", "kyun", "kaise", "kitna", "kitne",
    "jo", "jab", "jaise", "jitna",

    # Verbs / verb stems
    "hai", "hain", "tha", "thi", "ho", "hoga", "hogi", "honge",
    "chahiye", "chahta", "chahti", "chahte",
    "dekh", "dekhna", "dikhao", "dikhana", "dikhaiye",
    "lena", "leni", "lete", "lo", "lijiye",
    "karna", "karo", "karein", "karte", "kar",
    "bata", "batao", "bataiye", "batana",
    "dena", "dijiye",
    "aana", "aao", "aaiye",
    "jana", "jao",
    "rehna", "reh", "raho",
    "sochna", "socha", "sochenge",
    "milna", "milega", "milegi",
    "chalega", "chalegi", "chale",
    "aaega", "aaegi",

    # Common particles / connectors
    "aur", "ya", "lekin", "par", "pe", "mein", "se", "ko", "ka", "ki", "ke",
    "ne", "bhi", "toh", "na", "nahi", "nhi", "mat",
    "agar", "phir", "ab", "abhi", "pehle", "baad",
    "sab", "kuch", "bahut", "thoda", "zyada", "kam",
    "accha", "theek", "bilkul", "zaroor", "haan", "han", "ji",

    # Time / numbers
    "aaj", "kal", "parso", "ek", "teen", "char",
    "mahine", "hafte", "din", "ghante",

    # Furniture / domain specific Hinglish
    "diwan", "almirah", "almari", "palang", "takht",
    "daam", "keemat", "paisa", "rupaye",
    "samay", "kitni",
    "varanti", "rang",
    "lakdi", "lakkad", "loha",

    # Greetings / closings
    "namaste", "namaskar", "shukriya", "dhanyawad", "alvida",

    # Common expressions
    "ruko", "bhai", "yaar", "boss",
    "suno", "suniye", "dekho", "dekhiye",
}

# ── English-strong indicator words ───────────────────────────────────────────
ENGLISH_STRONG_WORDS = {
    "the", "this", "that", "these", "those", "with", "from", "have",
    "would", "could", "should", "which", "where", "when", "what",
    "please", "thank", "want", "need", "looking", "interested",
    "available", "deliver", "delivery", "price", "cost", "offer",
    "discount", "quality", "product", "furniture",
    "wardrobe", "table", "chair", "cabinet", "storage",
    "actually", "basically", "definitely", "certainly",
    "excellent", "wonderful", "perfect", "great",
    "tell", "show", "give", "make", "take", "see",
    "option", "options", "payment", "install", "installation",
}

# Words to never count as Hindi even if present in HINDI_ROMAN_WORDS
AMBIGUOUS_EXCLUDE = {"hi", "ok", "no", "me"}

# Devanagari Unicode range pattern
_DEVA = re.compile(r"[\u0900-\u097F]")


def _devanagari_ratio(text: str) -> float:
    chars = [c for c in text if c.isalpha()]
    if not chars:
        return 0.0
    deva = sum(1 for c in chars if "\u0900" <= c <= "\u097F")
    return deva / len(chars)


def _tokenize(text: str) -> list:
    return re.findall(r"[a-zA-Z\u0900-\u097F]+", text.lower())


def detect_lang(text: str) -> str:
    """
    Returns one of: "hi", "en", "hinglish"
    """
    if not text or not text.strip():
        return "hinglish"

    # Rule 1: Devanagari script → pure Hindi
    if _devanagari_ratio(text) > 0.3:
        return "hi"

    tokens = _tokenize(text)
    if not tokens:
        return "hinglish"

    hindi_count = sum(1 for t in tokens if t in HINDI_ROMAN_WORDS and t not in AMBIGUOUS_EXCLUDE)
    english_count = sum(1 for t in tokens if t in ENGLISH_STRONG_WORDS)
    total = len(tokens)

    hindi_frac = hindi_count / total
    english_frac = english_count / total

    # Both present → Hinglish
    if hindi_count >= 1 and english_count >= 1:
        return "hinglish"

    # Mostly Hindi Roman → Hinglish
    if hindi_frac >= 0.25:
        return "hinglish"

    # Strong English signal with no Hindi
    if english_frac >= 0.20 and hindi_count == 0:
        return "en"

    # Short utterances → Hinglish (safe default for Indian callers)
    if total <= 3:
        return "hinglish"

    return "hinglish"


def get_tts_language(detected_lang: str) -> tuple:
    """
    Returns (target_language_code, speaker) for Sarvam TTS.
    "hi"/"hinglish" → hi-IN, kavya
    "en"            → en-IN, meera
    """
    if detected_lang == "en":
        return "en-IN", "meera"
    return "hi-IN", "kavya"


def format_for_tts(text: str, lang: str) -> str:
    """Clean up reply text for natural TTS reading."""
    text = text.strip()
    if text and text[-1] not in ".!?,।":
        text += "."
    return text


def get_lang_instruction(detected_lang: str) -> str:
    """Returns language style instruction for LLM system prompt."""
    instructions = {
        "hi": (
            "LANGUAGE RULE: Caller is speaking Hindi. Reply ONLY in natural spoken Hindi. "
            "Use Devanagari script. Short sentences, phone-call tone, like a friendly Delhi sales rep. "
            "NEVER use formal/bookish Hindi. "
            "Example: 'जी हाँ, डिलीवरी होती है — आप कहाँ रहते हैं?'"
        ),
        "en": (
            "LANGUAGE RULE: Caller is speaking English. Reply ONLY in clear friendly Indian English. "
            "Short sentences, conversational, phone-call tone. No Hindi words in reply. "
            "Example: 'Yes, we deliver! Which area are you in?'"
        ),
        "hinglish": (
            "LANGUAGE RULE: Caller is speaking Hinglish (Hindi+English mix). "
            "Reply in natural Hinglish — mix Hindi and English exactly like a Gurgaon/Delhi "
            "sales rep would speak on a phone call. Roman script only (no Devanagari). "
            "Short sentences. Warm and friendly. "
            "Example: 'Haan ji, delivery hoti hai — aap kahan rehte hain?'"
        ),
    }
    return instructions.get(detected_lang, instructions["hinglish"])


# ── Test ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("sofa dekhna tha", "hinglish"),
        ("I want to see the sofa please", "en"),
        ("सोफा दिखाइए", "hi"),
        ("bhai delivery kitne din mein hogi", "hinglish"),
        ("what is the price of this wardrobe", "en"),
        ("kya aapke paas L-shape sofa hai", "hinglish"),
        ("haan ji mujhe bedroom set chahiye", "hinglish"),
        ("do you have EMI options available", "en"),
        ("EMI pe mil sakta hai kya", "hinglish"),
        ("ठीक है, मैं सोच कर बताता हूँ", "hi"),
        ("ok theek hai", "hinglish"),
        ("hello", "hinglish"),
        ("quality kaisi hai", "hinglish"),
        ("can you tell me more about the sofa options", "en"),
        ("aap batao", "hinglish"),
    ]

    print(f"{'Input':<48} {'Expected':<12} {'Got':<12} {'Match'}")
    print("-" * 84)
    correct = 0
    for text, expected in tests:
        got = detect_lang(text)
        match = "✓" if got == expected else "✗"
        if got == expected:
            correct += 1
        print(f"{text:<48} {expected:<12} {got:<12} {match}")

    print(f"\nAccuracy: {correct}/{len(tests)} ({correct/len(tests):.0%})")