import asyncio, base64, os, httpx

KEY = os.getenv("SARVAM_API_KEY", "")
TEXT = "नमस्ते! मैं प्रिया बात कर रही हूँ Krishna Furniture से — आपने हमारे furniture में interest दिखाया था, तो personally connect करना चाहती थी। एक मिनट है आपके पास?"

VARIANTS = [
    {"name": "pace_080", "pace": 0.80},
    {"name": "pace_085", "pace": 0.85},
    {"name": "pace_090", "pace": 0.90},
    {"name": "pace_095", "pace": 0.95},
    {"name": "pace_100", "pace": 1.00},
    {"name": "pace_105", "pace": 1.05},
]

async def gen(v):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"API-Subscription-Key": KEY, "Content-Type": "application/json"},
            json={
                "inputs": [TEXT],
                "target_language_code": "hi-IN",
                "speaker": "kavya",
                "pace": v["pace"],
                "speech_sample_rate": 8000,
                "model": "bulbul:v3",
            }
        )
    if r.status_code != 200:
        print(f"❌ {v['name']}: {r.text[:120]}")
        return
    raw = base64.b64decode(r.json()["audios"][0])
    path = f"/home/voiceagent/voice-ai/tts-cache/voice_test_{v['name']}.wav"
    with open(path, "wb") as f:
        f.write(raw)
    print(f"✅ {v['name']}")

async def main():
    for v in VARIANTS:
        await gen(v)
        await asyncio.sleep(0.3)

asyncio.run(main())
