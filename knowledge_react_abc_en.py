# knowledge_react_abc_en.py — English mirror of knowledge_react_abc.py
# Krishna Furniture Reactivation Campaign, English track
#
# 2026-08-18: bilingual system (Hindi default, English when the caller is
# speaking English -- see lang_detect.py's detect_lang() and
# webhook.py/respond()'s session.lang tracking, extended to the reactivation
# engine the same day). Every dict here has EXACTLY the same keys as its
# Hindi counterpart in knowledge_react_abc.py -- natural English phrasing of
# the same content/intent, not literal translations. _resolve_key_url()
# (webhook_reactivation.py) picks this module's dicts instead of the Hindi
# ones when session.lang == "en", and the cache filename's "_en" suffix
# (vs "_hi") keeps the two audio sets completely separate on disk.
#
# EN_SPEAKER: only "shreya" is an approved English voice so far (user
# listened to 9 candidates 2026-08-18 and approved shreya + ritu, but asked
# to ship with shreya only for now and add ritu later). Every English reply
# uses this ONE voice regardless of which Hindi voice that plan/prefix
# normally uses (react_a is ritu in Hindi, but shreya in English for now) --
# deliberately NOT touching PREFIX_VOICE_MAP or route_objection()'s per-plan
# voice selection to keep this change small; the {key}_{voice} suffix in
# shared keys still gets picked by prefix as before, it just always resolves
# to shreya's audio under a differently-named key until more English voices
# are approved. Revisit when ritu's English pass is added -- at that point
# react_a's English replies should switch to ritu-voiced audio too, and only
# the _ritu-suffixed shared keys would need to change.
EN_SPEAKER = "shreya"


# ─────────────────────────────────────────────────────────────────────────────
# Content shared verbatim across REACT_A/B/C's English scripts (mirrors which
# Hindi keys are word-for-word identical across ra_/rb_/rc_ in
# knowledge_react_abc.py -- only greet_main/greet_who/greet_repeat/offer_main/
# offer_trust/hook_cta/close(_conviction) differ by plan; offer_urgency is
# shared between A and C only, B has its own).
# ─────────────────────────────────────────────────────────────────────────────
_REACT_SHARED_EN = {
    "greet_privacy": "Of course — your number is right there in our old customer records, nothing shared with any third party. You've been a valued customer of ours, that's why I called personally.",
    "greet_hostile": "I'm sorry if this is a bad time. I'll send the details on WhatsApp instead — take a look whenever you like. Have a great day!",
    "offer_explain": "It's quite simple, actually — you come in to the showroom, and we calculate the value of your old furniture right in front of you. That value, plus 25%, plus another 25% on the new piece — so you're looking at 43 to 50% in total savings. No hidden conditions.",
    "obj_not_interested": "Just take a look at the photos and price on WhatsApp whenever you get a chance — no pressure at all. If you like what you see, we can take it from there.",
    "obj_busy": "Totally understand, you're busy — I'll just send the details on WhatsApp. Whenever you get a free moment, take a look. No rush at all.",
    "obj_expensive": "I understand, keeping an eye on the budget matters. That's exactly why this is an exchange offer — it's not a brand new price, it adjusts against your old furniture. I'll send the exact amount on WhatsApp so you can see for yourself how much it comes down to.",
    "obj_online": "Fair point. Just one thing — online, delivery, installation, and after-sales all cost extra. Here you get the factory price, plus the exchange value on top. I'll send a full comparison on WhatsApp so you can see the difference yourself.",
    "obj_think": "Of course, take your time to think it over — that's fair. I'll send the details on WhatsApp so they're there whenever you decide. Just keep in mind, the offer's only valid this month.",
    "obj_recovery": "Honestly, the families who've taken this offer have been really happy with it. Your whole home can get a fresh look for half the price. Do come by and see for yourself sometime, you'll like it.",
    "wa_cta": "I'll send you all the details on WhatsApp right now — photos, prices, everything. Take your time looking through it, you can decide later too.",
    "close_no_response": "That's absolutely fine! If you ever need us in future, do remember Krishna Furniture. Have a wonderful day.",
    "dnc": "Of course, I'm really sorry for any trouble. I'll take your number off our calling list right away — you won't get another call from us. Thank you so much, have a great day.",
    "q_location": "Our showrooms are in Sector 14 Gurgaon, Delhi, and Noida — open Monday to Sunday, 10 in the morning to 8 at night.",
    "q_name": "I'm Priya — I'm calling on behalf of Krishna Furniture.",
    "q_valuation": "Here's what you can do — come in to the showroom and meet me in person, we can go through everything properly there. Which day works for you?",
    "q_price_range": "Sofas start from ₹33,000, beds from ₹71,000, and dining sets from ₹1,19,000 — I'll send the exact prices on WhatsApp too.",
    "q_offer_scope": "Sofas, beds, dining tables, wardrobes, chairs — there's quite a range covered in this offer. Should I tell you one more good thing?",
    "already_purchased": "That's wonderful! If you ever need anything in future, do keep us in mind. Have a great day.",
    "appointment_ask": "I've sent the details on WhatsApp. Just confirm a date for your showroom visit — I'll personally be there waiting for you.",
    "appointment_confirmed": "Wonderful! I'll be right there at the store to meet you — do make sure to come.",
    "appointment_reask": "Sorry, I didn't quite catch the date — could you tell me once more, please?",
    "filler_1": "Right...", "filler_2": "Sure...", "filler_3": "Of course...",
    "filler_4": "I see...", "filler_5": "Got it...", "filler_6": "Alright...",
}

# offer_urgency: identical between A and C, B has its own -- kept separate
# from _REACT_SHARED_EN since it's a 2-of-3 share, not all 3.
_OFFER_URGENCY_AC_EN = "Just so you know, pieces are limited and the offer's only valid this month — that's why I'd say it's worth taking a look sooner rather than later. But it's completely up to you."

# close/close_conviction: identical between A and B, C has its own close and
# no close_conviction at all (mirrors the Hindi original exactly).
_CLOSE_AB_EN = "Wonderful! I'll send the photos and prices on WhatsApp right away. And do drop by the showroom once — we'll take care of your old furniture, you just pick out the new one. See you soon, thank you!"
_CLOSE_CONVICTION_AB_EN = "Just to say — pieces are limited, so do come by the showroom, get the value calculated right in front of you, and take your new furniture home the same day. We'll take care of the old one. Thank you so much!"


def _react_plan_en(prefix: str, unique: dict) -> dict:
    out = {f"{prefix}_{k}": v for k, v in _REACT_SHARED_EN.items()}
    out.update({f"{prefix}_{k}": v for k, v in unique.items()})
    return out


REACT_A_SCRIPT_EN = _react_plan_en("ra", {
    "greet_main": "Upgrading your home furniture has become really simple. We buy your old furniture at a good value, and give you a special discount on new pieces too. Just thirty seconds — can I quickly explain the offer?",
    "greet_who": "Hi, this is Priya from Krishna Furniture. You've been a valued customer of ours before, so I wanted to reach out personally — there's a special offer just for you.",
    "greet_repeat": "Yes — we'll take your old furniture at a good rate, and give you a heavy discount on new pieces. It means your whole home can get a fresh look, at half the price.",
    "offer_main": "Right now we have a 25% discount on new furniture, and when you exchange your old furniture, it gets its own separate value on top — so your overall cost comes down quite a bit. Should I tell you one more good part?",
    "offer_trust": "That's a completely fair question — with so many calls these days, it's natural to feel a little skeptical. That's exactly why I'd say, come visit the showroom once and see for yourself — no commitment at all, just for your own peace of mind. We have showrooms in Sector 14 Gurgaon, Delhi, and Noida.",
    "offer_urgency": _OFFER_URGENCY_AC_EN,
    "hook_cta": "You've been a valued customer of ours, that's why I called you personally. My suggestion would be — come by the showroom once and take a look, everything will be clear once you're there. After that, the decision is entirely yours.",
    "close": _CLOSE_AB_EN,
    "close_conviction": _CLOSE_CONVICTION_AB_EN,
})

REACT_B_SCRIPT_EN = _react_plan_en("rb", {
    "greet_main": "Quite a few of our customers have exchanged their old furniture for new lately — so I thought I'd let you know too. If you're looking to upgrade your home furniture, this offer is really worth it. Would you like to hear about it?",
    "greet_who": "Hi, this is Priya from Krishna Furniture. You've been a valued customer of ours before, so I called personally. A lot of families are giving their homes a fresh look these days — I've brought the same offer for you too.",
    "greet_repeat": "Yes — we have a special offer for our past customers. We'll take your old furniture at a good rate, and give you a heavy discount on new pieces. Should I tell you about the offer?",
    "offer_main": "Right now there's a 25% discount on new furniture, and when you exchange your old one, it gets its own value on top — which is why a lot of people are getting new furniture within a much smaller budget than they expected. Should I tell you one more good part?",
    "offer_trust": "Just come by the showroom once — you get a free estimate of your old furniture's value, no commitment at all.",
    "offer_urgency": "We've got quite a few families coming in this month, and pieces are limited — that's why I'd say, do take a look a little soon. But it's entirely up to you.",
    "hook_cta": "You've been a valued customer of ours too, that's why I shared this offer with you personally. I'll send you the furniture photos and prices on WhatsApp — take a look whenever you like, you can decide later too.",
    "close": _CLOSE_AB_EN,
    "close_conviction": _CLOSE_CONVICTION_AB_EN,
})

REACT_C_SCRIPT_EN = _react_plan_en("rc", {
    "greet_main": "Can I ask you a quick question? If you could get new furniture, and get good value for your old furniture too — at a lower cost — would you like to hear about it?",
    "greet_who": "Hi, this is Priya from Krishna Furniture. You've been a valued customer of ours before, so I called personally. Just had a quick question — if you could get new furniture at half the price, would you like to hear more?",
    "greet_repeat": "Yes — that's exactly what I was asking. New furniture, and your old furniture goes for a good rate too — at half the price. Would you like to hear about it?",
    "offer_main": "So that's the offer running right now — 25% discount on new furniture, and your old furniture gets its own separate value when you exchange it. Should I tell you one more good part?",
    "offer_trust": "Please, relax — I'm not pushing you at all. Just come by the showroom once — you get a free estimate of your old furniture's value, no commitment. Just come by once, that's all I'm asking.",
    "offer_urgency": _OFFER_URGENCY_AC_EN,
    "hook_cta": "We're sharing this offer specially with our existing customers, that's why I called you personally. I'll send you the photos and full details on WhatsApp — take a look whenever you like, there's no commitment at all.",
    "close": "Wonderful! I'll send the photos and prices on WhatsApp right away — you'll get a free value estimate too. And do drop by the showroom once — we'll take care of your old furniture, you just pick out the new one. See you soon, thank you!",
    # No close_conviction for React C, matches the Hindi original exactly.
})


# ─────────────────────────────────────────────────────────────────────────────
# SHARED_SCRIPT_EN — mirrors SHARED_SCRIPT's structure: one line of content
# per category, expanded to the 3 voice-suffixed keys route_objection() looks
# up via PREFIX_VOICE_MAP. All 3 currently resolve to the same EN_SPEAKER
# (shreya) audio -- see this file's header comment.
# ─────────────────────────────────────────────────────────────────────────────
_SHARED_VOICED_EN = {
    "obj_repeat_generic": "Oh, I'm sorry, I didn't quite catch that — could you say that once more, please?",
    "obj_timing_greet_generic": "Totally understand, no rush at all. Let me just take two minutes to explain something simple — then it's entirely up to you.",
    "obj_escalate_generic": "Of course — let me connect you with our Customer Relations Head about this. She isn't available on the call right now, so let me set up a callback for you — she'll be able to help you completely. What time would work for you?",
    "obj_personal_question_generic": "I'm Krishna Furniture's AI assistant, here to help you. Go ahead, what would you like to know?",
    "obj_wa_ok_generic": "Sure, sending that over on WhatsApp right now.",
    "obj_wa_prefers_generic": "Totally understand, let's continue on WhatsApp from here. Sending over the details right now.",
    "wa_fallback_deflect": "I'll send the details over on WhatsApp, please do check there.",
    "llm_filler_price": "One second, just checking the price...",
    "llm_filler_location": "One second, pulling up the showroom details...",
    "llm_filler_generic": "One second, let me check...",
    "obj_wrong_number_generic": "Oh, I'm really sorry — looks like our records have an outdated number. Sorry to have bothered you. Have a great day!",
    "obj_not_my_customer_generic": "No problem at all, there might be a small mix-up in our records — apologies for that. As it happens, we do have a good offer running for anyone looking at new furniture — would you like to hear about it?",
    "obj_person_unavailable_generic": "Oh, no problem at all. I'll try again a little later. Thank you for your time!",
    "obj_already_called_generic": "I'm sorry if we've called a bit too often — please don't mind. Just one more quick thing, then it's entirely up to you. Is that alright?",
    "obj_callback_later_generic": "Of course, I understand you're busy right now. Could you tell me what time would work better for you — later today, or tomorrow? I'll call you back at that time so it's convenient for you.",
    # route_objection() flips session.lang to "en" BEFORE calling play_key()
    # for lang_pref_english, so this is the copy that actually plays when a
    # caller asks for English -- the Hindi dict's version of this same key
    # is the normally-unreachable fallback (see its comment).
    "obj_lang_pref_english_generic": "Sure, I can continue in English if that's easier for you.",
    # Reachable if a caller currently in English mode asks to switch back to
    # Hindi -- session.lang flips to "hi" before play_key(), so in practice
    # the Hindi dict's version plays instead; kept for key-parity/fallback.
    "obj_lang_pref_hindi_generic": "Sure, I'll continue in Hindi from here.",
    "obj_lang_pref_other_generic": "I'm not able to do Punjabi just yet, but I can continue in Hindi or English — whichever works for you.",
    "obj_uncertain_generic": "No problem at all, there's no rush. I'll send the details on WhatsApp — take a look whenever you're free, and go with whatever feels right.",
    "obj_bare_negative_generic": "No problem — just let me know, is it that you're not interested in the offer, or is this just not a good time to talk? Whatever works for you.",
    "obj_ask_emi_generic": "EMI options are available at the showroom — the exact plan and details will be clearest there. I'll note it down and send it on WhatsApp too.",
    "obj_ask_payment_method_generic": "Of course — cash, card, UPI, all of it works at the showroom. No trouble at all.",
    "obj_ask_warranty_generic": "Warranty varies a bit by product — the team at the showroom will give you the exact terms. I'll send that on WhatsApp too.",
    "obj_ask_delivery_charge_generic": "Delivery and installation charges depend on the order — I'll confirm and send the exact details on WhatsApp.",
    "obj_ask_return_policy_generic": "The full return policy will be clearest at the showroom — I'll send it on WhatsApp too so you have it handy.",
    "obj_ask_bargain_generic": "I understand, everyone wants the best rate! The offer running right now is already our best rate — but do come by the showroom, sometimes there's a little extra room.",
    "obj_ask_invoice_gst_generic": "Of course — every purchase comes with a proper GST bill. No need to worry about that at all.",
    "obj_ask_product_quality_generic": "For quality and material, it's best to see and feel it yourself at the showroom — that way you can verify it in person and feel confident about it.",
    "obj_ask_pickup_logistics_generic": "We handle the pickup of your old furniture ourselves — the team will walk you through the full process when you visit the showroom. You won't need to arrange anything.",
    "obj_ask_call_recorded_generic": "Yes — calls may be recorded for quality and training purposes. Your conversation stays completely safe.",
    "obj_reschedule_appointment_generic": "No problem at all — let's plan for a new date. Which day works for you now?",
    "obj_cancel_appointment_generic": "Of course, I'll cancel the appointment — no problem. Do keep us in mind if you ever need us again. Have a great day!",
    "obj_legal_threat_generic": "I'm really sorry if this caused you any trouble — that's entirely on us. I'll remove your number right away, you won't get another call. Thank you so much.",
    "obj_want_human_generic": "Of course, I understand — you'd like to speak with someone directly. Let me set up a call with our Customer Relations Head for you — she'll walk you through everything in detail. What time would work best for you?",
}

SHARED_SCRIPT_EN = {"wa_decline_confirm_greet": "Hi there! I noticed you seemed a little unsure on WhatsApp — totally understand. Just wanted to check, are you not interested for now, or would a bit more information help you decide?"}
for _cat, _text in _SHARED_VOICED_EN.items():
    for _voice in ("ritu", "shreya", "simran"):
        SHARED_SCRIPT_EN[f"{_cat}_{_voice}"] = _text


CALL2_SCRIPT_EN = {
    "c2_greet_main": "Hi there! This is Priya from Krishna Furniture. We spoke last time — do you remember?",
    "c2_greet_reorient": "Hi, this is Krishna Furniture — I'd sent you the offer details on WhatsApp, that's what I'm calling about.",
    "c2_greet_annoyed": "Of course, I'll just take thirty seconds — I wanted to confirm a date for your showroom visit, that's why I called.",
    "c2_wa_check": "So, did you get a chance to look at the details I sent on WhatsApp?",
    "c2_invite_seen": "Wonderful! Then do come by the showroom sometime. Which day works for you? Just give me a date, and I'll be there to meet you.",
    "c2_invite_resend": "No problem, I'll send it again on WhatsApp right now — do take a look. Or you're welcome to just come by the showroom directly. Which day works for you?",
    "c2_date_direct": "Which day would work for you to visit the showroom? Just give me a date, I'll note it down.",
    "c2_date_reask": "Of course, no rush at all. Just tell me a day — we'll meet you at the store that day.",
    "c2_booked": "Alright, I'll be right there at the store to meet you. Do make sure to come. Thank you so much!",
    "c2_obj_price": "That might be — which is exactly why it's worth taking a look. The final decision is yours anyway once you're at the showroom, right?",
    "c2_obj_timing": "No problem at all, I completely understand. I'll send the details on WhatsApp, take a look at your own convenience. And whenever you're free, let me know a day.",
    "c2_obj_scam": "Please, do trust us — nothing shady going on. You're welcome to visit the showroom yourself and see. Which day works for you?",
    "c2_obj_not_interested": "No problem at all, I just wanted to confirm. Do keep Krishna Furniture in mind if you ever need us.",
    "c2_close_thinking": "Alright, take your time thinking it over — no rush. I'll send the details on WhatsApp.",
    "c2_close_busy": "No problem at all — take a look whenever you get time. I'll send it over.",
    "c2_close_price": "I completely understand. I'll send the details on WhatsApp, take a look whenever you're free.",
    "c2_close_declined": "Thank you so much for your time. Have a wonderful day!",
}

CALL3_SCRIPT_EN = {
    "c3_greet_main": "Hi there! This is Priya from Krishna Furniture. We've spoken before — just wanted to check one last time, what did you decide?",
    "c3_greet_reorient": "Hi, this is Krishna Furniture — the same offer I mentioned to you earlier.",
    "c3_greet_hostile": "That's completely fine, understood — I won't call again. Thank you for your time, have a great day.",
    "c3_decision_date": "Do come by the showroom once, it'll only take about five minutes. Which day works for you? Just give me a date.",
    "c3_date_reask": "Of course, no rush at all. Just tell me a day — we'll meet you at the store that day.",
    "c3_booked": "Alright, I'll be right there at the store to meet you. Do make sure to come. Thank you!",
    "c3_obj_price": "I completely understand. I've sent the offer on WhatsApp — take a look whenever it's convenient.",
    "c3_obj_scam": "Please, do trust us — you're welcome to visit the showroom yourself and see. Which day works for you? Just give me a date.",
    "c3_declined": "I completely understand. Thank you for your time. Have a great day.",
    "c3_close_thinking_final": "No problem at all — the details are there on WhatsApp, take a look whenever you like. Have a great day.",
    "c3_close_busy": "No problem at all, I won't disturb you right now. I've sent the details on WhatsApp — take a look whenever you get time.",
}

FRESH_CTA_SCRIPT_EN = {
    "fresh_greet_bed": "Hi there! We spoke on WhatsApp — you wanted to take a look at a bed. So, when are you coming by the store? I'll personally be there to meet you.",
    "fresh_greet_sofa": "Hi there! We spoke on WhatsApp — you wanted to take a look at a sofa. So, when are you coming by the store? I'll personally be there to meet you.",
    "fresh_greet_wardrobe": "Hi there! We spoke on WhatsApp — you wanted to take a look at a wardrobe. So, when are you coming by the store? I'll personally be there to meet you.",
    "fresh_greet_dining": "Hi there! We spoke on WhatsApp — you wanted to take a look at a dining set. So, when are you coming by the store? I'll personally be there to meet you.",
    "fresh_greet_generic": "Hi there! We spoke on WhatsApp about Krishna Furniture. When can you come by the store? I'll be there to meet you.",
    "fresh_objection": "We've got some really beautiful new designs in — you're sure to like them. I'll send them on WhatsApp, but you'll really see the difference once you visit the store. When can you come by?",
    "fresh_appointment_confirmed": "Wonderful! I'll confirm your appointment — our team will be waiting for you. See you soon!",
    "fresh_no_date_close": "No problem at all. I'll send you some lovely options on WhatsApp — take a look at your own pace, and we can plan the visit whenever's convenient.",
    "fresh_soft_defer": "Alright, you can just confirm on WhatsApp — I'll send over a few more options.",
    "fresh_location_info": "Our showrooms are in Sector 14 Gurgaon, Delhi, and Noida. I'll send you the exact address and a Google Maps link on WhatsApp — you can confirm the date from there, and that's where we'll meet.",
    "fresh_greet_who_bed": "Hi, this is Krishna Furniture — we spoke on WhatsApp about a bed. When can you come by the store?",
    "fresh_greet_who_sofa": "Hi, this is Krishna Furniture — we spoke on WhatsApp about a sofa. When can you come by the store?",
    "fresh_greet_who_wardrobe": "Hi, this is Krishna Furniture — we spoke on WhatsApp about a wardrobe. When can you come by the store?",
    "fresh_greet_who_dining": "Hi, this is Krishna Furniture — we spoke on WhatsApp about a dining set. When can you come by the store?",
    "fresh_greet_who_generic": "Hi, this is Krishna Furniture — we spoke on WhatsApp. When can you come by the store?",
    "fresh_price": "The price is quite reasonable — I'll send you the full details on WhatsApp. Once you see it at the store, you'll really understand the value. When can you come by?",
    "fresh_trust": "I completely understand. Come by the store and see for yourself — no obligation at all, that way you can decide with confidence. When can you come by?",
}

ALL_SCRIPTS_EN = {
    "react_a": REACT_A_SCRIPT_EN,
    "react_b": REACT_B_SCRIPT_EN,
    "react_c": REACT_C_SCRIPT_EN,
    "fresh_cta": FRESH_CTA_SCRIPT_EN,
}


def get_script_en(campaign: str) -> dict:
    return ALL_SCRIPTS_EN.get(campaign, REACT_A_SCRIPT_EN)
