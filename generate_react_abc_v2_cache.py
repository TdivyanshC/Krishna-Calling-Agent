"""
Generate TTS cache for A/B/C reactivation scripts (v2).
Voice assignment (Sarvam Bulbul v3, pace=0.95):
  ra_* → ritu   |  rb_* → shreya   |  rc_* → simran   |  shared_* → shreya
"""
import asyncio
import base64
import os
import sys

sys.path.insert(0, "/home/voiceagent/voice-ai")
import httpx

from knowledge_react_abc import REACT_A_SCRIPT, REACT_B_SCRIPT, REACT_C_SCRIPT, SHARED_SCRIPT

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
STATIC_DIR = "/home/voiceagent/voice-ai/tts-cache/static"
PACE = 0.95

SPEAKER_MAP = {
    "ra": "ritu",
    "rb": "shreya",
    "rc": "simran",
    "shared": "shreya",
}

# Keys whose text changed — always force-regenerate, even if cached file exists
FORCE_REGEN = {
    "ra_greet_main", "ra_offer_main", "ra_hook_cta",
    "rb_greet_main", "rb_offer_main", "rb_hook_cta",
    "rc_greet_main", "rc_offer_main", "rc_hook_cta",
    "shared_appointment_ask", "shared_appointment_confirmed",
}

# Keys removed from scripts — delete stale audio if present
DELETED_KEYS = {"ra_wa_cta", "rc_close_conviction"}


def _speaker_for(key: str) -> str:
    prefix = key.split("_")[0]
    return SPEAKER_MAP.get(prefix, "shreya")


def _is_filler(key: str) -> bool:
    parts = key.rsplit("_", 1)
    return len(parts) == 2 and parts[1].isdigit() and 1 <= int(parts[1]) <= 6


async def generate_wav(key: str, text: str) -> bool:
    out_path = os.path.join(STATIC_DIR, f"{key}_hi.wav")
    if key not in FORCE_REGEN and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"  SKIP (cached) → {key}")
        return True
    if key in FORCE_REGEN and os.path.exists(out_path):
        os.remove(out_path)
        print(f"  DELETED stale → {key}_hi.wav")
    speaker = _speaker_for(key)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={"API-Subscription-Key": SARVAM_API_KEY},
                json={
                    "inputs": [text],
                    "target_language_code": "hi-IN",
                    "speaker": speaker,
                    "pace": PACE,
                    "model": "bulbul:v3",
                    "enable_preprocessing": True,
                },
            )
        if r.status_code != 200:
            print(f"  ERROR {r.status_code} [{speaker}] → {key}: {r.text[:100]}")
            return False
        audio_bytes = base64.b64decode(r.json()["audios"][0])
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        print(f"  OK ({os.path.getsize(out_path) // 1024}KB) [{speaker}] → {key}")
        return True
    except Exception as e:
        print(f"  FAIL [{speaker}] → {key}: {e}")
        return False


async def main():
    if not SARVAM_API_KEY:
        print("❌ SARVAM_API_KEY not set")
        sys.exit(1)

    # Delete audio for removed keys
    print("\n── Cleaning up deleted keys ──────────────")
    for key in DELETED_KEYS:
        path = os.path.join(STATIC_DIR, f"{key}_hi.wav")
        if os.path.exists(path):
            os.remove(path)
            print(f"  DELETED → {key}_hi.wav")
        else:
            print(f"  NOT FOUND (already clean) → {key}_hi.wav")

    plans = [
        ("Plan A (ritu)",    REACT_A_SCRIPT),
        ("Plan B (shreya)",  REACT_B_SCRIPT),
        ("Plan C (simran)",  REACT_C_SCRIPT),
        ("Shared (shreya)",  SHARED_SCRIPT),
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

    print(f"\n{'✅' if fail == 0 else '⚠️ '} Done: {ok} generated/verified, {skip} skipped (fillers), {fail} failed")


if __name__ == "__main__":
    asyncio.run(main())
