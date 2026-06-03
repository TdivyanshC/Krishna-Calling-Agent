"""
tts_engine.py — Language-aware TTS with smart caching layer.

ARCHITECTURE:
  Layer 1: Static cache  — pre-generated FAQs/greetings (0ms, instant)
  Layer 2: Dynamic cache — hash-keyed past responses (0ms, from disk)
  Layer 3: Sarvam API    — fresh generation (3–6s, saved for next time)

KEY IMPROVEMENTS OVER OLD SYSTEM:
  1. Language-aware: uses correct voice per detected language
  2. Cache keys include language suffix → no cross-language cache collisions
  3. Parallel filler + TTS: filler plays while TTS generates
  4. Normalizes text before hashing → slight phrasing variants hit same cache

INTEGRATION:
  Replace your existing text_to_speech() and get_tts_audio() functions
  with get_speech() from this module.
"""

import asyncio
import base64
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SARVAM_API_KEY  = os.getenv("SARVAM_API_KEY", "")
BASE_URL        = os.getenv("BASE_URL", "https://voice.thesocialhood.in")
CACHE_DIR       = Path("/home/voiceagent/voice-ai/tts-cache")
STATIC_DIR      = CACHE_DIR / "static"
DYNAMIC_DIR     = CACHE_DIR / "dynamic"
FILLER_DIR      = CACHE_DIR / "fillers"

TTS_TIMEOUT     = 20  # seconds
TTS_PACE        = 1.00
TTS_SAMPLE_RATE = 8000
TTS_MODEL       = "bulbul:v3"

# ── Voice config per language ─────────────────────────────────────────────────
VOICE_CONFIG = {
    "hi":       {"target_language_code": "hi-IN", "speaker": "kavya"},
    "hinglish": {"target_language_code": "hi-IN", "speaker": "kavya"},
    "en":       {"target_language_code": "en-IN", "speaker": "kavya"},
}

# ── Static cache: pre-generated responses keyed by source tag ─────────────────
# Add every FAQ response here — these are generated ONCE and played forever.
# Format: "cache_key": {"hi": "...", "hinglish": "...", "en": "..."}
# Use generate_static_cache() below to pre-generate them all.

STATIC_RESPONSES = {
    # ── Greetings ──────────────────────────────────────────────────────────────
    "greeting_inbound": {
        "hinglish": "Krishna Furniture mein aapka swagat hai, main Priya bol rahi hoon — aapki kya madad kar sakti hoon?",
        "hi":       "कृष्णा फर्नीचर में आपका स्वागत है, मैं प्रिया बोल रही हूँ — आपकी कैसे मदद कर सकती हूँ?",
        "en":       "Welcome to Krishna Furniture, this is Priya speaking — how can I help you today?",
    },
    "greeting_outbound": {
        "hinglish": "Namaskar! Main Priya baat kar rahi hoon Krishna Furniture se — aapne hamare furniture mein interest dikhaya tha, toh personally connect karna chahti thi. Ek minute hai aapke paas?",
        "hi":       "नमस्ते! मैं प्रिया बात कर रही हूँ Krishna Furniture से — आपने हमारे furniture में interest दिखाया था, तो personally connect करना चाहती थी। एक मिनट है आपके पास?",
        "en":       "Hello! This is Priya from Krishna Furniture — you had shown interest in our furniture, so I wanted to personally connect. Do you have just a minute?",
    },

    # ── Qualification questions ────────────────────────────────────────────────
    "qualify_product": {
        "hinglish": "Kya dhundh rahe hain aap — sofa, bed, wardrobe, ya kuch aur?",
        "hi":       "आप क्या ढूंढ रहे हैं — सोफा, बेड, वार्डरोब, या कुछ और?",
        "en":       "What are you looking for — sofa, bed, wardrobe, or something else?",
    },
    "qualify_budget": {
        "hinglish": "Budget roughly kitna soch rahe hain — koi idea ho toh batao?",
        "hi":       "Budget में roughly कितना सोच रहे हैं — कोई idea हो तो बताइए?",
        "en":       "What's your rough budget in mind — any idea?",
    },
    "qualify_urgency": {
        "hinglish": "Aur kab tak chahiye — koi jaldi hai ya time hai?",
        "hi":       "और कब तक चाहिए — कोई जल्दी है, या अभी देख रहे हैं बस?",
        "en":       "And when do you need it — is there a rush or just browsing for now?",
    },
    "wrap_whatsapp": {
        "hinglish": "Bilkul ji, main aapko WhatsApp pe options bhej rahi hoon. Koi aur sawaal?",
        "hi":       "बिल्कुल जी, मैं आपको WhatsApp पर options भेज रही हूँ। कोई और सवाल?",
        "en":       "Perfect, I'll send you the options on WhatsApp. Any other questions?",
    },
    "goodbye": {
        "hinglish": "Bahut shukriya aapka. Krishna Furniture ki taraf se aapka din shubh ho!",
        "hi":       "बहुत शुक्रिया आपका। कृष्णा फर्नीचर की तरफ से आपका दिन शुभ हो!",
        "en":       "Thank you so much for calling. Have a wonderful day from all of us at Krishna Furniture!",
    },

    # ── Outbound response handlers ────────────────────────────────────────────
    "hook_positive": {
        "hi": "बहुत अच्छा! देखिए, इस महीने हमारे store में 35% तक की छूट चल रही है — और कुछ बेहतरीन नया collection भी आया है। आप किस तरह का furniture देख रहे हैं — sofa, bed, dining, या कुछ और?",
        "hinglish": "Bahut achha! Is mahine hamare store mein 35% tak ki choot chal rahi hai — aur kuch behtareen naya collection bhi aaya hai. Aap kis tarah ka furniture dekh rahe hain?",
        "en": "Great! We have up to 35% off this month and some stunning new arrivals too. What kind of furniture are you looking for — sofa, bed, dining, or something else?",
    },
    "hook_hesitant": {
        "hi": "जी माफ़ी चाहती हूँ अगर समय गलत हो — बस इसलिए call किया क्योंकि इस महीने special sale है और आपको personally बताना चाहती थी। बस 30 सेकंड — कौन सा furniture देख रहे थे आप?",
        "hinglish": "Ji maafi chahti hoon agar samay galat ho — bas isliye call kiya kyunki is mahine special sale hai. Bas 30 second — kaun sa furniture dekh rahe the aap?",
        "en": "I'm sorry if this is a bad time — I called because we have a special sale this month and I wanted to personally let you know. Just 30 seconds — what furniture were you looking for?",
    },
    "hook_negative_1": {
        "hi": "जी समझ गई, कोई बात नहीं। बस एक बात — अगर कभी भी घर के लिए furniture का ख़याल आए, हम pan-India delivery करते हैं और installation भी free है। WhatsApp पर कुछ options भेज दूँ बस एक बार देखने के लिए?",
        "hinglish": "Ji samajh gayi, koi baat nahi. Bas ek baat — agar kabhi bhi furniture ka khayal aaye, hum pan-India delivery karte hain aur installation bhi free hai. WhatsApp pe kuch options bhej doon?",
        "en": "I understand, no problem at all. Just one thing — whenever you think of furniture, we offer pan-India delivery and free installation. Can I send you some options on WhatsApp, just to browse?",
    },
    "hook_negative_2": {
        "hi": "बिल्कुल, आपका समय लेने के लिए माफ़ी। जब भी ज़रूरत हो — Krishna Furniture हमेशा यहाँ है। आपका दिन शुभ हो!",
        "hinglish": "Bilkul, aapka samay lene ke liye maafi. Jab bhi zaroorat ho — Krishna Furniture hamesha yahan hai. Aapka din shubh ho!",
        "en": "Of course, I'm sorry for taking your time. Whenever you need us — Krishna Furniture is always here. Have a wonderful day!",
    },
    "product_vague": {
        "hi": "बिल्कुल! एक काम करते हैं — मैं आपको WhatsApp पर हमारे सबसे popular options भेज देती हूँ, अपने हिसाब से देख लीजिए। नंबर यही है ना आपका?",
        "hinglish": "Bilkul! Ek kaam karte hain — main aapko WhatsApp pe hamare sabse popular options bhej deti hoon. Number yahi hai na aapka?",
        "en": "Of course! Let me send you our most popular options on WhatsApp — browse at your own time. This is your number, right?",
    },
    "product_busy": {
        "hi": "जी ज़रूर, आपका time waste नहीं करूँगी। WhatsApp पर थोड़ी देर में options भेजती हूँ — एक बार ज़रूर देखिएगा!",
        "hinglish": "Ji zaroor, aapka time waste nahi karungi. WhatsApp pe thodi der mein options bhejti hoon — ek baar zaroor dekhiyega!",
        "en": "Of course, I won't take your time. I'll send options on WhatsApp shortly — do take a look when you can!",
    },

    # ── Pre-cached wrap-up variants per product ────────────────────────────
    "wrap_up_dining": {
        "hi": "बिल्कुल! Dining set के कुछ बेहतरीन options अभी WhatsApp पर भेज रही हूँ — 6 seater से लेकर 8 seater तक, solid wood भी और premium लेमिनेट भी, आपके budget में perfect choices हैं। थोड़ी देर में message आएगा — एक बार ज़रूर देखिएगा!",
        "hinglish": "Bilkul! Dining set ke kuch behtareen options abhi WhatsApp pe bhej rahi hoon — 6 seater se lekar 8 seater tak, solid wood bhi aur premium laminate bhi. Thodi der mein message aayega!",
        "en": "Perfect! I'm sending you our best dining set options on WhatsApp right now — from 6 seater to 8 seater, solid wood and premium laminate, all within your budget. Message coming shortly!",
    },
    "wrap_up_sofa": {
        "hi": "बिल्कुल! Sofa के options अभी WhatsApp पर भेज रही हूँ — L-shape, 5 seater, recliner — fabric और leather दोनों में। थोड़ी देर में आएगा, एक बार देखिएगा!",
        "hinglish": "Bilkul! Sofa ke options abhi WhatsApp pe bhej rahi hoon — L-shape, 5 seater, recliner — fabric aur leather dono mein. Thodi der mein aayega!",
        "en": "Perfect! Sending sofa options on WhatsApp now — L-shape, 5 seater, recliner — available in both fabric and leather. Coming shortly!",
    },
    "wrap_up_bed": {
        "hi": "बिल्कुल! Bed के options अभी भेज रही हूँ — king size, queen size, hydraulic storage beds — सब आपके budget में perfect हैं। थोड़ी देर में WhatsApp पर आएगा!",
        "hinglish": "Bilkul! Bed ke options abhi bhej rahi hoon — king size, queen size, hydraulic storage beds — sab aapke budget mein. Thodi der mein WhatsApp pe aayega!",
        "en": "Perfect! Sending bed options now — king size, queen size, hydraulic storage beds — all within your budget. Coming to WhatsApp shortly!",
    },
    "wrap_up_office": {
        "hi": "बिल्कुल! Office furniture के options अभी WhatsApp पर भेज रही हूँ — ergonomic chairs, executive desks, workstations — सब ready है। थोड़ी देर में मिलेगा!",
        "hinglish": "Bilkul! Office furniture ke options abhi WhatsApp pe bhej rahi hoon — ergonomic chairs, executive desks, workstations. Thodi der mein milega!",
        "en": "Perfect! Sending office furniture options now — ergonomic chairs, executive desks, workstations — all ready. Coming shortly!",
    },
    "wrap_up_general": {
        "hi": "बिल्कुल! मैं अभी आपको WhatsApp पर हमारे best options भेज रही हूँ — एक बार ज़रूर देखिएगा, आपको कुछ न कुछ पसंद ज़रूर आएगा!",
        "hinglish": "Bilkul! Main abhi aapko WhatsApp pe hamare best options bhej rahi hoon. Ek baar zaroor dekhiyega!",
        "en": "Perfect! I'm sending you our best options on WhatsApp right now — do take a look, I'm sure something will catch your eye!",
    },

    # ── Post wrap-up objection handlers ───────────────────────────────────
    "obj_think_wrapup": {
        "hi": "बिल्कुल सोचिए! बस एक बात — यह sale महीने के अंत तक ही है और कुछ designs की limited pieces बची हैं। WhatsApp पर photos देख लीजिए, फिर decide करिए — कोई pressure नहीं!",
        "hinglish": "Bilkul sochiye! Bas ek baat — yeh sale mahine ke ant tak hi hai aur kuch designs ki limited pieces bachi hain. WhatsApp pe photos dekh lijiye, phir decide kariye — koi pressure nahi!",
        "en": "Of course, take your time! Just one thing — this sale ends at month's end and some designs have limited stock left. Check the WhatsApp photos, then decide — no pressure at all!",
    },
    "obj_online_wrapup": {
        "hi": "सर, online में जो दिखता है वो quality और जो मिलता है वो quality — दोनों अलग होती हैं। हमारे अपने manufacturing plants हैं, बीच का profit हम नहीं लेते — आपको सीधे factory price देते हैं। एक बार photos देखिए, फिर compare कीजिए खुद।",
        "hinglish": "Sir, online mein jo dikhta hai woh quality aur jo milta hai woh quality — dono alag hoti hain. Hamare apne manufacturing plants hain — aapko seedha factory price dete hain. Ek baar photos dekhiye phir compare kariye.",
        "en": "Sir, what you see online and what you receive are often very different qualities. We have our own manufacturing plants — you get factory-direct pricing. Check the photos once and compare yourself.",
    },
    "goodbye_warm": {
        "hi": "बहुत बहुत शुक्रिया! आपसे बात करके अच्छा लगा। अगर कोई भी सवाल हो तो बेझिझक call या WhatsApp कीजिए — Krishna Furniture हमेशा ready है। आपका दिन शानदार हो!",
        "hinglish": "Bahut bahut shukriya! Aapse baat karke achha laga. Agar koi bhi sawaal ho toh behjhijak call ya WhatsApp kariye — Krishna Furniture hamesha ready hai. Aapka din shandar ho!",
        "en": "Thank you so much! It was lovely talking to you. If you ever have any questions, call or WhatsApp anytime — Krishna Furniture is always here for you. Have a fantastic day!",
    },

    # ── Objections ─────────────────────────────────────────────────────────────
    "obj_expensive": {
        "hinglish": "Samajh sakti hoon, sir. Already 40% discount include hai. EMI mein convert karein toh sirf 3-4 hazaar per month padta hai. Budget batao — usi range mein best option dhundh leti hoon.",
        "hi":       "समझ सकती हूँ, सर। पहले से 40% छूट शामिल है। EMI में convert करें तो सिर्फ 3-4 हज़ार प्रति माह पड़ता है। बजट बताइए — उस रेंज में best option ढूंढ लेती हूँ।",
        "en":       "I understand. The 40% discount is already included. On EMI it's just 3-4 thousand per month. Tell me your budget and I'll find the best option in that range.",
    },
    "obj_think": {
        "hinglish": "Bilkul sochiye. Bas yeh offer limited time ka hai. Ek baar store aiye, quality feel kariye — phir decide kariye. Kaunsa din suit karega?",
        "hi":       "बिल्कुल सोचिए। बस यह offer limited time का है। एक बार स्टोर आइए, quality feel करिए — फिर decide करिए। कौन सा दिन suit करेगा?",
        "en":       "Of course, take your time. But this offer is for a limited time. Visit our store once, feel the quality — then decide. Which day works for you?",
    },
    "obj_online": {
        "hinglish": "Sir, online mein delivery, assembly aur quality guarantee alag hoti hai. Hamare khud ke plants hain — quality aur after-sales dono hamare haath mein. Ek baar dekhne aiye, fark samajh aayega.",
        "hi":       "सर, online में delivery, assembly और quality guarantee अलग होती है। हमारे खुद के plants हैं — quality और after-sales दोनों हमारे हाथ में। एक बार देखने आइए, फर्क समझ आएगा।",
        "en":       "Sir, with online you get different delivery, assembly and quality guarantees. We have our own manufacturing plants — quality and after-sales are both in our hands. Visit once and you'll see the difference.",
    },
    "obj_busy": {
        "hinglish": "Ji zaroor. Tab tak main aapko WhatsApp pe kuch options bhejti hoon. Number confirm kar loon?",
        "hi":       "जी ज़रूर। तब तक मैं आपको WhatsApp पर कुछ options भेजती हूँ। नंबर confirm कर लूँ?",
        "en":       "Of course. I'll send you some options on WhatsApp in the meantime. Can I confirm your number?",
    },

    # ── FAQs ───────────────────────────────────────────────────────────────────
    "faq_location": {
        "hinglish": "Hamare stores Gurgaon, Delhi, Faridabad aur Noida mein hain. Aap kis area mein hain? Nearest store ki detail deti hoon.",
        "hi":       "हमारे stores गुड़गाँव, दिल्ली, फरीदाबाद और नोएडा में हैं। आप किस area में हैं? Nearest store की detail देती हूँ।",
        "en":       "We have stores in Gurgaon, Delhi, Faridabad and Noida. Which area are you in? I'll give you the nearest store details.",
    },
    "faq_delivery": {
        "hinglish": "Delivery 7 se 14 din mein hoti hai. Same city mein free delivery hai. Installation bhi free mein milti hai.",
        "hi":       "Delivery 7 से 14 दिन में होती है। Same city में free delivery है। Installation भी free मिलती है।",
        "en":       "Delivery takes 7 to 14 days. Same-city delivery is free, and installation is also complimentary.",
    },
    "faq_emi": {
        "hinglish": "Haan ji, EMI available hai — 6, 12, aur 24 months ke options hain. No-cost EMI bhi hai kuch products pe. Kaunsa product dekhna tha?",
        "hi":       "हाँ जी, EMI available है — 6, 12, और 24 महीनों के options हैं। No-cost EMI भी है कुछ products पर। कौन सा product देखना था?",
        "en":       "Yes, EMI is available in 6, 12, and 24 month options. No-cost EMI is also available on select products. Which product were you looking at?",
    },
    "faq_warranty": {
        "hinglish": "1 saal ki warranty milti hai manufacturing defects pe. Cushions pe 6 mahine ki warranty hai. After-sales support hamare store pe available hai.",
        "hi":       "1 साल की warranty मिलती है manufacturing defects पर। Cushions पर 6 महीने की warranty है। After-sales support हमारे store पर available है।",
        "en":       "We offer 1 year warranty on manufacturing defects and 6 months on cushions. After-sales support is available at our store.",
    },
    "faq_customisation": {
        "hinglish": "Haan, customisation hoti hai — colour, fabric, size sab change ho sakta hai. 15 se 20 din extra lagte hain. Kya customise karna tha?",
        "hi":       "हाँ, customisation होती है — colour, fabric, size सब change हो सकता है। 15 से 20 दिन extra लगते हैं। क्या customise करना था?",
        "en":       "Yes, customisation is available — colour, fabric and size can all be changed. It takes an extra 15 to 20 days. What would you like to customise?",
    },
    "faq_repeat": {
        "hinglish": "Haan ji, main yahan hoon — phir se bolo?",
        "hi":       "हाँ जी, मैं यहाँ हूँ — फिर से बोलिए?",
        "en":       "Yes, I'm here — could you say that again?",
    },
    # ── Additional FAQ static responses ──────────────────────────────────────
    "store_location": {
        "hinglish": "Hamare stores Gurgaon, Delhi, Faridabad aur Noida mein hain. Aap kis area mein hain? Nearest store ki detail deti hoon.",
        "hi":       "हमारे स्टोर गुड़गाँव, दिल्ली, फरीदाबाद और नोएडा में हैं। आप किस एरिया में हैं? नज़दीकी स्टोर की डिटेल देती हूँ।",
        "en":       "We have stores in Gurgaon, Delhi, Faridabad and Noida. Which area are you in? I will give you the nearest store details.",
    },
    "delivery_charges": {
        "hinglish": "Delivery 7 se 14 din mein hoti hai. Same city mein free delivery hai, installation bhi free.",
        "hi":       "डिलीवरी 7 से 14 दिन में होती है। Same city में फ्री डिलीवरी है, इंस्टॉलेशन भी फ्री।",
        "en":       "Delivery takes 7 to 14 days. Same city delivery is free and installation is complimentary.",
    },
    "delivery_delay": {
        "hinglish": "Delivery update ke liye bill mein salesperson ka naam dekhiye aur unse contact karein — wo exact update denge.",
        "hi":       "डिलीवरी अपडेट के लिए बिल में सेल्सपर्सन का नाम देखिए और उनसे संपर्क करिए — वो exact अपडेट देंगे।",
        "en":       "For delivery updates, please check the salesperson name on your bill and contact them directly for an exact update.",
    },
    "general_discount_offer": {
        "hinglish": "Abhi flat 40% discount chal raha hai MRP pe har item pe. Kaun sa product dekhna hai?",
        "hi":       "अभी फ्लैट 40% छूट चल रही है MRP पर हर आइटम पे। कौन सा प्रोडक्ट देखना है?",
        "en":       "We currently have a flat 40% discount on MRP across all items. Which product are you looking for?",
    },
    "exchange_offer": {
        "hinglish": "Exchange offer mein purana furniture lao — pehle 25% off, phir baaki pe aur 25%. Double saving! Kaun sa furniture exchange karna hai?",
        "hi":       "एक्सचेंज ऑफर में पुराना फर्नीचर लाओ — पहले 25% छूट, फिर बाकी पर और 25%। Double saving! कौन सा फर्नीचर एक्सचेंज करना है?",
        "en":       "In our exchange offer, bring your old furniture and get 25% off first, then another 25% on the rest. Double saving! What furniture would you like to exchange?",
    },
    "warranty_quality": {
        "hinglish": "Warranty available hai — exact terms product pe depend karti hai. Manufacturing defect pe replacement bhi milti hai.",
        "hi":       "वारंटी उपलब्ध है — exact terms प्रोडक्ट पर निर्भर। Manufacturing defect पर replacement भी मिलती है।",
        "en":       "Warranty is available and varies by product. Manufacturing defects are covered with replacement.",
    },
    "timing_hours": {
        "hinglish": "Store Monday se Sunday, subah 10 baje se raat 8 baje tak khula rehta hai.",
        "hi":       "स्टोर सोमवार से रविवार, सुबह 10 बजे से रात 8 बजे तक खुला रहता है।",
        "en":       "The store is open Monday to Sunday, from 10 AM to 8 PM.",
    },
    "installation_assembly": {
        "hinglish": "Free installation milti hai delivery ke saath — hamari team sab set up kar degi.",
        "hi":       "फ्री इंस्टॉलेशन मिलती है डिलीवरी के साथ — हमारी टीम सब सेट अप कर देगी।",
        "en":       "Free installation is included with delivery. Our team will set everything up for you.",
    },
    "customization": {
        "hinglish": "Haan, size, color aur fabric customize ho sakta hai. Kis product mein badlav chahiye?",
        "hi":       "हाँ, साइज़, कलर और फैब्रिक customize हो सकता है। किस प्रोडक्ट में बदलाव चाहिए?",
        "en":       "Yes, size, colour and fabric can all be customised. Which product would you like to change?",
    },
    "manufacturing": {
        "hinglish": "Hamare khud ke plants hain — Kherki Daula aur Bamdoli mein. Koi import nahi, sab in-house. Quality guaranteed.",
        "hi":       "हमारे खुद के प्लांट्स हैं — खेड़की दौला और बामडोली में। कोई इम्पोर्ट नहीं, सब इन-हाउस। क्वालिटी गारंटीड।",
        "en":       "We have our own manufacturing plants in Kherki Daula and Bamdoli. No imports, everything in-house. Quality guaranteed.",
    },
    "store_address_request": {
        "hinglish": "Bilkul! Main aapko WhatsApp pe nearest showroom ka address aur Google Maps link bhej deti hoon. Number confirm kar loon?",
        "hi":       "ज़रूर! मैं आपको WhatsApp पर nearest शोरूम का address और Google Maps link भेज देती हूँ। नंबर confirm कर लूँ?",
        "en":       "Sure! I will send you the nearest showroom address and Google Maps link on WhatsApp. Can I confirm your number?",
    },
    "goodbye": {
        "hinglish": "Bahut shukriya aapka! Krishna Furniture ki taraf se aapka din shubh ho. Milte hain store pe!",
        "hi":       "बहुत शुक्रिया आपका! कृष्णा फर्नीचर की तरफ से आपका दिन शुभ हो। मिलते हैं स्टोर पे!",
        "en":       "Thank you so much! Have a wonderful day from all of us at Krishna Furniture. See you at the store!",
    },
    "not_understood": {
        "hinglish": "Maafi chahti hoon, thoda clear nahi hua. Kya aap dobara bol sakte hain?",
        "hi":       "माफी चाहती हूँ, थोड़ा clear नहीं हुआ। क्या आप दोबारा बोल सकते हैं?",
        "en":       "I'm sorry, I didn't quite catch that. Could you say that again?",
    },

    # ── Product acknowledgements (plays before budget question) ────────────
    "ack_sofa": {
        "hi":       "अच्छा, sofa देखना है!",
        "hinglish": "Achha, sofa dekhna hai!",
        "en":       "Got it, sofa!",
    },
    "ack_bed": {
        "hi":       "अच्छा, bed देखना है!",
        "hinglish": "Achha, bed dekhna hai!",
        "en":       "Got it, bed!",
    },
    "ack_dining": {
        "hi":       "अच्छा, dining set देखना है!",
        "hinglish": "Achha, dining set dekhna hai!",
        "en":       "Got it, dining set!",
    },
    "ack_wardrobe": {
        "hi":       "अच्छा, wardrobe देखनी है!",
        "hinglish": "Achha, wardrobe dekhni hai!",
        "en":       "Got it, wardrobe!",
    },
    "ack_office": {
        "hi":       "अच्छा, office furniture देखना है!",
        "hinglish": "Achha, office furniture dekhna hai!",
        "en":       "Got it, office furniture!",
    },
    "ack_general": {
        "hi":       "जी समझ गई!",
        "hinglish": "Ji samajh gayi!",
        "en":       "Got it!",
    },
    "ack_budget": {
        "hi":       "समझ गई!",
        "hinglish": "Samajh gayi!",
        "en":       "Got it!",
    },

    # ── Misunderstanding handlers ──────────────────────────────────────────
    "not_understood_budget": {
        "hi":       "माफ़ करना, समझ नहीं पाई — budget roughly कितना सोच रहे हैं?",
        "hinglish": "Maaf karna, samajh nahi paai — budget roughly kitna soch rahe hain?",
        "en":       "Sorry, I didn't catch that — what's your rough budget?",
    },
    "not_understood_urgency": {
        "hi":       "माफ़ करना, समझ नहीं पाई — कब तक चाहिए roughly?",
        "hinglish": "Maaf karna, samajh nahi paai — kab tak chahiye roughly?",
        "en":       "Sorry, I didn't catch that — when do you need it?",
    },
}


# ── Cache utilities ────────────────────────────────────────────────────────────

def _make_static_path(key: str, lang: str) -> Path:
    return STATIC_DIR / f"{key}_{lang}.wav"


def _make_dynamic_path(text: str, lang: str) -> Path:
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    h = hashlib.md5(f"{lang}:{normalized}".encode()).hexdigest()[:12]
    return DYNAMIC_DIR / f"dyn_{h}.wav"


def _make_url(path: Path) -> str:
    rel = path.relative_to(CACHE_DIR)
    return f"{BASE_URL}/audio/{rel}"


def get_static_audio(key: str, lang: str) -> Optional[bytes]:
    path = _make_static_path(key, lang)
    if path.exists():
        return path.read_bytes()
    # Fallback to hinglish if specific lang not cached
    if lang != "hinglish":
        fallback = _make_static_path(key, "hinglish")
        if fallback.exists():
            return fallback.read_bytes()
    return None


def get_dynamic_audio(text: str, lang: str) -> Optional[bytes]:
    path = _make_dynamic_path(text, lang)
    if path.exists():
        return path.read_bytes()
    return None


def save_dynamic_audio(text: str, lang: str, wav: bytes) -> Path:
    DYNAMIC_DIR.mkdir(parents=True, exist_ok=True)
    path = _make_dynamic_path(text, lang)
    path.write_bytes(wav)
    return path


# ── Sarvam API call ───────────────────────────────────────────────────────────

async def _call_sarvam_tts(text: str, lang: str) -> Optional[bytes]:
    """Raw Sarvam TTS API call. Returns WAV bytes or None."""
    cfg = VOICE_CONFIG.get(lang, VOICE_CONFIG["hinglish"])
    try:
        async with httpx.AsyncClient(timeout=TTS_TIMEOUT) as client:
            r = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={
                    "API-Subscription-Key": SARVAM_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "inputs": [text],
                    "target_language_code": cfg["target_language_code"],
                    "speaker": cfg["speaker"],
                    "pace": TTS_PACE,
                    "speech_sample_rate": TTS_SAMPLE_RATE,
                    "model": TTS_MODEL,
                },
            )
        if r.status_code == 200:
            data = r.json()
            if data.get("audios"):
                return base64.b64decode(data["audios"][0])
        logger.error(f"Sarvam TTS {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"Sarvam TTS error: {e}")
    return None


# ── Public API ────────────────────────────────────────────────────────────────

async def get_speech(
    text: str,
    lang: str,
    static_key: Optional[str] = None,
) -> tuple:
    """
    Main TTS function. Returns (wav_bytes, url, was_cached).

    Priority:
      1. Static cache (pre-generated FAQ/greeting) — instant
      2. Dynamic cache (past response with same text+lang) — instant
      3. Sarvam API — 3–6s, saves to dynamic cache

    Args:
      text:       The text to speak
      lang:       "hi", "en", or "hinglish"
      static_key: If provided, checks static cache first (e.g. "greeting_inbound")
    """
    # Layer 1: Static cache
    if static_key:
        wav = get_static_audio(static_key, lang)
        if wav:
            url = _make_url(_make_static_path(static_key, lang))
            logger.info(f"STATIC HIT [{lang}] → {static_key}")
            return wav, url, True

    # Layer 2: Dynamic cache
    wav = get_dynamic_audio(text, lang)
    if wav:
        url = _make_url(_make_dynamic_path(text, lang))
        logger.info(f"DYNAMIC HIT [{lang}] → {text[:40]!r}")
        return wav, url, True

    # Layer 3: Fresh from Sarvam
    wav = await _call_sarvam_tts(text, lang)
    if wav:
        path = save_dynamic_audio(text, lang, wav)
        url = _make_url(path)
        logger.info(f"TTS GENERATED [{lang}] → {text[:40]!r}")
        return wav, url, False

    return None, "", False


async def get_speech_url(text: str, lang: str, static_key: Optional[str] = None) -> str:
    """Returns just the URL (for Vobiz Play API). Generates and caches if needed."""
    _, url, _ = await get_speech(text, lang, static_key)
    return url


# ── Pre-generate static cache ─────────────────────────────────────────────────

async def generate_static_cache() -> None:
    """
    Pre-generate all static response WAVs.
    Run once at startup — skips already-generated files.
    Takes ~60–90s on first run, then all responses are instant forever.
    """
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Pre-generating static TTS cache...")

    tasks = []
    for key, lang_map in STATIC_RESPONSES.items():
        for lang, text in lang_map.items():
            path = _make_static_path(key, lang)
            if not path.exists():
                tasks.append(_generate_and_save_static(key, lang, text))
            else:
                logger.info(f"STATIC EXISTS: {key}_{lang}")

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success = sum(1 for r in results if r is True)
        logger.info(f"Static cache: {success}/{len(tasks)} generated")
    else:
        logger.info("Static cache already complete — all responses instant")


async def _generate_and_save_static(key: str, lang: str, text: str) -> bool:
    wav = await _call_sarvam_tts(text, lang)
    if wav:
        path = _make_static_path(key, lang)
        path.write_bytes(wav)
        logger.info(f"STATIC SAVED: {key}_{lang}")
        return True
    logger.error(f"STATIC FAILED: {key}_{lang}")
    return False


def static_cache_stats() -> dict:
    """Returns cache hit stats for monitoring."""
    total = sum(len(v) for v in STATIC_RESPONSES.values())
    cached = sum(
        1 for key, lang_map in STATIC_RESPONSES.items()
        for lang in lang_map
        if _make_static_path(key, lang).exists()
    )
    return {
        "static_total": total,
        "static_cached": cached,
        "static_ready": cached == total,
        "dynamic_count": len(list(DYNAMIC_DIR.glob("dyn_*.wav"))) if DYNAMIC_DIR.exists() else 0,
    }


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    print("TTS Engine — static cache stats:")
    stats = static_cache_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if "--generate" in sys.argv:
        print("\nGenerating static cache...")
        asyncio.run(generate_static_cache())
        print("Done.")