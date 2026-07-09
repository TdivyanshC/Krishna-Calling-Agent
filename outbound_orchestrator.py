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

CALL_START_HOUR = 10   # 10:00 AM IST
CALL_END_HOUR   = 22   # 10:00 PM IST

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
PICKUP_CADENCE = {
    "reactivation": {"pair_gap_days": {1: 1, 2: 1}, "max_attempts": 6},  # 2x/day, 3 days straight, 6 max
    "fresh_cta":    {"pair_gap_days": {1: 1, 2: 1},       "max_attempts": 6},  # Day1/2/3, 6 max
}
DEFAULT_PICKUP_CADENCE = "reactivation"  # used for any funnel_type not in PICKUP_CADENCE (incl. None)

POLL_INTERVAL = 20   # seconds

FRESH_CTA_CAMPAIGN_ID = "8fab0334-6d8c-4b71-be72-9d170c8ad3fc"


# ── Supabase helpers ──────────────────────────────────────────────────────────

def sb_headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


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
    Fetch leads ready to call (normal pickup/no-date cadence):
      - funnel_type matches FUNNEL_TYPE env var
      - status = pending, unanswered, or mid_answered (answered, no date yet)
      - dnc = false
      - visit_date_status IS NULL (expected/confirmed leads are never re-selected)
      - campaign_id IS NOT NULL AND its parent campaign.status = 'active'
        (active_campaign_ids passed in by tick() — see get_active_campaign_ids()
        for the NULL-handling caveat)
      - cooldown_until IS NULL OR cooldown_until <= now()
    Oldest first so no lead waits forever.
    """
    if not active_campaign_ids:
        return []

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    campaign_in = ",".join(active_campaign_ids)
    url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&funnel_type=in.({FUNNEL_TYPE})"
        f"&status=in.(pending,unanswered,mid_answered)"
        f"&dnc=eq.false"
        f"&visit_date_status=is.null"
        f"&campaign_id=in.({campaign_in})"
        f"&or=(cooldown_until.is.null,cooldown_until.lte.{now_iso})"
        f"&order=created_at.asc"
        f"&limit={slots}"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200:
        log.error(f"get_due_leads failed: {r.status_code} {r.text[:200]}")
        return []
    return r.json()


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
    url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&funnel_type=eq.fresh_cta"
        f"&status=in.(pending,unanswered,mid_answered)"
        f"&dnc=eq.false"
        f"&visit_date_status=is.null"
        f"&campaign_id=in.({campaign_in})"
        f"&or=(cooldown_until.is.null,cooldown_until.lte.{now_iso})"
        f"&order=created_at.asc"
        f"&limit={slots}"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200:
        log.error(f"get_due_fresh_leads failed: {r.status_code} {r.text[:200]}")
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

        # Avoid duplicate promotion — skip creating a new outbound_leads row
        # if one already exists for this contact (from this or any funnel).
        existing = await client.get(
            f"{SUPABASE_URL}/rest/v1/outbound_leads",
            headers=sb_headers(),
            params={"contact_id": f"eq.{contact_id}", "select": "id", "limit": "1"},
        )
        if existing.status_code == 200 and existing.json():
            log.info(f"scheduled_action for contact {contact_id}: outbound_leads row already exists — marking fired, skipping create")
        else:
            phone   = None
            name    = ""
            product = None

            c_r = await client.get(
                f"{SUPABASE_URL}/rest/v1/contacts",
                headers=sb_headers(),
                params={"id": f"eq.{contact_id}", "select": "phone", "limit": "1"},
            )
            if c_r.status_code == 200 and c_r.json():
                phone = c_r.json()[0].get("phone")

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
                product = row.get("interested_in") or None

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


async def get_wa_decline_leads(client: httpx.AsyncClient, slots: int, active_campaign_ids: list[str]) -> list[dict]:
    """
    Leads whose WhatsApp conversation ended in a decline — objection_type is set
    to 'wa_declined' by WF2/n8n (this codebase never sets that value itself, it
    only reacts to it) — and that haven't had their one confirmatory call yet.

    Same active-campaign gate as get_due_leads(), but otherwise bypasses
    cooldown_until/pickup_attempt_count/answered_no_date_count entirely — this
    is a separate, capped-at-exactly-one-attempt selection reason, not another
    tier of the pickup or no-date cadences.
    """
    if not active_campaign_ids:
        return []

    campaign_in = ",".join(active_campaign_ids)
    url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&objection_type=eq.wa_declined"
        f"&confirm_call_attempted=eq.false"
        f"&dnc=eq.false"
        f"&campaign_id=in.({campaign_in})"
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
    """Mark in_progress before dialling — prevents double-dispatch."""
    url = f"{SUPABASE_URL}/rest/v1/outbound_leads?id=eq.{lead_id}"
    payload = {
        "status":         "in_progress",
        "last_called_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    r = await client.patch(url, headers=sb_headers(), json=payload)
    return r.status_code in (200, 204)


async def schedule_retry_or_dnc(
    client: httpx.AsyncClient,
    lead_id: str,
    pickup_attempt_count: int,
    funnel_type: str = None,
):
    """
    Called ONLY for confirmed no-answer (cleanup_stuck_leads sweep, or a
    rejected /trigger-call dispatch).
    Cadence is looked up from PICKUP_CADENCE by funnel_type (falling back to
    DEFAULT_PICKUP_CADENCE for anything unrecognized, incl. None) — 2 attempts
    per "day" (morning + evening) until max_attempts, then dnc.

    CAVEAT: gaps are relative to the previous attempt, not anchored to an
    absolute "lead's first attempt" timestamp (no such field exists in the
    current schema). Morning-vs-evening slot is inferred purely from
    pickup_attempt_count parity, which assumes every attempt actually lands
    in its intended window — if attempts get delayed across window boundaries
    this can drift.
    """
    cadence       = PICKUP_CADENCE.get(funnel_type, PICKUP_CADENCE[DEFAULT_PICKUP_CADENCE])
    pair_gap_days = cadence["pair_gap_days"]
    max_attempts  = cadence["max_attempts"]

    new_count = pickup_attempt_count + 1

    if new_count >= max_attempts:
        payload = {
            "status":               "dnc",
            "dnc":                  True,
            "pickup_attempt_count": new_count,
            "cooldown_until":       None,
        }
        log.info(f"Lead {lead_id} ({funnel_type or DEFAULT_PICKUP_CADENCE}) → DNC after {new_count} unanswered attempts")

    elif new_count % 2 == 1:
        # Just completed a morning slot → next attempt is same-day evening
        next_call = datetime.now(IST).replace(
            hour=PICKUP_EVENING_HOUR, minute=PICKUP_EVENING_MINUTE, second=0, microsecond=0
        )
        if next_call <= datetime.now(IST):
            next_call += timedelta(days=1)  # safety net if evening slot already passed
        payload = {
            "status":               "unanswered",
            "pickup_attempt_count": new_count,
            "cooldown_until":       next_call.astimezone(timezone.utc).isoformat(),
        }
        log.info(
            f"Lead {lead_id} ({funnel_type or DEFAULT_PICKUP_CADENCE}) unanswered "
            f"(attempt {new_count}/{max_attempts}) → retry this evening"
        )

    else:
        # Just completed an evening slot (pair done) → next pair's morning, N days out
        pair_index = new_count // 2
        gap_days   = pair_gap_days.get(pair_index, 3)
        next_call  = datetime.now(IST).replace(
            hour=PICKUP_MORNING_HOUR, minute=PICKUP_MORNING_MINUTE, second=0, microsecond=0
        ) + timedelta(days=gap_days)
        payload = {
            "status":               "unanswered",
            "pickup_attempt_count": new_count,
            "cooldown_until":       next_call.astimezone(timezone.utc).isoformat(),
        }
        log.info(
            f"Lead {lead_id} ({funnel_type or DEFAULT_PICKUP_CADENCE}) unanswered "
            f"(attempt {new_count}/{max_attempts}) → retry in {gap_days} day(s), morning slot"
        )

    url = f"{SUPABASE_URL}/rest/v1/outbound_leads?id=eq.{lead_id}"
    await client.patch(url, headers=sb_headers(), json=payload)


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

def is_calling_window() -> bool:
    now  = datetime.now(IST)
    hour = now.hour
    ok   = CALL_START_HOUR <= hour < CALL_END_HOUR
    if not ok:
        log.info(
            f"Outside window ({now.strftime('%H:%M')} IST). "
            f"Allowed: {CALL_START_HOUR}:00–{CALL_END_HOUR}:00"
        )
    return ok


# ── Main dispatch loop ────────────────────────────────────────────────────────


async def cleanup_stuck_leads(client: httpx.AsyncClient):
    """
    Any lead stuck in_progress for >5 min = Vobiz never fired hangup.
    Mark as unanswered and schedule retry.
    """
    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&status=eq.in_progress"
        f"&last_called_at=lte.{now_iso}"
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
    await cleanup_stuck_leads(client)
    if not is_calling_window():
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
    fresh_leads = await get_due_fresh_leads(client, slots, active_campaign_ids)

    remaining_slots = slots - len(fresh_leads)
    due_leads     = []
    decline_leads = []
    if remaining_slots > 0:
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
    log.info(f"Window      : {CALL_START_HOUR}:00–{CALL_END_HOUR}:00 IST")
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