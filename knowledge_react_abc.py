# knowledge_react_abc.py — A/B/C Test Scripts
# Krishna Furniture Reactivation Campaign
# campaign_type: react_a | react_b | react_c

REACT_A_SCRIPT = {
    # 2026-08-15 warm rewrite (from Agent_Replies_Warm.md, user-approved
    # verbatim): consistent aap+lijiye/kijiye formal register replacing the
    # old casual imperatives (karo/socho/aao), acknowledge-first structure,
    # real empathy phrasing, store list standardized to the 3-showroom
    # version (Sector 14 Gurgaon, Delhi, Noida) that 3 of 4 flows already
    # used -- Fresh CTA's 4-store "Gurugram/Faridabad" version was the
    # stale outlier, confirmed inconsistent before this pass.
    "ra_greet_main": "Ghar ka furniture upgrade karna ab bahut aasaan ho gaya hai ji. Purana furniture hum achhi value par le lete hain, aur naye par special discount bhi de rahe hain. Sirf 30 second — offer samjha doon?",
    "ra_greet_who": "Ji, main Priya bol rahi hoon, Krishna Furniture se. Aap hamare purane customer rahe hain, isiliye maine khud aapko call kiya — ek khaas offer hai, sirf aapke liye.",
    "ra_greet_repeat": "Haan ji — purana furniture hum achhe rate par le lenge, aur naye par heavy discount denge. Matlab ghar ka poora look badal jaata hai, woh bhi aadhe daam mein.",
    "ra_greet_privacy": "Ji bilkul — aapka number hamare purane customer records mein hi hai, koi third party nahi. Aap hamare valued customer hain, isliye maine khud call ki.",
    "ra_greet_hostile": "Maafi chahti hoon agar galat time par call kiya ji. Details WhatsApp par bhej deti hoon — dekhna bilkul aapki marzi. Aapka din shubh ho!",
    "ra_offer_main": "Abhi naye furniture par 25% discount chal raha hai ji, aur purana exchange karne par uski alag value bhi milti hai — overall kharcha kaafi kam ho jaata hai. Ek aur achhi baat bataun?",
    "ra_offer_explain": "Bilkul simple hai ji — aap showroom aaiye, hum aapke saamne purane furniture ki value calculate karenge. Us value par 25%, aur upar se 25% — total 43 se 50% tak saving. Koi hidden condition nahi.",
    "ra_offer_trust": "Aapka sawaal bilkul jayaz hai ji — aajkal itni calls aati hain ki shak hona natural hai. Isiliye keh rahi hoon, ek baar showroom aa kar khud dekh lijiye — koi commitment nahi, sirf apni tasalli ke liye. Sector 14 Gurgaon, Delhi, aur Noida — teeno jagah hamare showroom hain.",
    "ra_offer_urgency": "Bas itna ki pieces limited hain aur offer is mahine tak hi hai ji — isiliye keh rahi hoon, dekh lijiye toh behtar rahega. Baaki poori tarah aapki marzi.",
    "ra_obj_not_interested": "Ek baar WhatsApp par bas photos aur price dekh lijiyega ji — koi pressure nahi. Pasand aaye toh baat aage badhaate hain.",
    "ra_obj_busy": "Bilkul samajhti hoon ji, aap busy hain — main sirf details WhatsApp par bhej deti hoon. Apni fursad mein, jab time mile tab dekh lijiyega. Koi jaldi nahi.",
    "ra_obj_expensive": "Samajhti hoon ji, budget dekhna zaroori hai. Isiliye toh yeh exchange offer hai — poora naya nahi, purane ke saath adjust hota hai. Exact amount WhatsApp par bhej deti hoon, aap khud dekh lijiyega kitna kam ho jaata hai.",
    "ra_obj_online": "Sahi kaha ji. Bas ek baat — online par delivery, installation, after-sales sab alag se lagta hai. Yahan factory price hai, upar se exchange value bhi. Poora comparison WhatsApp par bhej deti hoon, aap khud farak dekh lijiyega.",
    "ra_obj_think": "Zaroor soch lijiye ji, yeh toh sahi baat hai. Main details WhatsApp par bhej ke rakhti hoon — jab bhi decide karein, saamne rahengi. Bas offer is mahine tak hai, itna dhyaan rahe.",
    "ra_obj_recovery": "Sach batau ji — jo families yeh offer le kar gayi hain, bahut khush hain. Aadhe daam mein ghar ka look hi badal jaata hai. Aap bhi ek baar aa kar dekhiye, achha lagega.",
    "ra_hook_cta": "Aap hamare purane customer hain, isiliye maine khud personally call kiya ji. Mera suggestion hai — ek baar showroom aa kar dekh lijiye, waha aapko sab kuch clearly samajh aa jayega. Uske baad poora decision aapka hi rahega.",
    # Was missing entirely (script text + cache file both absent) while
    # rb_wa_cta/rc_wa_cta existed for the other 2 plans -- 5 live call sites
    # in webhook_reactivation.py (PRESENT_OFFER's buying_signal/expensive/
    # online_cheaper/busy branches, WHATSAPP_CTA's wa_diff_number branch) hit
    # play_key()'s "no text for key" silent-failure path for every react_a
    # call that reached them. Confirmed live bug, fixed here — text mirrors
    # rb_wa_cta verbatim, matching this file's existing convention of sharing
    # WA-CTA content across plans (only greet_main/offer_main meaningfully
    # differ by plan).
    "ra_wa_cta": "Main saari details abhi WhatsApp par bhej deti hoon ji — photos, prices, sab. Aap aaram se dekh lijiyega, decision baad mein bhi le sakte hain.",
    "ra_close": "Bahut achha ji! Main abhi WhatsApp par photos aur prices bhej deti hoon. Aur ek baar showroom aa jaiye — purana furniture hum sambhal lenge, aap bas naya pasand kijiye. Milte hain! Shukriya.",
    "ra_close_conviction": "Bas itna keh rahi hoon, pieces limited hain ji — showroom mein aaiye, apne saamne value calculate karwaiye, aur wohi din naya furniture le jaaiye. Purana hum sambhal lenge. Bahut shukriya!",
    # Confirmed live 2026-08-13 (real test call): the APPOINTMENT state's
    # give-up-after-unclear-replies fallback was reusing ra_close ("Bilkul
    # sahi decision hai" -- that's absolutely the right decision) as its
    # close line. That's wrong when the caller never actually confirmed
    # anything -- their last turn was literally "hello?" in confusion, not
    # agreement. Honest neutral sign-off instead, matching fresh_cta's
    # existing fresh_no_date_close for the same situation.
    "ra_close_no_response": "Bilkul theek hai ji! Aage kabhi zaroorat pade toh Krishna Furniture ko zaroor yaad rakhiyega. Aapka din shubh ho.",
    "ra_dnc": "Bilkul ji, maafi chahti hoon agar takleef hui. Main abhi aapka number DNC list mein daal deti hoon — ab koi call nahi aayegi. Bahut shukriya, aapka din shubh ho.",
    "ra_q_location": "Hamare showroom Sector 14 Gurgaon, Delhi aur Noida mein hain ji — Monday se Sunday, subah 10 baje se raat 8 baje tak khule rehte hain.",
    "ra_q_name": "Ji, mera naam Priya hai — main Krishna Furniture ki taraf se baat kar rahi hoon.",
    "ra_q_valuation": "Ji, ek kaam kijiye — showroom aa kar mujhse mil lijiye, waha aaram se sab dikha paungi. Aap kis din aa sakte hain?",
    # Three added 2026-08-13 -- real questions that previously got no answer
    # at all (silently swallowed or answered with an unrelated pitch line).
    # q_price_range uses the same grounded prices knowledge.py's fresh-lead
    # FAQ funnel already uses (sofa/bed/dining) -- react_a/b/c had zero
    # pricing knowledge wired in before this. q_offer_scope deliberately
    # doesn't assert which products are covered (never confirmed as true),
    # defers to WhatsApp instead of guessing.
    "ra_q_price_range": "Sofa ₹33,000 se, bed ₹71,000 se, aur dining set ₹1,19,000 se shuru hote hain ji — exact price main WhatsApp par bhi bhej deti hoon.",
    # Rewritten 2026-08-13 -- user feedback: don't defer a question that has
    # a real, known answer to WhatsApp. Sofa/bed/dining/wardrobe/chair are
    # the categories this store's real knowledge base (knowledge.py) has
    # grounded prices for, so this states them directly rather than
    # deflecting. Ends the same way offer_main does ("achhi baat bataun?")
    # so it flows straight into hook_cta next, same two-line shape as the
    # normal offer pitch.
    "ra_q_offer_scope": "Sofa, bed, dining table, wardrobe, chair — is offer mein kaafi options hain ji. Ek aur achhi baat bataun?",
    "ra_already_purchased": "Bahut badhiya ji! Agar future mein kabhi zaroorat pade toh humein zaroor yaad rakhiyega. Aapka din shubh ho.",
    "ra_appointment_ask": "Maine details WhatsApp par bhej di hain ji. Aap bas apni store visit ki ek date confirm kar dijiye — main khud aapka intezaar karungi.",
    "ra_appointment_confirmed": "Bahut badhiya ji! Main khud store par aapko milungi — zaroor aaiyega.",
    "ra_appointment_reask": "Maaf kijiye ji, date theek se samajh nahi aayi. Ek baar phir se bata dijiye please?",
    "ra_filler_1": "Haan ji...", "ra_filler_2": "Ji haan...", "ra_filler_3": "Bilkul ji...",
    "ra_filler_4": "Achha ji...", "ra_filler_5": "Samajh gayi ji...", "ra_filler_6": "Theek hai ji...",

}

REACT_B_SCRIPT = {
    # 2026-08-15 warm rewrite (Agent_Replies_Warm.md, user-approved verbatim).
    # Objection/close/Q&A/filler keys below are word-for-word identical to
    # REACT_A_SCRIPT's -- the doc's "Shared objection handlers"/"Shared
    # information replies" blocks are explicitly reused across A/B/C, only
    # the opener/pitch lines carry B's social-proof flavor.
    "rb_greet_main": "Pichhle kuch dino mein kaafi customers ne apna purana furniture exchange kar ke naya le liya ji — isiliye socha aapko bhi bata doon. Ghar ka furniture upgrade karna ho toh yeh offer kaafi kaam ka hai. Sunna chahenge?",
    "rb_greet_who": "Ji, main Priya bol rahi hoon, Krishna Furniture se. Aap hamare purane customer rahe hain, isiliye khud call kiya. Aaj kal bahut families ghar naya kara rahi hain — wahi offer aapke liye bhi laayi hoon.",
    "rb_greet_repeat": "Haan ji — purane customers ke liye ek special offer hai. Purana furniture achhe rate par le lenge, naye par heavy discount denge. Offer bata doon?",
    "rb_greet_privacy": "Ji bilkul — aapka number hamare purane customer records mein hi hai, koi third party nahi. Aap hamare valued customer hain, isliye maine khud call ki.",
    "rb_greet_hostile": "Maafi chahti hoon agar galat time par call kiya ji. Details WhatsApp par bhej deti hoon — dekhna bilkul aapki marzi. Aapka din shubh ho!",
    "rb_offer_main": "Abhi naye par 25% discount hai ji, aur purana exchange karne par alag value bhi milti hai — isiliye kaafi log soch se kam budget mein naya furniture le pa rahe hain. Ek aur baat bataun?",
    "rb_offer_explain": "Bilkul simple hai ji — aap showroom aaiye, hum aapke saamne purane furniture ki value calculate karenge. Us value par 25%, aur upar se 25% — total 43 se 50% tak saving. Koi hidden condition nahi.",
    "rb_offer_trust": "Ek baar showroom aa jaiye ji — free mein purane furniture ki value estimate ho jaati hai, koi commitment nahi.",
    "rb_offer_urgency": "Is mahine kaafi families aa rahi hain ji, aur pieces limited hain — isiliye keh rahi hoon, thoda jaldi dekh lijiyega. Baaki aapki marzi.",
    "rb_obj_not_interested": "Ek baar WhatsApp par bas photos aur price dekh lijiyega ji — koi pressure nahi. Pasand aaye toh baat aage badhaate hain.",
    "rb_obj_busy": "Bilkul samajhti hoon ji, aap busy hain — main sirf details WhatsApp par bhej deti hoon. Apni fursad mein, jab time mile tab dekh lijiyega. Koi jaldi nahi.",
    "rb_obj_expensive": "Samajhti hoon ji, budget dekhna zaroori hai. Isiliye toh yeh exchange offer hai — poora naya nahi, purane ke saath adjust hota hai. Exact amount WhatsApp par bhej deti hoon, aap khud dekh lijiyega kitna kam ho jaata hai.",
    "rb_obj_online": "Sahi kaha ji. Bas ek baat — online par delivery, installation, after-sales sab alag se lagta hai. Yahan factory price hai, upar se exchange value bhi. Poora comparison WhatsApp par bhej deti hoon, aap khud farak dekh lijiyega.",
    "rb_obj_think": "Zaroor soch lijiye ji, yeh toh sahi baat hai. Main details WhatsApp par bhej ke rakhti hoon — jab bhi decide karein, saamne rahengi. Bas offer is mahine tak hai, itna dhyaan rahe.",
    "rb_obj_recovery": "Sach batau ji — jo families yeh offer le kar gayi hain, bahut khush hain. Aadhe daam mein ghar ka look hi badal jaata hai. Aap bhi ek baar aa kar dekhiye, achha lagega.",
    # No distinct hook_cta line for React B in the doc -- constructed to
    # match rb_greet_who's social-proof framing, same shape as ra_hook_cta.
    "rb_hook_cta": "Aap bhi hamare purane customer hain, isliye yeh offer maine khud share kiya ji. Main WhatsApp par furniture ke photos aur prices bhej deti hoon — ek baar dekh lijiye, decision baad mein bhi le sakte hain.",
    "rb_wa_cta": "Main saari details abhi WhatsApp par bhej deti hoon ji — photos, prices, sab. Aap aaram se dekh lijiyega, decision baad mein bhi le sakte hain.",
    "rb_close": "Bahut achha ji! Main abhi WhatsApp par photos aur prices bhej deti hoon. Aur ek baar showroom aa jaiye — purana furniture hum sambhal lenge, aap bas naya pasand kijiye. Milte hain! Shukriya.",
    "rb_close_conviction": "Bas itna keh rahi hoon, pieces limited hain ji — showroom mein aaiye, apne saamne value calculate karwaiye, aur wohi din naya furniture le jaaiye. Purana hum sambhal lenge. Bahut shukriya!",
    # See ra_close_no_response's comment above -- same fix, this voice.
    "rb_close_no_response": "Bilkul theek hai ji! Aage kabhi zaroorat pade toh Krishna Furniture ko zaroor yaad rakhiyega. Aapka din shubh ho.",
    "rb_dnc": "Bilkul ji, maafi chahti hoon agar takleef hui. Main abhi aapka number DNC list mein daal deti hoon — ab koi call nahi aayegi. Bahut shukriya, aapka din shubh ho.",
    "rb_q_location": "Hamare showroom Sector 14 Gurgaon, Delhi aur Noida mein hain ji — Monday se Sunday, subah 10 baje se raat 8 baje tak khule rehte hain.",
    "rb_q_name": "Ji, mera naam Priya hai — main Krishna Furniture ki taraf se baat kar rahi hoon.",
    "rb_q_valuation": "Ji, ek kaam kijiye — showroom aa kar mujhse mil lijiye, waha aaram se sab dikha paungi. Aap kis din aa sakte hain?",
    # See ra_q_price_range/ra_q_offer_scope/ra_already_purchased's comment (REACT_A_SCRIPT above).
    "rb_q_price_range": "Sofa ₹33,000 se, bed ₹71,000 se, aur dining set ₹1,19,000 se shuru hote hain ji — exact price main WhatsApp par bhi bhej deti hoon.",
    # See ra_q_offer_scope's comment (REACT_A_SCRIPT above).
    "rb_q_offer_scope": "Sofa, bed, dining table, wardrobe, chair — is offer mein kaafi options hain ji. Ek aur achhi baat bataun?",
    "rb_already_purchased": "Bahut badhiya ji! Agar future mein kabhi zaroorat pade toh humein zaroor yaad rakhiyega. Aapka din shubh ho.",
    "rb_appointment_ask": "Maine details WhatsApp par bhej di hain ji. Aap bas apni store visit ki ek date confirm kar dijiye — main khud aapka intezaar karungi.",
    "rb_appointment_confirmed": "Bahut badhiya ji! Main khud store par aapko milungi — zaroor aaiyega.",
    "rb_appointment_reask": "Maaf kijiye ji, date theek se samajh nahi aayi. Ek baar phir se bata dijiye please?",
    "rb_filler_1": "Haan ji...", "rb_filler_2": "Ji haan...", "rb_filler_3": "Bilkul ji...",
    "rb_filler_4": "Achha ji...", "rb_filler_5": "Samajh gayi ji...", "rb_filler_6": "Theek hai ji...",

}

REACT_C_SCRIPT = {
    # 2026-08-15 warm rewrite (Agent_Replies_Warm.md, user-approved verbatim).
    # Objection/close/Q&A/filler keys below are word-for-word identical to
    # REACT_A_SCRIPT's -- see REACT_B_SCRIPT's header comment above.
    "rc_greet_main": "Ek chhota sa sawaal poochun ji? Agar aapko naya furniture mile, aur purana bhi achhi value mein chala jaaye — woh bhi kam kharche mein — toh sunna chahenge?",
    "rc_greet_who": "Ji, main Priya bol rahi hoon, Krishna Furniture se. Aap hamare purane customer rahe hain, isiliye khud call kiya. Bas ek chhoti si baat poochni thi — agar naya furniture aadhe daam mein mile, toh sunenge?",
    "rc_greet_repeat": "Haan ji — main yahi pooch rahi thi. Naya furniture bhi, aur purana bhi achhe rate mein chala jaaye — aadhe daam mein. Sunna chahenge?",
    "rc_greet_privacy": "Ji bilkul — aapka number hamare purane customer records mein hi hai, koi third party nahi. Aap hamare valued customer hain, isliye maine khud call ki.",
    "rc_greet_hostile": "Maafi chahti hoon agar galat time par call kiya ji. Details WhatsApp par bhej deti hoon — dekhna bilkul aapki marzi. Aapka din shubh ho!",
    "rc_offer_main": "Toh bas wahi offer chal raha hai ji — naye par 25% discount, aur purana exchange karne par uski alag value bhi. Ek aur baat bataun?",
    "rc_offer_explain": "Bilkul simple hai ji — aap showroom aaiye, hum aapke saamne purane furniture ki value calculate karenge. Us value par 25%, aur upar se 25% — total 43 se 50% tak saving. Koi hidden condition nahi.",
    "rc_offer_trust": "Bilkul relax rahiye ji, main zor bilkul nahi de rahi. Ek baar showroom aa jaiye — free mein value estimate ho jaati hai, koi commitment nahi. Bas ek baar aaiye toh sahi.",
    "rc_offer_urgency": "Bas itna ki pieces limited hain aur offer is mahine tak hi hai ji — isiliye keh rahi hoon, dekh lijiye toh behtar rahega. Baaki poori tarah aapki marzi.",
    "rc_obj_not_interested": "Ek baar WhatsApp par bas photos aur price dekh lijiyega ji — koi pressure nahi. Pasand aaye toh baat aage badhaate hain.",
    "rc_obj_busy": "Bilkul samajhti hoon ji, aap busy hain — main sirf details WhatsApp par bhej deti hoon. Apni fursad mein, jab time mile tab dekh lijiyega. Koi jaldi nahi.",
    "rc_obj_expensive": "Samajhti hoon ji, budget dekhna zaroori hai. Isiliye toh yeh exchange offer hai — poora naya nahi, purane ke saath adjust hota hai. Exact amount WhatsApp par bhej deti hoon, aap khud dekh lijiyega kitna kam ho jaata hai.",
    "rc_obj_online": "Sahi kaha ji. Bas ek baat — online par delivery, installation, after-sales sab alag se lagta hai. Yahan factory price hai, upar se exchange value bhi. Poora comparison WhatsApp par bhej deti hoon, aap khud farak dekh lijiyega.",
    "rc_obj_think": "Zaroor soch lijiye ji, yeh toh sahi baat hai. Main details WhatsApp par bhej ke rakhti hoon — jab bhi decide karein, saamne rahengi. Bas offer is mahine tak hai, itna dhyaan rahe.",
    "rc_obj_recovery": "Sach batau ji — jo families yeh offer le kar gayi hain, bahut khush hain. Aadhe daam mein ghar ka look hi badal jaata hai. Aap bhi ek baar aa kar dekhiye, achha lagega.",
    "rc_hook_cta": "Yeh offer hum specially apne existing customers ke saath share kar rahe hain ji, isiliye maine aapko personally call kiya. Main WhatsApp par photos aur poori details bhej deti hoon — ek baar dekh lijiye, koi commitment bilkul nahi hai.",
    "rc_wa_cta": "Main saari details abhi WhatsApp par bhej deti hoon ji — photos, prices, sab. Aap aaram se dekh lijiyega, decision baad mein bhi le sakte hain. Koi commitment nahi.",
    "rc_close": "Bahut achha ji! Main abhi WhatsApp par photos aur prices bhej deti hoon — free mein value estimate ho jaayegi. Aur ek baar showroom aa jaiye — purana furniture hum sambhal lenge, aap bas naya pasand kijiye. Milte hain! Shukriya.",
    # See ra_close_no_response's comment (REACT_A_SCRIPT above) -- same fix, this voice.
    "rc_close_no_response": "Bilkul theek hai ji! Main zor bilkul nahi de rahi. Aage kabhi zaroorat pade toh Krishna Furniture ko zaroor yaad rakhiyega. Aapka din shubh ho.",
    "rc_dnc": "Bilkul ji, maafi chahti hoon agar takleef hui. Main abhi aapka number DNC list mein daal deti hoon — ab koi call nahi aayegi. Bahut shukriya, aapka din shubh ho.",
    "rc_q_location": "Hamare showroom Sector 14 Gurgaon, Delhi aur Noida mein hain ji — Monday se Sunday, subah 10 baje se raat 8 baje tak khule rehte hain.",
    "rc_q_name": "Ji, mera naam Priya hai — main Krishna Furniture ki taraf se baat kar rahi hoon.",
    "rc_q_valuation": "Ji, ek kaam kijiye — showroom aa kar mujhse mil lijiye, waha aaram se sab dikha paungi. Aap kis din aa sakte hain?",
    # See ra_q_price_range/ra_q_offer_scope/ra_already_purchased's comment (REACT_A_SCRIPT above).
    "rc_q_price_range": "Sofa ₹33,000 se, bed ₹71,000 se, aur dining set ₹1,19,000 se shuru hote hain ji — exact price main WhatsApp par bhi bhej deti hoon.",
    # See ra_q_offer_scope's comment (REACT_A_SCRIPT above).
    "rc_q_offer_scope": "Sofa, bed, dining table, wardrobe, chair — is offer mein kaafi options hain ji. Ek aur achhi baat bataun?",
    "rc_already_purchased": "Bahut badhiya ji! Agar future mein kabhi zaroorat pade toh humein zaroor yaad rakhiyega. Aapka din shubh ho.",
    "rc_appointment_ask": "Maine details WhatsApp par bhej di hain ji. Aap bas apni store visit ki ek date confirm kar dijiye — main khud aapka intezaar karungi.",
    "rc_appointment_confirmed": "Bahut badhiya ji! Main khud store par aapko milungi — zaroor aaiyega.",
    "rc_appointment_reask": "Maaf kijiye ji, date theek se samajh nahi aayi. Ek baar phir se bata dijiye please?",
    "rc_filler_1": "Haan ji...", "rc_filler_2": "Ji haan...", "rc_filler_3": "Bilkul ji...",
    "rc_filler_4": "Achha ji...", "rc_filler_5": "Samajh gayi ji...", "rc_filler_6": "Theek hai ji...",
}

# The only 4 product categories fresh_greet_*/fresh_greet_who_* has dedicated
# audio for (see FRESH_CTA_SCRIPT below) — anything else falls back to
# fresh_greet_generic.
FRESH_CTA_PRODUCT_KEYS = ("bed", "sofa", "wardrobe", "dining")


def normalize_fresh_product_key(raw: str | None) -> str | None:
    """
    outbound_leads.product_interest is free text from the lead-intake pipeline
    ("dining table", "sofa cum bed", "centre table", "bed, sofa") — not
    constrained to FRESH_CTA_PRODUCT_KEYS. A bare `raw in FRESH_CTA_PRODUCT_KEYS`
    check only matched exact single-word values, so ~45% of fresh_cta calls
    with a real, non-null product_interest were silently falling back to the
    generic greeting (confirmed live against today's dispatch log: "dining
    table", "sofa cum bed", "bed, sofa" all missed). Substring-match against
    the same 4 categories instead; first match wins on multi-value strings
    ("bed, sofa" -> "bed"). Genuinely uncovered categories (centre table,
    study table — no dedicated audio exists for either) still correctly fall
    through to None/generic, same as before.
    """
    if not raw:
        return None
    t = raw.strip().lower()
    if t in FRESH_CTA_PRODUCT_KEYS:
        return t
    for key in FRESH_CTA_PRODUCT_KEYS:
        if key in t:
            return key
    return None


FRESH_CTA_SCRIPT = {
    # 2026-08-15 warm rewrite (Agent_Replies_Warm.md, user-approved verbatim).
    # All lines voiced as Simran. No dnc key here on purpose — hard decline
    # reuses ra_dnc's existing cached audio directly (see handle_fresh_cta_turn).
    "fresh_greet_bed": "Namaste ji! WhatsApp par hamari baat hui thi — aap bed dekhna chahte the. Toh store par kab aa rahe hain? Main khud aapko wahi milungi.",
    "fresh_greet_sofa": "Namaste ji! WhatsApp par hamari baat hui thi — aap sofa dekhna chahte the. Toh store par kab aa rahe hain? Main khud aapko wahi milungi.",
    "fresh_greet_wardrobe": "Namaste ji! WhatsApp par hamari baat hui thi — aap wardrobe dekhna chahte the. Toh store par kab aa rahe hain? Main khud aapko wahi milungi.",
    "fresh_greet_dining": "Namaste ji! WhatsApp par hamari baat hui thi — aap dining set dekhna chahte the. Toh store par kab aa rahe hain? Main khud aapko wahi milungi.",
    "fresh_greet_generic": "Namaste ji! WhatsApp par Krishna Furniture ke baare mein hamari baat hui thi. Store par kab aa sakte hain? Main aapko wahi milungi.",
    "fresh_objection": "Ji, bahut hi sundar naye designs aaye hain — aapko zaroor pasand aayenge. Main WhatsApp par bhej deti hoon, par ek baar store aa kar dekhenge toh farak khud dikhega. Kab aa sakte hain?",
    "fresh_appointment_confirmed": "Bahut badhiya ji! Main aapka appointment confirm kar deti hoon — hamari team aapka intezaar karegi. Jaldi milte hain!",
    "fresh_no_date_close": "Koi baat nahi ji. Main WhatsApp par kuch sundar options bhej deti hoon — aaram se dekh lijiye, phir jab convenient ho visit plan kar lenge.",
    "fresh_soft_defer": "Theek hai ji, aap WhatsApp par hi confirm kar dijiyega — main aur options bhej deti hoon.",
    # Store list standardized to the 3-showroom version (Sector 14 Gurgaon,
    # Delhi, Noida) that react_a/b/c already use, per the doc's own
    # [VERIFY STORES] flag -- Fresh CTA's old 4-store "Gurugram/Faridabad"
    # version was the stale outlier.
    "fresh_location_info": "Hamare showroom Sector 14 Gurgaon, Delhi aur Noida mein hain ji. WhatsApp par main aapko exact address aur Google Maps link bhej deti hoon — wahi se date confirm kar dijiyega, phir wahi milenge.",
    "fresh_greet_who_bed": "Ji, Krishna Furniture se — hamari WhatsApp par baat hui thi bed ke baare mein. Store par kab aana hoga?",
    "fresh_greet_who_sofa": "Ji, Krishna Furniture se — hamari WhatsApp par baat hui thi sofa ke baare mein. Store par kab aana hoga?",
    "fresh_greet_who_wardrobe": "Ji, Krishna Furniture se — hamari WhatsApp par baat hui thi wardrobe ke baare mein. Store par kab aana hoga?",
    "fresh_greet_who_dining": "Ji, Krishna Furniture se — hamari WhatsApp par baat hui thi dining set ke baare mein. Store par kab aana hoga?",
    "fresh_greet_who_generic": "Ji, Krishna Furniture se — hamari WhatsApp par baat hui thi. Store par kab aana hoga?",
    # Phase 2 — price/trust objection handling for fresh_cta's single
    # APPOINTMENT state, wired via route_objection() (webhook_reactivation.py).
    # Single key each (no voice fan-out needed) since this funnel is always
    # Simran, unlike obj_repeat_generic which crosses flows/voices.
    "fresh_price": "Ji, price bilkul reasonable hai — poori detail WhatsApp par bhej deti hoon. Store aa kar dekhenge toh value khud samajh aayegi. Kab aa sakte hain?",
    "fresh_trust": "Bilkul samajhti hoon ji. Store aa kar khud dekh lijiye — koi obligation nahi, wahi se sahi decide kar paayenge. Kab aa sakte hain?",
}

# fresh_cta Call 2/3 greetings — same Simran voice as Call 1 (fresh_ prefix, no
# voice change between cycles for this funnel, per earlier decision). Only the
# opening line differs per cycle; fresh_objection/fresh_appointment_confirmed/
# fresh_no_date_close/fresh_soft_defer/fresh_location_info (in FRESH_CTA_SCRIPT
# above) are reused as-is across all 3 cycles — handle_fresh_cta_turn's turn
# logic is identical regardless of which greeting played.
FRESH_CALL2_SCRIPT = {
    "fresh_c2_greet_bed": "Namaste ji, Priya bol rahi hoon Krishna Furniture se. Pichhli baar humne baat ki thi bed ke baare mein — bas confirm karna tha, kaunsa din aana hoga store par?",
    "fresh_c2_greet_sofa": "Namaste ji, Priya bol rahi hoon Krishna Furniture se. Pichhli baar humne baat ki thi sofa ke baare mein — bas confirm karna tha, kaunsa din aana hoga store par?",
    "fresh_c2_greet_wardrobe": "Namaste ji, Priya bol rahi hoon Krishna Furniture se. Pichhli baar humne baat ki thi wardrobe ke baare mein — bas confirm karna tha, kaunsa din aana hoga store par?",
    "fresh_c2_greet_dining": "Namaste ji, Priya bol rahi hoon Krishna Furniture se. Pichhli baar humne baat ki thi dining set ke baare mein — bas confirm karna tha, kaunsa din aana hoga store par?",
    "fresh_c2_greet_generic": "Namaste ji, Priya bol rahi hoon Krishna Furniture se. Pichhli baar humne baat ki thi — bas confirm karna tha, kaunsa din aana hoga store par?",
}

FRESH_CALL3_SCRIPT = {
    "fresh_c3_greet_bed": "Namaste ji, Priya, Krishna Furniture se. Bed ke baare mein do baar baat ho chuki hai — bas ek aakhri baar poochna tha, kaunsa din aa sakte hain aap?",
    "fresh_c3_greet_sofa": "Namaste ji, Priya, Krishna Furniture se. Sofa ke baare mein do baar baat ho chuki hai — bas ek aakhri baar poochna tha, kaunsa din aa sakte hain aap?",
    "fresh_c3_greet_wardrobe": "Namaste ji, Priya, Krishna Furniture se. Wardrobe ke baare mein do baar baat ho chuki hai — bas ek aakhri baar poochna tha, kaunsa din aa sakte hain aap?",
    "fresh_c3_greet_dining": "Namaste ji, Priya, Krishna Furniture se. Dining set ke baare mein do baar baat ho chuki hai — bas ek aakhri baar poochna tha, kaunsa din aa sakte hain aap?",
    "fresh_c3_greet_generic": "Namaste ji, Priya, Krishna Furniture se. Do baar baat ho chuki hai — bas ek aakhri baar poochna tha, kaunsa din aa sakte hain aap?",
}

CALL2_SCRIPT = {
    # 2026-08-15 warm rewrite (Agent_Replies_Warm.md, user-approved verbatim).
    "c2_greet_main": "Namaste ji! Priya bol rahi hoon, Krishna Furniture se. Pichhli baar hamari baat hui thi — yaad hai na aapko?",
    # "furniture exchange ki" deliberately dropped from these two lines
    # (2026-08-11) -- call2/call3 scripts are shared across every lead
    # regardless of which offer their Call 1 pitched (exchange, or the
    # Independence Day flat-50% sale from 2026-08-11), so the wording needs
    # to stay accurate for both without a second variant system. "Jo
    # details bheji thi" works either way.
    "c2_greet_reorient": "Ji, Krishna Furniture se — maine aapko WhatsApp par offer ki details bheji thi na, wahi.",
    "c2_greet_annoyed": "Bilkul ji, bas 30 second loongi — aapki store visit ki date confirm karni thi, isiliye call kiya.",
    "c2_wa_check": "Achha ji, WhatsApp par jo details bheji thi — ek nazar dekh paaye aap?",
    "c2_invite_seen": "Ji bahut badhiya! Toh ek baar showroom zaroor aa jaiye. Aap kis din free honge? Ek date bata dijiye, main wahi milungi.",
    "c2_invite_resend": "Koi baat nahi ji, main abhi dobara WhatsApp par bhej deti hoon — zaroor dekh lijiyega. Ya seedha showroom bhi aa sakte hain. Kis din free honge? Ek date bata dijiye.",
    "c2_date_direct": "Aap store visit ke liye kis din free honge ji? Ek date bata dijiye, main note kar leti hoon.",
    "c2_date_reask": "Bilkul ji, koi jaldi nahi. Bas ek din bata dijiye — usi din store mein milte hain.",
    "c2_booked": "Theek hai ji, main store par hi aapko milungi. Zaroor aaiyega. Bahut dhanyawad!",
    "c2_obj_price": "Ho sakta hai ji — isiliye ek baar dekh lena behtar rahega. Waise final decision toh aap showroom mein hi lenge na, tab tasalli ho jaayegi.",
    # Phase 2b -- WA_CHECK's busy/sochna_hai gap. Single-play, self-contained
    # (asks for a date itself, same shape as c2_invite_seen/c2_invite_resend
    # above it, since WA_CHECK has no separate opening line to hand off to).
    "c2_obj_timing": "Koi baat nahi ji, bilkul samajhti hoon. Details WhatsApp par bhej deti hoon, apni convenience se dekh lijiyega. Aur jab free ho, ek din bata dijiyega.",
    "c2_obj_scam": "Bilkul bharosa rakhiye ji — koi gadbad nahi. Aap chahein toh seedha showroom aa kar khud dekh lijiye. Kis din aa sakte hain?",
    "c2_obj_not_interested": "Koi baat nahi ji, bas confirm karna tha. Aage zaroorat ho toh Krishna Furniture ko yaad rakhiyega. Shukriya!",
    "c2_close_thinking": "Theek hai ji, aaram se soch lijiye — koi jaldi nahi. Details WhatsApp par bhej deti hoon.",
    "c2_close_busy": "Koi baat nahi ji — jab time mile tab dekh lijiyega. Main bhej deti hoon.",
    "c2_close_price": "Bilkul samajhti hoon ji. Details WhatsApp par bhej deti hoon, fursad mein dekh lijiyega.",
    "c2_close_declined": "Aapne time diya, uske liye bahut bahut shukriya ji. Aapka din shubh ho!",
}

CALL3_SCRIPT = {
    # 2026-08-15 warm rewrite (Agent_Replies_Warm.md, user-approved verbatim).
    "c3_greet_main": "Namaste ji! Priya, Krishna Furniture se. Aapse pehle bhi baat hui thi — bas ek aakhri baar poochne ke liye call kiya, kuch socha aapne?",
    # Same "exchange" drop as c2_greet_reorient/c2_wa_check above -- offer-
    # agnostic wording so this works for both the exchange pitch and the
    # Independence Day sale.
    "c3_greet_reorient": "Ji, Krishna Furniture se — wahi offer jo maine pehle aapko bataya tha.",
    "c3_greet_hostile": "Bilkul theek hai ji, samajh gayi — main aur call nahi karungi. Aapke time ke liye shukriya, aapka din shubh ho.",
    "c3_decision_date": "Ek baar showroom aa jaiye ji, sirf paanch minute lagenge. Kis din free honge? Ek date bata dijiye.",
    "c3_date_reask": "Bilkul ji, koi jaldi nahi. Bas ek din bata dijiye — usi din store mein milte hain.",
    "c3_booked": "Theek hai ji, main store par hi milungi. Zaroor aaiyega. Dhanyawad!",
    "c3_obj_price": "Bilkul samajhti hoon ji. Offer WhatsApp par bhej rakhi hai — jab convenient ho dekh lijiyega.",
    "c3_obj_scam": "Bilkul bharosa rakhiye ji — showroom khud aa kar dekh lijiye. Kis din aa sakte hain? Ek date bata dijiye.",
    "c3_declined": "Bilkul samajhti hoon ji. Aapne time diya, uske liye shukriya. Aapka din shubh ho.",
    "c3_close_thinking_final": "Koi baat nahi ji — details WhatsApp par hain, jab man kare dekh lijiyega. Aapka din shubh ho.",
    "c3_close_busy": "Koi baat nahi ji, abhi disturb nahi karti. Details WhatsApp par bhej rakhi hain — jab time mile dekh lijiyega.",
}

ALL_SCRIPTS = {
    "react_a": REACT_A_SCRIPT,
    "react_b": REACT_B_SCRIPT,
    "react_c": REACT_C_SCRIPT,
    "fresh_cta": FRESH_CTA_SCRIPT,
}

def get_script(campaign: str) -> dict:
    return ALL_SCRIPTS.get(campaign, REACT_A_SCRIPT)

def get_prefix(campaign: str) -> str:
    return {"react_a": "ra", "react_b": "rb", "react_c": "rc", "fresh_cta": "fresh"}.get(campaign, "ra")


# Runtime-importable mirror of generate_react_abc_v2_cache.py's SPEAKER_MAP —
# that file is a one-shot generation script, not meant to be imported by the
# live app, but route_objection() (webhook_reactivation.py) needs the same
# prefix->voice mapping at request time to pick the correctly-voiced variant
# of any cross-flow shared key (obj_repeat_generic_{voice},
# obj_timing_greet_generic_{voice}) for whichever flow/plan is speaking.
# Keep the two in sync if a plan/cycle's assigned voice ever changes.
PREFIX_VOICE_MAP = {
    "ra": "ritu", "rb": "shreya", "rc": "simran",
    "c2": "ritu", "c3": "simran", "fresh": "simran",
}


# ─────────────────────────────────────────────────────────────────────────────
# SHARED — Q&A/appointment keys migrated to per-plan dicts (ra_/rb_/rc_).
# Kept mostly empty so utility scripts that import SHARED_SCRIPT don't error;
# holds plan-agnostic one-off lines instead (e.g. the wa_decline_confirm lane's
# opener, which plays regardless of which of react_a/b/c the lead is on).
# ─────────────────────────────────────────────────────────────────────────────
SHARED_SCRIPT = {
    # 2026-08-15 warm rewrite (Agent_Replies_Warm.md, user-approved verbatim).
    "wa_decline_confirm_greet": "Namaste ji! Maine notice kiya aap WhatsApp par thoda soch mein the — bilkul samajhti hoon. Bas itna jaanna tha, abhi aap interested nahi hain, ya thodi aur jaankari chahiye taaki decide kar sakein?",
    # Flow-agnostic "please repeat that" acknowledgment, used by
    # route_objection() (webhook_reactivation.py) for every repeat-intent
    # turn EXCEPT react Call1's GREETING state, which keeps its existing
    # content-specific {p}_greet_repeat line. Same text in all 3 voices —
    # 3 separate keys (not 1) because this line is reachable from flows that
    # don't share a voice (fresh_cta/Call3=simran, Call2=ritu, react_a/b/c
    # =ritu/shreya/simran) and a single voice would audibly clash mid-call
    # in whichever flows it didn't match; route_objection() picks the right
    # one via PREFIX_VOICE_MAP above.
    "obj_repeat_generic_ritu": "Oh, maaf kijiye ji — aapki awaaz thodi clear nahi aayi. Ek baar phir se bata dijiye please?",
    "obj_repeat_generic_shreya": "Oh, maaf kijiye ji — aapki awaaz thodi clear nahi aayi. Ek baar phir se bata dijiye please?",
    "obj_repeat_generic_simran": "Oh, maaf kijiye ji — aapki awaaz thodi clear nahi aayi. Ek baar phir se bata dijiye please?",
    # Phase 2b — GREETING-stage busy/sochna_hai gap (react_a/b/c, call2,
    # call3). Same 3-voice-variant reasoning as obj_repeat_generic above.
    # Deliberately content-free (no offer/pitch reference) since the
    # customer hasn't heard anything yet at GREETING — route_objection()
    # plays this THEN immediately plays that flow's own next default line
    # in the same turn (offer_main / c2_wa_check / c3_decision_date),
    # mirroring the two-play convention GREETING already uses for every
    # other acknowledged intent there (confusion_who etc).
    "obj_timing_greet_generic_ritu": "Bilkul samajhti hoon ji, koi jaldi nahi. Bas do minute mein simple si baat bata deti hoon — phir poori tarah aapki marzi.",
    "obj_timing_greet_generic_shreya": "Bilkul samajhti hoon ji, koi jaldi nahi. Bas do minute mein simple si baat bata deti hoon — phir poori tarah aapki marzi.",
    "obj_timing_greet_generic_simran": "Bilkul samajhti hoon ji, koi jaldi nahi. Bas do minute mein simple si baat bata deti hoon — phir poori tarah aapki marzi.",
    # Four added 2026-08-14 -- "escalate"/"wa_ok"/"wa_prefers"/"personal_question"
    # were all being correctly detected by detect_intents() and then silently
    # dropped -- confirmed live, zero routing checks anywhere in the file for
    # any of the four. Same cross-flow-generic pattern as obj_repeat_generic/
    # obj_timing_greet_generic above (one text, three voice-suffixed keys).
    #
    # obj_escalate_generic rewritten 2026-08-15 to the doc's ★ escalate text,
    # which names a "Customer Relations Head" and asks the caller for a
    # callback time. NOTE: this promise has no backing implementation yet —
    # nothing captures the caller's answer to "aap kaunsa time batayenge?" or
    # logs a real callback task anywhere in the codebase. Implementing the
    # TEXT here per explicit instruction ("implement everything as it is");
    # the logging/follow-up mechanism to make this promise real is still a
    # separate, not-yet-designed piece of work (see pending tasks).
    "obj_escalate_generic_ritu": "Bilkul ji — is baare mein main hamari Customer Relations Head se aapki baat karwa deti hoon. Abhi woh call par available nahi hain, toh main aapke liye ek call schedule kar deti hoon — woh aapko poori tarah help karengi. Aap kaunsa time batayenge?",
    "obj_escalate_generic_shreya": "Bilkul ji — is baare mein main hamari Customer Relations Head se aapki baat karwa deti hoon. Abhi woh call par available nahi hain, toh main aapke liye ek call schedule kar deti hoon — woh aapko poori tarah help karengi. Aap kaunsa time batayenge?",
    "obj_escalate_generic_simran": "Bilkul ji — is baare mein main hamari Customer Relations Head se aapki baat karwa deti hoon. Abhi woh call par available nahi hain, toh main aapke liye ek call schedule kar deti hoon — woh aapko poori tarah help karengi. Aap kaunsa time batayenge?",
    # Not covered by the doc (personal_question isn't one of its named
    # categories -- it's distinct from ask_name, covering personal/off-topic
    # questions directed at the bot). Kept from the 2026-08-14 fix, given the
    # same "ji" warm-register polish as everything else in this pass.
    "obj_personal_question_generic_ritu": "Main Krishna Furniture ki AI assistant hoon ji, aapki madad ke liye yahan hoon. Bataiye, kya jaankari chahiye?",
    "obj_personal_question_generic_shreya": "Main Krishna Furniture ki AI assistant hoon ji, aapki madad ke liye yahan hoon. Bataiye, kya jaankari chahiye?",
    "obj_personal_question_generic_simran": "Main Krishna Furniture ki AI assistant hoon ji, aapki madad ke liye yahan hoon. Bataiye, kya jaankari chahiye?",
    "obj_wa_ok_generic_ritu": "Bilkul ji, abhi bhej rahi hoon WhatsApp par.",
    "obj_wa_ok_generic_shreya": "Bilkul ji, abhi bhej rahi hoon WhatsApp par.",
    "obj_wa_ok_generic_simran": "Bilkul ji, abhi bhej rahi hoon WhatsApp par.",
    "obj_wa_prefers_generic_ritu": "Bilkul samajhti hoon ji, WhatsApp par hi baat karte hain aage se. Abhi details bhej rahi hoon.",
    "obj_wa_prefers_generic_shreya": "Bilkul samajhti hoon ji, WhatsApp par hi baat karte hain aage se. Abhi details bhej rahi hoon.",
    "obj_wa_prefers_generic_simran": "Bilkul samajhti hoon ji, WhatsApp par hi baat karte hain aage se. Abhi details bhej rahi hoon.",
    # Added 2026-08-13 -- business decision: no turn should ever produce zero
    # reply. Previously, once a call was flagged as a likely IVR/hold loop
    # (ivr_fragment_count > 0), every further unmatched turn stayed silent
    # for the rest of that call -- built to avoid re-explaining the offer to
    # a voicemail machine, but confirmed live it also silenced a real,
    # engaged customer whose question happened to share a word with an IVR
    # pattern (see _IVR_FRAGMENT_PATTERNS' "अवेलेबल" removal same day). This
    # line replaces silence in all 4 of those branches -- harmless if it's
    # actually a machine, and means a real customer always gets acknowledged
    # instead of dead air, even when the system doesn't know how to answer
    # what they actually asked.
    "wa_fallback_deflect_ritu": "Main details WhatsApp par bhej deti hoon ji, aap wahan check kar lijiyega please.",
    "wa_fallback_deflect_shreya": "Main details WhatsApp par bhej deti hoon ji, aap wahan check kar lijiyega please.",
    "wa_fallback_deflect_simran": "Main details WhatsApp par bhej deti hoon ji, aap wahan check kar lijiyega please.",
    # Added 2026-08-13 -- fillers to bridge the LLM fallback's real latency
    # (0.5-4s, vs ~5-10ms for the normal cached-audio path) with something
    # topic-appropriate instead of dead air. Voice-matched per campaign
    # (unlike filler_audio.py's existing fillers, which hardcode "shreya"
    # for every call regardless of which voice is actually speaking --
    # likely part of why a voice sounded wrong on an earlier call). Picked
    # by a fast local keyword check on the raw transcript (webhook_reactivation.
    # _pick_llm_filler_key()) -- no LLM call, adds no latency of its own.
    "llm_filler_price_ritu": "Ek second ji, price dekh kar bataati hoon...",
    "llm_filler_price_shreya": "Ek second ji, price dekh kar bataati hoon...",
    "llm_filler_price_simran": "Ek second ji, price dekh kar bataati hoon...",
    "llm_filler_location_ritu": "Ek second ji, showroom ki detail nikaal rahi hoon...",
    "llm_filler_location_shreya": "Ek second ji, showroom ki detail nikaal rahi hoon...",
    "llm_filler_location_simran": "Ek second ji, showroom ki detail nikaal rahi hoon...",
    "llm_filler_generic_ritu": "Ek second ji, abhi dekhti hoon...",
    "llm_filler_generic_shreya": "Ek second ji, abhi dekhti hoon...",
    "llm_filler_generic_simran": "Ek second ji, abhi dekhti hoon...",

    # ─────────────────────────────────────────────────────────────────────
    # 22 new situational categories added 2026-08-15 (Agent_Replies_Warm.md,
    # user-approved verbatim) -- routing wired in route_objection()
    # (webhook_reactivation.py). See that function's comments for which of
    # these are terminal (end the call) vs continue, and which promises
    # (Customer Relations Head callback, real callback-time capture, human-
    # review flagging for legal_threat) are text-only, not yet backed by
    # real logic -- flagged there, not repeated here.
    # ─────────────────────────────────────────────────────────────────────
    "obj_wrong_number_generic_ritu": "Oh, maafi chahti hoon ji — lagta hai hamare record mein number thoda purana ho gaya hai. Aapko bekaar mein disturb kiya, iske liye sorry. Aapka din shubh ho!",
    "obj_wrong_number_generic_shreya": "Oh, maafi chahti hoon ji — lagta hai hamare record mein number thoda purana ho gaya hai. Aapko bekaar mein disturb kiya, iske liye sorry. Aapka din shubh ho!",
    "obj_wrong_number_generic_simran": "Oh, maafi chahti hoon ji — lagta hai hamare record mein number thoda purana ho gaya hai. Aapko bekaar mein disturb kiya, iske liye sorry. Aapka din shubh ho!",
    "obj_not_my_customer_generic_ritu": "Koi baat nahi ji, ho sakta hai hamare records mein thodi galti ho gayi ho — iske liye maafi. Waise abhi naya furniture lene walon ke liye ek accha offer chal raha hai — agar aap kahein toh bata doon?",
    "obj_not_my_customer_generic_shreya": "Koi baat nahi ji, ho sakta hai hamare records mein thodi galti ho gayi ho — iske liye maafi. Waise abhi naya furniture lene walon ke liye ek accha offer chal raha hai — agar aap kahein toh bata doon?",
    "obj_not_my_customer_generic_simran": "Koi baat nahi ji, ho sakta hai hamare records mein thodi galti ho gayi ho — iske liye maafi. Waise abhi naya furniture lene walon ke liye ek accha offer chal raha hai — agar aap kahein toh bata doon?",
    "obj_person_unavailable_generic_ritu": "Oh, koi baat nahi ji. Main thodi der baad dobara try kar leti hoon. Aapka time lene ke liye shukriya!",
    "obj_person_unavailable_generic_shreya": "Oh, koi baat nahi ji. Main thodi der baad dobara try kar leti hoon. Aapka time lene ke liye shukriya!",
    "obj_person_unavailable_generic_simran": "Oh, koi baat nahi ji. Main thodi der baad dobara try kar leti hoon. Aapka time lene ke liye shukriya!",
    "obj_already_called_generic_ritu": "Maafi chahti hoon ji agar baar baar call ho gaya — bura mat maaniyega. Bas ek chhoti si baat aur, phir poori tarah aapki marzi. Theek hai?",
    "obj_already_called_generic_shreya": "Maafi chahti hoon ji agar baar baar call ho gaya — bura mat maaniyega. Bas ek chhoti si baat aur, phir poori tarah aapki marzi. Theek hai?",
    "obj_already_called_generic_simran": "Maafi chahti hoon ji agar baar baar call ho gaya — bura mat maaniyega. Bas ek chhoti si baat aur, phir poori tarah aapki marzi. Theek hai?",
    "obj_callback_later_generic_ritu": "Bilkul ji, aap abhi busy hain — koi baat nahi. Aap bata dijiye, kaunsa time aapke liye theek rahega — aaj shaam ya kal? Main usi waqt call kar loongi, taaki aapko convenient ho.",
    "obj_callback_later_generic_shreya": "Bilkul ji, aap abhi busy hain — koi baat nahi. Aap bata dijiye, kaunsa time aapke liye theek rahega — aaj shaam ya kal? Main usi waqt call kar loongi, taaki aapko convenient ho.",
    "obj_callback_later_generic_simran": "Bilkul ji, aap abhi busy hain — koi baat nahi. Aap bata dijiye, kaunsa time aapke liye theek rahega — aaj shaam ya kal? Main usi waqt call kar loongi, taaki aapko convenient ho.",
    # Replaced 2026-08-18 -- real English support now exists
    # (knowledge_react_abc_en.py), so the old single Hindi-only honest
    # stopgap ("sorry, Hindi only for now") is stale for the English-request
    # direction. route_objection() flips session.lang BEFORE calling
    # play_key() for lang_pref_english/lang_pref_hindi, so in the normal
    # case these Hindi-dict copies are never actually heard (the English
    # dict's version plays instead once lang flips to "en") -- kept here
    # anyway for key-parity between the Hindi/English SHARED_SCRIPT dicts
    # and as a reasonable fallback if that ever changes.
    "obj_lang_pref_english_generic_ritu": "Bilkul ji, ab main English mein baat karti hoon.",
    "obj_lang_pref_english_generic_shreya": "Bilkul ji, ab main English mein baat karti hoon.",
    "obj_lang_pref_english_generic_simran": "Bilkul ji, ab main English mein baat karti hoon.",
    "obj_lang_pref_hindi_generic_ritu": "Bilkul ji, main Hindi mein hi baat karti hoon.",
    "obj_lang_pref_hindi_generic_shreya": "Bilkul ji, main Hindi mein hi baat karti hoon.",
    "obj_lang_pref_hindi_generic_simran": "Bilkul ji, main Hindi mein hi baat karti hoon.",
    # Punjabi isn't supported (no script/TTS for it) -- honest about that
    # specifically, doesn't flip session.lang either way.
    "obj_lang_pref_other_generic_ritu": "Punjabi mein abhi possible nahi hai ji, lekin main Hindi ya English dono mein baat kar sakti hoon — jo aapko sahi lage.",
    "obj_lang_pref_other_generic_shreya": "Punjabi mein abhi possible nahi hai ji, lekin main Hindi ya English dono mein baat kar sakti hoon — jo aapko sahi lage.",
    "obj_lang_pref_other_generic_simran": "Punjabi mein abhi possible nahi hai ji, lekin main Hindi ya English dono mein baat kar sakti hoon — jo aapko sahi lage.",
    "obj_uncertain_generic_ritu": "Koi baat nahi ji, jaldi bilkul nahi hai. Main details WhatsApp par bhej deti hoon — aaram se dekh lijiye, phir jaisa theek lage.",
    "obj_uncertain_generic_shreya": "Koi baat nahi ji, jaldi bilkul nahi hai. Main details WhatsApp par bhej deti hoon — aaram se dekh lijiye, phir jaisa theek lage.",
    "obj_uncertain_generic_simran": "Koi baat nahi ji, jaldi bilkul nahi hai. Main details WhatsApp par bhej deti hoon — aaram se dekh lijiye, phir jaisa theek lage.",
    "obj_bare_negative_generic_ritu": "Koi baat nahi ji — bas itna bata dijiye, offer mein interest nahi hai, ya abhi baat karne ka time nahi hai? Jaisa aap kahein.",
    "obj_bare_negative_generic_shreya": "Koi baat nahi ji — bas itna bata dijiye, offer mein interest nahi hai, ya abhi baat karne ka time nahi hai? Jaisa aap kahein.",
    "obj_bare_negative_generic_simran": "Koi baat nahi ji — bas itna bata dijiye, offer mein interest nahi hai, ya abhi baat karne ka time nahi hai? Jaisa aap kahein.",
    "obj_ask_emi_generic_ritu": "Ji, EMI ka option showroom mein available hai — exact plan aur detail wahin best samajh aayegi. Main WhatsApp par bhi note kar ke bhej deti hoon.",
    "obj_ask_emi_generic_shreya": "Ji, EMI ka option showroom mein available hai — exact plan aur detail wahin best samajh aayegi. Main WhatsApp par bhi note kar ke bhej deti hoon.",
    "obj_ask_emi_generic_simran": "Ji, EMI ka option showroom mein available hai — exact plan aur detail wahin best samajh aayegi. Main WhatsApp par bhi note kar ke bhej deti hoon.",
    "obj_ask_payment_method_generic_ritu": "Ji bilkul — cash, card, UPI, sab chalta hai showroom mein. Koi dikkat nahi hogi.",
    "obj_ask_payment_method_generic_shreya": "Ji bilkul — cash, card, UPI, sab chalta hai showroom mein. Koi dikkat nahi hogi.",
    "obj_ask_payment_method_generic_simran": "Ji bilkul — cash, card, UPI, sab chalta hai showroom mein. Koi dikkat nahi hogi.",
    "obj_ask_warranty_generic_ritu": "Ji, warranty product ke hisaab se thodi alag hoti hai — showroom mein team aapko exact term bata degi. Main WhatsApp par bhi bhej deti hoon.",
    "obj_ask_warranty_generic_shreya": "Ji, warranty product ke hisaab se thodi alag hoti hai — showroom mein team aapko exact term bata degi. Main WhatsApp par bhi bhej deti hoon.",
    "obj_ask_warranty_generic_simran": "Ji, warranty product ke hisaab se thodi alag hoti hai — showroom mein team aapko exact term bata degi. Main WhatsApp par bhi bhej deti hoon.",
    "obj_ask_delivery_charge_generic_ritu": "Ji, delivery aur installation ki exact detail order ke hisaab se hoti hai — main confirm kar ke WhatsApp par bhej deti hoon.",
    "obj_ask_delivery_charge_generic_shreya": "Ji, delivery aur installation ki exact detail order ke hisaab se hoti hai — main confirm kar ke WhatsApp par bhej deti hoon.",
    "obj_ask_delivery_charge_generic_simran": "Ji, delivery aur installation ki exact detail order ke hisaab se hoti hai — main confirm kar ke WhatsApp par bhej deti hoon.",
    "obj_ask_return_policy_generic_ritu": "Ji, return policy ki poori detail showroom mein clear ho jaayegi — main WhatsApp par bhi bhej deti hoon taaki aapke paas rahe.",
    "obj_ask_return_policy_generic_shreya": "Ji, return policy ki poori detail showroom mein clear ho jaayegi — main WhatsApp par bhi bhej deti hoon taaki aapke paas rahe.",
    "obj_ask_return_policy_generic_simran": "Ji, return policy ki poori detail showroom mein clear ho jaayegi — main WhatsApp par bhi bhej deti hoon taaki aapke paas rahe.",
    "obj_ask_bargain_generic_ritu": "Samajhti hoon ji, sab best rate chahte hain! Abhi jo offer chal raha hai wahi hamara best rate hai — par showroom aa kar dekhiye, kabhi kabhi kuch extra options nikal aate hain.",
    "obj_ask_bargain_generic_shreya": "Samajhti hoon ji, sab best rate chahte hain! Abhi jo offer chal raha hai wahi hamara best rate hai — par showroom aa kar dekhiye, kabhi kabhi kuch extra options nikal aate hain.",
    "obj_ask_bargain_generic_simran": "Samajhti hoon ji, sab best rate chahte hain! Abhi jo offer chal raha hai wahi hamara best rate hai — par showroom aa kar dekhiye, kabhi kabhi kuch extra options nikal aate hain.",
    "obj_ask_invoice_gst_generic_ritu": "Ji bilkul — har purchase par pakka GST bill milta hai. Iski koi tension nahi.",
    "obj_ask_invoice_gst_generic_shreya": "Ji bilkul — har purchase par pakka GST bill milta hai. Iski koi tension nahi.",
    "obj_ask_invoice_gst_generic_simran": "Ji bilkul — har purchase par pakka GST bill milta hai. Iski koi tension nahi.",
    "obj_ask_product_quality_generic_ritu": "Ji, quality aur material toh aap showroom mein khud dekhiye aur chhoo kar mehsoos kijiye — sabse achha yahi rahega ki aap khud verify karein. Aapko bharosa ho jaayega.",
    "obj_ask_product_quality_generic_shreya": "Ji, quality aur material toh aap showroom mein khud dekhiye aur chhoo kar mehsoos kijiye — sabse achha yahi rahega ki aap khud verify karein. Aapko bharosa ho jaayega.",
    "obj_ask_product_quality_generic_simran": "Ji, quality aur material toh aap showroom mein khud dekhiye aur chhoo kar mehsoos kijiye — sabse achha yahi rahega ki aap khud verify karein. Aapko bharosa ho jaayega.",
    "obj_ask_pickup_logistics_generic_ritu": "Ji, purane furniture ka pickup hum khud arrange karte hain — poora process team aapko store visit ke waqt aaram se samjha degi. Aapko kuch nahi karna padega.",
    "obj_ask_pickup_logistics_generic_shreya": "Ji, purane furniture ka pickup hum khud arrange karte hain — poora process team aapko store visit ke waqt aaram se samjha degi. Aapko kuch nahi karna padega.",
    "obj_ask_pickup_logistics_generic_simran": "Ji, purane furniture ka pickup hum khud arrange karte hain — poora process team aapko store visit ke waqt aaram se samjha degi. Aapko kuch nahi karna padega.",
    "obj_ask_call_recorded_generic_ritu": "Ji haan — quality aur training ke liye calls record ho sakti hain. Aapki baat bilkul safe rehti hai.",
    "obj_ask_call_recorded_generic_shreya": "Ji haan — quality aur training ke liye calls record ho sakti hain. Aapki baat bilkul safe rehti hai.",
    "obj_ask_call_recorded_generic_simran": "Ji haan — quality aur training ke liye calls record ho sakti hain. Aapki baat bilkul safe rehti hai.",
    "obj_reschedule_appointment_generic_ritu": "Bilkul koi baat nahi ji — nayi date se plan kar lete hain. Ab aap kis din aa sakte hain?",
    "obj_reschedule_appointment_generic_shreya": "Bilkul koi baat nahi ji — nayi date se plan kar lete hain. Ab aap kis din aa sakte hain?",
    "obj_reschedule_appointment_generic_simran": "Bilkul koi baat nahi ji — nayi date se plan kar lete hain. Ab aap kis din aa sakte hain?",
    "obj_cancel_appointment_generic_ritu": "Ji theek hai, main appointment cancel kar deti hoon — koi baat nahi. Aage kabhi zaroorat ho toh humein zaroor yaad rakhiyega. Aapka din shubh ho!",
    "obj_cancel_appointment_generic_shreya": "Ji theek hai, main appointment cancel kar deti hoon — koi baat nahi. Aage kabhi zaroorat ho toh humein zaroor yaad rakhiyega. Aapka din shubh ho!",
    "obj_cancel_appointment_generic_simran": "Ji theek hai, main appointment cancel kar deti hoon — koi baat nahi. Aage kabhi zaroorat ho toh humein zaroor yaad rakhiyega. Aapka din shubh ho!",
    "obj_legal_threat_generic_ritu": "Maafi chahti hoon ji agar aapko koi takleef hui — bilkul galti hamari. Main abhi aapka number turant hata deti hoon, aage koi call nahi aayegi. Bahut shukriya.",
    "obj_legal_threat_generic_shreya": "Maafi chahti hoon ji agar aapko koi takleef hui — bilkul galti hamari. Main abhi aapka number turant hata deti hoon, aage koi call nahi aayegi. Bahut shukriya.",
    "obj_legal_threat_generic_simran": "Maafi chahti hoon ji agar aapko koi takleef hui — bilkul galti hamari. Main abhi aapka number turant hata deti hoon, aage koi call nahi aayegi. Bahut shukriya.",
    "obj_want_human_generic_ritu": "Bilkul ji, samajhti hoon — aap kisi se seedha baat karna chahte hain. Main aapke liye hamari Customer Relations Head se ek call schedule karwa deti hoon — woh aapko poori detail se sab samjha dengi. Aap bata dijiye, kaunsa time theek rahega?",
    "obj_want_human_generic_shreya": "Bilkul ji, samajhti hoon — aap kisi se seedha baat karna chahte hain. Main aapke liye hamari Customer Relations Head se ek call schedule karwa deti hoon — woh aapko poori detail se sab samjha dengi. Aap bata dijiye, kaunsa time theek rahega?",
    "obj_want_human_generic_simran": "Bilkul ji, samajhti hoon — aap kisi se seedha baat karna chahte hain. Main aapke liye hamari Customer Relations Head se ek call schedule karwa deti hoon — woh aapko poori detail se sab samjha dengi. Aap bata dijiye, kaunsa time theek rahega?",
}

SHARED_INTENTS = {
    # Added 2026-08-13 (second pass, same audit as the "positive" fix) --
    # "पता"/"pata" is the single most natural Hindi word for "address" and
    # had ZERO coverage here, only the English loanword "एड्रेस"/"address".
    # Deliberately NOT added as a bare word -- "पता" alone collides with
    # "मुझे पता नहीं"/"पता है" ("I don't know"/"I know"), an extremely
    # common, totally unrelated phrase; same false-positive shape as the
    # "यह" rejection documented in the positive-list fix above. Scoped to
    # phrases that unambiguously ask FOR the address instead. Also added
    # bare "address"/"location" (English, previously only "address batao"
    # two-word form existed) and "nazdik"/"nearest"/"नज़दीक" (nearby
    # showroom), covered in knowledge.py's fresh-lead flow for months but
    # never ported here -- same pattern as the "yes" gap.
    # "where is your showroom"/"where is your store" (+ Devanagari phonetic)
    # added 2026-08-13 -- caught live, same session: a real test call asked
    # this exact thing in English twice and matched nothing both times,
    # falling through to the slower LLM fallback (which did answer
    # correctly, but a direct match should be instant). Bare "where"
    # deliberately NOT added -- far too generic, would match on almost any
    # question.
    #
    # EXPANDED 2026-08-19 (coverage-widening pass, user-requested) -- many
    # more real-world phrasings for the same underlying question: alternate
    # question words (kidhar/kis area/kis sector/kis shehar), map/pin-
    # location requests, branch/outlet/dukaan synonyms, and their Latin +
    # Devanagari forms. Deliberately still avoids bare "kaha"/"कहां" alone
    # (too generic, collides with "kaha tha" style unrelated past-tense
    # usage) and bare "pata" for the same reason documented above.
    "ask_location": ["kahan hai", "showroom kahan", "location kya", "address batao",
                     "kaha hai showroom", "kahan par hai", "kaunsi jagah",
                     "pata batao", "pata kya hai", "aapka pata", "store ka pata",
                     "address", "location", "nazdik", "nearest",
                     "where is your showroom", "where is your store", "where are you located",
                     "where is the showroom", "where is the store",
                     "where are your showrooms", "where are your stores", "your showrooms",
                     "कहां है", "कहाँ है", "शोरूम कहां", "लोकेशन क्या", "एड्रेस बताओ",
                     "कहां पर है", "कहाँ पर है", "स्टोर कहां", "स्टोर कहाँ", "कौनसी जगह",
                     "दुकान कहां", "shop kahan", "store kahan", "showroom kaha",
                     "पता बताओ", "पता क्या है", "आपका पता", "स्टोर का पता",
                     "वेयर इज योर शोरूम", "वेयर इज योर स्टोर",
                     "एड्रेस", "लोकेशन", "नज़दीक", "नज़दीकी",
                     "kidhar hai", "kidhar par hai", "kaha per", "kaunse area mein",
                     "kis area mein", "kis jagah", "konsi jagah pe", "dukan kidhar hai",
                     "showroom kidhar", "outlet kahan", "branch kahan",
                     "aapki shop kahan hai", "kahan se operate karte ho",
                     "location share karo", "location bhejo", "map bhejo",
                     "google maps bhejo", "pin location", "kis sector mein",
                     "kis city mein", "kaunse shehar mein", "gurgaon mein kahan",
                     "delhi mein kahan", "noida mein kahan",
                     "what's your address", "can you share the address", "where exactly is it",
                     "which area", "which sector", "send me the location", "share the location",
                     "google maps link", "pin location please", "share your location",
                     "किधर है", "किधर पर है", "कहां पर", "कौनसे एरिया में", "कौन से एरिया में",
                     "किस एरिया में", "कौनसी जगह पे", "आउटलेट कहां", "ब्रांच कहां",
                     "आपकी शॉप कहां है", "लोकेशन शेयर करो", "लोकेशन भेजो", "मैप भेजो",
                     "गूगल मैप्स भेजो", "पिन लोकेशन", "किस सेक्टर में", "किस शहर में",
                     "कौनसे शहर में", "गुड़गांव में कहां", "दिल्ली में कहां", "नोएडा में कहां",
                     "शोरूम का पता", "व्हेयर इज़ द एड्रेस", "शेयर द लोकेशन",
                     "गूगल मैप्स लिंक", "सेंड मी द लोकेशन"],
    # English-phonetic Devanagari forms added 2026-08-13 -- confirmed live,
    # multiple real customers this week asked for the agent's name in
    # English ("I'd like to know your name", "could you share your name
    # with me") and matched nothing -- Hindi STT renders spoken English
    # phonetically into Devanagari, not Latin text, so only Devanagari forms
    # actually match live transcripts (Latin "your name" kept too in case a
    # different STT path ever returns Latin script).
    #
    # EXPANDED 2026-08-19 -- more casual/direct ways of asking who's on the
    # line by name specifically (distinct from confusion_who's "who is
    # calling"/company-identity questions).
    "ask_name": ["tumhara naam", "aapka naam", "naam kya hai", "kaun bol rahe ho",
                "your name", "share your name", "give me your name", "know your name",
                "तुम्हारा नाम", "आपका नाम", "नाम क्या है", "कौन बोल रहे हो", "कौन बोल रही हो",
                "योर नेम", "शेयर योर नेम", "गिव मी योर नेम", "नो योर नेम",
                "tum kaun ho", "aap kaun bol rahe hain", "aap kaun bol rahi hain",
                "naam batao", "apna naam batao", "kaun si madam", "kis naam se",
                "madam ka naam", "may i know your name", "who am i speaking to",
                "who am i speaking with", "what should i call you", "can i get your name",
                "तुम कौन हो", "आप कौन बोल रहे हैं", "आप कौन बोल रही हैं",
                "नाम बताओ", "अपना नाम बताओ", "कौन सी मैडम", "किस नाम से",
                "मैडम का नाम", "मे आई नो योर नेम", "हू एम आई स्पीकिंग टू",
                "व्हाट शुड आई कॉल यू"],
    # "band hota"/"बंद होता" (closing time) added 2026-08-13 -- this only
    # covered "khulta"/opening time before; a customer asking when the store
    # CLOSES matched nothing. Plain English added same day (second pass,
    # customer explicitly asked to check English coverage across every
    # category) -- this list had ZERO English before, Hinglish/Devanagari
    # only.
    #
    # EXPANDED 2026-08-19 -- open-now / open-today variants, common in
    # actual calls right before a customer decides whether to head over.
    "ask_timings": ["time kya", "kab khulta", "timing kya hai", "kitne baje khulta",
                    "band hota", "band hoti", "kab tak khula",
                    "what time", "when do you open", "when do you close",
                    "opening hours", "closing time", "working hours", "office hours",
                    "टाइम क्या", "कब खुलता", "टाइमिंग क्या है", "कितने बजे खुलता",
                    "बंद होता", "बंद होती", "कब तक खुला",
                    "aaj khula hai kya", "sunday ko khula rehta hai kya",
                    "kitne baje tak khula", "store hours", "business hours",
                    "kya time hai aapka", "kab tak rehta hai open", "aaj open ho kya",
                    "is it open today", "is it open now", "are you open now",
                    "आज खुला है क्या", "संडे को खुला रहता है क्या",
                    "कितने बजे तक खुला", "स्टोर आवर्स", "बिज़नेस आवर्स",
                    "क्या टाइम है आपका", "कब तक रहता है ओपन", "आज ओपन हो क्या",
                    "अभी खुला है क्या", "अभी ओपन है क्या"],
    "ask_valuation": ["valuation kaise", "purana furniture kaise", "kaise pickup",
                      "value kaise milegi", "kaise calculate", "kaise lenge purana",
                      "how much will i get", "buyback value", "trade in value", "resale value",
                      "वैल्यूएशन कैसे", "पुराना फर्नीचर कैसे", "कैसे पिकअप", "वैल्यू कैसे मिलेगी",
                      "कैसे कैलकुलेट", "कैसे लेंगे पुराना",
                      "kaise assess karoge", "value kaun decide karega", "kaun value dega",
                      "kitna milega purane ka", "old furniture ki value",
                      "exchange value kitni milegi", "how is the value decided",
                      "who decides the value", "how much for my old furniture",
                      "पुराने का कितना मिलेगा", "ओल्ड फर्नीचर की वैल्यू",
                      "एक्सचेंज वैल्यू कितनी मिलेगी", "हाउ इज़ द वैल्यू डिसाइडेड"],
    "ask_delivery": ["delivery kab", "kab milega", "kitne din mein", "delivery kaise",
                     "when will it arrive", "delivery time", "how many days for delivery",
                     "how long for delivery",
                     "डिलीवरी कब", "कब मिलेगा", "कितने दिन में", "डिलीवरी कैसे",
                     "kab tak pahunchega", "ghar tak delivery hoti hai kya",
                     "delivery hoti hai ya khud lena padega", "delivery free hai kya",
                     "delivery mein kitna time lagta hai", "do you deliver",
                     "does it come with delivery",
                     "कब तक पहुंचेगा", "घर तक डिलीवरी होती है क्या",
                     "डिलीवरी होती है या खुद लेना पड़ेगा", "डिलीवरी फ्री है क्या",
                     "डिलीवरी में कितना टाइम लगता है", "डू यू डिलीवर"],
    "appointment_confirm": ["kal", "parso", "monday", "tuesday", "wednesday", "thursday",
                            "friday", "saturday", "sunday", "subah", "shaam", "raat",
                            "baje", "tareek", "date", "theek hai aa jaunga", "main aaunga",
                            "book kardo", "haan book karo", "confirm hai", "ji confirm",
                            "कल", "परसों", "सोमवार", "मंगलवार", "बुधवार", "गुरुवार",
                            "शुक्रवार", "शनिवार", "रविवार", "सुबह", "शाम", "रात", "बजे",
                            "तारीख", "ठीक है आ जाऊंगा", "मैं आऊंगा", "बुक कर दो",
                            "हां बुक करो", "कन्फर्म है", "जी कन्फर्म",
                            "सैटरडे", "सैंडे", "संडे", "मंडे", "ट्यूज़डे", "ट्यूजडे",
                            "वेडनेसडे", "थर्सडे", "फ्राइडे", "वीकेंड", "weekend",
                            "बैटर डे", "बैटरडे", "सैटर डे",
                            "सन डे", "मन डे", "ट्यूज डे", "वेड नेस डे", "थर्स डे", "फ्राई डे",
                            "जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून",
                            "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर",
                            "january", "february", "march", "april", "june", "july",
                            "august", "september", "october", "november", "december",
                            "agle hafte", "agle mahine", "अगले हफ्ते", "अगले महीने",
                            "is hafte", "इस हफ्ते",
                            # EXPANDED 2026-08-19 -- more relative-time phrasings
                            # customers actually use when committing to a visit.
                            "agla hafta", "is weekend", "next week", "this weekend",
                            "अगला हफ्ता", "इस वीकेंड", "नेक्स्ट वीक", "दिस वीकेंड",
                            "kal shaam", "kal subah", "parso shaam", "parso subah",
                            "कल शाम", "कल सुबह", "परसों शाम", "परसों सुबह",
                            "aaj shaam ko", "aaj hi aa jaunga", "आज शाम को", "आज ही आ जाऊंगा"],
}

REACT_ABC_INTENTS = {
    # "बताइए" (Devanagari transliteration of "bataiye") and "समझ गया/गई"/
    # "समझा ही है" (confirmatory understanding, not the negated "समझा नहीं"
    # already covered under "repeat") — confirmed live 2026-08-11
    # (hot_warm_leads_conversations.docx audit): both fell through to the
    # "sorry, didn't catch that" reprompt despite being unambiguous
    # affirmative replies, because only the Hinglish spelling ("bataiye")
    # or the negated form was covered, not these. Bare "समझा" deliberately
    # NOT added — it's a substring of "समझा नहीं" (repeat/negation), so
    # adding it risks false-matching a "didn't understand" reply as positive.
    # "yes"/"यस" (plain English affirmation, both Latin and its Devanagari
    # phonetic STT rendering) -- confirmed live 2026-08-13 (Pratham call
    # 919911117660). Bare "right" REMOVED 2026-08-13 (caught in this same
    # pass's own verification testing) -- collides with "right now"/"right
    # there"/"not right now" etc.
    #
    # EXPANDED 2026-08-19 (coverage-widening pass, user-requested) -- a much
    # wider set of everyday affirmations, invitations-to-continue, and
    # register variants (formal/casual/English). Still deliberately avoids
    # any bare word documented elsewhere in this file as a false-positive
    # risk (kya/yeh/ye/kaun/right/phone/call).
    "positive": ["haan", "han", "haa", "ha", "theek hai", "batao", "bolo", "sun raha hoon",
                 "okay", "ok", "sure", "bilkul", "achha", "bataiye", "sunenge", "ji",
                 "yes", "yeah", "yep", "yup", "correct", "sahi hai",
                 "जी", "हाँ", "हां", "ठीक है", "बताओ", "बोलो", "अच्छा", "बिल्कुल",
                 "बताइए", "समझ गया", "समझ गई", "समझा ही है", "samajh gaya", "samajh gayi",
                 "यस", "येस", "सही है",
                 "haanji", "haan ji", "han ji", "haanji bataiye", "theek hai bataiye",
                 "chaliye batao", "chalo batao", "bilkul bataiye", "zaroor",
                 "zaroor batao", "sunau", "suno", "sunaiye", "kahiye", "boliye",
                 "bolo bolo", "aage bolo", "aage boliye", "continue karo", "go ahead",
                 "sahi baat hai", "bilkul sahi", "of course", "definitely", "for sure",
                 "alright", "fine", "great", "sounds good", "no problem go ahead",
                 "haan bataiye ji", "achha theek hai", "achha ji bataiye", "acha", "acha ji",
                 "हांजी", "हां जी", "हांजी बताइए", "ठीक है बताइए", "चलिए बताओ",
                 "चलो बताओ", "बिल्कुल बताइए", "ज़रूर", "ज़रूर बताओ", "सुनाओ",
                 "सुनो", "सुनाइए", "कहिए", "बोलिए", "बोलो बोलो", "आगे बोलो",
                 "आगे बोलिए", "कंटिन्यू करो", "गो अहेड", "सही बात है", "बिल्कुल सही",
                 "ऑफ कोर्स", "डेफिनेटली", "फॉर श्योर", "ऑलराइट", "फाइन", "ग्रेट",
                 "साउंड्स गुड", "नो प्रॉब्लम गो अहेड", "हां बताइए जी", "अच्छा ठीक है",
                 "अच्छा जी बताइए", "अचा", "अचा जी"],
    # Narrowed 2026-08-13 -- bare "kaun"/"कौन" (who) collided with "कौन से"
    # (which). Replaced with phrasings that specifically mean "who is
    # this", not the bare word "who" that "which"/"who else" etc. also
    # contain. Also added English-phonetic Devanagari forms ("हू यू आर"
    # etc.).
    #
    # EXPANDED 2026-08-19 -- company/firm-identity phrasings, distinct from
    # ask_name's "what's your name" (this is "who/what company is calling").
    "confusion_who": ["kaun bol rahe", "kaun bol rahi", "kon ho", "pahchaan nahi",
                      "kaun sa number", "kaise mila", "number kahan se", "kahan se",
                      "aap kaun", "kaun hai yeh", "कौन बोल रहे", "कौन बोल रही",
                      "कहाँ से", "पहचान नहीं", "कौन सा नंबर", "आप कौन", "कौन है यह",
                      "यह कौन", "हू यू आर", "व्हाई यू आर कॉलिंग", "why you calling",
                      "who is this", "who is calling",
                      "aap kis company se", "kis company se bol rahe", "kahan se bol rahe ho",
                      "kis firm se", "kaunsi company", "identify yourself",
                      "which company are you calling from", "what company is this",
                      "आप किस कंपनी से", "किस कंपनी से बोल रहे", "कहां से बोल रहे हो",
                      "किस फर्म से", "कौनसी कंपनी", "आइडेंटिफाई योरसेल्फ",
                      "विच कंपनी आर यू कॉलिंग फ्रॉम", "व्हाट कंपनी इज़ दिस",
                      "kis number se call kiya", "किस नंबर से कॉल किया"],
    # Bare "kya"/"क्या" removed for false-positive reasons (see earlier
    # comment history). Narrowed to actual "say that again" phrases only.
    #
    # EXPANDED 2026-08-19 -- more natural ways of asking for a repeat,
    # including "network/awaaz" excuses customers commonly give.
    "repeat": ["kya bola", "phir se bolo", "samjha nahi", "dobara bolo", "suna nahi",
               "repeat karo", "say that again", "come again", "what did you say",
               "please repeat", "pardon",
               "फिर से बोलो", "क्या बोला", "समझा नहीं", "दोबारा बोलो",
               "सुना नहीं", "रिपीट करो",
               "ek baar phir", "ek baar aur bolo", "phir se batao", "phir se boliye",
               "wapas bolo", "clear nahi sunai diya", "aawaz nahi aa rahi thi",
               "network issue tha", "sound nahi aaya", "not clear", "can you repeat",
               "could you repeat that", "one more time", "say it again",
               "i didn't hear that", "i couldn't hear you",
               "एक बार फिर", "एक बार और बोलो", "फिर से बताओ", "फिर से बोलिए",
               "वापस बोलो", "क्लियर नहीं सुनाई दिया", "आवाज़ नहीं आ रही थी",
               "नेटवर्क इशू था", "साउंड नहीं आया", "नॉट क्लियर", "कैन यू रिपीट",
               "कुड यू रिपीट दैट", "वन मोर टाइम", "से इट अगेन", "आई डिडंट हियर दैट"],
    "privacy_concern": ["number kaise mila", "data kahan se", "mera number kyun hai", "spam", "privacy",
                        "how did you get my number", "who gave you my number",
                        "नंबर कैसे मिला", "डेटा कहां से", "मेरा नंबर क्यों है", "स्पैम", "प्राइवेसी",
                        "mera data kahan se leke aaye", "database kahan se mila",
                        "yeh number kisne diya", "consent liya kya", "permission li thi kya",
                        "where did you get this number", "who shared my details",
                        "is this legal",
                        "मेरा डेटा कहां से लेके आए", "डेटाबेस कहां से मिला",
                        "यह नंबर किसने दिया", "कंसेंट लिया क्या", "परमिशन ली थी क्या",
                        "व्हेयर डिड यू गेट दिस नंबर", "हू शेयर्ड माय डिटेल्स",
                        "इज़ दिस लीगल"],
    # "kitna discount milega" added 2026-08-19 -- confirmed live. Bare
    # "discount" deliberately included.
    #
    # EXPANDED 2026-08-19 -- broader "explain/how does this work" coverage.
    "offer_clarify": ["kya offer", "kaise hoga", "explain karo", "samjhao",
                      "exchange kaise", "purana furniture", "kya matlab",
                      "detail batao", "aur batao", "एक्सचेंज कैसे", "exchange kaisa",
                      "explain", "tell me more", "more details", "more information",
                      "what's the offer", "what is the offer",
                      "kitna discount", "discount kitna", "discount milega", "discount",
                      "क्या ऑफर", "कैसे होगा", "एक्सप्लेन करो", "समझाओ",
                      "पुराना फर्नीचर", "क्या मतलब", "डिटेल बताओ", "और बताओ", "एक्सचेंज कैसा",
                      "कितना डिस्काउंट", "डिस्काउंट कितना", "डिस्काउंट मिलेगा", "डिस्काउंट",
                      "offer samjhao", "offer clear nahi hai", "matlab kya hua iska",
                      "kaise kaam karta hai yeh", "process kya hai", "steps kya hain",
                      "kaise milega discount", "kaise milta hai exchange",
                      "how does this work", "explain the process", "what exactly do i get",
                      "what does this include",
                      "ऑफर समझाओ", "ऑफर क्लियर नहीं है", "मतलब क्या हुआ इसका",
                      "कैसे काम करता है यह", "प्रोसेस क्या है", "स्टेप्स क्या हैं",
                      "कैसे मिलेगा डिस्काउंट", "कैसे मिलता है एक्सचेंज",
                      "हाउ डज़ दिस वर्क", "एक्सप्लेन द प्रोसेस",
                      "व्हाट एक्जेक्टली डू आई गेट", "व्हाट डज़ दिस इंक्लूड"],
    "trust_issue": ["fake hai", "jhooth", "fraud", "scam", "sach mein",
                    "pakka", "sach hai kya", "vishwas nahi",
                    "bharosa nahi", "yakeen nahi", "trust nahi", "don't trust",
                    "is this real", "is this genuine", "sounds fake", "is this legit",
                    "फेक है", "झूठ", "फ्रॉड", "स्कैम", "सच में",
                    "पक्का", "सच है क्या", "विश्वास नहीं",
                    "भरोसा नहीं", "यकीन नहीं",
                    "aisa kaise ho sakta hai", "koi catch toh nahi", "hidden charges toh nahi",
                    "kahin cheat toh nahi kar rahe", "real company hai na",
                    "registered company hai kya", "gst number hai kya",
                    "is this a scam", "sounds too good to be true", "any hidden charges",
                    "any catch",
                    "आप कहीं फ्रॉड तो नहीं", "ऐसा कैसे हो सकता है", "कोई कैच तो नहीं",
                    "हिडन चार्जेज तो नहीं", "कहीं चीट तो नहीं कर रहे",
                    "रियल कंपनी है ना", "रजिस्टर्ड कंपनी है क्या", "जीएसटी नंबर है क्या",
                    "इज़ दिस अ स्कैम", "साउंड्स टू गुड टू बी ट्रू",
                    "एनी हिडन चार्जेज", "एनी कैच"],
    "buying_signal": ["kitna time hai", "kab tak hai", "interested hoon",
                      "showroom kab", "aana chahta", "visit karna", "kab aaye",
                      "i am interested", "when can i visit", "how much time do i have",
                      "कितना टाइम है", "कब तक है", "इंटरेस्टेड हूं",
                      "शोरूम कब", "आना चाहता", "विजिट करना", "कब आएं",
                      "mujhe chahiye", "hum le lenge", "le lenge", "final kar do",
                      "book kar do", "i want it", "we'll take it", "sounds interesting",
                      "i'm interested", "let's do it",
                      "मुझे चाहिए", "हम ले लेंगे", "ले लेंगे", "फाइनल कर दो",
                      "बुक कर दो", "आई वांट इट", "वी विल टेक इट", "साउंड्स इंटरेस्टिंग",
                      "आई एम इंटरेस्टेड", "लेट्स डू इट"],
    # Narrowed 2026-08-13 -- shares no bare affirmation words with "positive".
    #
    # EXPANDED 2026-08-19 -- more explicit send-confirmation phrasings that
    # unambiguously reference the WhatsApp send action (never bare "haan"-
    # style words, per the narrowing rationale above).
    "wa_ok": ["bhejo", "send karo", "bhej do", "kar do", "theek hai bhej do",
              "ok send", "haan bhejo", "de do", "kar lo",
              "please send", "yes send it", "send it",
              "send kijiye", "सेंड कीजिए", "bhej dijiye", "भेज दीजिए",
              "whatsapp par bhej sakte hain", "व्हाट्सएप पर भेज सकते हैं",
              "whatsapp par bhej sakte ho", "व्हाट्सएप पर भेज सकते हो",
              "haan bhej do", "abhi bhejo", "turant bhejo", "please bhej do",
              "bhejiye", "bheji dijiye", "de dijiye", "share kar do", "share kariye",
              "yes please send", "go ahead send it", "send now", "please share",
              "share it",
              "हां भेज दो", "अभी भेजो", "तुरंत भेजो", "प्लीज भेज दो", "भेजिए",
              "भेजी दीजिए", "दे दीजिए", "शेयर कर दो", "शेयर करिए",
              "यस प्लीज सेंड", "गो अहेड सेंड इट", "सेंड नाउ", "प्लीज शेयर", "शेयर इट"],
    "wa_no_whatsapp": ["whatsapp nahi hai", "use nahi karta", "no whatsapp",
                       "व्हाट्सएप नहीं है", "यूज़ नहीं करता", "नो व्हाट्सएप",
                       "whatsapp install nahi hai", "whatsapp use nahi karte",
                       "whatsapp nahi chalata", "mere paas whatsapp nahi",
                       "i don't have whatsapp", "i don't use whatsapp",
                       "no whatsapp on this number",
                       "व्हाट्सएप इंस्टॉल नहीं है", "व्हाट्सएप यूज़ नहीं करते",
                       "व्हाट्सएप नहीं चलाता", "मेरे पास व्हाट्सएप नहीं",
                       "आई डोंट हैव व्हाट्सएप", "आई डोंट यूज़ व्हाट्सएप",
                       "नो व्हाट्सएप ऑन दिस नंबर"],
    "wa_diff_number": ["alag number", "doosra number", "different number",
                       "अलग नंबर", "दूसरा नंबर", "डिफरेंट नंबर",
                       "iss number par mat bhejo", "doosre number par bhejo",
                       "yeh mera whatsapp number nahi hai", "kisi aur number par bhejo",
                       "send it on a different number", "not this number",
                       "इस नंबर पर मत भेजो", "दूसरे नंबर पर भेजो",
                       "यह मेरा व्हाट्सएप नंबर नहीं है", "किसी और नंबर पर भेजो",
                       "सेंड इट ऑन अ डिफरेंट नंबर", "नॉट दिस नंबर"],
    # "call nahi"/"कॉल नहीं" REMOVED 2026-08-19 (see route_objection()
    # comment / webhook_reactivation.py for the dead-code finding).
    #
    # EXPANDED 2026-08-19 -- more explicit "I'd rather WhatsApp" phrasings.
    "wa_prefers": ["whatsapp pe hi", "message karo",
                  "message me instead", "text me instead", "whatsapp only", "just whatsapp",
                  "व्हाट्सएप पे ही", "मैसेज करो",
                  "whatsapp better hai", "call na karo whatsapp karo",
                  "text karna better hai", "whatsapp par hi rakho", "prefer whatsapp",
                  "i'd rather you whatsapp me", "just text me", "message pe rakho",
                  "व्हाट्सएप बेटर है", "कॉल ना करो व्हाट्सएप करो", "टेक्स्ट करना बेटर है",
                  "व्हाट्सएप पर ही रखो", "प्रेफर व्हाट्सएप", "आई'ड रादर यू व्हाट्सएप मी",
                  "जस्ट टेक्स्ट मी", "मैसेज पे रखो"],
    "busy": ["busy hoon", "busy hu", "busy hun", "abhi nahi", "kaam mein hoon", "baad mein", "driving",
             "meeting mein", "abhi nahi kar sakta",
             "i am busy", "i'm busy", "not now", "can't talk", "cant talk",
             "in a meeting", "call me later", "call later",
             "बिज़ी हूं", "अभी नहीं", "काम में हूं", "बाद में", "ड्राइविंग",
             "मीटिंग में", "अभी नहीं कर सकता",
             "office mein hoon", "kaam par hoon", "gaadi chala raha hoon",
             "drive kar raha hoon", "abhi rasta mein hoon", "guests aaye hue hain",
             "ghar mein mehmaan hain", "abhi free nahi hoon", "thoda busy hoon",
             "i'm at work", "i'm in office", "i'm driving right now",
             "can't talk right now", "i'll call you back", "not a good time",
             "ऑफिस में हूं", "काम पर हूं", "गाड़ी चला रहा हूं", "ड्राइव कर रहा हूं",
             "अभी रास्ते में हूं", "गेस्ट्स आए हुए हैं", "घर में मेहमान हैं",
             "अभी फ्री नहीं हूं", "थोड़ा बिज़ी हूं", "आई एम एट वर्क", "आई एम इन ऑफिस",
             "आई एम ड्राइविंग राइट नाउ", "कांट टॉक राइट नाउ", "आई विल कॉल यू बैक",
             "नॉट अ गुड टाइम"],
    "not_interested": ["interested nahi", "nahi chahiye", "rehne do",
                       "hata do mera number", "band karo", "mat bhejo",
                       "nahi sunna", "nahi sunni", "mat batao",
                       "इंटरेस्टेड नहीं", "नहीं चाहिए", "रहने दो",
                       "हटा दो मेरा नंबर", "बंद करो", "मत भेजो",
                       "नहीं सुनना", "नहीं सुननी", "मत बताओ",
                       "no thanks", "no thank you", "not interested", "not in the mood",
                       "नो थैंक्स", "नो थेंक्स", "नो थैंक", "नो थैंक यू", "नो थैंकयू",
                       "नॉट इंटरेस्टेड", "नाट इंटरेस्टेड",
                       "नॉट इन मूड", "नॉट इन द मूड", "नाट इन मूड",
                       "interestiv nahi", "इंटरेस्टिव नहीं",
                       "zaroorat nahi", "ज़रूरत नहीं", "जरूरत नहीं",
                       "aavashyakta nahi", "आवश्यकता नहीं", "nahi jaanna", "नहीं जानना",
                       "koi zaroorat nahi hai", "abhi koi zaroorat nahi",
                       "kaam nahi hai humein", "hume kuch nahi chahiye",
                       "dobara call mat karna offer ke liye", "yeh offer humare liye nahi hai",
                       "we don't need it", "we're not looking", "no need",
                       "not looking to buy", "not planning to buy", "no requirement",
                       "कोई ज़रूरत नहीं है", "अभी कोई ज़रूरत नहीं", "काम नहीं है हमें",
                       "हमें कुछ नहीं चाहिए", "यह ऑफर हमारे लिए नहीं है",
                       "वी डोंट नीड इट", "वी आर नॉट लुकिंग", "नो नीड",
                       "नॉट लुकिंग टू बाय", "नॉट प्लानिंग टू बाय", "नो रिक्वायरमेंट"],
    "expensive": ["mahenga hai", "mahenge hain", "mahenga", "mahenge", "bahut zyada",
                 "budget nahi", "afford nahi", "costly", "rate zyada", "expensive",
                 "can't afford it", "cant afford it", "out of budget", "too costly",
                 "महंगा है", "महंगे हैं", "महंगा", "महंगे", "बहुत ज़्यादा", "बहुत रेट",
                 "रेट ज़्यादा", "बजट नहीं", "अफोर्ड नहीं", "कॉस्टली", "एक्सपेंसिव",
                 "itna mehenga kyun", "kam nahi ho sakta", "discount aur badhao",
                 "price kam karo", "yeh toh bahut zyada hai", "hamare budget se bahar hai",
                 "afford nahi kar sakte", "too expensive for us", "way too costly",
                 "beyond our budget",
                 "इतना महंगा क्यों", "कम नहीं हो सकता", "डिस्काउंट और बढ़ाओ",
                 "प्राइस कम करो", "यह तो बहुत ज़्यादा है", "हमारे बजट से बाहर है",
                 "अफोर्ड नहीं कर सकते", "टू एक्सपेंसिव फॉर अस", "वे टू कॉस्टली",
                 "बियॉन्ड अवर बजट"],
    "online_cheaper": ["online sasta", "amazon pe", "flipkart pe", "online better",
                       "cheaper online", "better deals online", "found it cheaper",
                       "ऑनलाइन सस्ता", "अमेज़न पे", "फ्लिपकार्ट पे", "ऑनलाइन बेटर",
                       "meesho pe sasta hai", "ajio pe sasta hai",
                       "internet pe sasta milta hai", "google pe dekha sasta hai",
                       "we found it cheaper somewhere else", "checked online it's cheaper",
                       "मीशो पे सस्ता है", "अजियो पे सस्ता है", "इंटरनेट पे सस्ता मिलता है",
                       "गूगल पे देखा सस्ता है", "वी फाउंड इट चीपर समव्हेयर एल्स",
                       "चेक्ड ऑनलाइन इट्स चीपर"],
    "sochna_hai": ["sochna hai", "soch ke batata hoon", "wife se puchna",
                   "family se puchna", "decide nahi kiya",
                   "let me think", "need to think", "will think about it", "thinking about it",
                   "सोचना है", "सोच के बताता हूं", "वाइफ से पूछना",
                   "फैमिली से पूछना", "डिसाइड नहीं किया",
                   "ek do din soch ke batata hoon", "ghar walon se baat karke batata hoon",
                   "husband se puchna hai", "consult karna hai",
                   "discuss karna hai family se", "need to discuss with family",
                   "have to consult my husband", "give me some time to think",
                   "एक दो दिन सोच के बताता हूं", "घर वालों से बात करके बताता हूं",
                   "हस्बैंड से पूछना है", "कंसल्ट करना है", "डिस्कस करना है फैमिली से",
                   "नीड टू डिस्कस विद फैमिली", "हैव टू कंसल्ट माय हस्बैंड",
                   "गिव मी सम टाइम टू थिंक"],
    "escalate": ["manager se baat", "senior se milao", "complaint karna",
                "manager", "supervisor", "speak to someone else", "complaint",
                "मैनेजर से बात", "सीनियर से मिलाओ", "कंप्लेंट करना", "मैनेजर",
                "kisi bade se baat karao", "aapke boss se baat karo",
                "authority se baat karni hai", "higher authority se baat karao",
                "let me speak to your boss", "connect me to your supervisor",
                "i want to speak to someone senior",
                "किसी बड़े से बात कराओ", "आपके बॉस से बात कराओ",
                "अथॉरिटी से बात करनी है", "हायर अथॉरिटी से बात कराओ",
                "लेट मी स्पीक टू योर बॉस", "कनेक्ट मी टू योर सुपरवाइज़र",
                "आई वांट टू स्पीक टू समवन सीनियर"],
    "dnc": ["dobara call mat karna", "number delete karo", "DNC", "harassment",
            "complaint karunga", "call mat karo kabhi", "band karo yeh call",
            "दोबारा कॉल मत करना", "नंबर डिलीट करो", "हैरेसमेंट",
            "कंप्लेंट करूंगा", "कॉल मत करो कभी", "बंद करो यह कॉल",
            "dobara call na karo", "dobara call na karein", "phir se call na karo",
            "aage se call na karo", "call na karo", "call mat karna",
            "phone mat karna", "bilkul interested nahi", "list se hata do",
            "list se nikal do",
            "दोबारा कॉल ना करो", "दोबारा कॉल ना करें", "फिर से कॉल ना करो",
            "आगे से कॉल ना करो", "कॉल ना करो", "कॉल मत करना",
            "फोन मत करना", "बिल्कुल इंटरेस्टेड नहीं", "इंटरेस्टेड नहीं हूं बिल्कुल",
            "लिस्ट से हटा दो", "लिस्ट से निकाल दो",
            "list se hata dena", "list se nikal dena", "लिस्ट से हटा देना", "लिस्ट से निकाल देना",
            "call karna band karo", "phone karna band karo",
            "कॉल करना बंद करो", "फोन करना बंद करो",
            "stop calling", "stop calling me", "please stop calling",
            "stop calling me please", "stop phoning me",
            "remove my number", "delete my number",
            "mera number hata do", "number hata do", "mera number nikal do",
            "dobara mat karna", "phir se mat karna", "aage se mat karna",
            "मेरा नंबर हटा दो", "नंबर हटा दो", "मेरा नंबर निकाल दो",
            "दोबारा मत करना", "फिर से मत करना", "आगे से मत करना",
            # EXPANDED 2026-08-19 -- more explicit list-removal / block requests.
            "mera number remove karo", "block kar do mera number",
            "yeh number band karo apni list se", "please remove my number",
            "take me off your list", "unsubscribe me",
            "मेरा नंबर रिमूव करो", "ब्लॉक कर दो मेरा नंबर",
            "यह नंबर बंद करो अपनी लिस्ट से", "प्लीज रिमूव माय नंबर",
            "टेक मी ऑफ योर लिस्ट", "अनसब्सक्राइब मी"],
    "personal_question": ["kaun ho tum", "real hai ya bot",
                          "robot ho", "bot ho", "AI ho", "human ho",
                          "bot ya insaan", "AI ya insaan", "bot ya human",
                          "are you a bot", "are you real", "are you human", "is this a bot",
                          "कौन हो तुम", "रियल है या बॉट",
                          "रोबोट हो", "बॉट हो", "एआई हो", "ह्यूमन हो",
                          "बॉट या इंसान", "एआई या इंसान", "तुम बहुत हो या इंसान",
                          "tum sach mein insaan ho", "voice kaisi generate hoti hai",
                          "yeh awaaz real hai kya", "are you a real person",
                          "is this a recorded voice", "is this automated",
                          "तुम सच में इंसान हो", "वॉइस कैसी जनरेट होती है",
                          "यह आवाज़ रियल है क्या", "आर यू अ रियल पर्सन",
                          "इज़ दिस अ रिकॉर्डेड वॉइस", "इज़ दिस ऑटोमेटेड"],
    "ask_price_range": ["starting range", "starting price", "price kya hai",
                        "rate kya hai", "kitne se shuru", "shuru kitne se",
                        "kitna paisa", "daam kya hai", "kitne ka hai", "kitne ki hai",
                        "kitni ka hai", "price",
                        "how much is it", "how much does it cost", "what's the price",
                        "what is the price",
                        "स्टार्टिंग रेंज", "प्राइस क्या है",
                        "रेट क्या है", "कितने से शुरू", "शुरू कितने से", "कितना पैसा",
                        "दाम क्या है", "कितने का है", "कितने की है", "कितनी का है", "प्राइस",
                        "sabse sasta kya hai", "sabse mehenga kya hai", "average price kya hai",
                        "range batao", "price list bhejo", "rate list bhejo",
                        "what's the cheapest option", "what's the most expensive option",
                        "send me the price list",
                        "सबसे सस्ता क्या है", "सबसे महंगा क्या है", "एवरेज प्राइस क्या है",
                        "रेंज बताओ", "प्राइस लिस्ट भेजो", "रेट लिस्ट भेजो",
                        "व्हाट्स द चीपेस्ट ऑप्शन", "व्हाट्स द मोस्ट एक्सपेंसिव ऑप्शन",
                        "सेंड मी द प्राइस लिस्ट"],
    "ask_offer_scope": ["kis kis cheez pe", "sab furniture pe", "sari furniture pe",
                        "kaunse product", "sabhi furniture", "kaun se furniture",
                        "which products", "what all is included", "what items",
                        "which items", "what all do you have",
                        "किस-किस चीज पे", "सब फर्नीचर पे", "सारी फर्नीचर पे",
                        "कौनसे प्रोडक्ट", "सभी फर्नीचर पर", "सारी फर्नीचर पर",
                        "कौन से फर्नीचर", "कौन सा फर्नीचर",
                        "sirf sofa pe hai ya sab pe", "kya sab items cover hote hain",
                        "kaunse items exclude hain", "is it on everything",
                        "does it apply to all products", "what's excluded",
                        "सिर्फ सोफा पे है या सब पे", "क्या सब आइटम्स कवर होते हैं",
                        "कौनसे आइटम्स एक्सक्लूड हैं", "इज़ इट ऑन एवरीथिंग",
                        "डज़ इट अप्लाई टू ऑल प्रोडक्ट्स", "व्हाट्स एक्सक्लूडेड"],
    "already_purchased": ["abhi liya hai", "already le liya", "naya furniture liya hai",
                          "abhi kharida", "already kharid liya", "abhi le chuke",
                          "i already bought", "i already have one", "already purchased",
                          "already own one", "already bought it",
                          "अभी लिया है", "पहले ही ले लिया", "नया फर्नीचर लिया है",
                          "अभी खरीदा", "पहले से ले चुके", "अभी ले चुके",
                          "hum already le chuke hain", "hamare paas already naya hai",
                          "abhi hi kharida hai", "we just bought new furniture",
                          "already got everything we need",
                          "हम पहले ही ले चुके हैं", "हमारे पास पहले से नया है",
                          "अभी ही खरीदा है", "वी जस्ट बॉट न्यू फर्नीचर",
                          "ऑलरेडी गॉट एवरीथिंग वी नीड"],

    # ─────────────────────────────────────────────────────────────────────
    # 22 new situational categories added 2026-08-15, from
    # NEW_CATEGORIES_PROPOSAL.md's vetted keyword lists + Agent_Replies_
    # Warm.md's approved script text. Routing wired in route_objection()
    # (webhook_reactivation.py). `bare_negative` deliberately excluded from
    # this dict -- see _is_bare_negative() in webhook_reactivation.py.
    # EXPANDED 2026-08-19: every category below has significantly more
    # phrasings added (coverage-widening pass, user-requested).
    # ─────────────────────────────────────────────────────────────────────
    "wrong_number": ["galat number hai", "aapko wrong number mila hai",
                     "is number pe koi aur rehta hai", "wrong number", "galat number",
                     "yeh mera number nahi hai",
                     "यह नंबर गलत है", "गलत नंबर", "आपको गलत नंबर मिला है",
                     "यह मेरा नंबर नहीं है", "रॉन्ग नंबर",
                     "aap galat number pe call kar rahe ho", "yeh number kisi aur ka hai",
                     "main woh insaan nahi hoon", "you have the wrong number",
                     "this isn't the right person",
                     "आप गलत नंबर पे कॉल कर रहे हो", "यह नंबर किसी और का है",
                     "मैं वो इंसान नहीं हूं", "यू हैव द रॉन्ग नंबर",
                     "दिस इज़्न्ट द राइट पर्सन"],
    "not_my_customer": ["main aapka customer nahi hoon", "maine kabhi kuch nahi khareeda",
                        "maine kabhi order nahi kiya", "mera koi record nahi hona chahiye",
                        "main pehli baar sun raha hoon", "kaunsa purana customer",
                        "मैं आपका ग्राहक नहीं हूं", "मैंने कभी कुछ नहीं खरीदा",
                        "मैंने कभी ऑर्डर नहीं किया", "कौनसा पुराना कस्टमर",
                        "मैं पहली बार सुन रहा हूं",
                        "maine kabhi Krishna Furniture se kuch nahi liya",
                        "main naya hoon aapke liye", "pehli baar sun raha hoon aapka naam",
                        "i've never bought from you before", "i'm not your customer",
                        "this is the first time i'm hearing this",
                        "मैंने कभी कृष्णा फर्नीचर से कुछ नहीं लिया", "मैं नया हूं आपके लिए",
                        "आई हैव नेवर बॉट फ्रॉम यू बिफोर", "आई एम नॉट योर कस्टमर",
                        "दिस इज़ द फर्स्ट टाइम आई एम हियरिंग दिस"],
    "person_unavailable": ["woh ghar par nahi hain", "unka number band hai",
                           "wo abhi available nahi hain", "main unki taraf se bol raha hoon",
                           "unhe baad mein call karo", "unka phone band hai",
                           "वो घर पर नहीं हैं", "वो अभी उपलब्ध नहीं हैं",
                           "मैं उनकी तरफ से बोल रहा हूं", "उन्हें बाद में कॉल करो",
                           "उनका फोन बंद है",
                           "woh abhi bahar gaye hain", "unse baad mein baat karna",
                           "wo office mein hain abhi", "woh call nahi le paayenge abhi",
                           "he's not available right now", "she's out at the moment",
                           "he's not home", "call him later",
                           "वो अभी बाहर गए हैं", "उनसे बाद में बात करना",
                           "वो ऑफिस में हैं अभी", "वो कॉल नहीं ले पाएंगे अभी",
                           "ही'ज़ नॉट अवेलेबल राइट नाउ", "शीज़ आउट एट द मोमेंट",
                           "ही'ज़ नॉट होम", "कॉल हिम लेटर"],
    "already_called": ["aap pehle bhi call kar chuke ho", "maine pehle bata diya tha",
                       "kitni baar call karoge", "dobara kyun call kiya", "roz call karte ho",
                       "बार-बार कॉल क्यों करते हो", "आप पहले भी कॉल कर चुके हो",
                       "मैंने पहले बता दिया था", "कितनी बार कॉल करोगे", "रोज़ कॉल करते हो",
                       "aap log baar baar call karte ho", "yeh teesri baar hai",
                       "roz roz call aati hai", "har din call karte ho",
                       "you keep calling again and again", "this is the third time",
                       "why do you call every day",
                       "आप लोग बार-बार कॉल करते हो", "यह तीसरी बार है",
                       "रोज़ रोज़ कॉल आती है", "हर दिन कॉल करते हो",
                       "यू कीप कॉलिंग अगेन एंड अगेन", "दिस इज़ द थर्ड टाइम",
                       "व्हाई डू यू कॉल एवरी डे"],
    # "thodi der mein call karna" ("mein" = in, vs "baad" = after) added
    # 2026-08-19 -- confirmed live (test call to 8799712556): the customer's
    # actual wording, "aap mujhe thodi der mein call karna, abhi busy hoon,"
    # only matched "busy" (from "abhi busy hoon"), not callback_later --
    # "thodi der baad call karo" was already covered, but "mein" is a
    # genuinely different preposition ("in a while" vs "after a while"),
    # not a spelling variant, so it needed its own entry.
    "callback_later": ["shaam ko call karna", "kal subah call karo", "thodi der baad call karo",
                       "thodi der mein call karo", "thodi der mein call karna",
                       "थोड़ी देर में कॉल करो", "थोड़ी देर में कॉल करना",
                       "evening mein try karna", "2 ghante baad call karo", "weekend pe call karna",
                       "baad mein call karo", "baad mein call karna", "baad mein call kar sakte hain",
                       "can you call me back", "could you call me back", "call me back",
                       "will you call me back", "please call me back", "call me back later",
                       "call back later", "can you call back", "please call back later",
                       "बाद में कॉल कर सकते हैं",
                       "शाम को कॉल करना", "कल सुबह कॉल करो", "थोड़ी देर बाद कॉल करो",
                       "2 घंटे बाद कॉल करो", "बाद में कॉल करो", "बाद में कॉल करना",
                       "raat ko call karna", "kal call karna", "kal subah try karo",
                       "weekend pe call karo", "monday ko call karna",
                       "office se aane ke baad call karo", "lunch ke baad call karo",
                       "try calling this evening", "try tomorrow morning",
                       "call me next week", "call me tomorrow",
                       "रात को कॉल करना", "कल कॉल करना", "कल सुबह ट्राई करो",
                       "वीकेंड पे कॉल करो", "सोमवार को कॉल करना",
                       "ऑफिस से आने के बाद कॉल करो", "लंच के बाद कॉल करो",
                       "ट्राई कॉलिंग दिस ईवनिंग", "ट्राई टुमॉरो मॉर्निंग",
                       "कॉल मी नेक्स्ट वीक", "कॉल मी टुमॉरो"],
    "lang_pref_english": ["english mein baat karo", "angrezi mein bolo",
                          "please speak in english", "can you speak english",
                          "speak in english", "speak to me in english",
                          "english mein bolo", "english please",
                          "mujhe hindi samajh nahi aati", "hindi thik se nahi aati",
                          "hindi samajh nahi aati",
                          "अंग्रेज़ी में बोलो", "इंग्लिश में बात करो", "इंग्लिश में बोलो",
                          "मुझे हिंदी समझ नहीं आती", "हिंदी ठीक से नहीं आती",
                          "can we talk in english", "switch to english please",
                          "i'm more comfortable in english",
                          "कैन वी टॉक इन इंग्लिश", "स्विच टू इंग्लिश प्लीज",
                          "आई एम मोर कम्फर्टेबल इन इंग्लिश", "इंग्लिश में बात करें",
                          "अंग्रेजी में बताओ"],
    "lang_pref_hindi": ["hindi mein baat karo", "hindi mein bolo", "hindi please",
                        "speak in hindi", "please speak in hindi",
                        "हिंदी में बात करो", "हिंदी में बोलो",
                        "hindi mein baat kariye", "hindi mein hi theek hai",
                        "please speak hindi",
                        "हिंदी में बात करिए", "हिंदी में ही ठीक है", "प्लीज़ स्पीक हिंदी"],
    "lang_pref_other": ["punjabi mein baat karo", "पंजाबी में बात करो"],
    "uncertain": ["pata nahi", "shayad", "dekhta hoon", "abhi nahi bol sakta",
                 "confirm nahi hai", "not sure",
                 "पता नहीं", "शायद", "देखता हूं", "अभी नहीं बोल सकता", "कन्फर्म नहीं है",
                 "abhi confirm nahi kar sakta", "clear nahi hai mujhe", "dekhte hain",
                 "maybe", "not really sure", "can't say right now",
                 "अभी कन्फर्म नहीं कर सकता", "क्लियर नहीं है मुझे", "देखते हैं",
                 "मेबी", "नॉट रियली श्योर", "कांट से राइट नाउ"],
    "ask_emi": ["EMI hai kya", "EMI available", "EMI available hai", "EMI available hai kya",
               "installment mein le sakte hain", "no cost emi",
               "loan mil sakta hai kya", "financing available hai",
               "इएमआई है क्या", "ईएमआई है क्या", "ईएमआई अवेलेबल है क्या", "ईएमआई अवेलेबल",
               "EMI अवेलेबल है क्या", "EMI अवेलेबल",
               "किश्तों में ले सकते हैं", "लोन मिल सकता है क्या",
               "monthly installment mein le sakte hain kya", "emi kitne months ki hai",
               "0% emi hai kya", "zero percent emi", "monthly kist",
               "installment plan hai kya",
               "मंथली इंस्टॉलमेंट में ले सकते हैं क्या", "ईएमआई कितने महीनों की है",
               "ज़ीरो परसेंट ईएमआई", "मंथली किस्त", "इंस्टॉलमेंट प्लान है क्या"],
    "ask_payment_method": ["cash accept karte ho", "card se le sakte hain", "upi chalega",
                           "online payment hota hai kya", "कैश एक्सेप्ट करते हो",
                           "कैश लेते हो क्या", "कार्ड से ले सकते हैं", "यूपीआई चलेगा क्या",
                           "credit card chalta hai kya", "debit card chalta hai kya",
                           "gpay chalta hai kya", "phonepe chalta hai kya",
                           "paytm chalta hai kya", "does credit card work",
                           "do you accept gpay",
                           "क्रेडिट कार्ड चलता है क्या", "डेबिट कार्ड चलता है क्या",
                           "जीपे चलता है क्या", "फोनपे चलता है क्या", "पेटीएम चलता है क्या",
                           "डज़ क्रेडिट कार्ड वर्क", "डू यू एक्सेप्ट जीपे"],
    "ask_warranty": ["warranty kitne saal ki hai", "guarantee hai kya",
                     "kharab hone par kya hoga", "replacement milega kya",
                     "warranty", "guarantee",
                     "वारंटी कितने साल की है", "गारंटी है क्या", "खराब होने पर क्या होगा",
                     "वारंटी", "गारंटी",
                     "kitne saal ki warranty milti hai", "warranty card milta hai kya",
                     "warranty ka proof milta hai kya", "how long is the warranty",
                     "is there a warranty card",
                     "कितने साल की वारंटी मिलती है", "वारंटी कार्ड मिलता है क्या",
                     "वारंटी का प्रूफ मिलता है क्या", "हाउ लॉन्ग इज़ द वारंटी",
                     "इज़ देयर अ वारंटी कार्ड"],
    "ask_delivery_charge": ["delivery charge kitna hai", "free delivery hai kya",
                            "installation charge alag hai kya", "ghar tak laoge kya",
                            "delivery charge",
                            "डिलीवरी चार्ज कितना है", "फ्री डिलीवरी है क्या",
                            "इंस्टॉलेशन चार्ज अलग है क्या", "डिलीवरी चार्ज",
                            "delivery free hai ya paid", "kitna extra lagega delivery ka",
                            "installation free hai kya", "is delivery included or extra",
                            "is installation free",
                            "डिलीवरी फ्री है या पेड", "कितना एक्स्ट्रा लगेगा डिलीवरी का",
                            "इंस्टॉलेशन फ्री है क्या", "इज़ डिलीवरी इंक्लूडेड ऑर एक्स्ट्रा",
                            "इज़ इंस्टॉलेशन फ्री"],
    "ask_return_policy": ["return kar sakte hain kya", "agar pasand nahi aaya toh",
                          "exchange ho sakta hai naye wale ka bhi", "return policy",
                          "रिटर्न कर सकते हैं क्या", "अगर पसंद नहीं आया तो", "रिटर्न पॉलिसी",
                          "kitne din mein return kar sakte hain",
                          "return karne ka process kya hai", "money back milega kya",
                          "refund milega kya", "what's the return window",
                          "can i get a refund",
                          "कितने दिन में रिटर्न कर सकते हैं", "रिटर्न करने का प्रोसेस क्या है",
                          "मनी बैक मिलेगा क्या", "रिफंड मिलेगा क्या",
                          "व्हाट्स द रिटर्न विंडो", "कैन आई गेट अ रिफंड"],
    "ask_bargain": ["aur discount milega kya", "thoda kam karo", "final price kya hai",
                    "aur kam karo",
                    "और डिस्काउंट मिलेगा क्या", "थोड़ा कम करो", "फाइनल प्राइस क्या है",
                    "aur kam mein ho jayega kya", "thoda aur discount do",
                    "kuch aur kam karo", "best price kya hai", "final price batao",
                    "can you reduce the price further", "give me the best price",
                    "और कम में हो जाएगा क्या", "थोड़ा और डिस्काउंट दो", "कुछ और कम करो",
                    "बेस्ट प्राइस क्या है", "फाइनल प्राइस बताओ",
                    "कैन यू रिड्यूस द प्राइस फर्दर", "गिव मी द बेस्ट प्राइस"],
    "ask_invoice_gst": ["bill milega kya", "gst invoice milega", "pakka bill doge",
                        "GST", "invoice",
                        "बिल मिलेगा क्या", "जीएसटी इनवॉइस मिलेगा क्या", "पक्का बिल दोगे",
                        "जीएसटी", "इनवॉइस",
                        "bill milta hai kya", "kaccha bill ya pakka bill",
                        "proper invoice milega kya", "do you give a proper bill",
                        "do you provide gst invoice",
                        "बिल मिलता है क्या", "कच्चा बिल या पक्का बिल",
                        "प्रॉपर इनवॉइस मिलेगा क्या", "डू यू गिव अ प्रॉपर बिल",
                        "डू यू प्रोवाइड जीएसटी इनवॉइस"],
    "ask_product_quality": ["material kya hai", "wood hai ya plastic", "quality kaisi hai",
                            "brand kaunsi hai", "quality", "material",
                            "मटेरियल क्या है", "क्वालिटी कैसी है", "ब्रांड कौनसी है",
                            "क्वालिटी", "मटेरियल",
                            "kaunsi wood use hoti hai", "solid wood hai ya engineered",
                            "kitne saal chalega", "durability kaisi hai",
                            "is it solid wood", "how long will it last",
                            "कौनसी वुड यूज़ होती है", "सॉलिड वुड है या इंजीनियर्ड",
                            "कितने साल चलेगा", "ड्यूरेबिलिटी कैसी है",
                            "इज़ इट सॉलिड वुड", "हाउ लॉन्ग विल इट लास्ट"],
    "ask_pickup_logistics": ["purana furniture kaun le jaega", "hum khud laayen kya",
                             "pickup free hai kya", "gaadi bhejoge kya",
                             "purana furniture khud le ja sakte hain",
                             "purana furniture khud le ja sakte ho",
                             "पुराना फर्नीचर कौन ले जाएगा", "पिकअप फ्री है क्या",
                             "गाड़ी भेजोगे क्या", "पुराना फर्नीचर खुद ले जा सकते हैं",
                             "पुराना फर्नीचर खुद ले जा सकते हो",
                             "purana furniture kab uthayenge", "pickup kab hoga",
                             "gaadi kab bhejoge purana lene",
                             "when will you collect the old furniture", "when is the pickup",
                             "पुराना फर्नीचर कब उठाएंगे", "पिकअप कब होगा",
                             "गाड़ी कब भेजोगे पुराना लेने",
                             "व्हेन विल यू कलेक्ट द ओल्ड फर्नीचर", "व्हेन इज़ द पिकअप"],
    "reschedule_appointment": ["date change karni hai", "meri appointment reschedule karo",
                               "main us din nahi aa paunga", "doosri date de do",
                               "meri date reschedule kar sakte hain", "date change kar sakte hain",
                               "date reschedule karo", "meri date reschedule karo",
                               "डेट चेंज करनी है", "अपॉइंटमेंट रीशेड्यूल करो",
                               "मैं उस दिन नहीं आ पाऊंगा", "दूसरी डेट दे दो",
                               "मेरी डेट रीशेड्यूल कर सकते हैं", "डेट चेंज कर सकते हैं",
                               "डेट रीशेड्यूल करो", "मेरी डेट रीशेड्यूल करो",
                               "date badalni hai", "us din nahi aa paunga",
                               "koi aur din de do", "shift kar do appointment",
                               "can we move the appointment", "need to change the date",
                               "can we reschedule",
                               "डेट बदलनी है", "उस दिन नहीं आ पाऊंगा", "कोई और दिन दे दो",
                               "शिफ्ट कर दो अपॉइंटमेंट", "कैन वी मूव द अपॉइंटमेंट",
                               "नीड टू चेंज द डेट", "कैन वी रीशेड्यूल"],
    "cancel_appointment": ["appointment cancel karo", "main nahi aa paunga ab",
                           "visit cancel kar do", "appointment cancel kar sakte hain",
                           "अपॉइंटमेंट कैंसिल करो", "मैं नहीं आ पाऊंगा अब", "विजिट कैंसिल कर दो",
                           "अपॉइंटमेंट कैंसिल कर सकते हैं",
                           "appointment cancel kar do", "ab nahi aa sakte",
                           "plan cancel ho gaya", "visit cancel karna hai",
                           "please cancel my appointment", "we can't make it anymore",
                           "need to cancel",
                           "अपॉइंटमेंट कैंसिल कर दो", "अब नहीं आ सकते", "प्लान कैंसिल हो गया",
                           "विजिट कैंसिल करना है", "प्लीज़ कैंसिल माय अपॉइंटमेंट",
                           "वी कांट मेक इट एनीमोर", "नीड टू कैंसल"],
    "legal_threat": ["consumer court jaunga", "legal action lunga",
                     "TRAI mein complaint karunga", "court mein le jaunga",
                     "कंज्यूमर कोर्ट जाऊंगा", "लीगल एक्शन लूंगा",
                     "ट्राई में कंप्लेंट करूंगा", "कोर्ट में ले जाऊंगा",
                     "police complaint karunga", "cyber cell mein report karunga",
                     "consumer forum jaunga", "i'll file a police complaint",
                     "i'll report this to cyber cell", "i'll take legal action",
                     "पुलिस कंप्लेंट करूंगा", "साइबर सेल में रिपोर्ट करूंगा",
                     "कंज्यूमर फोरम जाऊंगा", "आई विल फाइल अ पुलिस कंप्लेंट",
                     "आई विल रिपोर्ट दिस टू साइबर सेल", "आई विल टेक लीगल एक्शन"],
    "ask_call_recorded": ["yeh call record ho rahi hai kya", "is this call recorded",
                          "यह कॉल रिकॉर्ड हो रही है क्या", "ये कॉल रिकॉर्ड हो रही है क्या",
                          "recording ho rahi hai kya", "aap record kar rahe ho kya",
                          "is baat ki recording hai kya", "are you recording this",
                          "is this being recorded",
                          "रिकॉर्डिंग हो रही है क्या", "आप रिकॉर्ड कर रहे हो क्या",
                          "इस बात की रिकॉर्डिंग है क्या", "आर यू रिकॉर्डिंग दिस",
                          "इज़ दिस बीइंग रिकॉर्डेड"],
    "want_human": ["mujhe insaan se baat karni hai", "real agent se baat karwao",
                   "human se connect karo", "insaan se baat karwa sakte hain",
                   "insaan se baat karwao",
                   "मुझे इंसान से बात करनी है", "ह्यूमन से कनेक्ट करो", "असली आदमी से बात करवाओ",
                   "इंसान से बात कराओ", "इंसान से बात करवा सकते हैं",
                   "kisi real person se baat karao", "agent se connect karo",
                   "insaan chahiye baat karne ke liye", "please connect me to a human",
                   "i want to talk to a person", "transfer me to an agent",
                   "किसी रियल पर्सन से बात कराओ", "एजेंट से कनेक्ट करो",
                   "इंसान चाहिए बात करने के लिए", "प्लीज़ कनेक्ट मी टू अ ह्यूमन",
                   "आई वांट टू टॉक टू अ पर्सन", "ट्रांसफर मी टू एन एजेंट"],
}