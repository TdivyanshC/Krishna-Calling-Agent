"""
test_voice_compare.py — standalone, one-off voice comparison test.

NOT part of the production cache pipeline. Does not import or touch
knowledge_react_abc.py or generate_react_abc_v2_cache.py, and writes only to
tts-cache/test/ (not tts-cache/static/), so there's no chance of these being
picked up by the real generator or mistaken for production cache files.

Settings match generate_react_abc_v2_cache.py's actual Sarvam call exactly
(model=bulbul:v3, pace=0.95, target_language_code=hi-IN, enable_preprocessing=True)
for a fair comparison. That script sets no "temperature" — Sarvam's TTS endpoint
as used here doesn't expose one, so none is set here either.
"""
import asyncio
import base64
import os

import httpx
from dotenv import load_dotenv

load_dotenv("/home/voiceagent/voice-ai/.env")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
TEST_DIR       = "/home/voiceagent/voice-ai/tts-cache/test"

TEXT = (
    "Ji sir, main aapke budget ke hisaab se achhe options dikha dungi. "
    "Store par aur bhi designs dekhne ko milenge, aur best possible discount bhi karwa dungi. "
    "Ek baar visit karke dekh lijiye — konsa din sahi rahega?"
)

MODEL = "bulbul:v3"
PACE  = 0.95
LANG  = "hi-IN"

VOICES = ["ritu", "simran"]


async def generate(speaker: str) -> str:
    out_path = os.path.join(TEST_DIR, f"objection_{speaker}_hi.wav")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"API-Subscription-Key": SARVAM_API_KEY},
            json={
                "inputs": [TEXT],
                "target_language_code": LANG,
                "speaker": speaker,
                "pace": PACE,
                "model": MODEL,
                "enable_preprocessing": True,
            },
        )
    if r.status_code != 200:
        print(f"  ERROR {r.status_code} [{speaker}]: {r.text[:200]}")
        return ""
    audio_bytes = base64.b64decode(r.json()["audios"][0])
    with open(out_path, "wb") as f:
        f.write(audio_bytes)
    size = os.path.getsize(out_path)
    print(f"  OK ({size} bytes) [{speaker}] -> {out_path}")
    return out_path


async def main():
    if not SARVAM_API_KEY:
        print("SARVAM_API_KEY not set")
        return
    os.makedirs(TEST_DIR, exist_ok=True)
    for speaker in VOICES:
        await generate(speaker)


if __name__ == "__main__":
    asyncio.run(main())
