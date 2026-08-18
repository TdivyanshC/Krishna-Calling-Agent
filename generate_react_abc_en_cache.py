"""
Generate TTS cache for the English track of the reactivation scripts
(knowledge_react_abc_en.py -- mirrors generate_react_abc_v2_cache.py's
structure exactly, but for "_en.wav" files instead of "_hi.wav").

Voice: EN_SPEAKER (knowledge_react_abc_en.py) for every single key,
regardless of prefix/plan -- only one English voice (shreya) is approved so
far (user reviewed 9 candidates 2026-08-18). This deliberately does NOT
mirror generate_react_abc_v2_cache.py's per-plan SPEAKER_MAP -- ra_* stays
ritu-voiced in Hindi but is shreya-voiced in English for now. Revisit this
script (add a real per-plan EN_SPEAKER_MAP) once more English voices are
approved.
"""
import asyncio
import base64
import os
import sys

sys.path.insert(0, "/home/voiceagent/voice-ai")
import httpx

from knowledge_react_abc_en import (
    REACT_A_SCRIPT_EN, REACT_B_SCRIPT_EN, REACT_C_SCRIPT_EN, SHARED_SCRIPT_EN,
    FRESH_CTA_SCRIPT_EN, CALL2_SCRIPT_EN, CALL3_SCRIPT_EN, EN_SPEAKER,
)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
STATIC_DIR = "/home/voiceagent/voice-ai/tts-cache/static"
PACE = 0.95

# First-time generation for a brand new dict -- no force-regen needed here
# the way the Hindi script needed it for the warm-rewrite text change (these
# _en.wav files have never existed before), but keeping the same
# skip-if-cached-and-not-forced structure for consistency / safe re-runs.
FORCE_REGEN_ALL = False
FORCE_REGEN: set[str] = set()


def _is_filler(key: str) -> bool:
    parts = key.rsplit("_", 1)
    return len(parts) == 2 and parts[1].isdigit() and 1 <= int(parts[1]) <= 6


async def generate_wav(key: str, text: str) -> bool:
    out_path = os.path.join(STATIC_DIR, f"{key}_en.wav")
    if not FORCE_REGEN_ALL and key not in FORCE_REGEN and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"  SKIP (cached) → {key}")
        return True
    if (FORCE_REGEN_ALL or key in FORCE_REGEN) and os.path.exists(out_path):
        os.remove(out_path)
        print(f"  DELETED stale → {key}_en.wav")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={"API-Subscription-Key": SARVAM_API_KEY},
                json={
                    "inputs": [text],
                    "target_language_code": "en-IN",
                    "speaker": EN_SPEAKER,
                    "pace": PACE,
                    "model": "bulbul:v3",
                    "enable_preprocessing": True,
                },
            )
        if r.status_code != 200:
            print(f"  ERROR {r.status_code} [{EN_SPEAKER}] → {key}: {r.text[:100]}")
            return False
        audio_bytes = base64.b64decode(r.json()["audios"][0])
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        print(f"  OK ({os.path.getsize(out_path) // 1024}KB) [{EN_SPEAKER}] → {key}")
        return True
    except Exception as e:
        print(f"  FAIL [{EN_SPEAKER}] → {key}: {e}")
        return False


async def main():
    if not SARVAM_API_KEY:
        print("SARVAM_API_KEY not set")
        sys.exit(1)

    plans = [
        ("Plan A (en)", REACT_A_SCRIPT_EN),
        ("Plan B (en)", REACT_B_SCRIPT_EN),
        ("Plan C (en)", REACT_C_SCRIPT_EN),
        ("Shared (en)", SHARED_SCRIPT_EN),
        ("Fresh CTA (en)", FRESH_CTA_SCRIPT_EN),
        ("Call 2 (en)", CALL2_SCRIPT_EN),
        ("Call 3 (en)", CALL3_SCRIPT_EN),
    ]

    ok = fail = skip = 0
    for name, script in plans:
        print(f"\n── {name} ──────────────")
        for key, text in script.items():
            if _is_filler(key):
                print(f"  SKIP (filler) → {key}")
                skip += 1
                continue
            result = await generate_wav(key, text)
            if result:
                ok += 1
            else:
                fail += 1
            await asyncio.sleep(0.3)

    print(f"\n{'DONE' if fail == 0 else 'DONE WITH FAILURES'}: {ok} generated/verified, {skip} skipped (fillers), {fail} failed")


if __name__ == "__main__":
    asyncio.run(main())
