"""
Generate TTS cache for Call 2 / Call 3 reactivation follow-up scripts.
Voice/pace assignment (Sarvam Bulbul v3):
  c2_* → ritu,   pace=1.05
  c3_* → simran, pace=1.00
Run with --only c2 or --only c3 to regenerate a single script only.
"""
import argparse
import asyncio
import base64
import os
import sys

sys.path.insert(0, "/home/voiceagent/voice-ai")
import httpx

from knowledge_react_abc import CALL2_SCRIPT, CALL3_SCRIPT

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
STATIC_DIR = "/home/voiceagent/voice-ai/tts-cache/static"

SPEAKER_MAP = {
    "c2": "ritu",
    "c3": "simran",
}

PACE_MAP = {
    "c2": 1.05,
    "c3": 1.00,
}


def _speaker_for(key: str) -> str:
    prefix = key.split("_")[0]
    return SPEAKER_MAP[prefix]


def _pace_for(key: str) -> float:
    prefix = key.split("_")[0]
    return PACE_MAP[prefix]


async def generate_wav(key: str, text: str) -> bool:
    out_path = os.path.join(STATIC_DIR, f"{key}_hi.wav")
    if os.path.exists(out_path):
        os.remove(out_path)
        print(f"  DELETED stale → {key}_hi.wav")
    speaker = _speaker_for(key)
    pace = _pace_for(key)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={"API-Subscription-Key": SARVAM_API_KEY},
                json={
                    "inputs": [text],
                    "target_language_code": "hi-IN",
                    "speaker": speaker,
                    "pace": pace,
                    "model": "bulbul:v3",
                    "enable_preprocessing": True,
                },
            )
        if r.status_code != 200:
            print(f"  ERROR {r.status_code} [{speaker} pace={pace}] → {key}: {r.text[:100]}")
            return False
        audio_bytes = base64.b64decode(r.json()["audios"][0])
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        print(f"  OK ({os.path.getsize(out_path) // 1024}KB) [{speaker} pace={pace}] → {key}")
        return True
    except Exception as e:
        print(f"  FAIL [{speaker} pace={pace}] → {key}: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["c2", "c3"], help="Regenerate only this script")
    args = parser.parse_args()

    if not SARVAM_API_KEY:
        print("❌ SARVAM_API_KEY not set")
        sys.exit(1)

    plans = [
        ("c2", "Call 2 (ritu, pace=1.05)",   CALL2_SCRIPT),
        ("c3", "Call 3 (simran, pace=1.00)", CALL3_SCRIPT),
    ]
    if args.only:
        plans = [p for p in plans if p[0] == args.only]

    ok = fail = 0
    for _, name, script in plans:
        print(f"\n── {name} ──────────────")
        for key, text in script.items():
            result = await generate_wav(key, text)
            if result:
                ok += 1
            else:
                fail += 1
            await asyncio.sleep(0.3)

    print(f"\n{'✅' if fail == 0 else '⚠️ '} Done: {ok} generated/verified, {fail} failed")


if __name__ == "__main__":
    asyncio.run(main())
