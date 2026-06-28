#!/usr/bin/env python3
"""
generate_cache_reactivation.py — Pre-generate all reactivation TTS cache files.

Run ONCE before launching reactivation calls:
    cd /home/voiceagent/voice-ai
    source venv/bin/activate
    export $(grep -v '^#' .env | xargs)
    python3 generate_cache_reactivation.py

Files land at: tts-cache/static/{key}_hi.wav  (e.g. react_greet_main_hi.wav)
Already-cached files are skipped. Safe to re-run.
"""

import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

STATIC_DIR = "/home/voiceagent/voice-ai/tts-cache/static"


def _cached(key: str) -> bool:
    path = os.path.join(STATIC_DIR, f"{key}_hi.wav")
    return os.path.exists(path) and os.path.getsize(path) > 1000


async def _generate_one(key: str, text: str, sem: asyncio.Semaphore) -> dict:
    if _cached(key):
        return {"key": key, "status": "SKIP"}

    async with sem:
        t0 = time.perf_counter()
        try:
            from tts_engine import get_speech
            _, url, _ = await get_speech(text, lang="hi", static_key=key)
            elapsed = time.perf_counter() - t0
            if url:
                return {"key": key, "status": "OK", "msg": f"{elapsed:.1f}s"}
            return {"key": key, "status": "FAIL", "msg": "empty URL from get_speech"}
        except Exception as exc:
            return {"key": key, "status": "FAIL", "msg": str(exc)}


async def main():
    if not os.getenv("SARVAM_API_KEY"):
        logger.error("SARVAM_API_KEY not set. Run: export $(grep -v '#' .env | xargs)")
        sys.exit(1)

    from knowledge_reactivation import REACTIVATION_SCRIPT
    os.makedirs(STATIC_DIR, exist_ok=True)

    total     = len(REACTIVATION_SCRIPT)
    pre_done  = sum(1 for k in REACTIVATION_SCRIPT if _cached(k))
    need      = total - pre_done

    logger.info("=" * 55)
    logger.info(f"Reactivation TTS cache generator")
    logger.info(f"Total keys : {total}")
    logger.info(f"Already cached: {pre_done}  |  To generate: {need}")
    logger.info(f"Static dir : {STATIC_DIR}")
    logger.info("=" * 55)

    if need == 0:
        logger.info("All files already cached. Nothing to do.")
        logger.info("To force regenerate: rm tts-cache/static/react_*.wav")
        return

    # Max 2 concurrent Sarvam API calls
    sem     = asyncio.Semaphore(2)
    tasks   = [_generate_one(k, t, sem) for k, t in REACTIVATION_SCRIPT.items()]
    results = await asyncio.gather(*tasks)

    ok      = [r for r in results if r["status"] == "OK"]
    skipped = [r for r in results if r["status"] == "SKIP"]
    failed  = [r for r in results if r["status"] == "FAIL"]

    if ok:
        logger.info(f"\nGENERATED ({len(ok)}):")
        for r in ok:
            logger.info(f"  {r['key']:<45} {r.get('msg', '')}")
    if skipped:
        logger.info(f"\nSKIPPED — already cached ({len(skipped)}):")
        for r in skipped:
            logger.info(f"  {r['key']}")
    if failed:
        logger.error(f"\nFAILED ({len(failed)}):")
        for r in failed:
            logger.error(f"  {r['key']:<45} {r.get('msg', '')}")

    logger.info(f"\nDone: {len(ok)} generated, {len(skipped)} skipped, {len(failed)} failed")

    if failed:
        logger.warning("Re-run to retry failed files.")
        sys.exit(1)

    # Verify
    files = sorted(f for f in os.listdir(STATIC_DIR) if f.startswith("react_"))
    logger.info(f"\nreact_* files on disk: {len(files)}")
    for f in files:
        kb = os.path.getsize(os.path.join(STATIC_DIR, f)) // 1024
        logger.info(f"  {f:<52} {kb} KB")


if __name__ == "__main__":
    asyncio.run(main())
