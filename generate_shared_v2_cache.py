"""
Generate per-plan Q&A/appointment audio + 3 universal greeting variants.
Voice assignment (Sarvam Bulbul v3, pace=0.95):
  ra_* → ritu   |  rb_* → shreya   |  rc_* → simran
  universal_greeting_ra → ritu  |  _rb → shreya  |  _rc → simran

Total: 18 Q&A/appointment keys + 3 universal greeting variants = 21 files.
Also deletes the 6 now-orphaned shared_*_hi.wav cache files.
Does NOT touch universal_greeting_hi.wav (still used by legacy reactivation campaign).
"""
import asyncio
import base64
import os
import sys

sys.path.insert(0, "/home/voiceagent/voice-ai")
import httpx

from knowledge_react_abc import REACT_A_SCRIPT, REACT_B_SCRIPT, REACT_C_SCRIPT

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
STATIC_DIR = "/home/voiceagent/voice-ai/tts-cache/static"
PACE = 0.95

SPEAKER_MAP = {"ra": "ritu", "rb": "shreya", "rc": "simran"}

UNIVERSAL_GREETING_TEXT = (
    "Namaskar ji, main Priya bol rahi hoon Krishna Furniture se. "
    "Bas 2 minute baat karni thi, abhi baat kar sakte hain?"
)

# Keys to regenerate per plan (suffix portion, without plan prefix)
QA_SUFFIXES = [
    "q_location",
    "q_name",
    "q_valuation",
    "appointment_ask",
    "appointment_confirmed",
    "appointment_reask",
]

# Orphaned shared_ files to delete (keys removed from SHARED_SCRIPT)
ORPHANED_FILES = [
    "shared_q_location_hi.wav",
    "shared_q_name_hi.wav",
    "shared_q_valuation_hi.wav",
    "shared_appointment_ask_hi.wav",
    "shared_appointment_confirmed_hi.wav",
    "shared_appointment_reask_hi.wav",
]


async def generate_wav(key: str, text: str, speaker: str) -> bool:
    out_path = os.path.join(STATIC_DIR, f"{key}_hi.wav")
    if os.path.exists(out_path):
        os.remove(out_path)
        print(f"  DELETED stale → {key}_hi.wav")
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

    # Clean up orphaned shared_ files
    print("\n── Deleting orphaned shared_* files ──────────────")
    for fname in ORPHANED_FILES:
        path = os.path.join(STATIC_DIR, fname)
        if os.path.exists(path):
            os.remove(path)
            print(f"  DELETED → {fname}")
        else:
            print(f"  NOT FOUND (already clean) → {fname}")

    ok = fail = 0

    # 18 per-plan Q&A/appointment keys
    plans = [
        ("ra", REACT_A_SCRIPT),
        ("rb", REACT_B_SCRIPT),
        ("rc", REACT_C_SCRIPT),
    ]
    print("\n── Per-plan Q&A + appointment keys ──────────────")
    for prefix, script in plans:
        speaker = SPEAKER_MAP[prefix]
        for suffix in QA_SUFFIXES:
            key = f"{prefix}_{suffix}"
            text = script.get(key)
            if not text:
                print(f"  WARN: key {key!r} not found in script — skipping")
                fail += 1
                continue
            result = await generate_wav(key, text, speaker)
            if result:
                ok += 1
            else:
                fail += 1
            await asyncio.sleep(0.3)

    # 3 universal greeting variants
    print("\n── Universal greeting variants ──────────────")
    for prefix, suffix_label in [("ra", "ritu"), ("rb", "shreya"), ("rc", "simran")]:
        key = f"universal_greeting_{prefix}"
        speaker = SPEAKER_MAP[prefix]
        result = await generate_wav(key, UNIVERSAL_GREETING_TEXT, speaker)
        if result:
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.3)

    print(f"\n{'✅' if fail == 0 else '⚠️ '} Done: {ok} generated, {fail} failed  (expected 21)")


if __name__ == "__main__":
    asyncio.run(main())
