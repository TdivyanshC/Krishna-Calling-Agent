# knowledge_reactivation.py — Reactivation campaign script + intent map
# Krishna Furniture | Place in: /home/voiceagent/voice-ai/

REACTIVATION_SCRIPT = {

    # ── S1: GREETING ────────────────────────────────────────────────
    "react_greet_main":
        "नमस्ते! मैं Priya बोल रही हूँ Krishna Furniture की तरफ से। "
        "क्या आपके पास बस दो मिनट हैं?",

    "react_greet_confusion":
        "जी, Krishna Furniture — Gurgaon, Delhi, Noida में हमारे showrooms हैं। "
        "आपने पहले हमसे furniture लिया था, इसीलिए personally call कर रही हूँ।",

    "react_greet_privacy":
        "जी बिल्कुल समझ सकती हूँ। आपका number हमारे पुराने customer records में है — "
        "कोई third party नहीं है। बस एक ज़रूरी offer share करना था।",

    "react_greet_hostile":
        "माफ़ी चाहती हूँ disturb करने के लिए। "
        "WhatsApp पर details भेज देती हूँ — देखना न देखना आप पर है। "
        "आपका दिन अच्छा रहे!",

    # ── S2: THANK CUSTOMER ──────────────────────────────────────────
    "react_thank_main":
        "पहले, आपका बहुत बहुत शुक्रिया — आप Krishna Furniture के valued customer रहे हैं। "
        "हम genuinely appreciate करते हैं।",

    "react_thank_skip":
        "जी bilkul, directly बात करते हैं!",

    # ── S3: PRESENT OFFER ───────────────────────────────────────────
    "react_offer_main":
        "सुनिए — आप हमारे पुराने customer हैं, इसीलिए personally call की। "
        "Krishna Furniture में अभी एक ऐसा offer है जो पहले कभी नहीं आया — "
        "25% discount ऊपर से, और पुराना furniture देने पर 25% और। "
        "यानी आधे दाम में बिल्कुल नया, latest furniture घर में। "
        "क्या मैं आपको एक और exciting बात बता सकती हूँ?",

        "react_offer_explain_simple":
        "बिल्कुल! Process बहुत simple है — "
        "आप showroom आइए, हमारी team आपके पुराने furniture की value calculate करेगी — आपके सामने। "
        "उस value पर 25% और discount, plus ऊपर से 25% — total saving 43 से 50%। "
        "बाकी सारी details मैं अभी WhatsApp पर भेज रही हूँ। "
        "वहाँ exchange offer का button होगा — उसे click करें, हमारी team सब समझा देगी। चलेगा?",

    "react_offer_explain_maths":
        "आप बिल्कुल सही कह रहे हैं technically! "
        "25% price पर, फिर उस पर 25% exchange — effective saving 43 से 50% के बीच होती है। "
        "WhatsApp पर exact calculation के साथ भेज देती हूँ।",

    "react_offer_trust":
        "समझ सकती हूँ — आजकल बहुत calls आती हैं। "
        "आप showroom में आ कर personally verify कर सकते हैं — कोई commitment नहीं। "
        "Sector 14 Gurgaon, Delhi, Noida — तीनों जगह हैं।",

    "react_offer_past_bad":
        "आपकी बात सुन कर दुख हुआ। "
        "इस बार exchange value का calculation counter पर होता है — आपके सामने। "
        "कोई hidden condition नहीं है।",

    "react_offer_not_needed":
        "बिल्कुल ज़रूरी नहीं अभी लेना। "
        "WhatsApp पर details रहने दीजिए — जब ज़रूरत हो तब काम आएगी।",

    "react_offer_urgency":
        "यह offer इसी महीने तक है और limited pieces हैं। "
        "WhatsApp पर details check करिए पहले — फिर decide करिए।",

    "react_offer_product_sofa":
        "Sofa exchange में बहुत अच्छा value मिलता है — "
        "L-shape, 5-seater, recliner सब available हैं। "
        "WhatsApp पर current stock photos भेजती हूँ।",

    "react_offer_product_bed":
        "Bed के लिए king size, queen size, storage bed — सब हैं। "
        "Exchange में पुराना bed भी लेते हैं। Photos WhatsApp पर आ जाएंगे।",

    "react_offer_product_wardrobe":
        "Wardrobe exchange भी होता है — sliding door, 3-door, 4-door। "
        "Details WhatsApp पर भेजती हूँ।",

    "react_offer_product_dining":
        "Dining set exchange में बढ़िया deal है — "
        "4-seater से 8-seater तक, सब available हैं। WhatsApp पर photos भेजती हूँ।",

    # ── S4: WHATSAPP CTA ────────────────────────────────────────────
    "react_wa_cta_main":
        "बहुत families इस scheme का फायदा उठा रही हैं — "
        "पुराना furniture देकर नया ले जा रही हैं, घर को नया look दे रही हैं। "
        "आप भी यह मौका मत छोड़िए। "
        "मैं अभी WhatsApp पर photos, prices, exchange process सब भेज रही हूँ।",

    "react_wa_cta_prefers_wa":
        "बिल्कुल! Details अभी जा रही हैं WhatsApp पर। "
        "कोई question हो तो वहीं reply करिए।",

    "react_wa_cta_diff_number":
        "जी बताइए — कौन से number पर भेजूँ?",

    "react_wa_cta_no_whatsapp":
        "कोई बात नहीं! Showroom में directly आ सकते हैं — "
        "Sector 14 Gurgaon, सोमवार से रविवार, 10 बजे से 8 बजे तक।",

    # ── S5: OBJECTIONS ──────────────────────────────────────────────
    "react_obj_busy":
        "बिल्कुल, disturb नहीं करती। "
        "Details WhatsApp पर हैं — अपनी फुरसत में देख लीजिए।",

    "react_obj_later":
        "ज़रूर! WhatsApp message रहेगा — जब time मिले देख लीजिए। "
        "Offer इस महीने तक valid है।",

    "react_obj_not_interested":
        "बिल्कुल ठीक है। "
        "WhatsApp पर details भेज दी हैं — शायद बाद में काम आए। "
        "आपका दिन अच्छा रहे!",

    "react_obj_expensive":
        "समझ सकती हूँ। इसीलिए यह exchange offer है — "
        "new price पर नहीं, exchange के साथ। "
        "Exact amount WhatsApp पर देख सकते हैं।",

    "react_obj_online":
        "Online में delivery, installation, after-sales सब अलग होते हैं। "
        "हमारे पास factory price है plus exchange value — "
        "total comparison WhatsApp पर है।",

    "react_obj_zombie":
        "लग रहा है शायद अभी सही time नहीं है। "
        "WhatsApp पर details भेज देती हूँ — जब time मिले देखिए। शुक्रिया!",

    "react_obj_personal":
        "मेरा नाम Priya है — Krishna Furniture की customer service से। "
        "Offer के बारे में कोई और question?",

    "react_obj_escalate":
        "जी ज़रूर! आप किसी भी showroom में manager से मिल सकते हैं। "
        "Address और timings WhatsApp पर भेज रही हूँ।",

    "react_obj_repeat":
        "जी — 25% ऊपर से, 25% exchange पर। "
        "Total मिला कर बहुत अच्छी saving है। "
        "WhatsApp पर exact breakdown है।",

    "react_obj_ai_question":
        "जी, मैं Priya हूँ — Krishna Furniture की automated assistant। "
        "Offer बिल्कुल real है — showroom में जा कर verify कर सकते हैं।",

    # ── DNC ─────────────────────────────────────────────────────────
    "react_dnc_close":
        "माफ़ी चाहती हूँ! आपका number DNC list में add कर दिया जाएगा — "
        "अब कोई call नहीं आएगी। बहुत बहुत शुक्रिया।",

    # ── S6: CLOSE ───────────────────────────────────────────────────
    "react_close_main":
        "मुझे पूरा यकीन है आपको हमारा नया collection बहुत पसंद आएगा। "
        "WhatsApp देखिए, एक बार showroom ज़रूर आइए — "
        "आपका पुराना furniture हम संभाल लेंगे, आप बस नया चुनिए। बहुत शुक्रिया!",

    "react_close_warm":
        "बहुत बहुत शुक्रिया! WhatsApp message आ गया होगा। "
        "Store में मिलते हैं — take care!",

    # ── HOOK before WA CTA ──────────────────────────────────────────
    "react_hook_before_cta":
        "बहुत families इस offer का फायदा उठा रही हैं — "
        "पुराना furniture देकर नया ले जा रही हैं, घर को नया look दे रही हैं। "
        "आप भी यह मौका मत छोड़िए।",

    # ── Strong close after customer says okay ────────────────────────
    "react_close_conviction":
        "मुझे पूरा यकीन है आपको हमारा नया collection बहुत पसंद आएगा — "
        "latest designs हैं, family के लिए perfect। "
        "WhatsApp देखिए, एक बार showroom ज़रूर आइए। "
        "आपका पुराना furniture हम संभाल लेंगे, आप बस नया चुनिए। बहुत शुक्रिया!",

    # ── Rejection recovery ───────────────────────────────────────────
    "react_followup_wa":
        "नमस्ते! मैं प्रिया बोल रही हूँ Krishna Furniture की तरफ से। "
        "मैंने आपको WhatsApp पर एक message भेजा है — "
        "please उस पर जाइए और exchange offer का button click कीजिए। "
        "वहाँ आपको सारी details मिल जाएंगी। बहुत शुक्रिया!",
    "react_obj_recovery":
        "सच बताऊँ — जो families यह offer लेकर जा रही हैं वो बहुत खुश हैं। "
        "आधे दाम में घर का पूरा look बदल जाता है। "
        "आप भी इसका फायदा उठाइए।",

    # ── FILLERS ─────────────────────────────────────────────────────
    "react_filler_1": "जी...",
    "react_filler_2": "हाँ...",
    "react_filler_3": "बिल्कुल...",
    "react_filler_4": "अच्छा...",
    "react_filler_5": "समझ गई...",
    "react_filler_6": "हाँ जी...",
}

REACTIVATION_INTENTS = {
    "positive": ["हाँ", "हां", "ठीक है", "बताओ", "बोलो", "सुन रहा हूँ", "okay", "ok",
                 "sure", "बिल्कुल", "achha", "अच्छा", "haan", "han", "theek", "bolo", "batao", "suno"],
    "confusion_who": ["कहाँ से", "कहां से", "कौन", "kaun", "kahan se", "kaun sa number",
                      "kaise mila", "number kahan se", "pahchaan nahi", "kon ho"],
    "privacy_concern": ["number kaise mila", "data kahan se", "mera number kyun hai",
                        "kisi ne diya", "privacy", "spam", "number kahan se liya"],
    "skip_pleasantries": ["kya kaam tha", "seedha bolo", "directly", "kya baat hai",
                          "time waste mat karo", "jaldi bolo", "point pe aao", "kya chahiye"],
    "offer_clarify": ["kya matlab", "samjha nahi", "explain karo", "25 25 kya",
                      "kya offer hai", "detail batao", "kaise hoga", "samjhao", "aur batao",
                      "exchange kaise", "kaise exchange", "exchange hoga", "purana furniture",
                      "purana kaise", "exchange process", "एक्सचेंज कैसे", "कैसे एक्सचेंज",
                      "पुराना furniture", "exchange kaisa", "kaise kaam karta"],
    "offer_maths_challenge": ["25 plus 25", "50 nahi hota", "maths galat hai",
                              "calculation galat", "itna nahi milta", "mislead", "galat bol rahe"],
    "trust_issue": ["fake hai", "jhooth", "fraud", "scam", "believe nahi",
                    "sach mein", "prove karo", "pakka", "sach hai kya", "vishwas nahi"],
    "past_bad_experience": ["pehle bhi", "last time", "aisi hi baat thi",
                            "woh bhi", "experience achha nahi", "pehle bura hua"],
    "not_needed_now": ["nahi chahiye", "abhi nahi", "zarurat nahi",
                       "furniture liya hua hai", "recently liya", "abhi sochna nahi", "ghar mein hai"],
    "buying_signal": ["kitna time hai", "kab tak hai", "offer kb tak",
                      "main aana chahta hoon", "showroom kab", "interested hoon",
                      "dekhna chahta hoon", "aana chahta", "visit karna", "kab aaye"],
    "product_sofa": ["sofa", "sopha", "सोफा", "couch", "l shape", "recliner"],
    "product_bed": ["bed", "बेड", "palang", "king size", "queen size", "cot"],
    "product_wardrobe": ["wardrobe", "वार्डरोब", "almari", "अलमारी", "almirah", "cupboard"],
    "product_dining": ["dining", "dining table", "dining set", "table chair", "6 seater", "4 seater"],
    "wa_ok": ["bhejo", "send karo", "theek hai bhej do", "ok send",
              "WhatsApp pe bhejo", "haan bhejo", "kar do", "bhej do",
              "theek hai", "ठीक है", "okay", "ok", "haan", "हाँ", "हां",
              "bilkul", "बिल्कुल", "achha", "अच्छा", "sure", "done",
              "thik hai", "thik", "oke", "okey", "ji", "जी"],
    "wa_prefers": ["WhatsApp pe hi", "call nahi", "message karo", "WhatsApp better hai"],
    "wa_diff_number": ["alag number", "doosra number", "different number", "iss number pe nahi"],
    "wa_no_whatsapp": ["WhatsApp nahi hai", "use nahi karta", "WhatsApp nahi chalaata", "no whatsapp"],
    "busy": ["busy hoon", "abhi nahi", "kaam mein hoon", "meeting mein hoon",
             "driving", "ghar pe nahi hoon", "baad mein", "abhi nahi kar sakta"],
    "sochna_hai": ["sochna hai", "soch ke batata hoon", "wife se puchna hai",
                   "ghar mein baat karni hai", "decide nahi kiya", "family se puchna hai"],
    "not_interested": ["interested nahi", "nahi chahiye", "rehne do",
                       "hata do mera number", "band karo yeh", "mat bhejo"],
    "expensive": ["mahenga hai", "bahut zyada hai", "budget nahi hai",
                  "afford nahi", "sasta chahiye", "itna nahi denge", "costly"],
    "online_cheaper": ["online sasta milta hai", "Amazon pe", "Flipkart pe",
                       "online better hai", "ecommerce", "meesho"],
    "escalate": ["manager se baat karo", "senior se milao", "owner kaun hai",
                 "complaint karna hai", "complain", "supervisor"],
    "dnc": ["dobara call mat karna", "number delete karo", "DNC", "harassment",
            "complaint karunga", "call mat karo kabhi", "legal action",
            "mujhe disturb mat karo", "band karo yeh call"],
    "personal_question": ["tumhara naam", "kaun ho tum", "real hai ya bot",
                          "robot ho", "machine ho", "AI ho", "human ho", "computer ho"],
    "zombie": [],
}
