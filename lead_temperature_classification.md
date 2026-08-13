# Lead Temperature: Cold / Warm / Hot

**Scope:** Reactivation calls only (react_a/b/c, Call 2, Call 3). The fresh-lead
(first-time) funnel scores leads differently — on qualification completeness
(product + budget + urgency), not on conversation behavior — and is not
covered by this document.

## Cold
Not interested, or the reply doesn't engage with the conversation at all
(random/off-topic remarks, silence, garbled replies).

- Any hard rejection ("not interested", opt-out/DNC) **zeroes the score
  instantly**, no matter what else happened on the call.
- Everything else that doesn't earn warm/hot points by default sits here too.

## Warm
Talks like a real person — responds to the agent, listens to the offer, and
engages meaningfully. Typically shown by:

- Agreeing to receive the WhatsApp follow-up (biggest single signal)
- Asking real questions (exchange offer, pricing/EMI)
- Naming a specific product they're interested in
- Staying engaged across multiple turns without objecting

## Hot
Confirms a visit date. This is a **hard override** — the moment a date/visit
is confirmed, the lead is marked hot regardless of anything else on the call.

---

### How it's scored under the hood (for reference)
Each engagement signal adds points (WhatsApp accepted +40, buying signal +30,
offer/exchange questions +20, product interest +15, sustained positive
engagement +10, etc.), capped at 100:

| Score | Tier |
|-------|------|
| 0–24  | Cold |
| 25–59 | Warm |
| 60+, or date confirmed (forced) | Hot |
