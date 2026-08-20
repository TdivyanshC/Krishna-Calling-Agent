# -*- coding: utf-8 -*-
"""
Key-parity guard between the Hindi scripts (knowledge_react_abc.py) and their
English mirrors (knowledge_react_abc_en.py).

Recurring bug class (3+ incidents over the last 3 months, most recently
2026-08-20's obj_callback_time_noted/unclear): a key gets added to one
language's script dict and never mirrored into the other. Nothing caught this
until a live call hit "No text for key" in webhook_reactivation.py's
_resolve_key_url() and went silent. Every prior fix patched the one missing
key after the fact instead of adding a check that catches the *next* one
before it ships.

This test asserts, for every Hindi/English script pair the app actually
loads, that both sides have exactly the same key set. It does not check
content quality/translation accuracy -- only that a caller can never hit a
missing key in either language.

Usage:
    python3 test_script_key_parity.py
"""
import sys

from knowledge_react_abc import ALL_SCRIPTS, SHARED_SCRIPT, CALL2_SCRIPT, CALL3_SCRIPT
from knowledge_react_abc_en import ALL_SCRIPTS_EN, SHARED_SCRIPT_EN, CALL2_SCRIPT_EN, CALL3_SCRIPT_EN


def check_pair(name: str, hi: dict, en: dict) -> list[str]:
    hi_keys, en_keys = set(hi), set(en)
    missing_in_en = hi_keys - en_keys
    missing_in_hi = en_keys - hi_keys
    problems = []
    if missing_in_en:
        problems.append(f"  {name}: missing in EN: {sorted(missing_in_en)}")
    if missing_in_hi:
        problems.append(f"  {name}: missing in HI (EN-only, orphaned or HI regressed): {sorted(missing_in_hi)}")
    return problems


def main() -> int:
    problems = []

    problems += check_pair("SHARED_SCRIPT", SHARED_SCRIPT, SHARED_SCRIPT_EN)
    problems += check_pair("CALL2_SCRIPT", CALL2_SCRIPT, CALL2_SCRIPT_EN)
    problems += check_pair("CALL3_SCRIPT", CALL3_SCRIPT, CALL3_SCRIPT_EN)

    for campaign in ALL_SCRIPTS:
        hi = ALL_SCRIPTS[campaign]
        en = ALL_SCRIPTS_EN.get(campaign)
        if en is None:
            problems.append(f"  ALL_SCRIPTS_EN: campaign '{campaign}' has no English script at all")
            continue
        problems += check_pair(f"ALL_SCRIPTS[{campaign}]", hi, en)

    for campaign in ALL_SCRIPTS_EN:
        if campaign not in ALL_SCRIPTS:
            problems.append(f"  ALL_SCRIPTS: campaign '{campaign}' exists in EN only")

    if problems:
        print(f"FAIL: {len(problems)} key-parity gap(s) between Hindi and English scripts:\n")
        print("\n".join(problems))
        print(
            "\nEvery key here will hit \"No text for key\" and go silent on a live "
            "call for whichever language is missing it. Add the missing side's "
            "text (and generate its TTS audio) before merging."
        )
        return 1

    total = len(SHARED_SCRIPT) + len(CALL2_SCRIPT) + len(CALL3_SCRIPT) + sum(len(v) for v in ALL_SCRIPTS.values())
    print(f"PASS: {total} Hindi keys all have English mirrors (and vice versa) across "
          f"SHARED_SCRIPT, CALL2_SCRIPT, CALL3_SCRIPT, and {len(ALL_SCRIPTS)} campaign scripts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
