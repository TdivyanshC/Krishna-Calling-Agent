# knowledge_react_abc.py — A/B/C Test Scripts
# Krishna Furniture Reactivation Campaign
# campaign_type: react_a | react_b | react_c

REACT_A_SCRIPT = {
    "ra_greet_main": "Aap apne ghar ka furniture upgrade karna chahte ho toh ab woh bahut aasaan ho gaya hai. Hum aapka purana furniture bhi achhi value mein lete hain aur naye furniture par bhi special discount chal raha hai. 30 second mein offer samjha doon?",
    "ra_greet_who": "Jee, main Priya bol rahi hoon Krishna Furniture ki taraf se. Aap hamare customer reh chuke hain isliye maine personally phone kiya aapko. Ek khaas offer hai sirf aapke liye.",
    "ra_greet_repeat": "Haan ji — hum aapka purana furniture achhe rate mein khareed lenge aur naye par heavy discount denge. Matlab ghar ka poora look badal jaata hai aadhe daam mein.",
    "ra_greet_privacy": "Jee bilkul — aapka number hamare purane customer records mein hai. Koi third party nahi hai. Aap hamare valued customer hain isliye personally call ki.",
    "ra_greet_hostile": "Maafi chahti hoon disturb karne ke liye. WhatsApp par details bhej deti hoon — dekhna na dekhna aap par hai. Aapka din achha rahe!",
    "ra_offer_main": "Krishna Furniture mein abhi naye furniture par 25% discount chal raha hai. Aur agar aap apna purana furniture exchange karte hain toh uski value ka bhi extra benefit milta hai. Matlab overall kharcha kaafi kam ho jaata hai. Ek aur achhi baat bataun?",
    "ra_offer_explain": "Bilkul simple hai — aap showroom aao, hum aapke purane furniture ki value calculate karenge aapke saamne. Us value par 25% aur, plus upar se 25% — total saving 43 se 50%. Koi hidden condition nahi hai.",
    "ra_offer_trust": "Samajh sakti hoon — aajkal bahut calls aati hain. Aap showroom mein aa kar personally verify kar sakte hain — koi commitment nahi. Sector 14 Gurgaon, Delhi, Noida — teeno jagah hain hamare showrooms.",
    "ra_offer_urgency": "Yeh offer sirf is mahine tak hai aur pieces limited hain. Jo pehle aaya usne le liya. WhatsApp par details check karo pehle — phir decide karo.",
    "ra_obj_not_interested": "Ek baar WhatsApp par dekh lena — sirf photos aur price list. Koi pressure nahi hai. Offer is mahine tak valid hai.",
    "ra_obj_busy": "Bilkul, disturb nahi karti. Details WhatsApp par hain — apni fursad mein dekh lena.",
    "ra_obj_expensive": "Isliye toh yeh exchange offer hai — new price par nahi, exchange ke saath. Exact amount WhatsApp par dekh sakte ho.",
    "ra_obj_online": "Online mein delivery, installation, after-sales sab alag hote hain. Hamare paas factory price hai plus exchange value — total comparison WhatsApp par hai.",
    "ra_obj_think": "Zaroor socho — but offer is mahine tak hi hai. WhatsApp par details reh jaaye, jab decide karo tab kaam aayegi.",
    "ra_obj_recovery": "Sach bolunga — jo families yeh offer leke gayi hain wo bahut khush hain. Aadhe daam mein ghar ka poora look badal jaata hai. Aap bhi iska fayda uthao.",
    "ra_hook_cta": "Aap hamare purane customer hain, isliye maine personally call kiya. Mera suggestion hai — ek baar showroom aa kar dekh lijiye, waha aapko sab kuch clearly samajh aa jayega. Uske baad decision poori tarah aapka rahega.",
    # Was missing entirely (script text + cache file both absent) while
    # rb_wa_cta/rc_wa_cta existed for the other 2 plans -- 5 live call sites
    # in webhook_reactivation.py (PRESENT_OFFER's buying_signal/expensive/
    # online_cheaper/busy branches, WHATSAPP_CTA's wa_diff_number branch) hit
    # play_key()'s "no text for key" silent-failure path for every react_a
    # call that reached them. Confirmed live bug, fixed here — text mirrors
    # rb_wa_cta verbatim, matching this file's existing convention of sharing
    # WA-CTA content across plans (only greet_main/offer_main meaningfully
    # differ by plan).
    "ra_wa_cta": "Main abhi WhatsApp par photos, prices, exchange process sab bhej rahi hoon. Ek baar dekh lena — decision baad mein karna.",
    "ra_close": "Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — purana furniture hum sambhal lenge, aap bas naya chunna. Bahut shukriya!",
    "ra_close_conviction": "Ab der mat karo — pieces limited hain. Showroom mein aao, apne saamne value calculate karwao, aur wohi din naya furniture le jaao. Purana hum le lenge. Bahut shukriya!",
    # Confirmed live 2026-08-13 (real test call): the APPOINTMENT state's
    # give-up-after-unclear-replies fallback was reusing ra_close ("Bilkul
    # sahi decision hai" -- that's absolutely the right decision) as its
    # close line. That's wrong when the caller never actually confirmed
    # anything -- their last turn was literally "hello?" in confusion, not
    # agreement. Honest neutral sign-off instead, matching fresh_cta's
    # existing fresh_no_date_close for the same situation.
    "ra_close_no_response": "Koi baat nahi ji, main details WhatsApp par bhej deti hoon — jab convenient ho tab dekh lijiyega. Aapka din shubh ho.",
    "ra_dnc": "Maafi chahti hoon! Aapka number DNC list mein add kar diya jaayega — ab koi call nahi aayegi. Bahut bahut shukriya.",
    "ra_q_location": "Hamare showrooms Sector 14 Gurgaon, Delhi, aur Noida mein hain — Monday se Sunday, subah 10 baje se raat 8 baje tak khule rehte hain.",
    "ra_q_name": "Mera naam Priya hai — main Krishna Furniture ki taraf se baat kar rahi hoon.",
    "ra_q_valuation": "Aap ek kaam kar sakte hain, showroom mein aake mujhse mil lijiye. Waha achhe se baat ho paayegi. Aap kis din aa sakte hain?",
    # Three added 2026-08-13 -- real questions that previously got no answer
    # at all (silently swallowed or answered with an unrelated pitch line).
    # q_price_range uses the same grounded prices knowledge.py's fresh-lead
    # FAQ funnel already uses (sofa/bed/dining) -- react_a/b/c had zero
    # pricing knowledge wired in before this. q_offer_scope deliberately
    # doesn't assert which products are covered (never confirmed as true),
    # defers to WhatsApp instead of guessing.
    "ra_q_price_range": "Sofa ₹33,000 se, bed ₹71,000 se, aur dining set ₹1,19,000 se shuru hota hai — exact price WhatsApp par bhi bhej rahi hoon.",
    # Rewritten 2026-08-13 -- user feedback: don't defer a question that has
    # a real, known answer to WhatsApp. Sofa/bed/dining/wardrobe/chair are
    # the categories this store's real knowledge base (knowledge.py) has
    # grounded prices for, so this states them directly rather than
    # deflecting. Ends the same way offer_main does ("achhi baat bataun?")
    # so it flows straight into hook_cta next, same two-line shape as the
    # normal offer pitch.
    "ra_q_offer_scope": "Sofa, bed, dining table, wardrobe, chair — bahut saare options hain is offer mein. Ek aur achhi baat bataun?",
    "ra_already_purchased": "Bahut badhiya ji! Agar future mein kabhi zaroorat pade toh humein zaroor yaad rakhiyega. Aapka din shubh ho.",
    "ra_appointment_ask": "Maine details WhatsApp par bhej di hain. Aap mujhe apni store visit ki date confirm kar dijiyega mujhe please.",
    "ra_appointment_confirmed": "Bahut badhiya ji, main aapko store par hi milungi, zaroor aana.",
    "ra_appointment_reask": "Maaf kijiye, samajh nahi aaya. Aap phir se date bata sakte hain please?",
    "ra_filler_1": "Haan...", "ra_filler_2": "Ji haan...", "ra_filler_3": "Bilkul...",
    "ra_filler_4": "Achha...", "ra_filler_5": "Samajh gayi...", "ra_filler_6": "Theek hai...",

    # Independence Day sale (2026-08-11 to 2026-08-16 IST) — flat 50% off,
    # replacing the exchange-offer pitch above for the duration of the sale.
    # Added as separate "_sale" keys rather than editing the originals in
    # place: play_key() (webhook_reactivation.py) transparently swaps to
    # these while _sale_active() is true, so the exchange copy and its
    # cached audio are untouched and the Aug 17 revert needs no code change
    # or re-cache pass — the window just closes. "No hidden condition" is
    # deliberately NOT claimed here (unlike ra_offer_explain above) — not
    # confirmed as true for this sale.
    "ra_greet_main_sale": "Independence Day ke mauke par Krishna Furniture mein is samay bahut bada offer chal raha hai — flat 50% off, sirf 16 August tak. Ghar ka furniture upgrade karna chahte ho toh yeh sabse achha time hai. 30 second mein offer samjha doon?",
    "ra_greet_repeat_sale": "Haan ji — abhi Independence Day sale chal rahi hai Krishna Furniture mein, flat 50% off, sirf 16 August tak. Matlab ghar ka poora look badal jaata hai aadhe daam mein.",
    "ra_offer_main_sale": "Krishna Furniture mein abhi Independence Day sale chal raha hai — har furniture par flat 50% off, lekin sirf 16 August tak valid hai. Ek aur achhi baat bataun?",
    "ra_offer_explain_sale": "Bilkul simple hai — jo bhi furniture aapko pasand aaye, uske price par seedha 50% off mil jaata hai. Bas offer sirf 16 August tak hai, uske baad yeh price wapas nahi milega.",
    "ra_offer_urgency_sale": "Yeh offer sirf 16 August tak hai aur pieces limited hain. Jo pehle aaya usne le liya. WhatsApp par details check karo pehle — phir decide karo.",
    "ra_obj_not_interested_sale": "Ek baar WhatsApp par dekh lena — sirf photos aur sale price list. Koi pressure nahi hai. Offer sirf 16 August tak valid hai.",
    "ra_obj_busy_sale": "Bilkul, disturb nahi karti. Details WhatsApp par hain — bas offer sirf 16 August tak hai, isliye jaldi dekh lena.",
    "ra_obj_expensive_sale": "Isliye toh abhi sahi time hai — flat 50% off matlab seedha aadha price. 16 August ke baad yeh rate nahi milega. Exact price WhatsApp par dekh sakte ho.",
    "ra_obj_online_sale": "Online mein delivery, installation, after-sales sab alag hote hain. Yahan seedha 50% off milta hai showroom price par — total comparison WhatsApp par hai.",
    "ra_obj_think_sale": "Zaroor socho — but offer sirf 16 August tak hai. WhatsApp par details reh jaayengi, jab decide karo tab kaam aayengi.",
    "ra_obj_recovery_sale": "Sach bolunga — jo families yeh sale mein aayi hain wo bahut khush hain. Seedha aadhe daam mein naya furniture. Aap bhi iska fayda uthao, bas 16 August tak hi hai.",
    "ra_wa_cta_sale": "Main abhi WhatsApp par photos aur 50% off wali prices bhej rahi hoon. Ek baar dekh lena — offer sirf 16 August tak hai.",
    "ra_close_sale": "Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — 16 August se pehle. Bahut shukriya!",
    "ra_close_conviction_sale": "Ab der mat karo — pieces limited hain aur offer sirf 16 August tak hai. Showroom mein aao, seedha 50% off le jaao. Bahut shukriya!",
}

REACT_B_SCRIPT = {
    "rb_greet_main": "Pichhle kuch dino mein bahut saare customers ne apna purana furniture exchange karke naya furniture liya hai. Isliye maine socha aapko bhi call kar doon. Agar aap bhi ghar ka furniture upgrade karna chahte hain toh yeh offer kaafi useful ho sakta hai. Sunna chahenge?",
    "rb_greet_who": "Jee, main Priya bol rahi hoon Krishna Furniture ki taraf se. Aap hamare customer reh chuke hain isliye maine personally phone kiya. Soniya ji jaisi bahut families is mahine ghar badal rahi hain — aapke liye bhi yahi offer leke aayi hoon.",
    "rb_greet_repeat": "Haan ji — hum purane customers ko ek special offer de rahe hain. Purana furniture achhe rate mein khareed lenge aur naye par heavy discount denge. Aapko offer batau?",
    "rb_greet_privacy": "Jee bilkul — aapka number hamare purane customer records mein hai. Koi third party nahi. Aap hamare valued customer hain isliye personally call ki.",
    "rb_greet_hostile": "Maafi chahti hoon disturb karne ke liye. WhatsApp par details bhej deti hoon — dekhna na dekhna aap par hai. Aapka din achha rahe!",
    "rb_offer_main": "Abhi Krishna Furniture mein naye furniture par 25% discount chal raha hai. Aur purana furniture exchange karne par uski value ka bhi extra benefit milta hai. Is wajah se kaafi log expected se kam budget mein naya furniture le pa rahe hain. Ek aur baat bataun?",
    "rb_offer_explain": "Bilkul simple hai — aap showroom aao, hum aapke purane furniture ki value calculate karenge aapke saamne. Us value par 25% aur, plus upar se 25% — total saving 43 se 50%. Koi hidden condition nahi hai.",
    "rb_offer_trust": "Samajh sakti hoon — aajkal bahut calls aati hain. Aap showroom mein aa kar personally verify kar sakte hain — koi commitment nahi. Free mein value estimate ho jaati hai.",
    "rb_offer_urgency": "Is mahine bahut families aa rahi hain — pieces limited hain. Jo pehle aaya usne le liya. Aap der mat karo.",
    "rb_obj_not_interested": "Koi baat nahi — ek baar WhatsApp par photos dekh lena. Offer is mahine tak valid hai — decision aap ka hai.",
    "rb_obj_busy": "Bilkul, disturb nahi karti. Details WhatsApp par bhej deti hoon — jab time mile tab dekh lena. Offer is mahine tak valid hai.",
    "rb_obj_expensive": "Isliye toh exchange offer hai — new price par nahi, exchange ke saath. Exact amount WhatsApp par dekh sakte ho.",
    "rb_obj_online": "Online mein delivery, installation, after-sales sab alag hote hain. Yahan factory price hai plus exchange value — total comparison WhatsApp par hai.",
    "rb_obj_think": "Zaroor socho — but offer is mahine tak hi hai. WhatsApp details reh jaaye — jab decide karo tab kaam aayegi.",
    "rb_obj_recovery": "Jo families yeh offer le ke gayi hain wo bahut khush hain. Aap bhi ek baar showroom aao — free mein value estimate ho jaati hai. Koi commitment nahi.",
    "rb_hook_cta": "Aap bhi hamare purane customer hain, isliye yeh offer maine personally share kiya. Main WhatsApp par furniture ke photos, prices aur exchange process bhej deti hoon. Ek baar dekh lijiye, decision baad mein bhi le sakte hain.",
    "rb_wa_cta": "Main abhi WhatsApp par photos, prices, exchange process sab bhej rahi hoon. Ek baar dekh lena — decision baad mein karna.",
    "rb_close": "Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — purana furniture hum sambhal lenge, aap bas naya chunna. Bahut shukriya!",
    "rb_close_conviction": "Bahut sahi decision hai. Showroom mein aao, apne saamne value calculate karwao, aur wohi din naya furniture le jaao. Purana hum le lenge. Bahut shukriya!",
    # See ra_close_no_response's comment above -- same fix, this voice.
    "rb_close_no_response": "Theek hai ji, koi jaldi nahi. WhatsApp par details bhej deti hoon — jab time mile tab dekh lijiyega. Shukriya.",
    "rb_dnc": "Maafi chahti hoon! Aapka number DNC list mein add kar diya jaayega — ab koi call nahi aayegi. Bahut bahut shukriya.",
    "rb_q_location": "Hamare showrooms Sector 14 Gurgaon, Delhi, aur Noida mein hain — Monday se Sunday, subah 10 baje se raat 8 baje tak khule rehte hain.",
    "rb_q_name": "Mera naam Priya hai — main Krishna Furniture ki taraf se baat kar rahi hoon.",
    "rb_q_valuation": "Aap ek kaam kar sakte hain, showroom mein aake mujhse mil lijiye. Waha achhe se baat ho paayegi. Aap kis din aa sakte hain?",
    # See ra_q_price_range/ra_q_offer_scope/ra_already_purchased's comment (REACT_A_SCRIPT above).
    "rb_q_price_range": "Sofa ₹33,000 se, bed ₹71,000 se, aur dining set ₹1,19,000 se shuru hota hai — exact price WhatsApp par bhi bhej rahi hoon.",
    # See ra_q_offer_scope's comment (REACT_A_SCRIPT above).
    "rb_q_offer_scope": "Sofa, bed, dining table, wardrobe, chair — bahut saare options hain is offer mein. Ek aur achhi baat bataun?",
    "rb_already_purchased": "Bahut badhiya ji! Agar future mein kabhi zaroorat pade toh humein zaroor yaad rakhiyega. Aapka din shubh ho.",
    "rb_appointment_ask": "Maine details WhatsApp par bhej di hain. Aap mujhe apni store visit ki date confirm kar dijiyega mujhe please.",
    "rb_appointment_confirmed": "Bahut badhiya ji, main aapko store par hi milungi, zaroor aana.",
    "rb_appointment_reask": "Maaf kijiye, samajh nahi aaya. Aap phir se date bata sakte hain please?",
    "rb_filler_1": "Haan...", "rb_filler_2": "Ji haan...", "rb_filler_3": "Bilkul...",
    "rb_filler_4": "Achha...", "rb_filler_5": "Samajh gayi...", "rb_filler_6": "Theek hai...",

    # Independence Day sale -- see the matching comment block in
    # REACT_A_SCRIPT above for the mechanism (play_key()'s _sale_active()
    # swap) and why "no hidden condition" is deliberately not claimed.
    "rb_greet_main_sale": "Independence Day ke mauke par Krishna Furniture mein bahut bada sale chal raha hai — flat 50% off, sirf 16 August tak. Isliye maine socha aapko bhi call kar doon. Sunna chahenge?",
    "rb_greet_repeat_sale": "Haan ji — abhi Independence Day sale chal rahi hai, flat 50% off, sirf 16 August tak. Aapko offer batau?",
    "rb_offer_main_sale": "Abhi Krishna Furniture mein Independence Day sale chal raha hai — har furniture par flat 50% off, lekin sirf 16 August tak valid hai. Is wajah se kaafi log expected se kam budget mein naya furniture le pa rahe hain. Ek aur baat bataun?",
    "rb_offer_explain_sale": "Bilkul simple hai — jo bhi furniture aapko pasand aaye, uske price par seedha 50% off mil jaata hai. Bas offer sirf 16 August tak hai, uske baad yeh price wapas nahi milega.",
    "rb_offer_urgency_sale": "Is hafte bahut families aa rahi hain — pieces limited hain aur offer sirf 16 August tak hai. Aap der mat karo.",
    "rb_obj_not_interested_sale": "Koi baat nahi — ek baar WhatsApp par photos dekh lena. Offer sirf 16 August tak valid hai — decision aap ka hai.",
    "rb_obj_busy_sale": "Bilkul, disturb nahi karti. Details WhatsApp par bhej deti hoon — bas offer sirf 16 August tak hai, jaldi dekh lena.",
    "rb_obj_expensive_sale": "Isliye toh abhi sahi time hai — flat 50% off matlab seedha aadha price. 16 August ke baad yeh rate nahi milega. Exact price WhatsApp par dekh sakte ho.",
    "rb_obj_online_sale": "Online mein delivery, installation, after-sales sab alag hote hain. Yahan seedha 50% off milta hai showroom price par — total comparison WhatsApp par hai.",
    "rb_obj_think_sale": "Zaroor socho — but offer sirf 16 August tak hai. WhatsApp details reh jaayengi — jab decide karo tab kaam aayengi.",
    "rb_obj_recovery_sale": "Jo families yeh sale mein aayi hain wo bahut khush hain. Aap bhi ek baar showroom aao — seedha 50% off, bas 16 August tak hi hai.",
    "rb_hook_cta_sale": "Aap bhi hamare purane customer hain, isliye yeh Independence Day sale maine personally share kiya. Main WhatsApp par furniture ke photos aur 50% off prices bhej deti hoon. Ek baar dekh lijiye, decision baad mein bhi le sakte hain.",
    "rb_wa_cta_sale": "Main abhi WhatsApp par photos aur 50% off wali prices bhej rahi hoon. Ek baar dekh lena — offer sirf 16 August tak hai.",
    "rb_close_sale": "Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — 16 August se pehle. Bahut shukriya!",
    "rb_close_conviction_sale": "Bahut sahi decision hai. Pieces limited hain aur offer sirf 16 August tak hai. Showroom mein aao, seedha 50% off le jaao. Bahut shukriya!",
}

REACT_C_SCRIPT = {
    "rc_greet_main": "Ek chhota sa sawal poochun? Agar aapko naya furniture mil jaaye aur purana bhi achhi value mein chala jaaye, woh bhi kam kharche mein... toh kya aap uske baare mein sunna chahenge?",
    "rc_greet_who": "Jee, main Priya bol rahi hoon Krishna Furniture ki taraf se. Aap hamare customer reh chuke hain isliye maine personally phone kiya. Ek sawaal poochha tha — agar naya furniture aadhe daam mein mile toh sunenge?",
    "rc_greet_repeat": "Haan ji — main pooch rahi thi, agar aapko naya furniture mile aur purana bhi achhe rate mein chala jaaye — aadhe daam mein — toh aap sunna chahenge?",
    "rc_greet_privacy": "Jee bilkul — aapka number hamare purane customer records mein hai. Koi third party nahi. Aap hamare valued customer hain isliye personally call ki.",
    "rc_greet_hostile": "Maafi chahti hoon disturb karne ke liye. WhatsApp par details bhej deti hoon — dekhna na dekhna aap par hai. Aapka din achha rahe!",
    "rc_offer_main": "Toh bas wahi offer chal raha hai Krishna Furniture mein. Naye furniture par 25% discount hai aur purana furniture exchange karne par uski value ka bhi alag benefit milta hai. Ek aur baat bataun?",
    "rc_offer_explain": "Bilkul simple hai — aap showroom aao, hum aapke purane furniture ki value calculate karenge aapke saamne. Us value par 25% aur, plus upar se 25% — total saving 43 se 50%. Free mein value estimate ho jaati hai — koi commitment nahi.",
    "rc_offer_trust": "Samajh sakti hoon — aajkal bahut calls aati hain. Aap showroom mein aa kar personally verify kar sakte hain — koi commitment nahi. Free mein furniture ki value estimate ho jaati hai. Sirf ek baar aao toh sahi.",
    "rc_offer_urgency": "Yeh offer sirf apne purane customers ke liye hai — aur is mahine tak hi valid hai. Jo pehle aaya usne le liya. Aap der mat karo.",
    "rc_obj_not_interested": "Koi baat nahi — main force nahi kar rahi. Bas ek baar WhatsApp par photos dekh lena. Offer is mahine tak valid hai — decision aap ka hai.",
    "rc_obj_busy": "Bilkul, disturb nahi karti. Details WhatsApp par bhej deti hoon — apni fursad mein dekh lena.",
    "rc_obj_expensive": "Isliye toh yeh exchange offer hai — new price par nahi, exchange ke saath. Exact amount WhatsApp par dekh sakte ho. Free mein estimate bhi ho jaati hai showroom mein.",
    "rc_obj_online": "Online mein delivery, installation, after-sales sab alag hote hain. Hamare paas factory price hai plus exchange value — total comparison WhatsApp par hai.",
    "rc_obj_think": "Zaroor socho — main force nahi kar rahi. But offer is mahine tak hi hai. WhatsApp details reh jaaye — jab decide karo tab kaam aayegi.",
    "rc_obj_recovery": "Dekho, maine aapko force nahi karna. Bas ek baar WhatsApp dekho, showroom aao — free mein furniture ki value estimate ho jaati hai. Koi commitment nahi. Aao toh sahi.",
    "rc_hook_cta": "Yeh offer hum specially apne existing customers ke saath share kar rahe hain. Isliye maine aapko personally call kiya. Main WhatsApp par photos aur poori details bhej deti hoon. Ek baar dekh lijiye, koi commitment bilkul nahi hai.",
    "rc_wa_cta": "Main abhi WhatsApp par photos, prices, exchange process sab bhej rahi hoon. Ek baar dekh lena — decision baad mein karna. Koi commitment nahi.",
    "rc_close": "Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — free mein value estimate ho jaayegi. Purana furniture hum sambhal lenge, aap bas naya chunna. Bahut shukriya!",
    # See ra_close_no_response's comment (REACT_A_SCRIPT above) -- same fix, this voice.
    "rc_close_no_response": "Koi baat nahi ji, main force nahi kar rahi. WhatsApp par details bhej deti hoon — apni fursad mein dekh lijiyega. Shukriya.",
    "rc_dnc": "Maafi chahti hoon! Aapka number DNC list mein add kar diya jaayega — ab koi call nahi aayegi. Bahut bahut shukriya.",
    "rc_q_location": "Hamare showrooms Sector 14 Gurgaon, Delhi, aur Noida mein hain — Monday se Sunday, subah 10 baje se raat 8 baje tak khule rehte hain.",
    "rc_q_name": "Mera naam Priya hai — main Krishna Furniture ki taraf se baat kar rahi hoon.",
    "rc_q_valuation": "Aap ek kaam kar sakte hain, showroom mein aake mujhse mil lijiye. Waha achhe se baat ho paayegi. Aap kis din aa sakte hain?",
    # See ra_q_price_range/ra_q_offer_scope/ra_already_purchased's comment (REACT_A_SCRIPT above).
    "rc_q_price_range": "Sofa ₹33,000 se, bed ₹71,000 se, aur dining set ₹1,19,000 se shuru hota hai — exact price WhatsApp par bhi bhej rahi hoon.",
    # See ra_q_offer_scope's comment (REACT_A_SCRIPT above).
    "rc_q_offer_scope": "Sofa, bed, dining table, wardrobe, chair — bahut saare options hain is offer mein. Ek aur achhi baat bataun?",
    "rc_already_purchased": "Bahut badhiya ji! Agar future mein kabhi zaroorat pade toh humein zaroor yaad rakhiyega. Aapka din shubh ho.",
    "rc_appointment_ask": "Maine details WhatsApp par bhej di hain. Aap mujhe apni store visit ki date confirm kar dijiyega mujhe please.",
    "rc_appointment_confirmed": "Bahut badhiya ji, main aapko store par hi milungi, zaroor aana.",
    "rc_appointment_reask": "Maaf kijiye, samajh nahi aaya. Aap phir se date bata sakte hain please?",
    "rc_filler_1": "Haan...", "rc_filler_2": "Ji haan...", "rc_filler_3": "Bilkul...",
    "rc_filler_4": "Achha...", "rc_filler_5": "Samajh gayi...", "rc_filler_6": "Theek hai...",

    # Independence Day sale -- see the matching comment block in
    # REACT_A_SCRIPT above for the mechanism (play_key()'s _sale_active()
    # swap) and why "no hidden condition" is deliberately not claimed.
    "rc_greet_main_sale": "Ek chhota sa sawal poochun? Independence Day ke mauke par Krishna Furniture mein flat 50% off chal raha hai, sirf 16 August tak — kya aap uske baare mein sunna chahenge?",
    "rc_greet_repeat_sale": "Haan ji — main pooch rahi thi, Independence Day sale chal rahi hai abhi, flat 50% off, sirf 16 August tak — toh aap sunna chahenge?",
    "rc_offer_main_sale": "Toh bas wahi offer chal raha hai Krishna Furniture mein — Independence Day sale, flat 50% off, sirf 16 August tak valid hai. Ek aur baat bataun?",
    "rc_offer_explain_sale": "Bilkul simple hai — jo bhi furniture aapko pasand aaye, uske price par seedha 50% off mil jaata hai. Bas offer sirf 16 August tak hai — koi commitment nahi, bas ek baar dekh lijiye.",
    "rc_offer_urgency_sale": "Yeh offer sirf apne purane customers ke liye hai — aur sirf 16 August tak hi valid hai. Jo pehle aaya usne le liya. Aap der mat karo.",
    "rc_obj_not_interested_sale": "Koi baat nahi — main force nahi kar rahi. Bas ek baar WhatsApp par photos dekh lena. Offer sirf 16 August tak valid hai — decision aap ka hai.",
    "rc_obj_busy_sale": "Bilkul, disturb nahi karti. Details WhatsApp par bhej deti hoon — bas offer sirf 16 August tak hai, apni fursad mein jaldi dekh lena.",
    "rc_obj_expensive_sale": "Isliye toh abhi sahi time hai — flat 50% off matlab seedha aadha price. 16 August ke baad yeh rate nahi milega. Exact price WhatsApp par dekh sakte ho.",
    "rc_obj_online_sale": "Online mein delivery, installation, after-sales sab alag hote hain. Yahan seedha 50% off milta hai showroom price par — total comparison WhatsApp par hai.",
    "rc_obj_think_sale": "Zaroor socho — main force nahi kar rahi. But offer sirf 16 August tak hai. WhatsApp details reh jaayengi — jab decide karo tab kaam aayengi.",
    "rc_obj_recovery_sale": "Dekho, maine aapko force nahi karna. Bas ek baar WhatsApp dekho — seedha 50% off hai, bas 16 August tak. Aao toh sahi.",
    "rc_wa_cta_sale": "Main abhi WhatsApp par photos aur 50% off wali prices bhej rahi hoon. Ek baar dekh lena — offer sirf 16 August tak hai. Koi commitment nahi.",
    "rc_close_sale": "Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — 16 August se pehle. Bahut shukriya!",
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
    # All lines voiced as Simran. No dnc key here on purpose — hard decline
    # reuses ra_dnc's existing cached audio directly (see handle_fresh_cta_turn).
    "fresh_greet_bed": "Namaste ji, hamari WhatsApp par baat hui thi — aap bed dekhna chahte the. Toh kab aana hoga store par? Main aapko wahi milungi.",
    "fresh_greet_sofa": "Namaste ji, hamari WhatsApp par baat hui thi — aap sofa dekhna chahte the. Toh kab aana hoga store par? Main aapko wahi milungi.",
    "fresh_greet_wardrobe": "Namaste ji, hamari WhatsApp par baat hui thi — aap wardrobe dekhna chahte the. Toh kab aana hoga store par? Main aapko wahi milungi.",
    "fresh_greet_dining": "Namaste ji, hamari WhatsApp par baat hui thi — aap dining set dekhna chahte the. Toh kab aana hoga store par? Main aapko wahi milungi.",
    "fresh_greet_generic": "Namaste ji, hamari WhatsApp par baat hui thi Krishna Furniture ke baare mein. Toh kab aana hoga store par? Main aapko wahi milungi.",
    "fresh_objection": "Ji sir, bahut ache ache designs aaye hain, aapko zaroor pasand aaenge. Main WhatsApp par bhej deti hoon, lekin ek baar store aake dekhna zyada sahi rahega — waha ache se samajh aa jaayega. Kab aa sakte hain?",
    "fresh_appointment_confirmed": "Bahut badhiya ji! Main aapka appointment confirm kar deti hoon. Hamari team aapka intezar karegi. Jaldi milte hain!",
    "fresh_no_date_close": "Koi baat nahi ji. Main aapko WhatsApp par kuch achhe options bhej deti hoon — aap aaram se dekh lijiye, phir jab convenient ho tab visit plan kar lenge.",
    "fresh_soft_defer": "Okay ji, aap WhatsApp par hi confirm kar dena, main aur options bhej deti hoon.",
    "fresh_location_info": "Humare stores Gurugram, Delhi, Noida, aur Faridabad mein hain. WhatsApp par aapko exact address aur Google Maps link bhej deti hoon — aap wahi se date confirm kar dena, phir wahi milenge hum.",
    "fresh_greet_who_bed": "Ji, Krishna Furniture se — humari WhatsApp par baat hui thi bed ke baare mein. Kab aana hoga store par?",
    "fresh_greet_who_sofa": "Ji, Krishna Furniture se — humari WhatsApp par baat hui thi sofa ke baare mein. Kab aana hoga store par?",
    "fresh_greet_who_wardrobe": "Ji, Krishna Furniture se — humari WhatsApp par baat hui thi wardrobe ke baare mein. Kab aana hoga store par?",
    "fresh_greet_who_dining": "Ji, Krishna Furniture se — humari WhatsApp par baat hui thi dining set ke baare mein. Kab aana hoga store par?",
    "fresh_greet_who_generic": "Ji, Krishna Furniture se — humari WhatsApp par baat hui thi. Kab aana hoga store par?",
    # Phase 2 — price/trust objection handling for fresh_cta's single
    # APPOINTMENT state, wired via route_objection() (webhook_reactivation.py).
    # Single key each (no voice fan-out needed) since this funnel is always
    # Simran, unlike obj_repeat_generic which crosses flows/voices.
    "fresh_price": "Ji sir, price bilkul reasonable hai, poori detail WhatsApp par bhej deti hoon. Store aake dekhoge toh value khud samajh aa jaayegi — kab aa sakte hain?",
    "fresh_trust": "Bilkul samajh sakti hoon ji. Store aake khud dekh sakte hain, koi obligation nahi — waha se hi sahi decide kar paoge. Kab aa sakte hain?",
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
    "c2_greet_main": "Namaste ji, Priya bol rahi hoon Krishna Furniture se. Pichhli baar hamari baat hui thi, yaad hai na?",
    # "furniture exchange ki" deliberately dropped from these two lines
    # (2026-08-11) -- call2/call3 scripts are shared across every lead
    # regardless of which offer their Call 1 pitched (exchange, or the
    # Independence Day flat-50% sale from 2026-08-11), so the wording needs
    # to stay accurate for both without a second variant system. "Jo
    # details bheji thi" works either way.
    "c2_greet_reorient": "Ji, Krishna Furniture se. Maine aapko WhatsApp par offer ki details bheji thi.",
    "c2_greet_annoyed": "Bilkul ji, bas 30 second loongi. Aapki store visit ki date confirm karni thi.",
    "c2_wa_check": "Maine WhatsApp par jo details bheji thi, dekh li aapne?",
    "c2_invite_seen": "Ji badhiya! Toh ek baar showroom zaroor aaiye. Kab free honge aap? Ek date bata dijiye.",
    "c2_invite_resend": "Koi baat nahi ji, main abhi dobara WhatsApp par bhej deti hoon. Zaroor dekh lijiyega. Waise seedha showroom bhi aa sakte hain — kab free honge aap? Ek date bata dijiye.",
    "c2_date_direct": "Kab free honge aap store visit ke liye? Ek date bata dijiye.",
    "c2_date_reask": "Bilkul ji, koi jaldi nahi. Bas ek din bata dijiye, hum milte hain phir uss din store mein.",
    "c2_booked": "Okay ji, main store par hi milungi aapko. Zaroor aana. Dhanyawad.",
    "c2_obj_price": "Ho sakta hai ji, isiliye ek baar dekh lena behtar rahega — final decision toh aap showroom mein hi lenge na?",
    # Phase 2b -- WA_CHECK's busy/sochna_hai gap. Single-play, self-contained
    # (asks for a date itself, same shape as c2_invite_seen/c2_invite_resend
    # above it, since WA_CHECK has no separate opening line to hand off to).
    "c2_obj_timing": "Koi baat nahi ji, samajh sakti hoon. WhatsApp par details bhej deti hoon, aap apni convenience se dekh lijiyega — bas ek din bata dijiye jab aap free honge.",
    "c2_obj_scam": "Bilkul nahi ji, bharosa rakhiye. Aap chahein toh seedha showroom visit karke khud dekh sakte hain — kab free honge, ek date bata dijiye?",
    "c2_obj_not_interested": "Koi baat nahi ji. Bas confirm karna tha. Zaroorat ho toh yaad rakhiyega humein.",
    "c2_close_thinking": "Theek hai ji, aaram se soch lijiye. Main details WhatsApp par bhej deti hoon.",
    "c2_close_busy": "Koi baat nahi ji, jab time mile tab dekh lijiyega.",
    "c2_close_price": "Samajh sakti hoon ji. Main details WhatsApp par bhej deti hoon, dekh lijiyega.",
    "c2_close_declined": "Dhanyavaad ji, aapka time dene ke liye shukriya.",
}

CALL3_SCRIPT = {
    "c3_greet_main": "Namaste ji, Priya bol rahi hoon Krishna Furniture se. Aapse pehle bhi baat hui thi — bas ek aakhri baar poochna tha, kya socha aapne?",
    # Same "exchange" drop as c2_greet_reorient/c2_wa_check above -- offer-
    # agnostic wording so this works for both the exchange pitch and the
    # Independence Day sale.
    "c3_greet_reorient": "Arre, Krishna Furniture se — woh offer jo maine pehle bataya tha.",
    "c3_greet_hostile": "Bilkul theek hai ji, samajh gayi. Ab dobara call nahi karungi. Shukriya.",
    "c3_decision_date": "Ek baar showroom aa jaiye, sirf paanch minute lagenge. Kab free honge? Ek date bata dijiye.",
    "c3_date_reask": "Bilkul ji, koi jaldi nahi. Bas ek din bata dijiye, hum milte hain phir uss din store mein.",
    "c3_booked": "Okay ji, main store par hi milungi aapko. Zaroor aana. Dhanyawad.",
    "c3_obj_price": "Samajh sakti hoon ji. Offer WhatsApp par hai, jab convenient ho dekh lijiyega.",
    "c3_obj_scam": "Bilkul nahi ji, bharosa rakhiye — showroom khud visit karke dekh sakte hain. Kab free honge, ek date bata dijiye?",
    "c3_declined": "Bilkul samajh sakti hoon ji. Aapka time dene ke liye shukriya.",
    "c3_close_thinking_final": "Koi baat nahi ji. Details WhatsApp par hain, jab convenient ho dekh lijiyega. Aapka din shubh ho.",
    "c3_close_busy": "Koi baat nahi ji, abhi disturb nahi karti. Details WhatsApp par hain.",
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
    "wa_decline_confirm_greet": "Namaste ji, maine dekha aapne WhatsApp par thoda hesitant feel kiya tha. Bas ek baar confirm karna chahti thi — kya abhi ke liye interested nahi hain, ya kuch aur jaankari chahiye?",
    # DRAFT — flagged for wording review before this ever generates real
    # traffic. Flow-agnostic "please repeat that" acknowledgment, used by
    # route_objection() (webhook_reactivation.py) for every repeat-intent
    # turn EXCEPT react Call1's GREETING state, which keeps its existing
    # content-specific {p}_greet_repeat line. Same text in all 3 voices —
    # 3 separate keys (not 1) because this line is reachable from flows that
    # don't share a voice (fresh_cta/Call3=simran, Call2=ritu, react_a/b/c
    # =ritu/shreya/simran) and a single voice would audibly clash mid-call
    # in whichever flows it didn't match; route_objection() picks the right
    # one via PREFIX_VOICE_MAP above.
    "obj_repeat_generic_ritu": "Maaf kijiye, thik se sun nahi paayi. Kya aap phir se bata sakte hain?",
    "obj_repeat_generic_shreya": "Maaf kijiye, thik se sun nahi paayi. Kya aap phir se bata sakte hain?",
    "obj_repeat_generic_simran": "Maaf kijiye, thik se sun nahi paayi. Kya aap phir se bata sakte hain?",
    # Phase 2b — GREETING-stage busy/sochna_hai gap (react_a/b/c, call2,
    # call3). Same 3-voice-variant reasoning as obj_repeat_generic above.
    # Deliberately content-free (no offer/pitch reference) since the
    # customer hasn't heard anything yet at GREETING — route_objection()
    # plays this THEN immediately plays that flow's own next default line
    # in the same turn (offer_main / c2_wa_check / c3_decision_date),
    # mirroring the two-play convention GREETING already uses for every
    # other acknowledged intent there (confusion_who etc).
    "obj_timing_greet_generic_ritu": "Bilkul samajh sakti hoon ji, koi jaldi nahi hai. Bas do minute mein bata deti hoon, phir aap soch lijiyega.",
    "obj_timing_greet_generic_shreya": "Bilkul samajh sakti hoon ji, koi jaldi nahi hai. Bas do minute mein bata deti hoon, phir aap soch lijiyega.",
    "obj_timing_greet_generic_simran": "Bilkul samajh sakti hoon ji, koi jaldi nahi hai. Bas do minute mein bata deti hoon, phir aap soch lijiyega.",
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
    "wa_fallback_deflect_ritu": "Main details WhatsApp par bhej deti hoon, aap wahan check kar lijiyega please.",
    "wa_fallback_deflect_shreya": "Main details WhatsApp par bhej deti hoon, aap wahan check kar lijiyega please.",
    "wa_fallback_deflect_simran": "Main details WhatsApp par bhej deti hoon, aap wahan check kar lijiyega please.",
    # Added 2026-08-13 -- fillers to bridge the LLM fallback's real latency
    # (0.5-4s, vs ~5-10ms for the normal cached-audio path) with something
    # topic-appropriate instead of dead air. Voice-matched per campaign
    # (unlike filler_audio.py's existing fillers, which hardcode "shreya"
    # for every call regardless of which voice is actually speaking --
    # likely part of why a voice sounded wrong on an earlier call). Picked
    # by a fast local keyword check on the raw transcript (webhook_reactivation.
    # _pick_llm_filler_key()) -- no LLM call, adds no latency of its own.
    "llm_filler_price_ritu": "Ek second, price check kar rahi hoon...",
    "llm_filler_price_shreya": "Ek second, price check kar rahi hoon...",
    "llm_filler_price_simran": "Ek second, price check kar rahi hoon...",
    "llm_filler_location_ritu": "Ek second, showroom ki detail bata rahi hoon...",
    "llm_filler_location_shreya": "Ek second, showroom ki detail bata rahi hoon...",
    "llm_filler_location_simran": "Ek second, showroom ki detail bata rahi hoon...",
    "llm_filler_generic_ritu": "Ek second, dekhti hoon...",
    "llm_filler_generic_shreya": "Ek second, dekhti hoon...",
    "llm_filler_generic_simran": "Ek second, dekhti hoon...",
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
    "ask_location": ["kahan hai", "showroom kahan", "location kya", "address batao",
                     "kaha hai showroom", "kahan par hai", "kaunsi jagah",
                     "pata batao", "pata kya hai", "aapka pata", "store ka pata",
                     "address", "location", "nazdik", "nearest",
                     "where is your showroom", "where is your store", "where are you located",
                     "कहां है", "कहाँ है", "शोरूम कहां", "लोकेशन क्या", "एड्रेस बताओ",
                     "कहां पर है", "कहाँ पर है", "स्टोर कहां", "स्टोर कहाँ", "कौनसी जगह",
                     "दुकान कहां", "shop kahan", "store kahan", "showroom kaha",
                     "पता बताओ", "पता क्या है", "आपका पता", "स्टोर का पता",
                     "वेयर इज योर शोरूम", "वेयर इज योर स्टोर",
                     "एड्रेस", "लोकेशन", "नज़दीक", "नज़दीकी"],
    # English-phonetic Devanagari forms added 2026-08-13 -- confirmed live,
    # multiple real customers this week asked for the agent's name in
    # English ("I'd like to know your name", "could you share your name
    # with me") and matched nothing -- Hindi STT renders spoken English
    # phonetically into Devanagari, not Latin text, so only Devanagari forms
    # actually match live transcripts (Latin "your name" kept too in case a
    # different STT path ever returns Latin script).
    "ask_name": ["tumhara naam", "aapka naam", "naam kya hai", "kaun bol rahe ho",
                "your name", "share your name", "give me your name", "know your name",
                "तुम्हारा नाम", "आपका नाम", "नाम क्या है", "कौन बोल रहे हो", "कौन बोल रही हो",
                "योर नेम", "शेयर योर नेम", "गिव मी योर नेम", "नो योर नेम"],
    # "band hota"/"बंद होता" (closing time) added 2026-08-13 -- this only
    # covered "khulta"/opening time before; a customer asking when the store
    # CLOSES matched nothing. Plain English added same day (second pass,
    # customer explicitly asked to check English coverage across every
    # category) -- this list had ZERO English before, Hinglish/Devanagari
    # only.
    "ask_timings": ["time kya", "kab khulta", "timing kya hai", "kitne baje khulta",
                    "band hota", "band hoti", "kab tak khula",
                    "what time", "when do you open", "when do you close",
                    "opening hours", "closing time", "working hours", "office hours",
                    "टाइम क्या", "कब खुलता", "टाइमिंग क्या है", "कितने बजे खुलता",
                    "बंद होता", "बंद होती", "कब तक खुला"],
    "ask_valuation": ["valuation kaise", "purana furniture kaise", "kaise pickup",
                      "value kaise milegi", "kaise calculate", "kaise lenge purana",
                      "how much will i get", "buyback value", "trade in value", "resale value",
                      "वैल्यूएशन कैसे", "पुराना फर्नीचर कैसे", "कैसे पिकअप", "वैल्यू कैसे मिलेगी",
                      "कैसे कैलकुलेट", "कैसे लेंगे पुराना"],
    "ask_delivery": ["delivery kab", "kab milega", "kitne din mein", "delivery kaise",
                     "when will it arrive", "delivery time", "how many days for delivery",
                     "how long for delivery",
                     "डिलीवरी कब", "कब मिलेगा", "कितने दिन में", "डिलीवरी कैसे"],
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
                            "is hafte", "इस हफ्ते"],
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
    # 919911117660): the customer said "यस" then "यस यस" as his first two
    # replies and got the "sorry, didn't catch that" reprompt both times,
    # only succeeding on his third attempt once he switched to "haan ji".
    # This exact gap was already closed in knowledge.py's ACK_WORDS for the
    # fresh-lead flow months ago -- it just never made it into this file's
    # list. Same reasoning extended to "yeah"/"yep"/"ha" (bare, casual
    # Hinglish "yeah") and "sahi hai"/"सही है"/"correct", which are
    # equally common affirmations never covered here. Bare "right" REMOVED
    # 2026-08-13 (caught in this same pass's own verification testing) --
    # collides with "right now"/"right there"/"not right now" etc, which
    # have nothing to do with affirmation; "i am busy right now" was
    # matching both "busy" AND "positive" off "right" alone. Same
    # false-positive shape already documented for "यह"/bare "पता" above.
    "positive": ["haan", "han", "haa", "ha", "theek hai", "batao", "bolo", "sun raha hoon",
                 "okay", "ok", "sure", "bilkul", "achha", "bataiye", "sunenge", "ji",
                 "yes", "yeah", "yep", "yup", "correct", "sahi hai",
                 "जी", "हाँ", "हां", "ठीक है", "बताओ", "बोलो", "अच्छा", "बिल्कुल",
                 "बताइए", "समझ गया", "समझ गई", "समझा ही है", "samajh gaya", "samajh gayi",
                 "यस", "येस", "सही है"],
    # Narrowed 2026-08-13 -- bare "kaun"/"कौन" (who) collided with "कौन से"
    # (which), a completely unrelated interrogative. Confirmed live: "कौन से
    # फर्नीचर पे ऑफर है?" (which furniture is the offer on?) matched this and
    # got answered with a generic pitch continuation instead of the actual
    # question. Replaced with phrasings that specifically mean "who is this",
    # not the bare word "who" that "which"/"who else" etc. also contain.
    # Also added English-phonetic Devanagari forms ("हू यू आर" etc.) -- five
    # separate real customers asked for the agent's name/identity in English
    # this week and matched nothing at all, same class of gap as the
    # not_interested English fix earlier this session (see ask_name below
    # for the matching "what's your name" coverage).
    "confusion_who": ["kaun bol rahe", "kaun bol rahi", "kon ho", "pahchaan nahi",
                      "kaun sa number", "kaise mila", "number kahan se", "kahan se",
                      "aap kaun", "kaun hai yeh", "कौन बोल रहे", "कौन बोल रही",
                      "कहाँ से", "पहचान नहीं", "कौन सा नंबर", "आप कौन", "कौन है यह",
                      "यह कौन", "हू यू आर", "व्हाई यू आर कॉलिंग", "why you calling",
                      "who is this", "who is calling"],
    # Bare "kya"/"क्या" (just "what") used to be a keyword here -- it's the single
    # most common Hindi question word, so virtually any real question ("EMI hai
    # kya", "discount milega kya") false-matched "please repeat that" instead of
    # the actual question. Confirmed via a 291-case regression audit (2026-07-15,
    # test_reply_state_regression.py) -- ~62% of all failures traced to this one
    # keyword. Narrowed to actual "say that again" phrases only, kept symmetric
    # across Hinglish/Devanagari (the old list had asymmetric coverage -- e.g.
    # "dobara bolo" existed only in Hinglish, "suna nahi" only in Hinglish).
    # English added 2026-08-13 (second pass, English-coverage sweep) --
    # "come again"/"pardon" are unambiguous repeat-requests in English with
    # no collision risk in this domain, same reasoning as the Hindi/Hinglish
    # phrases already here.
    "repeat": ["kya bola", "phir se bolo", "samjha nahi", "dobara bolo", "suna nahi",
               "repeat karo", "say that again", "come again", "what did you say",
               "please repeat", "pardon",
               "फिर से बोलो", "क्या बोला", "समझा नहीं", "दोबारा बोलो",
               "सुना नहीं", "रिपीट करो"],
    "privacy_concern": ["number kaise mila", "data kahan se", "mera number kyun hai", "spam", "privacy",
                       "how did you get my number", "who gave you my number",
                       "नंबर कैसे मिला", "डेटा कहां से", "मेरा नंबर क्यों है", "स्पैम", "प्राइवेसी"],
    "offer_clarify": ["kya offer", "kaise hoga", "explain karo", "samjhao",
                      "exchange kaise", "purana furniture", "kya matlab",
                      "detail batao", "aur batao", "एक्सचेंज कैसे", "exchange kaisa",
                      "explain", "tell me more", "more details", "more information",
                      "what's the offer", "what is the offer",
                      "क्या ऑफर", "कैसे होगा", "एक्सप्लेन करो", "समझाओ",
                      "पुराना फर्नीचर", "क्या मतलब", "डिटेल बताओ", "और बताओ", "एक्सचेंज कैसा"],
    # "भरोसा नहीं"/"bharosa nahi" and "यकीन नहीं"/"yakeen nahi" added
    # 2026-08-13 -- both are more common, everyday Hindi words for
    # "trust"/"belief" than "vishwas" (which is more formal/literary), and
    # neither had any coverage. "trust nahi"/"don't trust" (English) added
    # requiring the negation, not bare "trust" alone -- "I trust you" bare
    # would be the opposite signal.
    "trust_issue": ["fake hai", "jhooth", "fraud", "scam", "sach mein",
                    "pakka", "sach hai kya", "vishwas nahi",
                    "bharosa nahi", "yakeen nahi", "trust nahi", "don't trust",
                    "is this real", "is this genuine", "sounds fake", "is this legit",
                    "फेक है", "झूठ", "फ्रॉड", "स्कैम", "सच में",
                    "पक्का", "सच है क्या", "विश्वास नहीं",
                    "भरोसा नहीं", "यकीन नहीं"],
    "buying_signal": ["kitna time hai", "kab tak hai", "interested hoon",
                      "showroom kab", "aana chahta", "visit karna", "kab aaye",
                      "i am interested", "when can i visit", "how much time do i have",
                      "कितना टाइम है", "कब तक है", "इंटरेस्टेड हूं",
                      "शोरूम कब", "आना चाहता", "विजिट करना", "कब आएं"],
    # Narrowed 2026-08-13 -- this used to share bare affirmation words
    # ("haan"/"ji"/"achha"/"theek hai"/"bilkul"/"sure"/"ok"...) with the
    # "positive" list above. Those words carry no WhatsApp-specific meaning
    # at all -- detect_intents() is state-blind, so the exact same "haan"
    # got credited as an explicit "yes I saw the WhatsApp" (+40, the single
    # biggest scoring signal) even in turns that never touched WhatsApp
    # (GREETING, PRESENT_OFFER, APPOINTMENT). Confirmed live 2026-08-13 on a
    # real call: "aur uske liye achha hai" scored a full wa_ok hit off
    # "achha" alone, in APPOINTMENT state, nowhere near a WA-check question.
    # This exact overlap was already flagged with ground-truth evidence back
    # on 2026-08-02 (see _is_filler_continuer's docstring above -- "two of
    # which blocked the caller's number") but only the pure-filler ("hmm")
    # case was carved out at the time; this closes the rest of the gap.
    # Left with only phrases that unambiguously reference the act of
    # sending/receiving something -- a bare "haan" now falls back to
    # wa_sent's own +20 credit (supabase_calling.py) instead of the full
    # +40, which is the right confidence level for an unverifiable bare yes.
    "wa_ok": ["bhejo", "send karo", "bhej do", "kar do", "theek hai bhej do",
              "ok send", "haan bhejo", "de do", "kar lo",
              "please send", "yes send it", "send it",
              # "सेंड कीजिए" -- polite/formal conjugation of "send karo" above.
              # Confirmed live 2026-08-13: "pehle mujhe detail send kijiye"
              # matched nothing, despite being an explicit, unambiguous
              # request to send the WhatsApp.
              "send kijiye", "सेंड कीजिए", "bhej dijiye", "भेज दीजिए"],
    "wa_no_whatsapp": ["whatsapp nahi hai", "use nahi karta", "no whatsapp",
                      "व्हाट्सएप नहीं है", "यूज़ नहीं करता", "नो व्हाट्सएप"],
    "wa_diff_number": ["alag number", "doosra number", "different number",
                      "अलग नंबर", "दूसरा नंबर", "डिफरेंट नंबर"],
    "wa_prefers": ["whatsapp pe hi", "call nahi", "message karo",
                  "message me instead", "text me instead", "whatsapp only", "just whatsapp",
                  "व्हाट्सएप पे ही", "कॉल नहीं", "मैसेज करो"],
    # "busy hu"/"busy hun" spelling variants added 2026-08-13 -- token-
    # boundary matching means "busy hu" doesn't match the keyword "busy
    # hoon" (different final token), and "hu"/"hun" are extremely common
    # casual-Hinglish spellings of "hoon" in STT output.
    # "not now" added same day (English pass) -- deliberately NOT added to
    # not_interested (see that list's comment) because it's a deferral, not
    # a decline; this is exactly where it belongs.
    "busy": ["busy hoon", "busy hu", "busy hun", "abhi nahi", "kaam mein hoon", "baad mein", "driving",
             "meeting mein", "abhi nahi kar sakta",
             "i am busy", "i'm busy", "not now", "can't talk", "cant talk",
             "in a meeting", "call me later", "call later",
             "बिज़ी हूं", "अभी नहीं", "काम में हूं", "बाद में", "ड्राइविंग",
             "मीटिंग में", "अभी नहीं कर सकता"],
    "not_interested": ["interested nahi", "nahi chahiye", "rehne do",
                       "hata do mera number", "band karo", "mat bhejo",
                       "nahi sunna", "nahi sunni", "mat batao",
                       "इंटरेस्टेड नहीं", "नहीं चाहिए", "रहने दो",
                       "हटा दो मेरा नंबर", "बंद करो", "मत भेजो",
                       # "सुनना/सुननी" (to listen) phrasing — a very natural way to
                       # say "don't want to hear it" that the "chahiye/bhejo"
                       # keywords above never covered (confirmed live: 3 explicit
                       # rejections in one call, none detected, call proceeded
                       # through the full offer script regardless).
                       "नहीं सुनना", "नहीं सुननी", "मत बताओ",
                       # Plain-English soft declines and their Devanagari phonetic
                       # transliterations (Hindi STT renders spoken English
                       # phonetically, not as Latin text) — every keyword above is
                       # Hinglish/Devanagari-only, so a customer declining in bare
                       # English fell through completely undetected. Confirmed live
                       # 2026-07-17: "नो थैंक्स राइट नाउ वी आर नॉट इन मूड" ("no
                       # thanks right now we are not in mood") on call 9911381351
                       # matched zero keywords, agent proceeded straight into the
                       # sales pitch, lead got called 7 more times before an
                       # unrelated attempt-cap (not this detection) finally stopped
                       # it. "not now"/"maybe later" deliberately NOT added here —
                       # those are deferrals, not declines, and already have a home
                       # in "busy" ("abhi nahi") / "sochna_hai" ("baad mein"-style
                       # phrasing) rather than a hard decline signal.
                       #
                       # "not interested" (bare) carries the same partial-preference
                       # risk as the existing "interested nahi" above always has —
                       # "not interested in the sofa, but the bed looks nice" would
                       # token-match and hard-decline the whole call, same as the
                       # Hindi equivalent would today. Checked all 970 call_summaries
                       # transcripts on file for this shape (any of these keywords,
                       # not just this one) — zero real occurrences, qualified or
                       # otherwise. Added for consistency with the Hindi keyword's
                       # existing accepted risk, not because it's risk-free — revisit
                       # if a real qualified-decline transcript surfaces.
                       "no thanks", "no thank you", "not interested", "not in the mood",
                       "नो थैंक्स", "नो थेंक्स", "नो थैंक", "नो थैंक यू", "नो थैंकयू",
                       "नॉट इंटरेस्टेड", "नाट इंटरेस्टेड",
                       "नॉट इन मूड", "नॉट इन द मूड", "नाट इन मूड",
                       # "interestiv" — garbled STT rendering of "interested" (STT
                       # sometimes drops/mishears the final syllable on English
                       # loanwords). Confirmed live 2026-07-17: "नहीं मैम, मैं
                       # इंटरेस्टिव नहीं हूं" (call 919868239010, 2026-07-12) matched
                       # zero keywords despite being an unambiguous decline — found
                       # incidentally during the false-positive spot-check for the
                       # additions above, not the original audit. Narrow, exact-
                       # phrase addition mirroring "interested nahi"/"इंटरेस्टेड नहीं"
                       # above — same "nahi" pairing, just the garbled spelling.
                       "interestiv nahi", "इंटरेस्टिव नहीं",
                       # "ज़रूरत नहीं" / "zaroorat nahi" ("[I] don't need [it]") —
                       # confirmed live 2026-08-11 (hot_warm_leads_conversations.docx
                       # audit): "abhi mere paas nahi hai, zaroorat nahi hai abhi
                       # mujhe... thank you" matched zero keywords despite being an
                       # explicit decline, so the agent replied "sorry, didn't catch
                       # that" to a customer who had just declined, and the lead was
                       # still scored warm on the next call.
                       "zaroorat nahi", "ज़रूरत नहीं", "जरूरत नहीं",
                       # "आवश्यकता नहीं" -- formal-register synonym of "zaroorat
                       # nahi" above (same meaning, "not needed"); "नहीं जानना" --
                       # "don't want to know". Both confirmed live 2026-08-13,
                       # real customer utterances that matched nothing.
                       "aavashyakta nahi", "आवश्यकता नहीं", "nahi jaanna", "नहीं जानना"],
    # Bare "expensive" added 2026-08-13 -- ironically absent from the intent
    # named after it; only its synonym "costly" was covered.
    "expensive": ["mahenga hai", "mahenge hain", "mahenga", "mahenge", "bahut zyada",
                 "budget nahi", "afford nahi", "costly", "rate zyada", "expensive",
                 "can't afford it", "cant afford it", "out of budget", "too costly",
                 "महंगा है", "महंगे हैं", "महंगा", "महंगे", "बहुत ज़्यादा", "बहुत रेट",
                 "रेट ज़्यादा", "बजट नहीं", "अफोर्ड नहीं", "कॉस्टली", "एक्सपेंसिव"],
    "online_cheaper": ["online sasta", "amazon pe", "flipkart pe", "online better",
                      "cheaper online", "better deals online", "found it cheaper",
                      "ऑनलाइन सस्ता", "अमेज़न पे", "फ्लिपकार्ट पे", "ऑनलाइन बेटर"],
    "sochna_hai": ["sochna hai", "soch ke batata hoon", "wife se puchna",
                   "family se puchna", "decide nahi kiya",
                   "let me think", "need to think", "will think about it", "thinking about it",
                   "सोचना है", "सोच के बताता हूं", "वाइफ से पूछना",
                   "फैमिली से पूछना", "डिसाइड नहीं किया"],
    "escalate": ["manager se baat", "senior se milao", "complaint karna",
                "manager", "supervisor", "speak to someone else", "complaint",
                "मैनेजर से बात", "सीनियर से मिलाओ", "कंप्लेंट करना"],
    "dnc": ["dobara call mat karna", "number delete karo", "DNC", "harassment",
            "complaint karunga", "call mat karo kabhi", "band karo yeh call",
            "दोबारा कॉल मत करना", "नंबर डिलीट करो", "हैरेसमेंट",
            "कंप्लेंट करूंगा", "कॉल मत करो कभी", "बंद करो यह कॉल",
            # Confirmed live: "दोबारा कॉल ना करें" (customer's actual wording on
            # call 3cf6a87b) uses "ना करें" negation — a different conjugation
            # from "मत करना" above — and was completely undetected, so the
            # agent kept pursuing a showroom date after an explicit opt-out.
            # Added alongside _is_explicit_optout()'s pattern check (any
            # negation word + any call-word within a 3-token window) so
            # phrasing variants beyond this exact list are also caught.
            "dobara call na karo", "dobara call na karein", "phir se call na karo",
            "aage se call na karo", "call na karo", "call mat karna",
            "phone mat karna", "bilkul interested nahi", "list se hata do",
            "list se nikal do",
            "दोबारा कॉल ना करो", "दोबारा कॉल ना करें", "फिर से कॉल ना करो",
            "आगे से कॉल ना करो", "कॉल ना करो", "कॉल मत करना",
            "फोन मत करना", "बिल्कुल इंटरेस्टेड नहीं", "इंटरेस्टेड नहीं हूं बिल्कुल",
            "लिस्ट से हटा दो", "लिस्ट से निकाल दो",
            # Added 2026-07-15 (regression audit): "hata do"/"nikal do" conjugation
            # variants, and explicit "stop calling"/"band karo" phrasings that the
            # _is_explicit_optout() window can't catch on their own -- "band"/"बंद"
            # is deliberately NOT a generic negation word there (false-positive risk
            # on unrelated "call disconnected" mentions), so these stay exact phrases.
            "list se hata dena", "list se nikal dena", "लिस्ट से हटा देना", "लिस्ट से निकाल देना",
            "call karna band karo", "phone karna band karo",
            "कॉल करना बंद करो", "फोन करना बंद करो",
            "stop calling", "stop calling me", "please stop calling",
            "stop calling me please", "stop phoning me",
            # English equivalent of "number delete karo"/"list se hata do" above —
            # no real transcript evidence of this specific gap (unlike the
            # not_interested additions above, which trace to a confirmed live
            # miss), added purely for consistency with the existing Hindi/Hinglish
            # phrase already covered. No Devanagari transliteration added for this
            # one — unlike "call"/"phone"/"interested", "remove"/"delete" aren't
            # established loanwords in this transcript corpus, so guessing at STT
            # spelling variants isn't grounded in anything real. Revisit if evidence
            # surfaces.
            "remove my number", "delete my number",
            # "mera number hata do" / "dobara mat karna" — opt-out phrasings that
            # drop the object noun ("call") the rest of this list and the
            # _is_explicit_optout() proximity window both rely on, so neither
            # caught them. Added as exact phrases rather than loosening the
            # proximity window (which would risk false-positiving on unrelated
            # "mat karna" utterances that have nothing to do with calling).
            "mera number hata do", "number hata do", "mera number nikal do",
            "dobara mat karna", "phir se mat karna", "aage se mat karna",
            "मेरा नंबर हटा दो", "नंबर हटा दो", "मेरा नंबर निकाल दो",
            "दोबारा मत करना", "फिर से मत करना", "आगे से मत करना"],
    "personal_question": ["tumhara naam", "kaun ho tum", "real hai ya bot",
                          "robot ho", "AI ho", "human ho",
                          "are you a bot", "are you real", "are you human", "is this a bot",
                          "तुम्हारा नाम", "कौन हो तुम", "रियल है या बॉट",
                          "रोबोट हो", "एआई हो", "ह्यूमन हो"],
    # Three added 2026-08-13 -- all confirmed live this week as real customer
    # questions that matched nothing at all anywhere in this file.
    # "दाम"/"daam" (the native Hindi word for price/rate) and "kitne ka
    # hai"/"कितने का है" ("how much is it" -- one of the single most common
    # everyday ways to ask a price, in any language) added 2026-08-13 --
    # neither had any coverage; this list only had English loanwords
    # (price/rate) and one Hinglish phrase (kitna paisa). Bare "price"
    # (English) added too; bare "cost" deliberately NOT added -- it
    # collides with "no cost emi", a payment-method phrase, not a price
    # question.
    "ask_price_range": ["starting range", "starting price", "price kya hai",
                        "rate kya hai", "kitne se shuru", "shuru kitne se",
                        "kitna paisa", "daam kya hai", "kitne ka hai", "kitne ki hai",
                        "kitni ka hai", "price",
                        "how much is it", "how much does it cost", "what's the price",
                        "what is the price",
                        "स्टार्टिंग रेंज", "प्राइस क्या है",
                        "रेट क्या है", "कितने से शुरू", "शुरू कितने से", "कितना पैसा",
                        "दाम क्या है", "कितने का है", "कितने की है", "कितनी का है", "प्राइस"],
    "ask_offer_scope": ["kis kis cheez pe", "sab furniture pe", "sari furniture pe",
                        "kaunse product", "sabhi furniture", "kaun se furniture",
                        "which products", "what all is included", "what items",
                        "which items", "what all do you have",
                        "किस-किस चीज पे", "सब फर्नीचर पे", "सारी फर्नीचर पे",
                        "कौनसे प्रोडक्ट", "सभी फर्नीचर पर", "सारी फर्नीचर पर",
                        # "कौन से फर्नीचर पे ऑफर है" -- the exact real utterance
                        # that started this whole audit (2026-08-13). Deliberately
                        # NOT just "कौन से" alone -- that's what caused the
                        # confusion_who false-positive this replaces; kept scoped
                        # to "which furniture/product" specifically.
                        "कौन से फर्नीचर", "कौन सा फर्नीचर"],
    "already_purchased": ["abhi liya hai", "already le liya", "naya furniture liya hai",
                          "abhi kharida", "already kharid liya", "abhi le chuke",
                          "i already bought", "i already have one", "already purchased",
                          "already own one", "already bought it",
                          "अभी लिया है", "पहले ही ले लिया", "नया फर्नीचर लिया है",
                          "अभी खरीदा", "पहले से ले चुके", "अभी ले चुके"],
}
