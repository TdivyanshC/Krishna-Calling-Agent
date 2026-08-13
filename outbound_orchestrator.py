"""
outbound_orchestrator.py
========================
Place in: /home/voiceagent/voice-ai/outbound_orchestrator.py

Fires calls via webhook.py's /trigger-call endpoint (already built).
Handles IST window, concurrency, and the day1/2/4/7 pickup-attempt cadence.

Start:
    nohup python3 outbound_orchestrator.py > logs/orchestrator.log 2>&1 &

Or via systemd (recommended).
"""

import asyncio
import logging
import os
import httpx
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from groq_normalize import ai_normalize_visit_date

load_dotenv("/home/voiceagent/voice-ai/.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ORCH] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
IST               = ZoneInfo("Asia/Kolkata")
SUPABASE_URL      = os.getenv("SUPABASE_URL")
SUPABASE_KEY      = os.getenv("SUPABASE_SERVICE_KEY")   # service_role key
TENANT_ID         = os.getenv("TENANT_ID", "krishna_furniture")
WEBHOOK_BASE_URL  = os.getenv("WEBHOOK_BASE_URL", "https://voice.thesocialhood.in")
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "2"))
FUNNEL_TYPE       = os.getenv("FUNNEL_TYPE", "fresh_lead")     # "reactivation" for reactivation campaign

# Test-run isolation valve — when set, EVERY selection lane below (get_due_leads,
# get_due_fresh_leads, get_wa_decline_leads, get_due_walkin_followup_leads) is
# additionally scoped to this one batch_id, so a test batch can be dialed
# without any other due lead (old backlog included) being able to fire in the
# same tick. Unset (the default) changes nothing — no code path is affected.
ORCHESTRATOR_TEST_BATCH = os.getenv("ORCHESTRATOR_TEST_BATCH", "").strip()

CALL_START_HOUR = 10   # 10:00 AM IST, all funnels
# fresh_cta (first-contact outreach) gets the wider 10-22 window; everything
# else (the FUNNEL_TYPE-based reactivation/fresh_lead lane, wa-decline
# confirms, walk-in follow-ups) is clamped tighter to 10-20 -- a late-evening
# call reads as more intrusive on a repeat contact than a first touch.
CALL_END_HOUR_BY_FUNNEL = {
    "fresh_cta": 22,   # 10:00 PM IST
}
CALL_END_HOUR_DEFAULT = 20   # 8:00 PM IST
# Latest possible end hour across all funnels -- used only for tick()'s cheap
# "is it the dead-of-night zone" early exit, not as an actual per-funnel bound.
CALL_END_HOUR_LATEST = max(CALL_END_HOUR_BY_FUNNEL.values(), default=CALL_END_HOUR_DEFAULT)
CALL_END_HOUR_LATEST = max(CALL_END_HOUR_LATEST, CALL_END_HOUR_DEFAULT)

# Dispatch plumbing is live (get_due_walkin_followup_leads() below, wired into
# tick()) but webhook.py's /answer-outbound has no campaign=="walkin_followup"
# branch yet — a dispatched call would fall through to the generic greeting,
# not a walk-in-specific script. Keep off until that branch exists. Campaign
# row already exists in Supabase with status='active' (created by
# walkin_followup.py's _ensure_walkin_followup_campaign()), so this flag is
# the only thing standing between "queued" and "actually dialed."
WALKIN_FOLLOWUP_DISPATCH_ENABLED = False

# Pickup-attempt cadence (tracked via pickup_attempt_count; unanswered calls only):
#   Day 1: morning + evening  (attempts 1-2)
#   Day 2: morning + evening  (attempts 3-4)
#   Day 4: morning + evening  (attempts 5-6)
#   Day 7: morning + evening  (attempts 7-8)
#   attempt 8 still unanswered -> dnc
# Gaps below are RELATIVE (days after the previous pair finishes) — there is no
# anchor timestamp for "lead's first attempt" in the current schema, so this is
# reconstructed purely from pickup_attempt_count parity/pair-index. See caveat
# in schedule_retry_or_dnc().
PICKUP_MORNING_HOUR, PICKUP_MORNING_MINUTE = 10, 30   # 10:30 IST
PICKUP_EVENING_HOUR, PICKUP_EVENING_MINUTE = 19, 30   # 19:30 IST

# Pickup-attempt cadence, keyed by funnel_type (looked up by the caller and
# passed into schedule_retry_or_dnc() — see its docstring — rather than
# hardcoded, so each funnel's cadence stays independently readable/editable
# without duplicating the function itself).
#   pair_gap_days[p] = days until pair p+1's morning slot, once pair p just finished
#   max_attempts     = total unanswered attempts before dnc
#
# Business decision 2026-08-10: reactivation/fresh_cta redesigned from fixed
# 10:30/19:30 clock slots + flat 1-day pair gaps to "4 hours after a failed
# attempt (same day if it fits the window), max 2/day, then growing 1/2/3-day
# gaps between pairs" -- see compute_retry_schedule(). max_attempts raised
# 6->8 to fit 4 full pairs (1 initial + 3 more at growing gaps); the
# pickup_attempt_count<4 hard backstop in get_due_leads()/get_due_fresh_leads()
# was raised to <8 to match, otherwise it would silently cap leads at 4
# attempts regardless of this cadence. walkin_followup is unchanged (out of
# scope for this redesign).
PICKUP_CADENCE = {
    # same_day_gap_hours: 2026-08-12 business decision (reactivation only) --
    # first pass dials every untouched lead; the fresh-leads-first priority
    # in get_due_leads() means retries can't get a slot until that first
    # pass is fully exhausted, so this gap is really "how long the
    # orchestrator sits idle between the end of pass 1 and the start of
    # pass 2 (no-answers only -- anyone who had a real conversation is on
    # the separate answered_no_date_count cadence, not this one)." Narrowed
    # from 4h to 1h; fresh_cta/walkin_followup untouched at 4h since this
    # wasn't discussed for them.
    "reactivation":    {"pair_gap_days": {1: 1, 2: 2, 3: 3}, "max_attempts": 8, "same_day_gap_hours": 1},
    "fresh_cta":       {"pair_gap_days": {1: 1, 2: 2, 3: 3}, "max_attempts": 8, "same_day_gap_hours": 4},
    "walkin_followup": {"pair_gap_days": {1: 1, 2: 1}, "max_attempts": 3, "same_day_gap_hours": 4},  # cap: 3 calls per walk-in (walkin_followup.py)
}
DEFAULT_PICKUP_CADENCE = "reactivation"  # used for any funnel_type not in PICKUP_CADENCE (incl. None)

POLL_INTERVAL = 20   # seconds

FRESH_CTA_CAMPAIGN_ID = "8fab0334-6d8c-4b71-be72-9d170c8ad3fc"

# Cutoff for detect_and_schedule_fresh_leads(): only contacts created AFTER
# this process started are eligible for the new 5-hour-first-call detector.
# Captured once at import time (≈ deploy/restart time), not recomputed per
# tick or per calendar day — deliberately excludes the pre-existing backlog
# of old contacts (53/73 at the time this was written) that have no
# outbound_leads row today; backfilling those would immediately queue real
# calls to people who messaged days ago, not "5 hours ago." Anything older
# than this cutoff is simply never touched by this detector.
FRESH_LEAD_DETECTOR_STARTED_AT = datetime.now(timezone.utc)


# ── Supabase helpers ──────────────────────────────────────────────────────────

def sb_headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def _real_interest(value: str | None) -> str | None:
    """
    leads.interested_in is sometimes the literal string "null" (upstream
    n8n/WhatsApp write bug — a template producing text from a JS/JSON null
    instead of omitting the field) rather than a real SQL NULL. A bare
    truthiness/non-null check doesn't catch this — treat both as "no value"
    wherever this field feeds a backfill or dispatch decision.
    """
    if not value:
        return None
    return None if value.strip().lower() == "null" else value


async def get_active_campaign_ids(client: httpx.AsyncClient) -> list[str]:
    """
    Active campaign IDs for this tenant — gates get_due_leads() so a paused
    (or missing) campaign stops dialing immediately, full stop.

    NOTE: a lead with campaign_id = NULL is treated the SAME as a lead tied to
    a non-active campaign — i.e. NULL is excluded too (explicit choice, not a
    default). Right now there is exactly one campaign row in the whole
    `campaigns` table and its status is 'paused', so until a campaign exists
    with status='active', this returns [] and get_due_leads() short-circuits
    to no leads at all — including the ~30 leads that currently have no
    campaign_id assigned.
    """
    url = (
        f"{SUPABASE_URL}/rest/v1/campaigns"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&status=eq.active"
        f"&select=id"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200:
        log.error(f"get_active_campaign_ids failed: {r.status_code} {r.text[:200]}")
        return []
    return [row["id"] for row in r.json()]


async def get_due_leads(client: httpx.AsyncClient, slots: int, active_campaign_ids: list[str]) -> list[dict]:
    """
    Fetch leads ready to call (normal pickup/no-date cadence), untouched
    leads always filling slots ahead of retries.

    2026-08-12: previously a single query mixed status=pending (never
    dialed) with status=unanswered/mid_answered (retry-due) in one
    order=created_at.asc list. created_at reflects insertion time, not
    "how overdue is this retry" -- a growing retry backlog from an older
    batch could sit ahead of a brand-new untouched batch indefinitely,
    since both are ordered by the same clock. Confirmed live: 100+ leads in
    batch_02_p1 sat completely untouched for days while retries from
    batch_full_remainder kept consuming both concurrency slots every tick.
    Split into two tiers so that can't happen again: tier 1 (status=pending,
    i.e. genuinely never contacted) always fills as many slots as it can;
    retries only get whatever's left over. As long as any untouched lead
    exists anywhere in scope, retries get zero slots that tick.
    """
    if not active_campaign_ids:
        return []

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    campaign_in = ",".join(active_campaign_ids)
    _test_batch_clause = f"&batch_id=eq.{ORCHESTRATOR_TEST_BATCH}" if ORCHESTRATOR_TEST_BATCH else ""

    fresh_url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&funnel_type=in.({FUNNEL_TYPE})"
        f"&status=eq.pending"
        f"&pickup_attempt_count=eq.0"
        f"&dnc=eq.false"
        f"&visit_date_status=is.null"
        f"&campaign_id=in.({campaign_in})"
        f"&or=(cooldown_until.is.null,cooldown_until.lte.{now_iso})"
        f"{_test_batch_clause}"
        f"&order=created_at.asc"
        f"&limit={slots}"
    )
    r = await client.get(fresh_url, headers=sb_headers())
    if r.status_code != 200:
        log.error(f"get_due_leads (fresh tier) failed: {r.status_code} {r.text[:200]}")
        fresh = []
    else:
        fresh = r.json()

    remaining = slots - len(fresh)
    if remaining <= 0:
        return fresh

    # Tier 2: retries. Same pickup_attempt_count<8 backstop as before,
    # matching PICKUP_CADENCE's max_attempts=8 for reactivation/fresh_cta.
    retry_url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&funnel_type=in.({FUNNEL_TYPE})"
        f"&status=in.(unanswered,mid_answered)"
        f"&dnc=eq.false"
        f"&visit_date_status=is.null"
        f"&campaign_id=in.({campaign_in})"
        f"&or=(cooldown_until.is.null,cooldown_until.lte.{now_iso})"
        f"&pickup_attempt_count=lt.8"
        f"{_test_batch_clause}"
        f"&order=created_at.asc"
        f"&limit={remaining}"
    )
    r2 = await client.get(retry_url, headers=sb_headers())
    if r2.status_code != 200:
        log.error(f"get_due_leads (retry tier) failed: {r2.status_code} {r2.text[:200]}")
        retries = []
    else:
        retries = r2.json()

    return fresh + retries


async def get_due_fresh_leads(client: httpx.AsyncClient, slots: int, active_campaign_ids: list[str]) -> list[dict]:
    """
    Fetch fresh_cta leads ready to call — same filter shape as get_due_leads(),
    just funnel_type='fresh_cta' hardcoded instead of the FUNNEL_TYPE env var.
    Kept as its own function rather than folded into get_due_leads() so each
    funnel's selection logic stays independently readable (same principle as
    get_active_campaign_ids() being its own function rather than inlined).

    NOTE on "oldest-fire_at-due first": outbound_leads has no fire_at column
    of its own — that lives on scheduled_actions. promote_due_scheduled_actions()
    processes due scheduled_actions oldest-fire_at-first and creates the
    corresponding outbound_leads rows in that same order, so order=created_at.asc
    here is a proxy for fire_at order, not a literal re-sort of it. If promotion
    and dispatch ever drift out of the same tick, this proxy would drift too.
    """
    if not active_campaign_ids:
        return []

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    campaign_in = ",".join(active_campaign_ids)
    _test_batch_clause = f"&batch_id=eq.{ORCHESTRATOR_TEST_BATCH}" if ORCHESTRATOR_TEST_BATCH else ""
    url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&funnel_type=eq.fresh_cta"
        f"&status=in.(pending,unanswered,mid_answered)"
        f"&dnc=eq.false"
        f"&visit_date_status=is.null"
        f"&product_interest=not.is.null"
        f"&campaign_id=in.({campaign_in})"
        f"&or=(cooldown_until.is.null,cooldown_until.lte.{now_iso})"
        f"&pickup_attempt_count=lt.8"  # matches PICKUP_CADENCE's fresh_cta max_attempts=8 (2026-08-10)
        f"{_test_batch_clause}"
        f"&order=created_at.asc"
        f"&limit={slots}"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200:
        log.error(f"get_due_fresh_leads failed: {r.status_code} {r.text[:200]}")
        return []
    return r.json()


async def get_due_walkin_followup_leads(client: httpx.AsyncClient, slots: int, active_campaign_ids: list[str]) -> list[dict]:
    """
    Fetch walkin_followup leads ready to call — same filter shape as
    get_due_fresh_leads(), just funnel_type='walkin_followup' hardcoded.
    Rows are created explicitly by walkin_followup.py's
    schedule_next_walkin_followup_call() (no auto-fire timing), so this is
    a no-op (empty list) unless something has actually queued a walk-in
    follow-up. Lowest dispatch priority — see tick().
    """
    if not active_campaign_ids:
        return []

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    campaign_in = ",".join(active_campaign_ids)
    _test_batch_clause = f"&batch_id=eq.{ORCHESTRATOR_TEST_BATCH}" if ORCHESTRATOR_TEST_BATCH else ""
    url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&funnel_type=eq.walkin_followup"
        f"&status=in.(pending,unanswered,mid_answered)"
        f"&dnc=eq.false"
        f"&campaign_id=in.({campaign_in})"
        f"&or=(cooldown_until.is.null,cooldown_until.lte.{now_iso})"
        f"{_test_batch_clause}"
        f"&order=created_at.asc"
        f"&limit={slots}"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200:
        log.error(f"get_due_walkin_followup_leads failed: {r.status_code} {r.text[:200]}")
        return []
    return r.json()


async def promote_due_scheduled_actions(client: httpx.AsyncClient):
    """
    Promotes due scheduled_actions rows into outbound_leads so they become
    callable. Does NOT dispatch calls itself — whatever this creates gets
    picked up by get_due_fresh_leads() later in the SAME tick (see tick()).

    OPEN QUESTIONS not resolved here, flagged rather than guessed at:
      - scheduled_actions currently has 0 rows (checked live), so there's no
        data to confirm whether ALL action_type values should promote to a
        fresh_cta outbound_leads row, or only some. No action_type filter is
        applied below — if this table is shared with other automations
        (e.g. WhatsApp reminders), this needs a filter added.
      - scheduled_actions has no tenant_id column (unlike every other table
        this codebase writes to), so this query is tenant-agnostic — not
        fixable from this side without a schema change.
      - contacts has no `name` column (only id, phone, created_at — confirmed
        via schema) — name is resolved via a separate lookup into `leads` by
        contact_id, which may not have a matching row for every contact; if
        not, name is left as "".
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"{SUPABASE_URL}/rest/v1/scheduled_actions"
        f"?status=eq.pending"
        f"&fire_at=lte.{now_iso}"
        f"&order=fire_at.asc"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200:
        log.error(f"promote_due_scheduled_actions fetch failed: {r.status_code} {r.text[:200]}")
        return
    due = r.json()
    if not due:
        return

    log.info(f"Promoting {len(due)} due scheduled_action(s)")

    for action in due:
        contact_id = action.get("contact_id")
        row_phone  = action.get("phone")
        flip_field = "contact_id"
        flip_value = contact_id

        if not contact_id:
            if not row_phone:
                log.error("promote_due_scheduled_actions: due row has no contact_id and no phone — cannot resolve or flip, skipping")
                continue
            up_r = await client.post(
                f"{SUPABASE_URL}/rest/v1/contacts",
                headers={**sb_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
                params={"on_conflict": "phone"},
                json={"phone": row_phone},
            )
            if up_r.status_code not in (200, 201) or not up_r.json():
                log.error(f"promote_due_scheduled_actions: failed to resolve/create contact for phone {row_phone}: {up_r.status_code} {up_r.text[:200]}")
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/scheduled_actions?phone=eq.{row_phone}&status=eq.pending",
                    headers=sb_headers(),
                    json={"status": "failed"},
                )
                continue
            contact_id = up_r.json()[0]["id"]
            flip_field = "phone"
            flip_value = row_phone
            log.info(f"promote_due_scheduled_actions: resolved contact_id {contact_id} from phone {row_phone}")

        _final_status = "fired"  # overwritten to "failed" below on either recoverable error

        # Resolve phone up front (not just inside the create branch below) —
        # the phone-based duplicate check right after this needs it too.
        phone = None
        c_r = await client.get(
            f"{SUPABASE_URL}/rest/v1/contacts",
            headers=sb_headers(),
            params={"id": f"eq.{contact_id}", "select": "phone", "limit": "1"},
        )
        if c_r.status_code == 200 and c_r.json():
            phone = c_r.json()[0].get("phone")

        # Avoid duplicate promotion — skip creating a new outbound_leads row
        # if one already exists for this contact (from this or any funnel).
        existing = await client.get(
            f"{SUPABASE_URL}/rest/v1/outbound_leads",
            headers=sb_headers(),
            params={"contact_id": f"eq.{contact_id}", "select": "id", "limit": "1"},
        )
        existing_rows = existing.json() if existing.status_code == 200 else []

        # Fallback guard: the contact_id check above only catches rows that
        # already went through this codebase's contact-linkage path. It
        # misses a row created some other way (e.g. a bulk campaign import)
        # for the SAME phone but with no/different contact_id — confirmed
        # live 2026-07-17: a reactivation lead bulk-imported as
        # '+919810649832' (contact_id left null) got a second, independent
        # fresh_cta row created here for '919810649832' because this check
        # never looked at phone at all. Same bare/plus-prefixed variants
        # pattern used everywhere else in this codebase for phone lookups
        # (outbound_leads.phone is stored inconsistently across write
        # paths) — built via params= rather than spliced into the URL so
        # httpx percent-encodes '+' correctly (a raw '+' in a query string
        # is parsed as a space by PostgREST otherwise).
        if not existing_rows and phone:
            phone_bare = phone.lstrip("+")
            phone_or = ",".join(f"phone.eq.{v}" for v in {phone, phone_bare, f"+{phone_bare}"})
            phone_existing = await client.get(
                f"{SUPABASE_URL}/rest/v1/outbound_leads",
                headers=sb_headers(),
                params={"or": f"({phone_or})", "select": "id,contact_id", "limit": "1"},
            )
            if phone_existing.status_code == 200 and phone_existing.json():
                existing_rows = phone_existing.json()
                log.warning(
                    f"promote_due_scheduled_actions: contact {contact_id} (phone {phone}) matched "
                    f"existing outbound_leads row {existing_rows[0]['id']} by PHONE only (its "
                    f"contact_id={existing_rows[0].get('contact_id')} differs) — skipping create to "
                    f"avoid duplicating this lead across funnels"
                )

        if existing_rows:
            log.info(f"scheduled_action for contact {contact_id}: outbound_leads row already exists — marking fired, skipping create")
        else:
            name    = ""
            product = None

            # NOTE on product: `interested_in` is a guess among several equally
            # plausible, equally-unpopulated leads columns (furniture_interest,
            # selected_product_name, liked_product_1) — every one of the 45
            # current leads rows has source='ai_call' (this codebase's own
            # call-log linkage writer) and 0/45 populated on ANY of them, so
            # this lookup returns None for every contact today regardless of
            # which field name is used here. Whatever actually writes
            # WhatsApp-sourced product interest — possibly not `leads` at all;
            # `whatsapp_conversations` (raw per-message log, content/context
            # jsonb, keyed by lead_id) exists as a candidate source but isn't
            # queried here since task 4b scoped this to the leads/contacts
            # join specifically — needs to land somewhere before this ever
            # resolves to a real value.
            l_r = await client.get(
                f"{SUPABASE_URL}/rest/v1/leads",
                headers=sb_headers(),
                params={"contact_id": f"eq.{contact_id}", "select": "name,interested_in", "limit": "1"},
            )
            if l_r.status_code == 200 and l_r.json():
                row     = l_r.json()[0]
                name    = row.get("name") or ""
                product = _real_interest(row.get("interested_in"))
            else:
                # No matching leads row for this contact_id — the outbound_leads
                # row about to be created below will have blank name/product with
                # no way to backfill later (confirmed live: this is exactly how
                # 919198310770 ended up permanently stuck with no interest data
                # anywhere in the system). Not a behavior change — still creates
                # the row the same way — just surfaces the case instead of
                # silently producing an orphaned row.
                log.warning(
                    f"promote_due_scheduled_actions: no leads row found for contact_id "
                    f"{contact_id} — creating outbound_leads row with blank name/product_interest"
                )

            if not phone:
                log.error(f"scheduled_action for contact {contact_id}: no resolvable phone via contacts — marking failed, skipping promotion")
                _final_status = "failed"
            else:
                create_r = await client.post(
                    f"{SUPABASE_URL}/rest/v1/outbound_leads",
                    headers=sb_headers(),
                    json={
                        "tenant_id":        TENANT_ID,
                        "contact_id":       contact_id,
                        "phone":            phone,
                        "name":             name,
                        "funnel_type":      "fresh_cta",
                        "campaign_type":    "fresh_cta",
                        "campaign_id":      FRESH_CTA_CAMPAIGN_ID,
                        "product_interest": product,
                        "status":           "pending",
                    },
                )
                if create_r.status_code not in (200, 201):
                    log.error(f"promote_due_scheduled_actions: create failed for contact {contact_id}: {create_r.status_code} {create_r.text[:200]}")
                    _final_status = "failed"
                else:
                    log.info(f"Promoted scheduled_action → outbound_leads for contact {contact_id}")

        # Flip regardless of branch above — created, already existed, or hit a
        # recoverable error — so this contact's due action is never
        # re-evaluated on a future tick. 'failed' (not 'fired') marks the two
        # recoverable error cases for manual review, distinct from a real
        # success or an already-existing lead.
        flip_r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/scheduled_actions?{flip_field}=eq.{flip_value}",
            headers=sb_headers(),
            json={"status": _final_status},
        )
        if flip_r.status_code not in (200, 204):
            log.error(f"promote_due_scheduled_actions: failed to flip {_final_status} for contact {contact_id}: {flip_r.status_code}")


async def detect_and_schedule_fresh_leads(client: httpx.AsyncClient):
    """
    Detects brand-new WhatsApp contacts — rows in `contacts` with no matching
    `outbound_leads` row yet, from ANY funnel_type/source — and schedules
    their first fresh_cta call for exactly 5 hours after the contact was
    created, clamped to fresh_cta's 10:00-22:00 IST calling window.

    This is a NEW, deterministic path this codebase fully owns. It does NOT
    replace promote_due_scheduled_actions() above, which keeps running
    unchanged for whatever n8n still schedules via scheduled_actions. Both
    paths write into the same outbound_leads table and are mutually
    exclusive by construction: the "no matching outbound_leads row" check
    below is the same existence check promote_due_scheduled_actions() already
    does before creating its own row — whichever path gets to a given
    contact first, the other finds a row already exists and skips it. No
    conflict, no duplicate calls, no ordering dependency between the two.

    Only contacts created AFTER FRESH_LEAD_DETECTOR_STARTED_AT (this
    process's start time) are eligible — see that constant's comment for why
    the pre-existing backlog is deliberately excluded rather than backfilled.

    Query technique: a single PostgREST embed + `is.null` filter expresses
    the LEFT JOIN / NOT EXISTS pattern in one request (verified live against
    this schema — outbound_leads.contact_id's FK to contacts.id is detected
    by PostgREST), rather than the per-row existence-check loop
    promote_due_scheduled_actions() uses above (that loop pre-dates this
    function and was written against scheduled_actions rows one at a time;
    no need to match that shape here when a single query does the job).
    """
    cutoff_iso = FRESH_LEAD_DETECTOR_STARTED_AT.strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"{SUPABASE_URL}/rest/v1/contacts"
        f"?select=id,phone,created_at,outbound_leads(id)"
        f"&outbound_leads=is.null"
        f"&created_at=gt.{cutoff_iso}"
        f"&order=created_at.asc"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200:
        log.error(f"detect_and_schedule_fresh_leads fetch failed: {r.status_code} {r.text[:200]}")
        return
    new_contacts = r.json()
    if not new_contacts:
        return

    log.info(f"detect_and_schedule_fresh_leads: {len(new_contacts)} brand-new contact(s) with no outbound_leads row")

    for contact in new_contacts:
        contact_id = contact["id"]
        raw_phone  = contact.get("phone") or ""
        if not raw_phone:
            log.error(f"detect_and_schedule_fresh_leads: contact {contact_id} has no phone — skipping")
            continue
        # contacts.phone never carries a '+' prefix (confirmed live), but
        # outbound_leads.phone is dialed verbatim by /trigger-call and looked
        # up elsewhere assuming '+' — normalize here rather than propagate
        # the same phone-format bug promote_due_scheduled_actions() has
        # (that function inserts contacts.phone into outbound_leads.phone
        # as-is, with no '+' — flagged separately, not fixed here since it's
        # out of this task's scope).
        phone = raw_phone if raw_phone.startswith("+") else f"+{raw_phone}"

        created_dt_utc = datetime.fromisoformat(contact["created_at"].replace("Z", "+00:00"))
        # Business decision 2026-08-05: first-touch moved from +5h to +20min --
        # was originally 5h to avoid looking too automated/immediate; now
        # deliberately fast so the WhatsApp CTA a real call can trigger
        # (fire_whatsapp(), see webhook_reactivation.py) lands close to the
        # actual inquiry instead of hours later.
        target_ist = created_dt_utc.astimezone(IST) + timedelta(minutes=20)

        # This schedules a fresh_cta call specifically (see docstring) — use
        # fresh_cta's own 10-22 bound, not the tighter reactivation default.
        _fresh_cta_end_hour = CALL_END_HOUR_BY_FUNNEL.get("fresh_cta", CALL_END_HOUR_DEFAULT)
        if target_ist.hour < CALL_START_HOUR:
            target_ist = target_ist.replace(hour=CALL_START_HOUR, minute=0, second=0, microsecond=0)
        elif target_ist.hour >= _fresh_cta_end_hour:
            target_ist = (target_ist + timedelta(days=1)).replace(hour=CALL_START_HOUR, minute=0, second=0, microsecond=0)
        # else: leave as computed — already inside the calling window

        cooldown_until_utc = target_ist.astimezone(timezone.utc).isoformat()

        create_r = await client.post(
            f"{SUPABASE_URL}/rest/v1/outbound_leads",
            headers=sb_headers(),
            json={
                "tenant_id":      TENANT_ID,
                "contact_id":     contact_id,
                "phone":          phone,
                "funnel_type":    "fresh_cta",
                "campaign_type":  "fresh_cta",
                "campaign_id":    FRESH_CTA_CAMPAIGN_ID,
                "status":         "pending",
                "cooldown_until": cooldown_until_utc,
            },
        )
        if create_r.status_code not in (200, 201):
            log.error(f"detect_and_schedule_fresh_leads: create failed for contact {contact_id}: {create_r.status_code} {create_r.text[:200]}")
        else:
            log.info(f"detect_and_schedule_fresh_leads: scheduled contact={contact_id} phone={phone} fire_at={cooldown_until_utc}")


async def sync_whatsapp_visit_dates(client: httpx.AsyncClient):
    """
    Syncs WhatsApp-confirmed visit dates into outbound_leads, so the existing
    visit_date_status IS NULL dispatch filter (get_due_leads/get_due_fresh_leads)
    correctly excludes leads who already confirmed a visit date over WhatsApp,
    not just over a call. Without this, a lead who told the WhatsApp bot
    "Sunday" still shows visit_date_status=NULL in outbound_leads and gets
    auto-called by fresh_cta despite already having a confirmed date — this
    was confirmed live on two real leads (919891984799, 919818428944) before
    this function existed.

    Status vocabulary: leads.visit_date_status uses 'expected' for a
    WhatsApp-confirmed date (confirmed live via SELECT DISTINCT on leads and
    lead_full_details — 'expected' is the only non-null value in either
    table, nothing else like 'declined'/'tentative' exists to exclude).
    outbound_leads uses a DIFFERENT word for the same real-world state —
    'confirmed' — written today only by the call-based path (see
    supabase_calling.py finalize_call(), the appointment_confirmed branch).
    This function writes 'confirmed' into outbound_leads, NOT 'expected' —
    matching the vocabulary the dispatch filter and the rest of the system
    already expect, not inventing a third value.

    Phone matching: leads.phone never carries a '+' prefix (same as
    contacts/whatsapp_conversations), but outbound_leads.phone is mixed —
    some rows have '+', some don't (the same promote_due_scheduled_actions()
    normalization gap noted in detect_and_schedule_fresh_leads()'s docstring
    — confirmed live on these exact two rows, neither has '+') — so both
    phone forms are matched via an `or=` filter, same defensive pattern
    webhook.py's /answer already uses for inbound reactivation lookups.

    Idempotent by construction: the visit_date_status=is.null filter in the
    PATCH itself means a lead already synced (or already call-confirmed)
    simply matches zero rows on the next tick — no extra bookkeeping needed.

    Date normalization: leads.visit_date holds whatever raw text the WhatsApp
    bot captured ("Sunday", "kal", "6 august") — not a SQL date literal.
    outbound_leads.visit_date IS a real `date` column, so writing the raw
    text through unnormalized fails Postgres's type check on every single
    tick forever (confirmed live: 620+ repeats logged for two leads whose
    text was "Sunday" / "On Saturday", dating back to whenever this function
    first ran against them). Run the same ai_normalize_visit_date() the
    call-based path already uses (supabase_calling.py's finalize_call(),
    appointment_confirmed branch) before writing. If it can't resolve a
    confident date, still flip visit_date_status='confirmed' (the WhatsApp
    confirmation itself is real — that's what stops fresh_cta/reactivation
    from re-dialing this lead) and just leave visit_date null, rather than
    retrying the same unparseable text forever.
    """
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/leads",
        headers=sb_headers(),
        params={"visit_date_status": "eq.expected", "select": "phone,visit_date"},
    )
    if r.status_code != 200:
        log.error(f"sync_whatsapp_visit_dates: leads fetch failed: {r.status_code} {r.text[:200]}")
        return
    confirmed_leads = r.json()
    if not confirmed_leads:
        return

    for lead in confirmed_leads:
        phone = (lead.get("phone") or "").strip()
        if not phone:
            continue

        # Skip the Groq call entirely if outbound_leads is already synced for
        # this phone -- the PATCH below is guarded by visit_date_status=is.null
        # and would no-op anyway, but that guard only protects the WRITE, not
        # the expensive work before it. leads.visit_date_status never
        # transitions away from 'expected' once processed (no code path does
        # that), so without this check the same already-synced phones get
        # re-fetched AND re-sent to Groq every single tick forever. Confirmed
        # live 2026-07-28: this drove sustained 429 rate-limiting against the
        # same Groq account finalize_call()'s own real appointment-date
        # normalization depends on, for two phones already synced days
        # earlier. One cheap GET here replaces one Groq round-trip + its
        # retry/backoff every tick, for every already-synced phone.
        phone_variants_check = {phone, phone if phone.startswith("+") else f"+{phone}"}
        phone_or_check = ",".join(f"phone.eq.{v}" for v in phone_variants_check)
        check_r = await client.get(
            f"{SUPABASE_URL}/rest/v1/outbound_leads",
            headers=sb_headers(),
            params={"or": f"({phone_or_check})", "select": "visit_date_status", "limit": "1"},
        )
        if check_r.status_code == 200:
            existing_rows = check_r.json()
            if existing_rows and existing_rows[0].get("visit_date_status"):
                continue  # already synced -- nothing to do, skip the Groq call

        visit_date_raw = lead.get("visit_date")

        parsed_date = None
        if visit_date_raw:
            try:
                parsed_date = await ai_normalize_visit_date(
                    visit_date_raw, datetime.now(timezone.utc).isoformat()
                )
            except Exception as e:
                log.error(f"sync_whatsapp_visit_dates: visit_date parse error for {phone}: {e} | raw={visit_date_raw!r}")
            if not parsed_date:
                log.warning(
                    f"sync_whatsapp_visit_dates: {phone} visit_date_raw={visit_date_raw!r} "
                    f"could not be resolved confidently — visit_date left null, "
                    f"visit_date_status still set to 'confirmed'"
                )

        phone_variants = {phone, phone if phone.startswith("+") else f"+{phone}"}
        phone_or = ",".join(f"phone.eq.{v}" for v in phone_variants)

        update_payload = {"visit_date_status": "confirmed"}
        if parsed_date:
            update_payload["visit_date"] = parsed_date

        patch_r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/outbound_leads",
            headers=sb_headers(),
            params={"or": f"({phone_or})", "visit_date_status": "is.null"},
            json=update_payload,
        )
        if patch_r.status_code not in (200, 204):
            log.error(f"sync_whatsapp_visit_dates: patch failed for {phone}: {patch_r.status_code} {patch_r.text[:200]}")
            continue
        updated = patch_r.json() if patch_r.status_code == 200 else []
        if updated:
            log.info(
                f"sync_whatsapp_visit_dates: {phone} -> visit_date_status=confirmed on "
                f"{len(updated)} outbound_leads row(s), visit_date={parsed_date!r} (raw={visit_date_raw!r})"
            )


async def get_wa_decline_leads(client: httpx.AsyncClient, slots: int, active_campaign_ids: list[str]) -> list[dict]:
    """
    Leads whose WhatsApp conversation ended in a decline — objection_type is set
    to 'wa_declined' by WF2/n8n (this codebase never sets that value itself, it
    only reacts to it) — and that haven't had their one confirmatory call yet.

    Same active-campaign gate as get_due_leads(), but otherwise bypasses
    cooldown_until/pickup_attempt_count/answered_no_date_count entirely — this
    is a separate, capped-at-exactly-one-attempt selection reason, not another
    tier of the pickup or no-date cadences.

    status IS filtered, though: without it, a lead already locked in_progress
    by an earlier tick (confirm_call_attempted only flips to true once that
    call fully completes and finalize_call() runs) would still match this
    query on every subsequent 20s poll and get selected again.
    """
    if not active_campaign_ids:
        return []

    campaign_in = ",".join(active_campaign_ids)
    _test_batch_clause = f"&batch_id=eq.{ORCHESTRATOR_TEST_BATCH}" if ORCHESTRATOR_TEST_BATCH else ""
    url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&objection_type=eq.wa_declined"
        f"&confirm_call_attempted=eq.false"
        f"&status=in.(pending,unanswered,mid_answered)"
        f"&dnc=eq.false"
        f"&campaign_id=in.({campaign_in})"
        f"{_test_batch_clause}"
        f"&order=created_at.asc"
        f"&limit={slots}"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200:
        log.error(f"get_wa_decline_leads failed: {r.status_code} {r.text[:200]}")
        return []
    return r.json()


async def count_active_calls(client: httpx.AsyncClient) -> int:
    """Count leads currently in_progress."""
    url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&status=eq.in_progress"
        f"&select=id"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200:
        return CONCURRENCY_LIMIT   # fail safe: assume full
    return len(r.json())


async def lock_lead(client: httpx.AsyncClient, lead_id: str) -> bool:
    """
    Mark in_progress before dialling — the actual compare-and-swap that
    prevents double-dispatch. Previously this PATCH had no status= guard, so
    it unconditionally set in_progress and always returned True even if the
    row was already locked by an earlier tick/dispatch — a lead selected
    twice (e.g. by get_wa_decline_leads(), which bypasses cooldown_until
    entirely by design) would just get re-locked and re-dialed instead of
    being rejected here. Scoping to status=not.eq.in_progress + checking the
    response body (return=representation) makes this a real CAS: if the row
    was already in_progress, the WHERE clause matches zero rows and this
    correctly returns False.
    """
    url = f"{SUPABASE_URL}/rest/v1/outbound_leads?id=eq.{lead_id}&status=not.eq.in_progress"
    payload = {
        "status":         "in_progress",
        "last_called_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    r = await client.patch(url, headers=sb_headers(), json=payload)
    return r.status_code in (200, 204) and bool(r.json())


def compute_retry_schedule(pickup_attempt_count: int, funnel_type: str = None) -> dict:
    """
    Pure function (no I/O, no DB access) computing the next-attempt timing
    for a lead that just failed to produce a real conversation. Shared
    between schedule_retry_or_dnc() below (true no-answer) and
    supabase_calling.py's finalize_call() 0-turn/IVR-tainted "answered"
    branch — both need identical cadence math, they just write different
    terminal status labels for it (dnc for a lead that's never once
    connected vs max_retries_exhausted for one that connected but never
    produced a real turn — an existing distinction this function doesn't
    collapse; callers decide the label, this only decides the timing).

    Business decision 2026-08-10 (reactivation/fresh_cta): same_day_gap_hours
    after a failed attempt (per-funnel, PICKUP_CADENCE), same day if that
    still lands inside the funnel's window, else pushed to next day's
    window-open; max 2 attempts/day; once a day's pair is done, wait a
    growing number of days (1, then 2, then 3) before the next pair; after
    max_attempts total, stop. reactivation narrowed to 1h on 2026-08-12
    (fresh_cta/walkin_followup left at 4h) -- see PICKUP_CADENCE's comment.

    Replaces the prior fixed 10:30/19:30 IST clock-slot design, which didn't
    match this cadence and was also the design the missing-cooldown bug
    (2026-08-09) bypassed entirely for the 0-turn/answered path — that path
    now goes through this same function instead of a flat 24h stopgap.

    CAVEAT (unchanged from the prior design): gaps are relative to the
    previous attempt's actual time, not an absolute "lead's first attempt"
    anchor — no such field exists in the schema.

    Returns {"pickup_attempt_count": new_count, "cooldown_until": iso_str_or_None,
    "max_attempts_hit": bool}.
    """
    cadence          = PICKUP_CADENCE.get(funnel_type, PICKUP_CADENCE[DEFAULT_PICKUP_CADENCE])
    pair_gap_days    = cadence["pair_gap_days"]
    max_attempts     = cadence["max_attempts"]
    same_day_gap_hrs = cadence.get("same_day_gap_hours", 4)

    new_count = pickup_attempt_count + 1

    if new_count >= max_attempts:
        return {"pickup_attempt_count": new_count, "cooldown_until": None, "max_attempts_hit": True}

    now = datetime.now(IST)
    _end_hour = CALL_END_HOUR_BY_FUNNEL.get(funnel_type, CALL_END_HOUR_DEFAULT)
    if new_count % 2 == 1:
        # First attempt of today's pair just failed — retry same_day_gap_hrs
        # later, same day, if that still lands inside the window; otherwise
        # push to tomorrow's window-open rather than dialing outside
        # business hours (this one lead loses the "2/day" property for this
        # pair, which is the safer failure than calling at night).
        next_call = now + timedelta(hours=same_day_gap_hrs)
        if not (CALL_START_HOUR <= next_call.hour < _end_hour):
            next_call = (now + timedelta(days=1)).replace(
                hour=PICKUP_MORNING_HOUR, minute=PICKUP_MORNING_MINUTE, second=0, microsecond=0
            )
    else:
        # Second attempt of the pair just failed — wait a growing number of
        # days before the next pair, landing at that day's morning slot.
        pair_index = new_count // 2
        gap_days   = pair_gap_days.get(pair_index, 3)
        next_call  = (now + timedelta(days=gap_days)).replace(
            hour=PICKUP_MORNING_HOUR, minute=PICKUP_MORNING_MINUTE, second=0, microsecond=0
        )

    return {
        "pickup_attempt_count": new_count,
        "cooldown_until":       next_call.astimezone(timezone.utc).isoformat(),
        "max_attempts_hit":     False,
    }


async def schedule_retry_or_dnc(
    client: httpx.AsyncClient,
    lead_id: str,
    pickup_attempt_count: int,
    funnel_type: str = None,
):
    """
    Called ONLY for confirmed no-answer (cleanup_stuck_leads sweep, or a
    rejected /trigger-call dispatch). Cadence/timing comes from
    compute_retry_schedule() — see its docstring for the actual design.
    """
    schedule = compute_retry_schedule(pickup_attempt_count, funnel_type)
    new_count = schedule["pickup_attempt_count"]
    max_attempts = PICKUP_CADENCE.get(funnel_type, PICKUP_CADENCE[DEFAULT_PICKUP_CADENCE])["max_attempts"]

    if schedule["max_attempts_hit"]:
        payload = {
            "status":               "dnc",
            "dnc":                  True,
            "pickup_attempt_count": new_count,
            "cooldown_until":       None,
        }
        log.info(f"Lead {lead_id} ({funnel_type or DEFAULT_PICKUP_CADENCE}) → DNC after {new_count} unanswered attempts")
    else:
        payload = {
            "status":               "unanswered",
            "pickup_attempt_count": new_count,
            "cooldown_until":       schedule["cooldown_until"],
        }
        log.info(
            f"Lead {lead_id} ({funnel_type or DEFAULT_PICKUP_CADENCE}) unanswered "
            f"(attempt {new_count}/{max_attempts}) → retry at {schedule['cooldown_until']}"
        )

    # Compare-and-swap on status='in_progress': the /hangup webhook's
    # finalize_call() (supabase_calling.py, separate process) can be mid-flight
    # for this exact call_uuid when cleanup_stuck_leads() calls in here — a slow
    # call's total ring+talk+finalize time can straddle the 5-minute staleness
    # window this function is triggered from. Scoping the PATCH to
    # status=eq.in_progress makes the two writers mutually exclusive: whichever
    # UPDATE commits first (Postgres serializes concurrent writes to the same
    # row) flips status away from in_progress, so the other's WHERE clause
    # matches zero rows instead of also landing its counter bump.
    url = f"{SUPABASE_URL}/rest/v1/outbound_leads?id=eq.{lead_id}&status=eq.in_progress"
    r = await client.patch(url, headers=sb_headers(), json=payload)
    if r.status_code == 200 and not r.json():
        log.info(
            f"Lead {lead_id}: retry/dnc write skipped — status no longer "
            f"in_progress (already finalized by the hangup handler)"
        )


# ── Call firing — uses /trigger-call in webhook.py ───────────────────────────

async def fire_call(client: httpx.AsyncClient, lead: dict, wa_decline_confirm: bool = False) -> bool:
    """
    Hits /trigger-call on webhook.py.
    webhook.py → Vobiz → /answer-outbound → agent conversation.
    Returns True if accepted.

    wa_decline_confirm=True tells webhook.py to play the WA-decline confirm
    greeting instead of the lead's plan's usual opener, before falling into
    that same plan's existing GREETING state — see /answer-outbound.
    """
    url  = f"{WEBHOOK_BASE_URL}/trigger-call"
    # answered_no_date_count tracks real answered conversations with no date yet:
    # 0/None = Call 1 (existing ra_/rb_/rc_ routing), 1 = Call 2 (Ritu), 2 = Call 3
    # (Simran) — capped at 3 since >=3 already exits the cadence before reaching here.
    _no_date_count = lead.get("answered_no_date_count") or 0
    call_cycle = min(_no_date_count + 1, 3)
    body = {
        "to":         lead["phone"],
        "name":       lead.get("name") or "",
        "campaign":   lead.get("campaign_type") or "",
        "product":    lead.get("product_interest") or "",
        "call_cycle": call_cycle,
    }
    if wa_decline_confirm:
        body["wa_decline_confirm"] = True
    try:
        r = await client.post(url, json=body, timeout=15)
        if r.status_code == 200:
            log.info(f"✅ Call fired → {lead['phone']} ({lead.get('name', '?')})")
            return True
        else:
            log.error(
                f"❌ /trigger-call {r.status_code} "
                f"for {lead['phone']}: {r.text[:200]}"
            )
            return False
    except Exception as e:
        log.error(f"❌ /trigger-call exception for {lead['phone']}: {e}")
        return False


# ── IST window check ──────────────────────────────────────────────────────────

def is_calling_window(funnel_type: str = None) -> bool:
    now      = datetime.now(IST)
    hour     = now.hour
    end_hour = CALL_END_HOUR_BY_FUNNEL.get(funnel_type, CALL_END_HOUR_DEFAULT)
    ok       = CALL_START_HOUR <= hour < end_hour
    if not ok:
        log.info(
            f"Outside window ({now.strftime('%H:%M')} IST) for funnel={funnel_type or 'default'}. "
            f"Allowed: {CALL_START_HOUR}:00–{end_hour}:00"
        )
    return ok


# ── Main dispatch loop ────────────────────────────────────────────────────────


STUCK_LEAD_TIMEOUT_MINUTES = 3   # was 5 -- see cleanup_stuck_leads() docstring for the 2026-08-12 change


async def cleanup_stuck_leads(client: httpx.AsyncClient):
    """
    Any lead stuck in_progress for >STUCK_LEAD_TIMEOUT_MINUTES = Vobiz never
    fired hangup. Mark as unanswered and schedule retry.

    Narrowed from 5 to 3 minutes on 2026-08-12: real data from that day's
    reactivation run showed 51% of dial attempts never got a hangup callback
    at all (dead/disconnected numbers, mostly from a newly-imported list with
    2023-era contact data) -- for those, no callback is ever coming regardless
    of how long this waits, so every extra minute here is pure wasted
    concurrency-slot time. That single factor accounted for ~11 hours of
    slot-time out of one ~7.5-hour dialing window. 3 minutes was chosen with
    real margin above that same day's single longest legitimate connected
    call (124s) -- not shortened to 2 minutes, which would sit close enough
    to that outlier to risk marking a still-completing real call as stuck.
    Residual risk if a real call ever does run past 3 minutes: this only
    flips the DB status (it doesn't hang up the live call), and finalize_call()
    overwrites it with the true outcome once the real hangup callback arrives
    -- the narrow remaining risk is a lead becoming reselectable and getting
    redialed before that original call has actually ended.
    """
    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=STUCK_LEAD_TIMEOUT_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # or=(last_called_at.is.null,...) -- a row that never got far enough to
    # have last_called_at set (stuck in_progress before the write that sets
    # it) previously matched neither branch of a plain lte filter: NULL<=X
    # is NULL/false in Postgres, so it was silently excluded from this sweep
    # forever, not just once. Confirmed live 2026-07-28: 3 in_progress rows
    # with last_called_at=NULL sat uncleaned for ~15 hours, permanently
    # exhausting both concurrency slots and blocking all real dialing.
    url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&status=eq.in_progress"
        f"&or=(last_called_at.is.null,last_called_at.lte.{now_iso})"
        f"&select=id,pickup_attempt_count,funnel_type"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200 or not r.json():
        return
    stuck = r.json()
    log.info(f"Cleaning up {len(stuck)} stuck in_progress lead(s)")
    for lead in stuck:
        await schedule_retry_or_dnc(client, lead["id"], lead.get("pickup_attempt_count", 0), lead.get("funnel_type"))


async def tick(client: httpx.AsyncClient):
    await promote_due_scheduled_actions(client)
    await detect_and_schedule_fresh_leads(client)
    await sync_whatsapp_visit_dates(client)
    await cleanup_stuck_leads(client)

    # Cheap early exit for the dead-of-night zone that's outside EVERY
    # funnel's window (before 10am, or past the latest funnel's end hour) —
    # avoids the DB round-trips below when nothing could possibly be dialed.
    # The real per-funnel gating happens at each lane's fetch, further down:
    # fresh_cta gets its own wider window, everything else the tighter default.
    _now_hour = datetime.now(IST).hour
    if not (CALL_START_HOUR <= _now_hour < CALL_END_HOUR_LATEST):
        log.info(f"Outside every funnel's window ({datetime.now(IST).strftime('%H:%M')} IST)")
        return

    active = await count_active_calls(client)
    slots  = CONCURRENCY_LIMIT - active

    if slots <= 0:
        log.info(f"All {CONCURRENCY_LIMIT} slot(s) busy")
        return

    active_campaign_ids = await get_active_campaign_ids(client)
    if not active_campaign_ids:
        log.info("No active campaigns — skipping lead selection this tick")
        return

    # Priority order: fresh_cta leads (time-sensitive, just promoted from
    # scheduled_actions) get first claim on available slots. Whatever's left
    # over fills from the existing reactivation lanes — wa_decline-confirm
    # first (as before), then the normal pickup/no-date cadence — unchanged
    # from the prior merge behavior, just now bounded by remaining_slots
    # instead of the full slots count.
    #
    # Each lane checks its OWN funnel's window rather than one blanket check
    # up top: fresh_cta is allowed till 22:00 IST, everything else (the
    # FUNNEL_TYPE-based lane and wa-decline confirms) is clamped to 20:00 —
    # a single shared gate previously stopped fresh_cta dialing at 20:00 too.
    fresh_leads = await get_due_fresh_leads(client, slots, active_campaign_ids) if is_calling_window("fresh_cta") else []

    remaining_slots = slots - len(fresh_leads)
    due_leads     = []
    decline_leads = []
    if remaining_slots > 0 and is_calling_window(FUNNEL_TYPE):
        due_leads     = await get_due_leads(client, remaining_slots, active_campaign_ids)
        decline_leads = await get_wa_decline_leads(client, remaining_slots, active_campaign_ids)

    seen  = set()
    leads = []
    for lead in fresh_leads:
        seen.add(lead["id"])
        lead["_fresh_cta"] = True
        leads.append(lead)
    for lead in decline_leads:
        if lead["id"] in seen:
            continue
        seen.add(lead["id"])
        lead["_wa_decline_confirm"] = True
        leads.append(lead)
    for lead in due_leads:
        if lead["id"] in seen:
            continue
        seen.add(lead["id"])
        leads.append(lead)

    # Lowest priority: walk-in follow-up calls (walkin_followup.py) — only
    # fills whatever slots the existing lanes above didn't use. Empty list
    # (no-op) unless something has explicitly queued a walk-in follow-up.
    # Gated off by WALKIN_FOLLOWUP_DISPATCH_ENABLED — see that flag's comment.
    remaining_slots = slots - len(leads)
    if remaining_slots > 0 and WALKIN_FOLLOWUP_DISPATCH_ENABLED and is_calling_window():
        walkin_followup_leads = await get_due_walkin_followup_leads(client, remaining_slots, active_campaign_ids)
        for lead in walkin_followup_leads:
            if lead["id"] in seen:
                continue
            seen.add(lead["id"])
            leads.append(lead)

    leads = leads[:slots]

    if not leads:
        log.info("No leads due right now")
        return

    log.info(f"Dispatching {len(leads)} lead(s) | {slots} slot(s) free")

    for lead in leads:
        lead_id              = lead["id"]
        pickup_attempt_count = lead.get("pickup_attempt_count", 0)
        is_decline_confirm   = lead.get("_wa_decline_confirm", False)

        # Lock first — prevents race if orchestrator restarts
        locked = await lock_lead(client, lead_id)
        if not locked:
            log.warning(f"Could not lock {lead_id} — skipping")
            continue

        success = await fire_call(client, lead, wa_decline_confirm=is_decline_confirm)

        if not success:
            # /trigger-call or Vobiz rejected — schedule retry
            await schedule_retry_or_dnc(client, lead_id, pickup_attempt_count, lead.get("funnel_type"))

        # If success: Vobiz fires /hangup when call ends
        # webhook.py hangup handler updates outbound_leads status automatically

        await asyncio.sleep(3)   # gap between initiating calls


async def main():
    log.info("=" * 55)
    log.info("Outbound Orchestrator started")
    log.info(f"Tenant      : {TENANT_ID}")
    log.info(f"Funnel type : {FUNNEL_TYPE}")
    log.info(f"Concurrency : {CONCURRENCY_LIMIT} simultaneous calls")
    log.info(f"Window      : {CALL_START_HOUR}:00–{CALL_END_HOUR_DEFAULT}:00 IST (fresh_cta till {CALL_END_HOUR_BY_FUNNEL.get('fresh_cta', CALL_END_HOUR_DEFAULT)}:00)")
    log.info(f"Pickup slots : {PICKUP_MORNING_HOUR}:{PICKUP_MORNING_MINUTE:02d} & {PICKUP_EVENING_HOUR}:{PICKUP_EVENING_MINUTE:02d} IST")
    for _ft, _c in PICKUP_CADENCE.items():
        log.info(f"Pickup cadence [{_ft}]: max {_c['max_attempts']} attempts, gaps {_c['pair_gap_days']}")
    log.info(f"Webhook base: {WEBHOOK_BASE_URL}")
    log.info(f"Poll every  : {POLL_INTERVAL}s")
    log.info("=" * 55)

    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            try:
                await tick(client)
            except Exception as e:
                log.error(f"Tick error (continuing): {e}", exc_info=True)
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())