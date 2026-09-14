"""
new_flows_pricing.py
=====================
Canonical, owner-confirmed starting-price list for Krishna Furniture.

Source: owner-confirmed pricing sheet (Sep 2026) — NOT the website-observed
catalog (see knowledge.py's earlier product_specific_* comments for that
source; this one explicitly runs BELOW the website's listed prices per the
owner's own note, and is the number that should be quoted on calls).

This file was recreated from scratch on 2026-09-14. An earlier
new_flows_pricing.py existed (compiled evidence: __pycache__/
new_flows_pricing.cpython-312.pyc) but was never committed to git and was
lost in an untracked-file cleanup during an earlier revert-to-Sep-1 this
same day — it could not be recovered (checked all branches, both stashes,
VS Code local history, the June backup). The bytecode showed it imported
new_flows_config for category/price data and referenced grounding-safety
helpers (PricingRuleViolation, UnknownPriceListEntry,
reply_speaks_unconfirmed_price) but the actual price figures were not
recoverable from the compiled constants. This rewrite does not attempt to
reconstruct that module's architecture (config/capture/escalation split,
enums, dataclasses) since none of that was specified — it's deliberately
just the data plus the one safety helper (grounded price checking) that
matters for not letting a caller be quoted a number that isn't in this list.
"""

from __future__ import annotations

# Every price in INR (whole rupees). A category with on_request=True has NO
# confirmed number and must never be spoken as a figure -- only "on
# request"/"let me confirm and get back to you" style language.
PRICE_LIST: dict[str, dict] = {
    "sofas_seating": {
        "label": "Sofas & Seating",
        "hero": True,
        "subtypes": [
            "1_seater", "2_seater", "3_seater", "sectional",
            "l_shape", "u_shape", "chester", "sofa_cum_bed", "lounge_chair",
        ],
        "pricing_model": "per_seat",
        "prices": {
            "1_seater_min": 7000,
            "1_seater_max": 8000,
            "2_seater": 15000,
            "3_seater_min": 21000,
            "3_seater_max": 24000,
            "sofa_cum_bed": 35000,
        },
        "notes": (
            "Lounge chairs are a sub-type here with no distinct confirmed "
            "price -- do not quote a specific lounge-chair figure; fall "
            "back to the per-seat starting point (₹7,000-8,000) or say "
            "it needs confirming."
        ),
    },
    "living_room": {
        "label": "Living Room",
        "hero": True,
        "subtypes": ["tv_unit", "coffee_table", "center_table", "cabinet", "side_table"],
        "on_request": True,
        "notes": "No confirmed price for any sub-type as of 2026-09-14. Never quote a number for TV units, coffee/center tables, cabinets, or side tables.",
    },
    "beds_bedroom": {
        "label": "Beds & Bedroom",
        "hero": True,
        "subtypes": ["single_bed", "double_bed", "dressing_table"],
        "prices": {
            "single_bed": 15000,
            "double_bed": 25000,
            "dressing_table_min": 20000,
            "dressing_table_max": 25000,
        },
        "notes": (
            "This table has no confirmed price for a king-size / storage "
            "bed as a distinct line item -- only single and double. Do not "
            "quote a 'king size storage bed' price; the earlier "
            "website-observed figure for that is superseded and unconfirmed here."
        ),
    },
    "dining": {
        "label": "Dining",
        "hero": True,
        "subtypes": ["4_seater", "6_seater", "8_seater", "sheesham", "marble", "chairs"],
        "prices": {
            "sheesham_4_seater": 30000,
            "sheesham_6_seater": 40000,   # UNCONFIRMED, see caveat below
            "sheesham_8_seater": 50000,
            "marble_4_seater": 40000,
            "marble_6_seater": 65000,
            "marble_8_seater": 80000,
        },
        "unconfirmed": ["sheesham_6_seater"],
        "notes": (
            "sheesham_6_seater is a WORKING ASSUMPTION of ₹40,000, not a "
            "confirmed figure -- the source sheet itself flagged this "
            "('assumed ₹40k, you wrote 405K -- confirm'). Get an explicit "
            "owner confirmation before treating ₹40,000 (or any other "
            "figure) as settled for sheesham 6-seater specifically."
        ),
    },
    "storage_wardrobes": {
        "label": "Storage & Wardrobes",
        "hero": False,
        "subtypes": ["wardrobe", "wooden_wardrobe", "chest_of_drawers"],
        "prices": {
            "wardrobe": 25000,
            "wooden_wardrobe": 15000,
        },
    },
    "recliners": {
        "label": "Recliners",
        "hero": False,
        "subtypes": ["manual_recliner", "power_recliner"],
        "prices": {
            "manual": 25000,
            "recliner": 35000,
        },
    },
    "office_study": {
        "label": "Office & Study",
        "hero": False,
        "subtypes": ["office_chair", "office_table", "study_table"],
        "prices": {
            "office_chair": 6000,
            "office_table_min": 10000,
            "office_table_max": 12000,
        },
    },
    "mattresses": {
        "label": "Mattresses",
        "hero": False,
        "subtypes": ["single", "double"],
        "prices": {
            "single_min": 10000,
            "single_max": 12000,
            "double_min": 20000,
            "double_max": 25000,
        },
    },
    "outdoor_essentials": {
        "label": "Outdoor & Essentials",
        "hero": False,
        "subtypes": ["garden_swing", "table_chair_set"],
        "prices": {
            "garden_swing": 15000,
            "table_chair_set": 25000,
        },
    },
    "home_decor": {
        "label": "Home Décor",
        "hero": False,
        "subtypes": ["decor", "accessories"],
        "on_request": True,
        "notes": "No confirmed price for any decor/accessory item as of 2026-09-14.",
    },
}

# Categories the owner's sheet does not cover AT ALL (not even as
# on_request) -- the earlier website-observed catalog had numbers for these,
# but this owner-confirmed pass gave none, so they're unconfirmed rather
# than carried forward. Never speak a specific price for these; treat like
# on_request categories until a future price sheet actually includes them.
UNCOVERED_CATEGORIES = ["ottoman_pouffe", "bedroom_chair"]

SOURCE = "Owner-confirmed starting prices, Sep 2026 (Krishna_Furniture_Price_List_1.docx follow-up correction). Deliberately runs below the website-listed prices per the owner's own reconciliation note."


def _grounded_prices() -> set[int]:
    """Every whole-rupee figure in PRICE_LIST that's safe to speak as fact."""
    prices: set[int] = set()
    for cat in PRICE_LIST.values():
        for v in cat.get("prices", {}).values():
            prices.add(int(v))
    return prices


def reply_speaks_unconfirmed_price(reply_prices: "set[int] | list[int]") -> bool:
    """
    True if any of the given rupee figures (already extracted from a reply
    by the caller) is NOT in this price list's grounded set -- i.e. would be
    an unconfirmed/fabricated number if spoken. Deliberately takes already-
    extracted ints rather than parsing text itself, since text/regex parsing
    conventions differ across the fresh_lead vs reactivation flows (see
    knowledge.py's _PRICE_RE vs webhook_reactivation.py's own price-figure
    scanning) -- this stays a pure set-membership check either caller can use.
    """
    grounded = _grounded_prices()
    return any(int(p) not in grounded for p in reply_prices)
