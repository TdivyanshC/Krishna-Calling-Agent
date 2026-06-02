import os
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv("/home/voiceagent/voice-ai/.env")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import silero

# ============================================
# IMPORTS FOR OUR CUSTOM COMPONENTS
# ============================================
from groq import AsyncGroq
import httpx
import base64
import tempfile
from faster_whisper import WhisperModel

# ============================================
# INITIALIZE COMPONENTS
# ============================================
groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

logger.info("Loading Whisper model...")
whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
logger.info("Whisper model ready")

# Conversation memory
conversations = {}

# ============================================
# FAQ DATABASE
# ============================================
FAQS = {
    "timing": {
        "keywords": ["timing", "timings", "time", "open", "close", "kab", "band", "khula", "hours", "baje"],
        "answer": "Hum Monday se Saturday, subah 10 baje se raat 8 baje tak khule rehte hain."
    },
    "location": {
        "keywords": ["location", "address", "kahan", "where", "showroom", "shop", "jagah"],
        "answer": "Humara showroom Gurgaon mein hai. Exact address ke liye WhatsApp par contact karein."
    },
    "emi": {
        "keywords": ["emi", "loan", "installment", "finance", "kist", "monthly"],
        "answer": "Haan! Hum 0% EMI dete hain 6 mahine tak kisi bhi badi purchase par."
    },
    "delivery": {
        "keywords": ["delivery", "deliver", "home", "ghar", "bhejo"],
        "answer": "Hum free home delivery karte hain Gurgaon aur Delhi NCR mein. 7-10 working days mein."
    },
    "sofa": {
        "keywords": ["sofa", "couch", "settee"],
        "answer": "Hamare paas 3-seater aur L-shape sofa hain. Kaunsa dekhna chahenge?"
    },
    "chair": {
        "keywords": ["chair", "kursi", "dining chair", "office chair"],
        "answer": "Dining chair 2,000 se shuru, office chair 5,000 se. Kaunsa chahiye?"
    },
    "bed": {
        "keywords": ["bed", "palang", "bedroom", "mattress"],
        "answer": "Single, double aur king size bed available hai. Kis size ki zaroorat hai?"
    },
    "table": {
        "keywords": ["table", "dining table", "coffee table", "centre table"],
        "answer": "Dining table 4-seater 15,000 se shuru. Kitne log ke liye chahiye?"
    },
    "almirah": {
        "keywords": ["almirah", "wardrobe", "cupboard", "almari"],
        "answer": "2-door aur 3-door wardrobe available hai. Bedroom ke liye hai?"
    },
    "price": {
        "keywords": ["price", "cost", "kitna", "rate", "dam", "paisa", "budget"],
        "answer": "Humari furniture 5,000 se 5 lakh tak available hai. Kaunsa furniture chahiye aapko?"
    },
    "warranty": {
        "keywords": ["warranty", "guarantee", "garanti", "repair"],
        "answer": "2 saal ki warranty milti hai. Manufacturing defect par free repair ya replacement."
    },
    "discount": {
        "keywords": ["discount", "offer", "sale", "chhoot", "deal"],
        "answer": "Abhi 15% discount chal raha hai selected furniture par."
    },
    "installation": {
        "keywords": ["installation", "install", "lagana", "setup"],
        "answer": "Free installation milti hai delivery ke saath. Team aake set up kar degi."
    }
}

SYSTEM_PROMPT = """You are Priya, a sales agent for a furniture showroom in Gurgaon.
Your ONLY job is to help customers buy furniture and book showroom visits.

STRICT RULES:
- Only discuss furniture, prices, delivery, EMI, showroom visits, and appointments.
- If customer says anything unrelated, redirect: "Aapke liye kaunsa furniture chahiye?"
- Respond in Hindi or Hinglish only. Max 12 words. One question per response.
- Never make up facts. Never mention competitors. Never discuss non-furniture topics.
- Goal: get customer to visit showroom or share their furniture requirement clearly."""


def check_faq(text: str):
    text_lower = text.lower()
    for key, faq in FAQS.items():
        for keyword in faq["keywords"]:
            if keyword in text_lower:
                return faq["answer"]
    return None


async def get_groq_response(call_id: str, user_text: str) -> str:
    if call_id not in conversations:
        conversations[call_id] = []
    conversations[call_id].append({"role": "user", "content": user_text})
    history = conversations[call_id][-6:]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    response = await groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        max_tokens=80,
        temperature=0.7
    )
    reply = response.choices[0].message.content.strip()
    conversations[call_id].append({"role": "assistant", "content": reply})
    return reply


async def sarvam_tts(text: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={
                    "API-Subscription-Key": SARVAM_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "inputs": [text],
                    "target_language_code": "hi-IN",
                    "speaker": "manisha",
                    "pitch": 0,
                    "pace": 0.95,
                    "loudness": 2.5,
                    "speech_sample_rate": 8000,
                    "enable_preprocessing": True,
                    "model": "bulbul:v2"
                }
            )
        if response.status_code == 200:
            data = response.json()
            if data.get("audios"):
                return base64.b64decode(data["audios"][0])
    except Exception as e:
        logger.error(f"Sarvam error: {e}")
    return None


# ============================================
# LIVEKIT AGENT
# ============================================
class FurnitureAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions=SYSTEM_PROMPT
        )

    async def on_enter(self):
        greeting = "Namaste! Main Priya hun, aapke furniture store ki taraf se. Aaj main aapki kaise madad kar sakti hun?"
        await self.session.say(greeting)


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    logger.info(f"Connected to room: {ctx.room.name}")

    session = AgentSession(
        vad=silero.VAD.load(),
    )

    await session.start(
        room=ctx.room,
        agent=FurnitureAgent(),
        room_input_options=RoomInputOptions(),
    )

    await session.wait_for_disconnect()


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            worker_type=agents.WorkerType.ROOM,
        )
    )
