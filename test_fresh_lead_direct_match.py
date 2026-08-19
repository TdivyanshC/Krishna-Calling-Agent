# -*- coding: utf-8 -*-
"""
Regression suite for the 2026-08-19 fresh-lead-flow audit (knowledge.py's
get_direct_match()) -- the same treatment given to webhook_reactivation.py's
matcher earlier the same day, applied to the OTHER keyword-matching system
in this codebase (the qualification funnel, not the reactivation engine).

Two real bugs found and fixed here, both confirmed via direct testing before
the fix:

  1. No negation awareness at all -- "warranty nahi chahiye" (I don't want
     the warranty info) still matched "warranty" and got the warranty FAQ
     pitch; "exchange nahi karna mujhe" got the exchange pitch. Fixed with a
     word-proximity negation guard (clause-scoped, same discipline as
     webhook_reactivation.py's _is_explicit_optout()).
  2. Raw substring matching with no word-boundary check -- "main purana
     customer hoon" (I'm a returning customer) matched "custom" sitting
     inside "customer" and routed to the customization FAQ; "resale value
     kya hoga" matched "sale" inside "resale" and routed to the discount-
     offer pitch. Fixed by reusing _phrase_in_tokens()'s own padded-string
     word-boundary technique from webhook_reactivation.py.

Usage:
    python3 test_fresh_lead_direct_match.py
"""
import knowledge as k

_results = []


def check(label, text, expected):
    got = k.get_direct_match(k.fix_stt(text))
    ok = got == expected
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label:<70} -> {got!r} (expected {expected!r})")
    _results.append(ok)


def main():
    print("--- negation guard: decline should suppress the FAQ match ---")
    check("warranty decline suppressed", "warranty nahi chahiye", None)
    check("delivery decline suppressed", "delivery nahi chahiye mujhe", None)
    check("discount decline suppressed", "discount ki zaroorat nahi hai", None)
    check("exchange decline suppressed", "exchange nahi karna mujhe", None)
    check("emi decline suppressed (mat batao)", "emi mat batao", None)
    check("bare 'pata nahi' (don't know) not misread as address request",
          "मुझे पता नहीं है", None)
    check("negation in an earlier, unrelated clause doesn't suppress a real match",
          "sofa nahi bed chahiye, EMI hai kya", "payment_methods")
    check("repeated keyword-first-word, one negated + one legitimate in the same clause -- must still match (all() semantics, 2026-08-19 review fix)",
          "warranty nahi chahiye lekin warranty kitne saal ki hai batao", "warranty_quality")

    print("\n--- word-boundary guard: substring-inside-a-word must not match ---")
    check("'customer' must not trigger bare 'custom' -> customization",
          "main purana customer hoon", None)
    check("'resale' must not trigger bare 'sale' -> general_discount_offer",
          "resale value kya hoga", None)
    check("genuine 'custom' request still matches", "mujhe custom design chahiye", "customization")
    check("genuine 'sale' mention still matches", "flat 40% sale chal rahi hai kya", "general_discount_offer")

    print("\n--- legitimate matches must be unaffected by either fix ---")
    check("warranty question", "warranty kitne saal ki hai", "warranty_quality")
    check("emi question", "emi available hai kya", "payment_methods")
    check("delivery timing question", "delivery kab tak hogi", "delivery_delay")
    check("exchange process question", "exchange kaise hota hai", "exchange_offer")
    check("location question", "kahan hai aapka showroom", "store_location")
    check("payment method question", "cash accept karte ho", "payment_methods")
    check("manufacturing question", "kherki daula wali factory", "manufacturing")

    print("\n--- full keyword-map self-consistency sweep ---")
    mismatches = 0
    for kw, expected_cat in k.DIRECT_KEYWORD_MAP.items():
        got = k.get_direct_match(kw)
        if got != expected_cat:
            mismatches += 1
            print(f"  MISMATCH: {kw!r} -> {got} (expected {expected_cat})")
    ok = mismatches == 0
    print(f"[{'PASS' if ok else 'FAIL'}] {len(k.DIRECT_KEYWORD_MAP)} keywords self-resolve correctly ({mismatches} mismatches)")
    _results.append(ok)

    passed = sum(_results)
    total = len(_results)
    print(f"\n{'='*60}\n{passed}/{total} passed\n{'='*60}")
    return passed == total


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
