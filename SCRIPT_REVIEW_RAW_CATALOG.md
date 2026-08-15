# Script Review — Raw Catalog

Two lists, kept deliberately separate and unconnected, exactly as requested:
1. **Every customer-reply pattern the system currently recognizes**, grouped by category (this is the literal keyword list from the code — not a guess, this is what's actually live).
2. **Every line the agent currently says**, grouped by campaign/flow.

Nothing here is mapped to anything else. Add to either list directly — this file is meant to be edited.

---

## PART 1 — CUSTOMER REPLIES (by category)

Each category name is the internal label the system uses; the phrases under it are the actual patterns currently recognized as meaning that thing (Hindi, Hinglish, Devanagari-phonetic English, and plain English, as they exist in the code today).

### ask_location
kahan hai, showroom kahan, location kya, address batao, kaha hai showroom, kahan par hai, kaunsi jagah, pata batao, pata kya hai, aapka pata, store ka pata, address, location, nazdik, nearest, where is your showroom, where is your store, where are you located, कहां है, कहाँ है, शोरूम कहां, लोकेशन क्या, एड्रेस बताओ, कहां पर है, कहाँ पर है, स्टोर कहां, स्टोर कहाँ, कौनसी जगह, दुकान कहां, shop kahan, store kahan, showroom kaha, पता बताओ, पता क्या है, आपका पता, स्टोर का पता, वेयर इज योर शोरूम, वेयर इज योर स्टोर, एड्रेस, लोकेशन, नज़दीक, नज़दीकी

### ask_name
tumhara naam, aapka naam, naam kya hai, kaun bol rahe ho, your name, share your name, give me your name, know your name, तुम्हारा नाम, आपका नाम, नाम क्या है, कौन बोल रहे हो, कौन बोल रही हो, योर नेम, शेयर योर नेम, गिव मी योर नेम, नो योर नेम

### ask_timings
time kya, kab khulta, timing kya hai, kitne baje khulta, band hota, band hoti, kab tak khula, what time, when do you open, when do you close, opening hours, closing time, working hours, office hours, टाइम क्या, कब खुलता, टाइमिंग क्या है, कितने बजे खुलता, बंद होता, बंद होती, कब तक खुला

### ask_valuation
valuation kaise, purana furniture kaise, kaise pickup, value kaise milegi, kaise calculate, kaise lenge purana, how much will i get, buyback value, trade in value, resale value, वैल्यूएशन कैसे, पुराना फर्नीचर कैसे, कैसे पिकअप, वैल्यू कैसे मिलेगी, कैसे कैलकुलेट, कैसे लेंगे पुराना

### ask_delivery
delivery kab, kab milega, kitne din mein, delivery kaise, when will it arrive, delivery time, how many days for delivery, how long for delivery, डिलीवरी कब, कब मिलेगा, कितने दिन में, डिलीवरी कैसे

### appointment_confirm
kal, parso, monday, tuesday, wednesday, thursday, friday, saturday, sunday, subah, shaam, raat, baje, tareek, date, theek hai aa jaunga, main aaunga, book kardo, haan book karo, confirm hai, ji confirm, कल, परसों, सोमवार, मंगलवार, बुधवार, गुरुवार, शुक्रवार, शनिवार, रविवार, सुबह, शाम, रात, बजे, तारीख, ठीक है आ जाऊंगा, मैं आऊंगा, बुक कर दो, हां बुक करो, कन्फर्म है, जी कन्फर्म, सैटरडे, सैंडे, संडे, मंडे, ट्यूज़डे, ट्यूजडे, वेडनेसडे, थर्सडे, फ्राइडे, वीकेंड, weekend, बैटर डे, बैटरडे, सैटर डे, सन डे, मन डे, ट्यूज डे, वेड नेस डे, थर्स डे, फ्राई डे, जनवरी, फरवरी, मार्च, अप्रैल, मई, जून, जुलाई, अगस्त, सितंबर, अक्टूबर, नवंबर, दिसंबर, january, february, march, april, june, july, august, september, october, november, december, agle hafte, agle mahine, अगले हफ्ते, अगले महीने, is hafte, इस हफ्ते

### positive
haan, han, haa, ha, theek hai, batao, bolo, sun raha hoon, okay, ok, sure, bilkul, achha, bataiye, sunenge, ji, yes, yeah, yep, yup, correct, sahi hai, जी, हाँ, हां, ठीक है, बताओ, बोलो, अच्छा, बिल्कुल, बताइए, समझ गया, समझ गई, समझा ही है, samajh gaya, samajh gayi, यस, येस, सही है

### confusion_who
kaun bol rahe, kaun bol rahi, kon ho, pahchaan nahi, kaun sa number, kaise mila, number kahan se, kahan se, aap kaun, kaun hai yeh, कौन बोल रहे, कौन बोल रही, कहाँ से, पहचान नहीं, कौन सा नंबर, आप कौन, कौन है यह, यह कौन, हू यू आर, व्हाई यू आर कॉलिंग, why you calling, who is this, who is calling

### repeat
kya bola, phir se bolo, samjha nahi, dobara bolo, suna nahi, repeat karo, say that again, come again, what did you say, please repeat, pardon, फिर से बोलो, क्या बोला, समझा नहीं, दोबारा बोलो, सुना नहीं, रिपीट करो

### privacy_concern
number kaise mila, data kahan se, mera number kyun hai, spam, privacy, how did you get my number, who gave you my number, नंबर कैसे मिला, डेटा कहां से, मेरा नंबर क्यों है, स्पैम, प्राइवेसी

### offer_clarify
kya offer, kaise hoga, explain karo, samjhao, exchange kaise, purana furniture, kya matlab, detail batao, aur batao, एक्सचेंज कैसे, exchange kaisa, explain, tell me more, more details, more information, what's the offer, what is the offer, क्या ऑफर, कैसे होगा, एक्सप्लेन करो, समझाओ, पुराना फर्नीचर, क्या मतलब, डिटेल बताओ, और बताओ, एक्सचेंज कैसा

### trust_issue
fake hai, jhooth, fraud, scam, sach mein, pakka, sach hai kya, vishwas nahi, bharosa nahi, yakeen nahi, trust nahi, don't trust, is this real, is this genuine, sounds fake, is this legit, फेक है, झूठ, फ्रॉड, स्कैम, सच में, पक्का, सच है क्या, विश्वास नहीं, भरोसा नहीं, यकीन नहीं

### buying_signal
kitna time hai, kab tak hai, interested hoon, showroom kab, aana chahta, visit karna, kab aaye, i am interested, when can i visit, how much time do i have, कितना टाइम है, कब तक है, इंटरेस्टेड हूं, शोरूम कब, आना चाहता, विजिट करना, कब आएं

### wa_ok
bhejo, send karo, bhej do, kar do, theek hai bhej do, ok send, haan bhejo, de do, kar lo, please send, yes send it, send it, send kijiye, सेंड कीजिए, bhej dijiye, भेज दीजिए

### wa_no_whatsapp
whatsapp nahi hai, use nahi karta, no whatsapp, व्हाट्सएप नहीं है, यूज़ नहीं करता, नो व्हाट्सएप

### wa_diff_number
alag number, doosra number, different number, अलग नंबर, दूसरा नंबर, डिफरेंट नंबर

### wa_prefers
whatsapp pe hi, call nahi, message karo, message me instead, text me instead, whatsapp only, just whatsapp, व्हाट्सएप पे ही, कॉल नहीं, मैसेज करो

### busy
busy hoon, busy hu, busy hun, abhi nahi, kaam mein hoon, baad mein, driving, meeting mein, abhi nahi kar sakta, i am busy, i'm busy, not now, can't talk, cant talk, in a meeting, call me later, call later, बिज़ी हूं, अभी नहीं, काम में हूं, बाद में, ड्राइविंग, मीटिंग में, अभी नहीं कर सकता

### not_interested
interested nahi, nahi chahiye, rehne do, hata do mera number, band karo, mat bhejo, nahi sunna, nahi sunni, mat batao, इंटरेस्टेड नहीं, नहीं चाहिए, रहने दो, हटा दो मेरा नंबर, बंद करो, मत भेजो, नहीं सुनना, नहीं सुननी, मत बताओ, no thanks, no thank you, not interested, not in the mood, नो थैंक्स, नो थेंक्स, नो थैंक, नो थैंक यू, नो थैंकयू, नॉट इंटरेस्टेड, नाट इंटरेस्टेड, नॉट इन मूड, नॉट इन द मूड, नाट इन मूड, interestiv nahi, इंटरेस्टिव नहीं, zaroorat nahi, ज़रूरत नहीं, जरूरत नहीं, aavashyakta nahi, आवश्यकता नहीं, nahi jaanna, नहीं जानना

### expensive
mahenga hai, mahenge hain, mahenga, mahenge, bahut zyada, budget nahi, afford nahi, costly, rate zyada, expensive, can't afford it, cant afford it, out of budget, too costly, महंगा है, महंगे हैं, महंगा, महंगे, बहुत ज़्यादा, बहुत रेट, रेट ज़्यादा, बजट नहीं, अफोर्ड नहीं, कॉस्टली, एक्सपेंसिव

### online_cheaper
online sasta, amazon pe, flipkart pe, online better, cheaper online, better deals online, found it cheaper, ऑनलाइन सस्ता, अमेज़न पे, फ्लिपकार्ट पे, ऑनलाइन बेटर

### sochna_hai
sochna hai, soch ke batata hoon, wife se puchna, family se puchna, decide nahi kiya, let me think, need to think, will think about it, thinking about it, सोचना है, सोच के बताता हूं, वाइफ से पूछना, फैमिली से पूछना, डिसाइड नहीं किया

### escalate
manager se baat, senior se milao, complaint karna, manager, supervisor, speak to someone else, complaint, मैनेजर से बात, सीनियर से मिलाओ, कंप्लेंट करना

### dnc
dobara call mat karna, number delete karo, DNC, harassment, complaint karunga, call mat karo kabhi, band karo yeh call, दोबारा कॉल मत करना, नंबर डिलीट करो, हैरेसमेंट, कंप्लेंट करूंगा, कॉल मत करो कभी, बंद करो यह कॉल, dobara call na karo, dobara call na karein, phir se call na karo, aage se call na karo, call na karo, call mat karna, phone mat karna, bilkul interested nahi, list se hata do, list se nikal do, दोबारा कॉल ना करो, दोबारा कॉल ना करें, फिर से कॉल ना करो, आगे से कॉल ना करो, कॉल ना करो, कॉल मत करना, फोन मत करना, बिल्कुल इंटरेस्टेड नहीं, इंटरेस्टेड नहीं हूं बिल्कुल, लिस्ट से हटा दो, लिस्ट से निकाल दो, list se hata dena, list se nikal dena, लिस्ट से हटा देना, लिस्ट से निकाल देना, call karna band karo, phone karna band karo, कॉल करना बंद करो, फोन करना बंद करो, stop calling, stop calling me, please stop calling, stop calling me please, stop phoning me, remove my number, delete my number, mera number hata do, number hata do, mera number nikal do, dobara mat karna, phir se mat karna, aage se mat karna, मेरा नंबर हटा दो, नंबर हटा दो, मेरा नंबर निकाल दो, दोबारा मत करना, फिर से मत करना, आगे से मत करना

### personal_question
tumhara naam, kaun ho tum, real hai ya bot, robot ho, AI ho, human ho, are you a bot, are you real, are you human, is this a bot, तुम्हारा नाम, कौन हो तुम, रियल है या बॉट, रोबोट हो, एआई हो, ह्यूमन हो

### ask_price_range
starting range, starting price, price kya hai, rate kya hai, kitne se shuru, shuru kitne se, kitna paisa, daam kya hai, kitne ka hai, kitne ki hai, kitni ka hai, price, how much is it, how much does it cost, what's the price, what is the price, स्टार्टिंग रेंज, प्राइस क्या है, रेट क्या है, कितने से शुरू, शुरू कितने से, कितना पैसा, दाम क्या है, कितने का है, कितने की है, कितनी का है, प्राइस

### ask_offer_scope
kis kis cheez pe, sab furniture pe, sari furniture pe, kaunse product, sabhi furniture, kaun se furniture, which products, what all is included, what items, which items, what all do you have, किस-किस चीज पे, सब फर्नीचर पे, सारी फर्नीचर पे, कौनसे प्रोडक्ट, सभी फर्नीचर पर, सारी फर्नीचर पर, कौन से फर्नीचर, कौन सा फर्नीचर

### already_purchased
abhi liya hai, already le liya, naya furniture liya hai, abhi kharida, already kharid liya, abhi le chuke, i already bought, i already have one, already purchased, already own one, already bought it, अभी लिया है, पहले ही ले लिया, नया फर्नीचर लिया है, अभी खरीदा, पहले से ले चुके, अभी ले चुके

### (also recognized, handled separately in code, not as a plain keyword list)
- **Filler / "still there?" check-ins** — customer says only: hmm, hmmm, हम्म, हम्म्म, hello, हेलो, ye, ये, yeh, यह (treated as "keep going," not a real question, only when the ENTIRE utterance is just one of these words)
- **Low-content fragments** — customer says only connector words with no real content: aur, और, ye, ये, yeh, यह, woh, वो, toh, तो, bhi, भी, hi, ही, ki, कि, jo, जो, tha, था, thi, थी, the, थे, hai, है (also only when the entire utterance is made of these — treated as "didn't catch that," never sent to the AI for a made-up answer)
- **IVR / voicemail fragments** — carrier hold-message phrases (recording, hang up, please stay on the line, leave a message, etc.) — call is treated as possibly hitting an answering machine, not a real person

---

## PART 1 ADDENDUM — Missing Customer-Reply Categories

Cross-checked against the live keyword list and against every Part 2 line — verified none of these are already covered anywhere in the code (grepped for overlap before adding). All new material, grouped by why the gap matters.

### A. Gaps that break the call's basic premise

**wrong_number**
galat number hai, aapko wrong number mila hai, main woh nahi hoon jise aap dhoondh rahe ho, is number pe koi aur rehta hai, wrong number, galat number, aapne galat number dial kiya, yeh mera number nahi hai, main [naam] nahi hoon, यह नंबर गलत है, गलत नंबर, आपको गलत नंबर मिला है, मैं वो नहीं हूं जिसे आप ढूंढ रहे हो, यह मेरा नंबर नहीं है, रॉन्ग नंबर

**not_my_customer** — denies the "aap hamare purane customer hain" claim every opener leans on. Nothing catches this today, so the bot keeps asserting a relationship the customer is actively rejecting.
main aapka customer nahi hoon, maine kabhi kuch nahi khareeda, maine kabhi order nahi kiya, mera koi record nahi hona chahiye, main pehli baar sun raha hoon, kaunsa purana customer, main toh naya hoon, मैं आपका ग्राहक नहीं हूं, मैंने कभी कुछ नहीं खरीदा, मैंने कभी ऑर्डर नहीं किया, कौनसा पुराना कस्टमर, मैं पहली बार सुन रहा हूं

**person_unavailable** — someone other than the lead picks up.
woh ghar par nahi hain, unka number band hai, wo abhi available nahi hain, main unki taraf se bol raha hoon, unhe baad mein call karo, yeh unka number tha ab mera hai, वो घर पर नहीं हैं, वो अभी उपलब्ध नहीं हैं, मैं उनकी तरफ से बोल रहा हूं, उन्हें बाद में कॉल करो, यह उनका नंबर था अब मेरा है

### B. Call-fatigue responses softer than DNC
Annoyance short of "stop calling me forever" — currently misfires into `not_interested`/`dnc` (overreacts) or nothing at all.

**already_called**
aap pehle bhi call kar chuke ho, maine pehle bata diya tha, kitni baar call karoge, dobara kyun call kiya, already bata chuka hoon, roz call karte ho, बार-बार कॉल क्यों करते हो, आप पहले भी कॉल कर चुके हो, मैंने पहले बता दिया था, कितनी बार कॉल करोगे, रोज़ कॉल करते हो

**callback_later** — a specific reschedule-the-call request, distinct from `busy` (which has no time-of-day capture today).
shaam ko call karna, kal subah call karo, thodi der baad call karo, evening mein try karna, 2 ghante baad call karo, weekend pe call karna, शाम को कॉल करना, कल सुबह कॉल करो, थोड़ी देर बाद कॉल करो, 2 घंटे बाद कॉल करो

### C. Language handling

**language_preference** — no category exists for a customer asking to switch languages, a very common India-outbound moment, especially with Gurgaon/Delhi/Noida/Faridabad catchment (Punjabi- and English-first speakers).
English mein baat karo, hindi mein baat karo, mujhe hindi samajh nahi aati, angrezi mein bolo, please speak in english, can you speak english, mujhe angrezi nahi aati, punjabi mein baat karo, hindi thik se nahi aati, अंग्रेज़ी में बोलो, हिंदी में बात करो, मुझे हिंदी समझ नहीं आती, पंजाबी में बात करो

### D. Bare / ambiguous responses

**bare_negative** — `not_interested` only matches full phrases today ("interested nahi", "nahi chahiye"). A standalone "nahi"/"na"/"नहीं"/"ना" isn't caught by anything — falls into the low-content-fragment bucket (treated as "didn't catch that," which is wrong) or gets missed entirely. Recommend routing to a soft clarifying prompt rather than straight into not_interested/dnc — bare "no" is genuinely ambiguous (no to what?).
nahi, na, नहीं, ना, नही

**uncertain** — distinct from `sochna_hai` (deliberate "let me think it over"); this is a non-committal "I don't know," often a stalling reflex.
pata nahi, shayad, dekhta hoon, abhi nahi bol sakta, maybe, may be, not sure, confirm nahi hai, पता नहीं, शायद, देखता हूं, अभी नहीं बोल सकता, कन्फर्म नहीं है

### E. Product / commercial questions with no home right now
Every one of these is a completely normal furniture-purchase question the current 27 categories don't cover — all currently fall through to a generic/made-up LLM answer.

**ask_emi**
EMI hai kya, installment mein le sakte hain, no cost emi, loan mil sakta hai kya, financing available hai, credit card se emi ho sakta hai, इएमआई है क्या, किश्तों में ले सकते हैं, लोन मिल सकता है क्या, फाइनेंसिंग अवेलेबल है क्या

**ask_payment_method**
cash accept karte ho, card se le sakte hain, upi chalega, online payment hota hai kya, cheque le lete ho, कैश लेते हो क्या, कार्ड से ले सकते हैं, यूपीआई चलेगा क्या, ऑनलाइन पेमेंट होता है क्या

**ask_warranty**
warranty kitne saal ki hai, guarantee hai kya, kharab hone par kya hoga, replacement milega kya, वारंटी कितने साल की है, गारंटी है क्या, खराब होने पर क्या होगा

**ask_delivery_charge** — separate from the existing `ask_delivery` (purely "kab milega"/timing); this is cost and service scope.
delivery charge kitna hai, free delivery hai kya, installation charge alag hai kya, ghar tak laoge kya, assembly bhi karte ho, डिलीवरी चार्ज कितना है, फ्री डिलीवरी है क्या, इंस्टॉलेशन चार्ज अलग है क्या

**ask_return_policy**
return kar sakte hain kya, agar pasand nahi aaya toh, exchange ho sakta hai naye wale ka bhi, रिटर्न कर सकते हैं क्या, अगर पसंद नहीं आया तो

**ask_bargain** — a negotiation attempt, different from `expensive` ("I can't afford this" resignation); this is "give me a better number."
aur discount milega kya, thoda kam karo, final price kya hai, kam nahi hoga kya, aur kam karo, और डिस्काउंट मिलेगा क्या, थोड़ा कम करो, फाइनल प्राइस क्या है, और कम करो

**ask_invoice_gst**
bill milega kya, gst invoice milega, pakka bill doge, बिल मिलेगा क्या, जीएसटी इनवॉइस मिलेगा क्या, पक्का बिल दोगे

**ask_product_quality**
material kya hai, wood hai ya plastic, quality kaisi hai, brand kaunsi hai, मटेरियल क्या है, क्वालिटी कैसी है, ब्रांड कौनसी है

**ask_pickup_logistics** — logistics of the old-furniture side of the exchange, different from `ask_valuation` (how the price is calculated).
purana furniture kaun le jaega, hum khud laayen kya, pickup free hai kya, gaadi bhejoge kya, पुराना फर्नीचर कौन ले जाएगा, पिकअप फ्री है क्या, गाड़ी भेजोगे क्या

### F. Appointment lifecycle — only "set" exists, not "change" or "cancel"
`appointment_confirm` only recognizes giving a date. Nothing handles modifying one.

**reschedule_appointment**
date change karni hai, meri appointment reschedule karo, main us din nahi aa paunga, doosri date de do, डेट चेंज करनी है, अपॉइंटमेंट रीशेड्यूल करो, मैं उस दिन नहीं आ पाऊंगा, दूसरी डेट दे दो

**cancel_appointment**
appointment cancel karo, main nahi aa paunga ab, visit cancel kar do, अपॉइंटमेंट कैंसिल करो, मैं नहीं आ पाऊंगा अब, विजिट कैंसिल कर दो

### G. Compliance-sensitive escalations
More severe than `escalate` (manager request) or `dnc` (stop calling) — these signal regulatory/legal risk rather than plain irritation, and probably deserve their own handling path.

**legal_threat**
consumer court jaunga, legal action lunga, TRAI mein complaint karunga, court mein le jaunga, कंज्यूमर कोर्ट जाऊंगा, लीगल एक्शन लूंगा, ट्राई में कंप्लेंट करूंगा, कोर्ट में ले जाऊंगा

**ask_call_recorded**
yeh call record ho rahi hai kya, is this call recorded, यह कॉल रिकॉर्ड हो रही है क्या

**want_human** — distinct from `personal_question` ("are you a bot," a curiosity check); this is an explicit request to be handed to a person, which `escalate` (manager specifically) doesn't quite cover either.
mujhe insaan se baat karni hai, real agent se baat karwao, human se connect karo, मुझे इंसान से बात करनी है, ह्यूमन से कनेक्ट करो, असली आदमी से बात करवाओ

### Two things confirmed by checking the code directly (not just missing keywords)

- **`escalate` is detected but never acted on — confirmed.** Grepped the entire state machine: `"escalate"` appears exactly once in the whole codebase, in the keyword list itself. Nothing anywhere checks `if "escalate" in intents`. Every other category (dnc, already_purchased, ask_location, etc.) has a scripted reply in every campaign; "manager se baat karo" has nowhere to go today — it gets recognized and then silently dropped. Needs a decision on what should happen, even a polite deflection line, in every campaign's script (Part 2).
- **Dead silence and mid-sentence hangups — confirmed already handled, not a gap.** Silence has real logic (`session.silence_count`, closes gracefully after 3 consecutive silent turns instead of hanging forever). Mid-call hangups of any kind go through a dedicated webhook that finalizes the call record regardless of timing — verified this firing correctly on multiple real test calls tonight. Not reply-text categories, and not something missing from Part 1 by omission.

---

## PART 2 — AGENT REPLIES (by script/campaign)

Each campaign is a full, self-contained conversation script. `ra_`/`rb_`/`rc_` are three different opening angles for the *same* first-touch call (react_a, react_b, react_c) — same customer could hear any one of the three depending on which is assigned. `c2_`/`c3_` are the second and third follow-up calls to a lead already contacted once. `fresh_` is the very first call to a brand-new lead who already messaged on WhatsApp.

Lines ending in `_sale` are the Independence Day variant of the same line (swapped in automatically while the sale is running, 11-16 Aug 2026).

### Shared (used across every flow, not campaign-specific)
- **wa_decline_confirm_greet:** Namaste ji, maine dekha aapne WhatsApp par thoda hesitant feel kiya tha. Bas ek baar confirm karna chahti thi — kya abhi ke liye interested nahi hain, ya kuch aur jaankari chahiye?
- **obj_repeat_generic (ritu/shreya/simran, same text):** Maaf kijiye, thik se sun nahi paayi. Kya aap phir se bata sakte hain?
- **obj_timing_greet_generic (ritu/shreya/simran, same text):** Bilkul samajh sakti hoon ji, koi jaldi nahi hai. Bas do minute mein bata deti hoon, phir aap soch lijiyega.
- **wa_fallback_deflect (ritu/shreya/simran, same text):** Main details WhatsApp par bhej deti hoon, aap wahan check kar lijiyega please.
- **llm_filler_price (ritu/shreya/simran, same text):** Ek second, price check kar rahi hoon...
- **llm_filler_location (ritu/shreya/simran, same text):** Ek second, showroom ki detail bata rahi hoon...
- **llm_filler_generic (ritu/shreya/simran, same text):** Ek second, dekhti hoon...

### React A (campaign "ra" — voice: ritu)
- **greet_main:** Aap apne ghar ka furniture upgrade karna chahte ho toh ab woh bahut aasaan ho gaya hai. Hum aapka purana furniture bhi achhi value mein lete hain aur naye furniture par bhi special discount chal raha hai. 30 second mein offer samjha doon?
- **greet_who:** Jee, main Priya bol rahi hoon Krishna Furniture ki taraf se. Aap hamare customer reh chuke hain isliye maine personally phone kiya aapko. Ek khaas offer hai sirf aapke liye.
- **greet_repeat:** Haan ji — hum aapka purana furniture achhe rate mein khareed lenge aur naye par heavy discount denge. Matlab ghar ka poora look badal jaata hai aadhe daam mein.
- **greet_privacy:** Jee bilkul — aapka number hamare purane customer records mein hai. Koi third party nahi hai. Aap hamare valued customer hain isliye personally call ki.
- **greet_hostile:** Maafi chahti hoon disturb karne ke liye. WhatsApp par details bhej deti hoon — dekhna na dekhna aap par hai. Aapka din achha rahe!
- **offer_main:** Krishna Furniture mein abhi naye furniture par 25% discount chal raha hai. Aur agar aap apna purana furniture exchange karte hain toh uski value ka bhi extra benefit milta hai. Matlab overall kharcha kaafi kam ho jaata hai. Ek aur achhi baat bataun?
- **offer_explain:** Bilkul simple hai — aap showroom aao, hum aapke purane furniture ki value calculate karenge aapke saamne. Us value par 25% aur, plus upar se 25% — total saving 43 se 50%. Koi hidden condition nahi hai.
- **offer_trust:** Samajh sakti hoon — aajkal bahut calls aati hain. Aap showroom mein aa kar personally verify kar sakte hain — koi commitment nahi. Sector 14 Gurgaon, Delhi, Noida — teeno jagah hain hamare showrooms.
- **offer_urgency:** Yeh offer sirf is mahine tak hai aur pieces limited hain. Jo pehle aaya usne le liya. WhatsApp par details check karo pehle — phir decide karo.
- **obj_not_interested:** Ek baar WhatsApp par dekh lena — sirf photos aur price list. Koi pressure nahi hai. Offer is mahine tak valid hai.
- **obj_busy:** Bilkul, disturb nahi karti. Details WhatsApp par hain — apni fursad mein dekh lena.
- **obj_expensive:** Isliye toh yeh exchange offer hai — new price par nahi, exchange ke saath. Exact amount WhatsApp par dekh sakte ho.
- **obj_online:** Online mein delivery, installation, after-sales sab alag hote hain. Hamare paas factory price hai plus exchange value — total comparison WhatsApp par hai.
- **obj_think:** Zaroor socho — but offer is mahine tak hi hai. WhatsApp par details reh jaaye, jab decide karo tab kaam aayegi.
- **obj_recovery:** Sach bolunga — jo families yeh offer leke gayi hain wo bahut khush hain. Aadhe daam mein ghar ka poora look badal jaata hai. Aap bhi iska fayda uthao.
- **hook_cta:** Aap hamare purane customer hain, isliye maine personally call kiya. Mera suggestion hai — ek baar showroom aa kar dekh lijiye, waha aapko sab kuch clearly samajh aa jayega. Uske baad decision poori tarah aapka rahega.
- **wa_cta:** Main abhi WhatsApp par photos, prices, exchange process sab bhej rahi hoon. Ek baar dekh lena — decision baad mein karna.
- **close:** Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — purana furniture hum sambhal lenge, aap bas naya chunna. Bahut shukriya!
- **close_conviction:** Ab der mat karo — pieces limited hain. Showroom mein aao, apne saamne value calculate karwao, aur wohi din naya furniture le jaao. Purana hum le lenge. Bahut shukriya!
- **close_no_response:** Koi baat nahi ji, main details WhatsApp par bhej deti hoon — jab convenient ho tab dekh lijiyega. Aapka din shubh ho.
- **dnc:** Maafi chahti hoon! Aapka number DNC list mein add kar diya jaayega — ab koi call nahi aayegi. Bahut bahut shukriya.
- **q_location:** Hamare showrooms Sector 14 Gurgaon, Delhi, aur Noida mein hain — Monday se Sunday, subah 10 baje se raat 8 baje tak khule rehte hain.
- **q_name:** Mera naam Priya hai — main Krishna Furniture ki taraf se baat kar rahi hoon.
- **q_valuation:** Aap ek kaam kar sakte hain, showroom mein aake mujhse mil lijiye. Waha achhe se baat ho paayegi. Aap kis din aa sakte hain?
- **q_price_range:** Sofa ₹33,000 se, bed ₹71,000 se, aur dining set ₹1,19,000 se shuru hota hai — exact price WhatsApp par bhi bhej rahi hoon.
- **q_offer_scope:** Sofa, bed, dining table, wardrobe, chair — bahut saare options hain is offer mein. Ek aur achhi baat bataun?
- **already_purchased:** Bahut badhiya ji! Agar future mein kabhi zaroorat pade toh humein zaroor yaad rakhiyega. Aapka din shubh ho.
- **appointment_ask:** Maine details WhatsApp par bhej di hain. Aap mujhe apni store visit ki date confirm kar dijiyega mujhe please.
- **appointment_confirmed:** Bahut badhiya ji, main aapko store par hi milungi, zaroor aana.
- **appointment_reask:** Maaf kijiye, samajh nahi aaya. Aap phir se date bata sakte hain please?
- **filler_1:** Haan...
- **filler_2:** Ji haan...
- **filler_3:** Bilkul...
- **filler_4:** Achha...
- **filler_5:** Samajh gayi...
- **filler_6:** Theek hai...

React A — Independence Day sale variants (auto-swapped in while the sale is live):
- **greet_main_sale:** Independence Day ke mauke par Krishna Furniture mein is samay bahut bada offer chal raha hai — flat 50% off, sirf 16 August tak. Ghar ka furniture upgrade karna chahte ho toh yeh sabse achha time hai. 30 second mein offer samjha doon?
- **greet_repeat_sale:** Haan ji — abhi Independence Day sale chal rahi hai Krishna Furniture mein, flat 50% off, sirf 16 August tak. Matlab ghar ka poora look badal jaata hai aadhe daam mein.
- **offer_main_sale:** Krishna Furniture mein abhi Independence Day sale chal raha hai — har furniture par flat 50% off, lekin sirf 16 August tak valid hai. Ek aur achhi baat bataun?
- **offer_explain_sale:** Bilkul simple hai — jo bhi furniture aapko pasand aaye, uske price par seedha 50% off mil jaata hai. Bas offer sirf 16 August tak hai, uske baad yeh price wapas nahi milega.
- **offer_urgency_sale:** Yeh offer sirf 16 August tak hai aur pieces limited hain. Jo pehle aaya usne le liya. WhatsApp par details check karo pehle — phir decide karo.
- **obj_not_interested_sale:** Ek baar WhatsApp par dekh lena — sirf photos aur sale price list. Koi pressure nahi hai. Offer sirf 16 August tak valid hai.
- **obj_busy_sale:** Bilkul, disturb nahi karti. Details WhatsApp par hain — bas offer sirf 16 August tak hai, isliye jaldi dekh lena.
- **obj_expensive_sale:** Isliye toh abhi sahi time hai — flat 50% off matlab seedha aadha price. 16 August ke baad yeh rate nahi milega. Exact price WhatsApp par dekh sakte ho.
- **obj_online_sale:** Online mein delivery, installation, after-sales sab alag hote hain. Yahan seedha 50% off milta hai showroom price par — total comparison WhatsApp par hai.
- **obj_think_sale:** Zaroor socho — but offer sirf 16 August tak hai. WhatsApp par details reh jaayengi, jab decide karo tab kaam aayengi.
- **obj_recovery_sale:** Sach bolunga — jo families yeh sale mein aayi hain wo bahut khush hain. Seedha aadhe daam mein naya furniture. Aap bhi iska fayda uthao, bas 16 August tak hi hai.
- **wa_cta_sale:** Main abhi WhatsApp par photos aur 50% off wali prices bhej rahi hoon. Ek baar dekh lena — offer sirf 16 August tak hai.
- **close_sale:** Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — 16 August se pehle. Bahut shukriya!
- **close_conviction_sale:** Ab der mat karo — pieces limited hain aur offer sirf 16 August tak hai. Showroom mein aao, seedha 50% off le jaao. Bahut shukriya!

### React B (campaign "rb" — voice: shreya)
- **greet_main:** Pichhle kuch dino mein bahut saare customers ne apna purana furniture exchange karke naya furniture liya hai. Isliye maine socha aapko bhi call kar doon. Agar aap bhi ghar ka furniture upgrade karna chahte hain toh yeh offer kaafi useful ho sakta hai. Sunna chahenge?
- **greet_who:** Jee, main Priya bol rahi hoon Krishna Furniture ki taraf se. Aap hamare customer reh chuke hain isliye maine personally phone kiya. Soniya ji jaisi bahut families is mahine ghar badal rahi hain — aapke liye bhi yahi offer leke aayi hoon.
- **greet_repeat:** Haan ji — hum purane customers ko ek special offer de rahe hain. Purana furniture achhe rate mein khareed lenge aur naye par heavy discount denge. Aapko offer batau?
- **greet_privacy:** Jee bilkul — aapka number hamare purane customer records mein hai. Koi third party nahi. Aap hamare valued customer hain isliye personally call ki.
- **greet_hostile:** Maafi chahti hoon disturb karne ke liye. WhatsApp par details bhej deti hoon — dekhna na dekhna aap par hai. Aapka din achha rahe!
- **offer_main:** Abhi Krishna Furniture mein naye furniture par 25% discount chal raha hai. Aur purana furniture exchange karne par uski value ka bhi extra benefit milta hai. Is wajah se kaafi log expected se kam budget mein naya furniture le pa rahe hain. Ek aur baat bataun?
- **offer_explain:** Bilkul simple hai — aap showroom aao, hum aapke purane furniture ki value calculate karenge aapke saamne. Us value par 25% aur, plus upar se 25% — total saving 43 se 50%. Koi hidden condition nahi hai.
- **offer_trust:** Samajh sakti hoon — aajkal bahut calls aati hain. Aap showroom mein aa kar personally verify kar sakte hain — koi commitment nahi. Free mein value estimate ho jaati hai.
- **offer_urgency:** Is mahine bahut families aa rahi hain — pieces limited hain. Jo pehle aaya usne le liya. Aap der mat karo.
- **obj_not_interested:** Koi baat nahi — ek baar WhatsApp par photos dekh lena. Offer is mahine tak valid hai — decision aap ka hai.
- **obj_busy:** Bilkul, disturb nahi karti. Details WhatsApp par bhej deti hoon — jab time mile tab dekh lena. Offer is mahine tak valid hai.
- **obj_expensive:** Isliye toh exchange offer hai — new price par nahi, exchange ke saath. Exact amount WhatsApp par dekh sakte ho.
- **obj_online:** Online mein delivery, installation, after-sales sab alag hote hain. Yahan factory price hai plus exchange value — total comparison WhatsApp par hai.
- **obj_think:** Zaroor socho — but offer is mahine tak hi hai. WhatsApp details reh jaaye — jab decide karo tab kaam aayegi.
- **obj_recovery:** Jo families yeh offer le ke gayi hain wo bahut khush hain. Aap bhi ek baar showroom aao — free mein value estimate ho jaati hai. Koi commitment nahi.
- **hook_cta:** Aap bhi hamare purane customer hain, isliye yeh offer maine personally share kiya. Main WhatsApp par furniture ke photos, prices aur exchange process bhej deti hoon. Ek baar dekh lijiye, decision baad mein bhi le sakte hain.
- **wa_cta:** Main abhi WhatsApp par photos, prices, exchange process sab bhej rahi hoon. Ek baar dekh lena — decision baad mein karna.
- **close:** Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — purana furniture hum sambhal lenge, aap bas naya chunna. Bahut shukriya!
- **close_conviction:** Bahut sahi decision hai. Showroom mein aao, apne saamne value calculate karwao, aur wohi din naya furniture le jaao. Purana hum le lenge. Bahut shukriya!
- **close_no_response:** Theek hai ji, koi jaldi nahi. WhatsApp par details bhej deti hoon — jab time mile tab dekh lijiyega. Shukriya.
- **dnc:** Maafi chahti hoon! Aapka number DNC list mein add kar diya jaayega — ab koi call nahi aayegi. Bahut bahut shukriya.
- **q_location:** Hamare showrooms Sector 14 Gurgaon, Delhi, aur Noida mein hain — Monday se Sunday, subah 10 baje se raat 8 baje tak khule rehte hain.
- **q_name:** Mera naam Priya hai — main Krishna Furniture ki taraf se baat kar rahi hoon.
- **q_valuation:** Aap ek kaam kar sakte hain, showroom mein aake mujhse mil lijiye. Waha achhe se baat ho paayegi. Aap kis din aa sakte hain?
- **q_price_range:** Sofa ₹33,000 se, bed ₹71,000 se, aur dining set ₹1,19,000 se shuru hota hai — exact price WhatsApp par bhi bhej rahi hoon.
- **q_offer_scope:** Sofa, bed, dining table, wardrobe, chair — bahut saare options hain is offer mein. Ek aur achhi baat bataun?
- **already_purchased:** Bahut badhiya ji! Agar future mein kabhi zaroorat pade toh humein zaroor yaad rakhiyega. Aapka din shubh ho.
- **appointment_ask:** Maine details WhatsApp par bhej di hain. Aap mujhe apni store visit ki date confirm kar dijiyega mujhe please.
- **appointment_confirmed:** Bahut badhiya ji, main aapko store par hi milungi, zaroor aana.
- **appointment_reask:** Maaf kijiye, samajh nahi aaya. Aap phir se date bata sakte hain please?
- **filler_1 → filler_6:** same six as React A (Haan... / Ji haan... / Bilkul... / Achha... / Samajh gayi... / Theek hai...)

React B — Independence Day sale variants:
- **greet_main_sale:** Independence Day ke mauke par Krishna Furniture mein bahut bada sale chal raha hai — flat 50% off, sirf 16 August tak. Isliye maine socha aapko bhi call kar doon. Sunna chahenge?
- **greet_repeat_sale:** Haan ji — abhi Independence Day sale chal rahi hai, flat 50% off, sirf 16 August tak. Aapko offer batau?
- **offer_main_sale:** Abhi Krishna Furniture mein Independence Day sale chal raha hai — har furniture par flat 50% off, lekin sirf 16 August tak valid hai. Is wajah se kaafi log expected se kam budget mein naya furniture le pa rahe hain. Ek aur baat bataun?
- **offer_explain_sale:** Bilkul simple hai — jo bhi furniture aapko pasand aaye, uske price par seedha 50% off mil jaata hai. Bas offer sirf 16 August tak hai, uske baad yeh price wapas nahi milega.
- **offer_urgency_sale:** Is hafte bahut families aa rahi hain — pieces limited hain aur offer sirf 16 August tak hai. Aap der mat karo.
- **obj_not_interested_sale:** Koi baat nahi — ek baar WhatsApp par photos dekh lena. Offer sirf 16 August tak valid hai — decision aap ka hai.
- **obj_busy_sale:** Bilkul, disturb nahi karti. Details WhatsApp par bhej deti hoon — bas offer sirf 16 August tak hai, jaldi dekh lena.
- **obj_expensive_sale:** Isliye toh abhi sahi time hai — flat 50% off matlab seedha aadha price. 16 August ke baad yeh rate nahi milega. Exact price WhatsApp par dekh sakte ho.
- **obj_online_sale:** Online mein delivery, installation, after-sales sab alag hote hain. Yahan seedha 50% off milta hai showroom price par — total comparison WhatsApp par hai.
- **obj_think_sale:** Zaroor socho — but offer sirf 16 August tak hai. WhatsApp details reh jaayengi — jab decide karo tab kaam aayengi.
- **obj_recovery_sale:** Jo families yeh sale mein aayi hain wo bahut khush hain. Aap bhi ek baar showroom aao — seedha 50% off, bas 16 August tak hi hai.
- **hook_cta_sale:** Aap bhi hamare purane customer hain, isliye yeh Independence Day sale maine personally share kiya. Main WhatsApp par furniture ke photos aur 50% off prices bhej deti hoon. Ek baar dekh lijiye, decision baad mein bhi le sakte hain.
- **wa_cta_sale:** Main abhi WhatsApp par photos aur 50% off wali prices bhej rahi hoon. Ek baar dekh lena — offer sirf 16 August tak hai.
- **close_sale:** Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — 16 August se pehle. Bahut shukriya!
- **close_conviction_sale:** Bahut sahi decision hai. Pieces limited hain aur offer sirf 16 August tak hai. Showroom mein aao, seedha 50% off le jaao. Bahut shukriya!

### React C (campaign "rc" — voice: simran)
- **greet_main:** Ek chhota sa sawal poochun? Agar aapko naya furniture mil jaaye aur purana bhi achhi value mein chala jaaye, woh bhi kam kharche mein... toh kya aap uske baare mein sunna chahenge?
- **greet_who:** Jee, main Priya bol rahi hoon Krishna Furniture ki taraf se. Aap hamare customer reh chuke hain isliye maine personally phone kiya. Ek sawaal poochha tha — agar naya furniture aadhe daam mein mile toh sunenge?
- **greet_repeat:** Haan ji — main pooch rahi thi, agar aapko naya furniture mile aur purana bhi achhe rate mein chala jaaye — aadhe daam mein — toh aap sunna chahenge?
- **greet_privacy:** Jee bilkul — aapka number hamare purane customer records mein hai. Koi third party nahi. Aap hamare valued customer hain isliye personally call ki.
- **greet_hostile:** Maafi chahti hoon disturb karne ke liye. WhatsApp par details bhej deti hoon — dekhna na dekhna aap par hai. Aapka din achha rahe!
- **offer_main:** Toh bas wahi offer chal raha hai Krishna Furniture mein. Naye furniture par 25% discount hai aur purana furniture exchange karne par uski value ka bhi alag benefit milta hai. Ek aur baat bataun?
- **offer_explain:** Bilkul simple hai — aap showroom aao, hum aapke purane furniture ki value calculate karenge aapke saamne. Us value par 25% aur, plus upar se 25% — total saving 43 se 50%. Free mein value estimate ho jaati hai — koi commitment nahi.
- **offer_trust:** Samajh sakti hoon — aajkal bahut calls aati hain. Aap showroom mein aa kar personally verify kar sakte hain — koi commitment nahi. Free mein furniture ki value estimate ho jaati hai. Sirf ek baar aao toh sahi.
- **offer_urgency:** Yeh offer sirf apne purane customers ke liye hai — aur is mahine tak hi valid hai. Jo pehle aaya usne le liya. Aap der mat karo.
- **obj_not_interested:** Koi baat nahi — main force nahi kar rahi. Bas ek baar WhatsApp par photos dekh lena. Offer is mahine tak valid hai — decision aap ka hai.
- **obj_busy:** Bilkul, disturb nahi karti. Details WhatsApp par bhej deti hoon — apni fursad mein dekh lena.
- **obj_expensive:** Isliye toh yeh exchange offer hai — new price par nahi, exchange ke saath. Exact amount WhatsApp par dekh sakte ho. Free mein estimate bhi ho jaati hai showroom mein.
- **obj_online:** Online mein delivery, installation, after-sales sab alag hote hain. Hamare paas factory price hai plus exchange value — total comparison WhatsApp par hai.
- **obj_think:** Zaroor socho — main force nahi kar rahi. But offer is mahine tak hi hai. WhatsApp details reh jaaye — jab decide karo tab kaam aayegi.
- **obj_recovery:** Dekho, maine aapko force nahi karna. Bas ek baar WhatsApp dekho, showroom aao — free mein furniture ki value estimate ho jaati hai. Koi commitment nahi. Aao toh sahi.
- **hook_cta:** Yeh offer hum specially apne existing customers ke saath share kar rahe hain. Isliye maine aapko personally call kiya. Main WhatsApp par photos aur poori details bhej deti hoon. Ek baar dekh lijiye, koi commitment bilkul nahi hai.
- **wa_cta:** Main abhi WhatsApp par photos, prices, exchange process sab bhej rahi hoon. Ek baar dekh lena — decision baad mein karna. Koi commitment nahi.
- **close:** Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — free mein value estimate ho jaayegi. Purana furniture hum sambhal lenge, aap bas naya chunna. Bahut shukriya!
- **close_no_response:** Koi baat nahi ji, main force nahi kar rahi. WhatsApp par details bhej deti hoon — apni fursad mein dekh lijiyega. Shukriya.
- **dnc:** Maafi chahti hoon! Aapka number DNC list mein add kar diya jaayega — ab koi call nahi aayegi. Bahut bahut shukriya.
- **q_location:** Hamare showrooms Sector 14 Gurgaon, Delhi, aur Noida mein hain — Monday se Sunday, subah 10 baje se raat 8 baje tak khule rehte hain.
- **q_name:** Mera naam Priya hai — main Krishna Furniture ki taraf se baat kar rahi hoon.
- **q_valuation:** Aap ek kaam kar sakte hain, showroom mein aake mujhse mil lijiye. Waha achhe se baat ho paayegi. Aap kis din aa sakte hain?
- **q_price_range:** Sofa ₹33,000 se, bed ₹71,000 se, aur dining set ₹1,19,000 se shuru hota hai — exact price WhatsApp par bhi bhej rahi hoon.
- **q_offer_scope:** Sofa, bed, dining table, wardrobe, chair — bahut saare options hain is offer mein. Ek aur achhi baat bataun?
- **already_purchased:** Bahut badhiya ji! Agar future mein kabhi zaroorat pade toh humein zaroor yaad rakhiyega. Aapka din shubh ho.
- **appointment_ask:** Maine details WhatsApp par bhej di hain. Aap mujhe apni store visit ki date confirm kar dijiyega mujhe please.
- **appointment_confirmed:** Bahut badhiya ji, main aapko store par hi milungi, zaroor aana.
- **appointment_reask:** Maaf kijiye, samajh nahi aaya. Aap phir se date bata sakte hain please?
- **filler_1 → filler_6:** same six as React A/B

React C — Independence Day sale variants:
- **greet_main_sale:** Ek chhota sa sawal poochun? Independence Day ke mauke par Krishna Furniture mein flat 50% off chal raha hai, sirf 16 August tak — kya aap uske baare mein sunna chahenge?
- **greet_repeat_sale:** Haan ji — main pooch rahi thi, Independence Day sale chal rahi hai abhi, flat 50% off, sirf 16 August tak — toh aap sunna chahenge?
- **offer_main_sale:** Toh bas wahi offer chal raha hai Krishna Furniture mein — Independence Day sale, flat 50% off, sirf 16 August tak valid hai. Ek aur baat bataun?
- **offer_explain_sale:** Bilkul simple hai — jo bhi furniture aapko pasand aaye, uske price par seedha 50% off mil jaata hai. Bas offer sirf 16 August tak hai — koi commitment nahi, bas ek baar dekh lijiye.
- **offer_urgency_sale:** Yeh offer sirf apne purane customers ke liye hai — aur sirf 16 August tak hi valid hai. Jo pehle aaya usne le liya. Aap der mat karo.
- **obj_not_interested_sale:** Koi baat nahi — main force nahi kar rahi. Bas ek baar WhatsApp par photos dekh lena. Offer sirf 16 August tak valid hai — decision aap ka hai.
- **obj_busy_sale:** Bilkul, disturb nahi karti. Details WhatsApp par bhej deti hoon — bas offer sirf 16 August tak hai, apni fursad mein jaldi dekh lena.
- **obj_expensive_sale:** Isliye toh abhi sahi time hai — flat 50% off matlab seedha aadha price. 16 August ke baad yeh rate nahi milega. Exact price WhatsApp par dekh sakte ho.
- **obj_online_sale:** Online mein delivery, installation, after-sales sab alag hote hain. Yahan seedha 50% off milta hai showroom price par — total comparison WhatsApp par hai.
- **obj_think_sale:** Zaroor socho — main force nahi kar rahi. But offer sirf 16 August tak hai. WhatsApp details reh jaayengi — jab decide karo tab kaam aayengi.
- **obj_recovery_sale:** Dekho, maine aapko force nahi karna. Bas ek baar WhatsApp dekho — seedha 50% off hai, bas 16 August tak. Aao toh sahi.
- **wa_cta_sale:** Main abhi WhatsApp par photos aur 50% off wali prices bhej rahi hoon. Ek baar dekh lena — offer sirf 16 August tak hai. Koi commitment nahi.
- **close_sale:** Bilkul sahi decision hai. WhatsApp dekho, ek baar showroom aao — 16 August se pehle. Bahut shukriya!

### Call 2 (second call to the same lead — voice: ritu)
- **greet_main:** Namaste ji, Priya bol rahi hoon Krishna Furniture se. Pichhli baar hamari baat hui thi, yaad hai na?
- **greet_reorient:** Ji, Krishna Furniture se. Maine aapko WhatsApp par offer ki details bheji thi.
- **greet_annoyed:** Bilkul ji, bas 30 second loongi. Aapki store visit ki date confirm karni thi.
- **wa_check:** Maine WhatsApp par jo details bheji thi, dekh li aapne?
- **invite_seen:** Ji badhiya! Toh ek baar showroom zaroor aaiye. Kab free honge aap? Ek date bata dijiye.
- **invite_resend:** Koi baat nahi ji, main abhi dobara WhatsApp par bhej deti hoon. Zaroor dekh lijiyega. Waise seedha showroom bhi aa sakte hain — kab free honge aap? Ek date bata dijiye.
- **date_direct:** Kab free honge aap store visit ke liye? Ek date bata dijiye.
- **date_reask:** Bilkul ji, koi jaldi nahi. Bas ek din bata dijiye, hum milte hain phir uss din store mein.
- **booked:** Okay ji, main store par hi milungi aapko. Zaroor aana. Dhanyawad.
- **obj_price:** Ho sakta hai ji, isiliye ek baar dekh lena behtar rahega — final decision toh aap showroom mein hi lenge na?
- **obj_timing:** Koi baat nahi ji, samajh sakti hoon. WhatsApp par details bhej deti hoon, aap apni convenience se dekh lijiyega — bas ek din bata dijiye jab aap free honge.
- **obj_scam:** Bilkul nahi ji, bharosa rakhiye. Aap chahein toh seedha showroom visit karke khud dekh sakte hain — kab free honge, ek date bata dijiye?
- **obj_not_interested:** Koi baat nahi ji. Bas confirm karna tha. Zaroorat ho toh yaad rakhiyega humein.
- **close_thinking:** Theek hai ji, aaram se soch lijiye. Main details WhatsApp par bhej deti hoon.
- **close_busy:** Koi baat nahi ji, jab time mile tab dekh lijiyega.
- **close_price:** Samajh sakti hoon ji. Main details WhatsApp par bhej deti hoon, dekh lijiyega.
- **close_declined:** Dhanyavaad ji, aapka time dene ke liye shukriya.

### Call 3 (third and final call — voice: simran)
- **greet_main:** Namaste ji, Priya bol rahi hoon Krishna Furniture se. Aapse pehle bhi baat hui thi — bas ek aakhri baar poochna tha, kya socha aapne?
- **greet_reorient:** Arre, Krishna Furniture se — woh offer jo maine pehle bataya tha.
- **greet_hostile:** Bilkul theek hai ji, samajh gayi. Ab dobara call nahi karungi. Shukriya.
- **decision_date:** Ek baar showroom aa jaiye, sirf paanch minute lagenge. Kab free honge? Ek date bata dijiye.
- **date_reask:** Bilkul ji, koi jaldi nahi. Bas ek din bata dijiye, hum milte hain phir uss din store mein.
- **booked:** Okay ji, main store par hi milungi aapko. Zaroor aana. Dhanyawad.
- **obj_price:** Samajh sakti hoon ji. Offer WhatsApp par hai, jab convenient ho dekh lijiyega.
- **obj_scam:** Bilkul nahi ji, bharosa rakhiye — showroom khud visit karke dekh sakte hain. Kab free honge, ek date bata dijiye?
- **declined:** Bilkul samajh sakti hoon ji. Aapka time dene ke liye shukriya.
- **close_thinking_final:** Koi baat nahi ji. Details WhatsApp par hain, jab convenient ho dekh lijiyega. Aapka din shubh ho.
- **close_busy:** Koi baat nahi ji, abhi disturb nahi karti. Details WhatsApp par hain.

### Fresh CTA (first-ever call, lead already messaged on WhatsApp — voice: simran)
- **greet_bed:** Namaste ji, hamari WhatsApp par baat hui thi — aap bed dekhna chahte the. Toh kab aana hoga store par? Main aapko wahi milungi.
- **greet_sofa:** Namaste ji, hamari WhatsApp par baat hui thi — aap sofa dekhna chahte the. Toh kab aana hoga store par? Main aapko wahi milungi.
- **greet_wardrobe:** Namaste ji, hamari WhatsApp par baat hui thi — aap wardrobe dekhna chahte the. Toh kab aana hoga store par? Main aapko wahi milungi.
- **greet_dining:** Namaste ji, hamari WhatsApp par baat hui thi — aap dining set dekhna chahte the. Toh kab aana hoga store par? Main aapko wahi milungi.
- **greet_generic:** Namaste ji, hamari WhatsApp par baat hui thi Krishna Furniture ke baare mein. Toh kab aana hoga store par? Main aapko wahi milungi.
- **objection:** Ji sir, bahut ache ache designs aaye hain, aapko zaroor pasand aaenge. Main WhatsApp par bhej deti hoon, lekin ek baar store aake dekhna zyada sahi rahega — waha ache se samajh aa jaayega. Kab aa sakte hain?
- **appointment_confirmed:** Bahut badhiya ji! Main aapka appointment confirm kar deti hoon. Hamari team aapka intezar karegi. Jaldi milte hain!
- **no_date_close:** Koi baat nahi ji. Main aapko WhatsApp par kuch achhe options bhej deti hoon — aap aaram se dekh lijiye, phir jab convenient ho tab visit plan kar lenge.
- **soft_defer:** Okay ji, aap WhatsApp par hi confirm kar dena, main aur options bhej deti hoon.
- **location_info:** Humare stores Gurugram, Delhi, Noida, aur Faridabad mein hain. WhatsApp par aapko exact address aur Google Maps link bhej deti hoon — aap wahi se date confirm kar dena, phir wahi milenge hum.
- **greet_who_bed:** Ji, Krishna Furniture se — humari WhatsApp par baat hui thi bed ke baare mein. Kab aana hoga store par?
- **greet_who_sofa:** Ji, Krishna Furniture se — humari WhatsApp par baat hui thi sofa ke baare mein. Kab aana hoga store par?
- **greet_who_wardrobe:** Ji, Krishna Furniture se — humari WhatsApp par baat hui thi wardrobe ke baare mein. Kab aana hoga store par?
- **greet_who_dining:** Ji, Krishna Furniture se — humari WhatsApp par baat hui thi dining set ke baare mein. Kab aana hoga store par?
- **greet_who_generic:** Ji, Krishna Furniture se — humari WhatsApp par baat hui thi. Kab aana hoga store par?
- **price:** Ji sir, price bilkul reasonable hai, poori detail WhatsApp par bhej deti hoon. Store aake dekhoge toh value khud samajh aa jaayegi — kab aa sakte hain?
- **trust:** Bilkul samajh sakti hoon ji. Store aake khud dekh sakte hain, koi obligation nahi — waha se hi sahi decide kar paoge. Kab aa sakte hain?

---

*End of raw catalog. Add to either part directly — nothing above is wired together on purpose.*
