# Call Quality Architecture Audit
**Date:** 2026-08-13
**Trigger:** Pratham call (919911117660, call_uuid `4d90b47e-7c96-468d-9020-155e82828680`, 13:54 IST) — customer said "yes" twice and wasn't understood, a real question got a non-answer, the agent's voice audibly changed mid-call, and the call ended on an unanswered "haan ji."
**Method:** Read the live dialogue/intent code across all three call flows, then independently re-transcribed the raw call recording with faster-whisper (the same STT model the agent uses) and diffed it against what's actually stored in `call_summaries.full_transcript`, rather than trusting the DB record alone.

---

## 0. The one-sentence answer to "why does this keep happening after 3 months"

**There is no single place in this codebase that decides "did the customer just say yes."** There are at least three independently-maintained keyword systems (`knowledge.py`, `knowledge_react_abc.py`, `knowledge_reactivation.py`), each built at a different time, each with different coverage, and fixes made in one never propagate to the others. The fix for "customer said यस" and "customer said हेलो as a check-in, not a question" **already exists in `knowledge.py`** — and was simply never carried over to the flow that's actually live for warm/reactivation calls (`knowledge_react_abc.py`, which is what handled Pratham's call). This is not a missing-keyword bug. It's a missing-single-source-of-truth bug, and it will keep reproducing itself indefinitely until the three systems are merged, because every fix so far has been applied to whichever one file the engineer investigating that day happened to be looking at.

Layered on top of that: the fallback path that catches "detect_intents found nothing" doesn't just answer imperfectly — it **speaks in a different voice** than the rest of the call, because voice identity was never threaded through that code path at all. That's a separate, codebase-wide bug, not specific to Hinglish coverage, and it's arguably the most damaging one for "does this sound like one continuous person" — see §3.

---

## 1. What's actually built here

Three largely-parallel calling flows exist, each with its own state machine and its own private keyword/intent vocabulary:

| Flow | Entry point | Keyword source | Used for |
|---|---|---|---|
| Fresh-lead Call 1 | `webhook.py` | `knowledge.py` (`ACK_WORDS`, `JUNK_WORDS`, `is_noise()`, exact-match) | First outbound call to a brand-new lead |
| Reactivation Call 1 (react_a/b/c) | `webhook_reactivation.py` → `handle_call2_turn` etc. | `knowledge_react_abc.py` (`REACT_ABC_INTENTS`, substring token match via `detect_intents()`) | Warm/reactivation leads, campaigns `ra`/`rb`/`rc` |
| Call 2 / Call 3 follow-ups | `webhook_reactivation.py` (`handle_call2_turn`, `handle_call3_turn`) | Same `REACT_ABC_INTENTS` (shared with the row above) | Second/third touch on a lead already contacted once |
| (Legacy, appears dead) | — | `knowledge_reactivation.py` — only imported by `generate_cache_reactivation.py`, not by any live webhook handler | Unclear — looks like an earlier iteration of the react flow that was superseded but never deleted |

**Pratham's call used the `ra` campaign** (confirmed by matching script text: `ra_greet_main`, `ra_offer_main_sale`, `ra_q_offer_scope`), so it ran entirely on `knowledge_react_abc.py`'s keyword lists — the weakest-coverage of the three systems, not the one with `knowledge.py`'s more mature handling.

**Intent matching mechanism (`detect_intents()`, `webhook_reactivation.py:984`):** token-boundary exact-phrase substring matching against ~22 hand-written per-intent keyword lists. No fuzzy matching, no stemming, no synonym expansion, no edit-distance tolerance. If a phrase isn't verbatim in the list (accounting only for a narrow "one bridging filler word" exception, `webhook_reactivation.py:787-806`), it doesn't match — full stop.

**LLM fallback exists, but only as a last resort:** `llm_fallback_reply()` (`webhook_reactivation.py:1242`) is invoked *only* when `detect_intents()` returns nothing at all. It classifies the utterance as ANSWERABLE / UNKNOWN / UNCLEAR via a Groq 8B model with a 1.5s budget, then either generates a grounded answer, or returns one of two fixed canned strings (`_REACT_LLM_REPROMPT_TEXT` for UNCLEAR, `_REACT_LLM_UNKNOWN_TEXT` for UNKNOWN). The whole pipeline has a hard 4.0s ceiling before giving up and falling back to a static reprompt line. So the "intelligent" layer this system has is real, but it's scoped narrowly to "nothing matched at all" — it is never used to help the *keyword* matcher itself understand near-miss phrasing, and its own output has a separate, serious bug (§3).

---

## 2. Root cause 1 — three parallel, unsynchronized vocabularies

Concrete proof, checked directly against the code (not inferred):

**"yes" / "यस":**
- `knowledge.py:138,142` (fresh-lead flow) — **has it.** `ACK_WORDS` includes `"yes"`, `"यस"`, `"यस।"`.
- `knowledge_react_abc.py:477-480` (`REACT_ABC_INTENTS["positive"]`, the flow Pratham's call ran on) — **does not have it.** 29 entries, none of them "yes" or "यस" in any spelling.
- `knowledge_reactivation.py:199-200` (legacy/dead) — **also does not have it.**

**"हेलो" as a mid-call check-in, not a real question:**
- `knowledge.py:146` — **already solved.** `"हेलो"`/`"hello"` are explicitly in `ACK_WORDS` with the comment *"Greetings used as ACK (caller checking if agent is there)"*.
- `webhook_reactivation.py:776` (`_FILLER_CONTINUER_WORDS`, the only filler-suppression list the react flow has) — **only contains `{"hmm", "hmmm", "हम्म", "हम्म्म"}`.** No "हेलो". So the exact case someone already solved for fresh leads three months ago (or whenever `knowledge.py` was written) is unsolved for warm/reactivation calls today.

**Why this matters more than "add the missing word":** this is the *pattern* that explains the 3-month persistence. Every one of the ~15 "confirmed live 2026-0X-XX" comments throughout `knowledge_react_abc.py` and `webhook_reactivation.py` documents a real customer breaking the system in a way that, in several cases, was *already handled somewhere else in the same repository*. The engineering process has been: customer breaks call → find the file that's live for that call type → patch that one file. Nobody has been asking "does a different flow already know how to handle this." Until there is exactly one intent/ack/filler vocabulary that every flow reads from, this class of bug is structurally guaranteed to keep recurring — new campaigns, new flows, or new engineers touching only one file will keep reintroducing gaps the codebase already closed elsewhere.

---

## 3. Root cause 2 — the fallback path breaks voice identity, codebase-wide

This is the "agent's voice changed" bug, and it is **not specific to Pratham's call or to Hinglish coverage** — it's a structural gap in the TTS layer that fires every single time any flow falls back to dynamic/LLM-generated speech.

- Each campaign has an assigned voice: `PREFIX_VOICE_MAP = {"ra": "ritu", "rb": "shreya", "rc": "simran", "c2": "ritu", "c3": "simran", "fresh": "simran"}` (`knowledge_react_abc.py:351-354`). Pratham's call (`ra`) should sound like **ritu** throughout.
- Every *scripted* line (`ra_greet_main`, `obj_repeat_generic_ritu`, etc.) is pre-recorded per-voice and cached correctly — `tts-cache/static/obj_repeat_generic_ritu_hi.wav` exists alongside `_shreya_` and `_simran_` variants. This part works.
- But `play_dynamic_text()` (`webhook_reactivation.py:1262`) — the function that speaks **any** LLM-fallback output, including the exact same "Maaf kijiye, thik se sun nahi paayi" reprompt text — calls `tts_engine.get_speech(text, lang="hi", static_key=None)` with **no voice/speaker parameter at all**.
- `get_speech()` (`tts_engine.py:432`) has no voice parameter in its signature, full stop. When it falls through to live synthesis, `_call_sarvam_tts()` uses a config table that **hardcodes `"speaker": "shreya"`** for every language (`tts_engine.py:48-50`), unconditionally.

**Net effect:** any time `detect_intents()` comes back empty (which — per §2 — happens routinely for extremely common utterances like a bare "yes" in the `ra`/`rc`/`c2`/`c3`/`fresh` campaigns), there is a real chance the reply gets spoken by `play_dynamic_text()` in **hardcoded "shreya"**, not the campaign's actual voice. Only campaign `rb` (already "shreya") is immune. On Pratham's `ra` call, this means the moment the fallback path fired — which it did, repeatedly — the customer could hear the voice snap from "ritu" to "shreya" and potentially back again seconds later when a *different* branch used the correctly-voiced static cache. This is almost certainly what "the agent's voice changed" refers to, and it's a much bigger deal for perceived seriousness/trustworthiness than a missed keyword: a keyword miss reads as "she misheard me"; a voice change reads as "this isn't a real, continuous person" — the two failures compound but the second one is qualitatively worse.

This bug also means the two root causes are coupled: the sparser the keyword coverage (§2), the more often calls fall into this path, the more often the voice breaks. Fixing keyword coverage will reduce how often this fires, but the underlying voice-threading bug needs its own fix regardless — a well-covered keyword list still leaves the LLM-fallback path live for genuinely novel utterances, which will always exist.

---

## 4. What actually happened on Pratham's call (audio-verified, not DB-verified)

I pulled `recording_url` directly and re-transcribed the full 158-second call myself. The stored `call_summaries.full_transcript` **does not reliably reflect what was said** — worth fixing on its own, see §5. Reconstructed real timeline:

| Time | Speaker | What happened | Root cause |
|---|---|---|---|
| 0–18s | Agent | Opening pitch plays correctly | — |
| 22–30s | Customer | **"Yes"** | unmatched → fallback fires |
| 30–33s | Agent | "Sorry, didn't catch that, please repeat" | §2 — "यस" not in `positive` list |
| 33–38s | Customer | **"Yes yes"** | unmatched again |
| 38–42s | Agent | Same reprompt, again | §2, compounding |
| 42–44s | Customer | "Haan ji" ×3 | finally matches — "haan" *is* in the list |
| 44–77s | Agent/Customer | Pitch continues normally | — |
| 98s | Customer | **Real question: "what's your furniture price range starting at?"** | STT rendered this as a short, unrelated fragment (logged in the DB as "हेलो") — question never actually answered |
| 100–120s | Agent | Generic "I'll send details on WhatsApp" deflection + re-asks for a visit date | Consequence of the above — genuine customer question effectively dropped |
| 123–130s | Customer | "What furniture do you have?" | matched correctly this time (`ask_offer_scope`) |
| 132–140s | Agent | Furniture list + "one more good thing?" | — |
| 142–157s | Customer | **"Haan ji"** | not a date → correctly falls to the re-ask branch |
| 157–158s | Agent | "Sorry, I didn't under—" *(cut off, call ends)* | Customer very likely hung up from accumulated frustration — this is the **third** "didn't catch/understand you" in a 161-second call for what were, from the customer's side, perfectly clear answers |

Two things worth being precise about, because they matter for what to fix:

1. **The final "haan ji" is not a silent dead-end in the code.** The logic at `webhook_reactivation.py:2087-2091` does correctly re-ask for a date. The audio confirms the agent started speaking. What actually went wrong is (a) the customer hung up before hearing it, most plausibly because it's the third non-answer in under three minutes, and (b) that specific line is called with `log_transcript=False` (`webhook_reactivation.py:2090`), so the stored transcript makes it *look* like the agent went completely silent, which isn't quite what happened — it looked broken because we couldn't see it, not only because it was broken.

2. **The "हेलो" the DB shows is very likely a real, substantive question the STT mangled**, not an actual dead-air "hello." This is a live-transcription-accuracy issue that no keyword list can fix — it needs attention on the STT side (model/prompt/language-context tuning), separate from the intent-matching gaps.

---

## 5. Adjacent problems found in passing (flagging per your standing instruction, not silently fixing)

- **`full_transcript` cannot currently be trusted as a record of the call.** Two concrete gaps found in this one call alone: the very first assistant line stored in the DB doesn't match any script key or the actual audio at all (real audio played the standard `ra_greet_main` pitch; DB shows unrelated "Independence Day Sale" text from nowhere identifiable in the script files); and the entire 98–120s price-question exchange is missing from the stored transcript. Combined with 17 separate `log_transcript=False` call sites across `webhook_reactivation.py` (deliberate, for legitimate "don't double-log the second half of a combined reply" reasons in most cases, but with the side effect described in §4.1), anyone auditing a call from the DB alone — which is what I did before pulling the recording — will draw wrong conclusions about what actually broke.
- **"available" mis-triggering IVR detection** — this was real and is already fixed, same day (`webhook_reactivation.py:56-65`, dated 2026-08-13). Good example of the reactive-patch pattern in action: found live, one word removed from one list, done — but it's exactly the kind of fix that, per §2, may or may not exist in the *other* two keyword systems now. (Quick check: IVR fragment detection is only implemented in `webhook_reactivation.py`, not duplicated elsewhere, so this one is probably fine — but it's the same shape of risk.)
- **`knowledge_reactivation.py` appears to be dead code** — only referenced by `generate_cache_reactivation.py` (a cache pre-generation script), not by any live call handler. It still has its own incomplete `positive` list (also missing "yes"/"यस"), which is harmless if truly dead, but worth confirming and either deleting or documenting why it's kept — a stale near-duplicate sitting next to the live version is exactly the kind of thing that causes a future engineer to edit the wrong file and wonder why their fix didn't take effect on a live call.
- **`positive` intent list is genuinely under-built relative to its traffic.** 29 entries vs. 41 for `not_interested` and 61 for `dnc`, despite `positive`/affirmation being the single highest-frequency customer response in *every* state of *every* flow. Your instinct that it should be closer to 50 is directionally right — not as an arbitrary number, but because affirmation is where Hinglish/English/Devanagari-phonetic code-switching shows up most (haan/han/ha/ji/yes/yeah/ok/okay/theek/bilkul/achha/sure — and each of those again in Devanagari phonetic spelling).

---

## 6. Recommended direction (for discussion before anything is implemented)

I haven't changed any code. Given the scope, here's the shape of a fix that addresses causes, not just this one call:

1. **Consolidate to one canonical intent/ack/filler module**, merging the best coverage from `knowledge.py`, `knowledge_react_abc.py`, and (if anything's salvageable) `knowledge_reactivation.py`. Every flow (`webhook.py`, `webhook_reactivation.py`) reads from it. This is the only way a fix made once stops needing to be re-made three times.
2. **Thread voice identity through the entire TTS path**, including `get_speech()`/`_call_sarvam_tts()`/`play_dynamic_text()`, so dynamic/LLM-fallback speech always uses the calling campaign's assigned voice instead of a hardcoded default. This is independent of #1 and, given how visible it is to a customer, arguably the highest-leverage single fix available.
3. **Rebuild the `positive`/affirmation list deliberately** (not word-by-word reactively) — systematically enumerate Hindi/Hinglish/English/Devanagari-phonetic affirmation forms up front, the way you're asking for, backed by the existing 291-case regression suite (`test_reply_state_regression.py`) extended to cover it so this doesn't silently regress again.
4. **Make `full_transcript` trustworthy** — stop suppressing spoken content from the log; if there's a real reason to avoid duplicate-looking entries, mark them (e.g. a `continuation` flag) instead of dropping them, since the log is also the only thing anyone (including me, until I pulled the recording) can audit a call from.
5. **Delete or clearly mark `knowledge_reactivation.py` as dead**, so it stops being a plausible-looking place to make a fix that won't actually apply to live calls.
6. Separately, flag the STT-accuracy question (the mangled price-range question) to whoever owns the live ASR pipeline/model choice — that's not a dialogue-logic fix.

Happy to scope any of these into an actual implementation plan once you've read through this — my read is #1 and #2 are the two that actually address "why does this keep happening," and everything else is a needed but smaller consequence of those two.
