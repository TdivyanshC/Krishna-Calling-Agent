"""
filler_audio.py — Instant filler audio system for voice agent.

WHY THIS EXISTS:
  Sarvam TTS takes 3–6s on cache miss. Without a filler, the caller
  hears dead silence and thinks the call dropped. A 0.5–1s filler
  ("haan ji, ek second...") plays INSTANTLY from disk while the real
  TTS generates in the background.

  This alone makes the agent feel 3x more human.

HOW IT WORKS:
  1. On cache MISS, play a filler immediately (from pre-generated WAV)
  2. Generate TTS in background
  3. Play the real response when ready

SETUP:
  Run generate_fillers() once at startup to pre-generate all filler WAVs.
  They are stored in tts-cache/fillers/ and served via existing audio endpoint.

FILLER STRATEGY by context:
  - General thinking  → "haan ji, ek second..."
  - After a question  → "dekhti hoon..."
  - After product ask → "product ke baare mein batati hoon..."
  - English caller    → "sure, one moment..."
  - Positive confirm  → "bilkul ji..."
"""

import asyncio
import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
FILLER_DIR = Path("/home/voiceagent/voice-ai/tts-cache/fillers")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://voice.thesocialhood.in")

# ── Filler text map ───────────────────────────────────────────────────────────
# Key: filler_id → (text_hinglish, text_hindi, text_english)
# Use the right one based on detected language

FILLERS = {
    # General thinking pause — most common
    "thinking": {
        "hinglish": "haan ji, ek second...",
        "hi":       "जी, एक सेकंड...",
        "en":       "sure, one moment...",
    },

    # Checking something
    "checking": {
        "hinglish": "dekhti hoon...",
        "hi":       "देखती हूँ...",
        "en":       "let me check...",
    },

    # After product enquiry
    "product": {
        "hinglish": "haan, batati hoon...",
        "hi":       "हाँ, बताती हूँ...",
        "en":       "yes, let me tell you...",
    },

    # Positive acknowledgement + pause
    "ack_positive": {
        "hinglish": "bilkul ji...",
        "hi":       "बिल्कुल जी...",
        "en":       "absolutely...",
    },

    # After hearing a complaint / objection
    "empathy": {
        "hinglish": "samajh sakti hoon...",
        "hi":       "समझ सकती हूँ...",
        "en":       "I understand...",
    },
}

# Pre-computed filename map (generated at startup)
_filler_cache: dict[str, str] = {}  # filler_id:lang → WAV URL


def _filler_path(filler_id: str, lang: str) -> Path:
    return FILLER_DIR / f"filler_{filler_id}_{lang}.wav"


def _filler_url(filler_id: str, lang: str) -> str:
    return f"{BASE_URL}/audio/fillers/filler_{filler_id}_{lang}.wav"


async def _generate_one_filler(filler_id: str, lang: str, text: str) -> bool:
    """Generate a single filler WAV via Sarvam TTS."""
    path = _filler_path(filler_id, lang)
    if path.exists():
        return True  # Already exists

    tts_lang, speaker = ("en-IN", "shreya") if lang == "en" else ("hi-IN", "shreya")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={
                    "API-Subscription-Key": SARVAM_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "inputs": [text],
                    "target_language_code": tts_lang,
                    "speaker": speaker,
                    "pace": 1.0,
                    "speech_sample_rate": 8000,
                    "model": "bulbul:v3",
                },
            )
        if r.status_code == 200:
            data = r.json()
            if data.get("audios"):
                wav_bytes = base64.b64decode(data["audios"][0])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(wav_bytes)
                logger.info(f"Filler generated: {path.name}")
                return True
        logger.error(f"Filler TTS failed {filler_id}/{lang}: {r.status_code}")
    except Exception as e:
        logger.error(f"Filler generation error: {e}")
    return False


async def generate_fillers() -> None:
    """
    Generate all filler WAVs at startup. Call this once in your app startup.
    Skips already-generated files. Usually takes ~10–20s total.
    """
    FILLER_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Generating filler audio files...")

    tasks = []
    for filler_id, lang_map in FILLERS.items():
        for lang, text in lang_map.items():
            tasks.append(_generate_one_filler(filler_id, lang, text))

    results = await asyncio.gather(*tasks)
    success = sum(results)
    total = len(tasks)
    logger.info(f"Fillers ready: {success}/{total}")

    # Populate cache map
    for filler_id, lang_map in FILLERS.items():
        for lang in lang_map:
            if _filler_path(filler_id, lang).exists():
                key = f"{filler_id}:{lang}"
                _filler_cache[key] = _filler_url(filler_id, lang)


def get_filler_url(filler_id: str, lang: str) -> Optional[str]:
    """
    Returns the URL of a pre-generated filler WAV, or None if not available.
    lang should be one of: "hi", "en", "hinglish"
    """
    key = f"{filler_id}:{lang}"
    url = _filler_cache.get(key)
    if url and _filler_path(filler_id, lang).exists():
        return url
    # Fallback: try hinglish if specific lang not found
    fallback_key = f"{filler_id}:hinglish"
    return _filler_cache.get(fallback_key)


def get_filler_for_context(source: str, lang: str) -> Optional[str]:
    """
    Smart filler selection based on what triggered the response.

    source: the response source tag from your FAQ/LLM pipeline
      "faq:*"      → product / checking
      "llm"        → thinking
      "needs_llm"  → thinking
      "greeting"   → None (no filler for greetings, they're instant)
      "objection"  → empathy
    """
    if source == "greeting":
        return None  # Greetings come from static cache — already instant

    if source and source.startswith("faq:"):
        filler_id = "checking"
    elif "product" in (source or ""):
        filler_id = "product"
    elif "obj" in (source or "") or "rebut" in (source or ""):
        filler_id = "empathy"
    else:
        filler_id = "thinking"

    return get_filler_url(filler_id, lang)


# ── Regeneration check on startup ─────────────────────────────────────────────

def fillers_ready() -> bool:
    """Returns True if all fillers are pre-generated."""
    for filler_id, lang_map in FILLERS.items():
        for lang in lang_map:
            if not _filler_path(filler_id, lang).exists():
                return False
    return True


def load_filler_cache() -> None:
    """Load existing fillers into cache map without API calls."""
    for filler_id, lang_map in FILLERS.items():
        for lang in lang_map:
            if _filler_path(filler_id, lang).exists():
                key = f"{filler_id}:{lang}"
                _filler_cache[key] = _filler_url(filler_id, lang)
    logger.info(f"Filler cache loaded: {len(_filler_cache)} entries")