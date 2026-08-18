"""
Generate the English track of the per-plan filler audio
(ra/rb/rc_filler_1..6_en.wav) -- mirrors generate_fillers_v2.py, but reads
knowledge_react_abc_en.py and uses EN_SPEAKER for every voice (see that
module's header comment for why -- only one English voice approved so far).
"""
import asyncio
import base64
import os
import sys

sys.path.insert(0, "/home/voiceagent/voice-ai")
import httpx

from knowledge_react_abc_en import REACT_A_SCRIPT_EN, REACT_B_SCRIPT_EN, REACT_C_SCRIPT_EN, EN_SPEAKER

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
STATIC_DIR = "/home/voiceagent/voice-ai/tts-cache/static"
PACE = 0.95


async def generate_wav(key: str, text: str) -> bool:
    out_path = os.path.join(STATIC_DIR, f"{key}_en.wav")
    if os.path.exists(out_path):
        os.remove(out_path)
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
            print(f"  ERROR {r.status_code} → {key}: {r.text[:100]}")
            return False
        audio_bytes = base64.b64decode(r.json()["audios"][0])
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        print(f"  OK ({os.path.getsize(out_path) // 1024}KB) → {key}: {text!r}")
        return True
    except Exception as e:
        print(f"  FAIL → {key}: {e}")
        return False


async def main():
    if not SARVAM_API_KEY:
        print("SARVAM_API_KEY not set")
        sys.exit(1)

    targets = []
    for prefix, script in [("ra", REACT_A_SCRIPT_EN), ("rb", REACT_B_SCRIPT_EN), ("rc", REACT_C_SCRIPT_EN)]:
        for n in range(1, 7):
            key = f"{prefix}_filler_{n}"
            text = script.get(key)
            if not text:
                print(f"  WARN: key {key} not found — skipping")
                continue
            targets.append((key, text))

    print(f"\n── Generating {len(targets)} files ──────────────")
    ok = fail = 0
    for key, text in targets:
        result = await generate_wav(key, text)
        if result:
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.3)

    print(f"\n{'DONE' if fail == 0 else 'DONE WITH FAILURES'}: {ok} generated, {fail} failed")


if __name__ == "__main__":
    asyncio.run(main())
