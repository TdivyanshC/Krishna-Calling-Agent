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
PICKUP_PAIR_GAP_DAYS = {1: 1, 2: 2, 3: 3}   # pair index just finished -> days until next pair's morning slot
MAX_PICKUP_ATTEMPTS  = 8

POLL_INTERVAL = 20   # seconds


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
):
    """
    Called ONLY for confirmed no-answer (cleanup_stuck_leads sweep).
    Cadence: Day1, Day2, Day4, Day7 — 2 attempts/day (morning + evening).
    After MAX_PICKUP_ATTEMPTS total unanswered attempts → dnc.

    CAVEAT: gaps are relative to the previous attempt, not anchored to an
    absolute "lead's first attempt" timestamp (no such field exists in the
    current schema). Morning-vs-evening slot is inferred purely from
    pickup_attempt_count parity, which assumes every attempt actually lands
    in its intended window — if attempts get delayed across window boundaries
    this can drift.
    """
    new_count = pickup_attempt_count + 1

    if new_count >= MAX_PICKUP_ATTEMPTS:
        payload = {
            "status":               "dnc",
            "dnc":                  True,
            "pickup_attempt_count": new_count,
            "cooldown_until":       None,
        }
        log.info(f"Lead {lead_id} → DNC after {new_count} unanswered attempts")

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
            f"Lead {lead_id} unanswered (attempt {new_count}/{MAX_PICKUP_ATTEMPTS}) "
            f"→ retry this evening"
        )

    else:
        # Just completed an evening slot (pair done) → next pair's morning, N days out
        pair_index = new_count // 2
        gap_days   = PICKUP_PAIR_GAP_DAYS.get(pair_index, 3)
        next_call  = datetime.now(IST).replace(
            hour=PICKUP_MORNING_HOUR, minute=PICKUP_MORNING_MINUTE, second=0, microsecond=0
        ) + timedelta(days=gap_days)
        payload = {
            "status":               "unanswered",
            "pickup_attempt_count": new_count,
            "cooldown_until":       next_call.astimezone(timezone.utc).isoformat(),
        }
        log.info(
            f"Lead {lead_id} unanswered (attempt {new_count}/{MAX_PICKUP_ATTEMPTS}) "
            f"→ retry in {gap_days} day(s), morning slot"
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
    body = {
        "to":       lead["phone"],
        "name":     lead.get("name") or "",
        "campaign": lead.get("campaign_type") or "",
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
        f"&select=id,pickup_attempt_count"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200 or not r.json():
        return
    stuck = r.json()
    log.info(f"Cleaning up {len(stuck)} stuck in_progress lead(s)")
    for lead in stuck:
        await schedule_retry_or_dnc(client, lead["id"], lead.get("pickup_attempt_count", 0))


async def tick(client: httpx.AsyncClient):
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

    # Merge the normal pickup/no-date lane with the wa_decline-confirm lane.
    # decline_leads is processed FIRST when de-duping so that a lead unlucky
    # enough to match both (e.g. it didn't pick up its confirm call and fell
    # back to status='unanswered', which also satisfies get_due_leads()) keeps
    # the decline-confirm treatment on retry instead of silently reverting to
    # a normal pickup-cadence call.
    due_leads     = await get_due_leads(client, slots, active_campaign_ids)
    decline_leads = await get_wa_decline_leads(client, slots, active_campaign_ids)

    seen  = set()
    leads = []
    for lead in decline_leads:
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
            await schedule_retry_or_dnc(client, lead_id, pickup_attempt_count)

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
    log.info(f"Pickup cadence: Day1/2/4/7, 2 attempts/day ({PICKUP_MORNING_HOUR}:{PICKUP_MORNING_MINUTE:02d} & {PICKUP_EVENING_HOUR}:{PICKUP_EVENING_MINUTE:02d} IST) → DNC after {MAX_PICKUP_ATTEMPTS}")
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