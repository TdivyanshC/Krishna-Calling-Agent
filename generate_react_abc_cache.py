"""Generate TTS cache for A/B/C reactivation scripts."""
import asyncio, base64, os, sys, wave
sys.path.insert(0, "/home/voiceagent/voice-ai")
import httpx
from knowledge_react_abc import REACT_A_SCRIPT, REACT_B_SCRIPT, REACT_C_SCRIPT

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
STATIC_DIR     = "/home/voiceagent/voice-ai/tts-cache/static"
SPEAKER        = "shreya"
PACE           = 1.05

async def generate_wav(key: str, text: str):
    out_path = os.path.join(STATIC_DIR, f"{key}_hi.wav")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"  SKIP → {key}")
        return True
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={"API-Subscription-Key": SARVAM_API_KEY},
                json={"inputs": [text], "target_language_code": "hi-IN",
                      "speaker": SPEAKER, "pace": PACE, "model": "bulbul:v3",
                      "enable_preprocessing": True}
            )
        if r.status_code != 200:
            print(f"  ERROR {r.status_code} → {key}: {r.text[:80]}")
            return False
        audio_bytes = base64.b64decode(r.json()["audios"][0])
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        print(f"  OK ({os.path.getsize(out_path)//1024}KB) → {key}")
        return True
    except Exception as e:
        print(f"  FAIL → {key}: {e}")
        return False

async def main():
    plans = [("Plan A", REACT_A_SCRIPT), ("Plan B", REACT_B_SCRIPT), ("Plan C", REACT_C_SCRIPT)]
    ok = fail = skip = 0
    for name, script in plans:
        print(f"\n── {name} ──────────────")
        for key, text in script.items():
            if any(key.endswith(f"_{i}") for i in range(1,7)):
                print(f"  SKIP (filler) → {key}")
                skip += 1
                continue
            if await generate_wav(key, text):
                ok += 1
            else:
                fail += 1
            await asyncio.sleep(0.3)
    print(f"\n✅ Done: {ok} generated, {skip} skipped, {fail} failed")

if __name__ == "__main__":
    if not SARVAM_API_KEY:
        print("❌ SARVAM_API_KEY not set"); sys.exit(1)
    asyncio.run(main())
