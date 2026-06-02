#!/usr/bin/env python3
"""
generate_cache.py — Run this ONCE to pre-generate all static TTS cache.

Run it before starting your webhook server:
    cd /home/voiceagent/voice-ai
    python3 generate_cache.py

What it generates:
  - All FAQ responses (Hindi, English, Hinglish) → tts-cache/static/
  - All filler audio files → tts-cache/fillers/
  - Prints a report of what's ready

After running: all greetings, FAQs, objections play INSTANTLY (0ms TTS wait).
Only truly novel LLM replies hit the Sarvam API.

Cost: ~60-80 Sarvam API calls (one-time). After that, zero API calls for standard responses.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add voice-ai to path
sys.path.insert(0, "/home/voiceagent/voice-ai")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    from tts_engine import generate_static_cache, static_cache_stats
    from filler_audio import generate_fillers, fillers_ready, FILLER_DIR

    logger.info("=" * 60)
    logger.info("Krishna Furniture Voice Agent — Cache Generator")
    logger.info("=" * 60)

    # Check Sarvam key
    if not os.getenv("SARVAM_API_KEY"):
        logger.error("SARVAM_API_KEY not set! Load your .env first:")
        logger.error("  source /home/voiceagent/voice-ai/.env")
        sys.exit(1)

    # Show what we're about to do
    from tts_engine import STATIC_RESPONSES
    total_static = sum(len(v) for v in STATIC_RESPONSES.values())
    from filler_audio import FILLERS
    total_fillers = sum(len(v) for v in FILLERS.values())

    logger.info(f"Static responses to generate: {total_static}")
    logger.info(f"Filler audio files to generate: {total_fillers}")
    logger.info(f"Total API calls (first run): ~{total_static + total_fillers}")
    logger.info("")

    # Step 1: Generate static cache
    logger.info("Step 1/2: Generating FAQ / greeting / objection responses...")
    await generate_static_cache()

    # Step 2: Generate fillers
    logger.info("\nStep 2/2: Generating filler audio...")
    await generate_fillers()

    # Final report
    logger.info("\n" + "=" * 60)
    stats = static_cache_stats()
    logger.info("CACHE REPORT:")
    logger.info(f"  Static responses: {stats['static_cached']}/{stats['static_total']}")
    logger.info(f"  Dynamic cache entries: {stats['dynamic_count']}")
    filler_count = len(list(FILLER_DIR.glob("filler_*.wav"))) if FILLER_DIR.exists() else 0
    logger.info(f"  Filler audio files: {filler_count}/{total_fillers}")

    if stats["static_ready"]:
        logger.info("\n✅ All static responses ready — greetings/FAQs will be INSTANT")
    else:
        missing = stats["static_total"] - stats["static_cached"]
        logger.warning(f"\n⚠️  {missing} static responses missing — check Sarvam API key/credits")

    logger.info("\nStart your webhook server now:")
    logger.info("  pkill -f webhook.py; python3 webhook.py")


if __name__ == "__main__":
    asyncio.run(main())