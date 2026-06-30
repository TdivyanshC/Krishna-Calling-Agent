"""
Generate per-plan filler audio and shared_appointment_reask.
Voice assignment (Sarvam Bulbul v3, pace=0.95):
  ra_filler_* → ritu   |  rb_filler_* → shreya   |  rc_filler_* → simran
  shared_*    → shreya
Force-regenerates all 18 filler files + shared_appointment_reask.
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

SPEAKER_MAP = {"ra": "ritu", "rb": "shreya", "rc": "simran", "shared": "shreya"}


def _speaker_for(key: str) -> str:
    return SPEAKER_MAP.get(key.split("_")[0], "shreya")


async def generate_wav(key: str, text: str) -> bool:
    out_path = os.path.join(STATIC_DIR, f"{key}_hi.wav")
    if os.path.exists(out_path):
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
        print(f"  OK ({os.path.getsize(out_path) // 1024}KB) [{speaker}] → {key}: {text!r}")
        return True
    except Exception as e:
        print(f"  FAIL [{speaker}] → {key}: {e}")
        return False


async def main():
    if not SARVAM_API_KEY:
        print("❌ SARVAM_API_KEY not set")
        sys.exit(1)

    targets = []

    # 18 per-plan fillers (keys 1-6 for each of ra/rb/rc)
    for prefix, script in [("ra", REACT_A_SCRIPT), ("rb", REACT_B_SCRIPT), ("rc", REACT_C_SCRIPT)]:
        for n in range(1, 7):
            key = f"{prefix}_filler_{n}"
            text = script.get(key)
            if not text:
                print(f"  WARN: key {key} not found in script — skipping")
                continue
            targets.append((key, text))

    # shared_appointment_reask
    reask_text = SHARED_SCRIPT.get("shared_appointment_reask")
    if reask_text:
        targets.append(("shared_appointment_reask", reask_text))
    else:
        print("  WARN: shared_appointment_reask not found in SHARED_SCRIPT")

    print(f"\n── Generating {len(targets)} files ──────────────")
    ok = fail = 0
    for key, text in targets:
        result = await generate_wav(key, text)
        if result:
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.3)

    print(f"\n{'✅' if fail == 0 else '⚠️ '} Done: {ok} generated, {fail} failed")


if __name__ == "__main__":
    asyncio.run(main())
