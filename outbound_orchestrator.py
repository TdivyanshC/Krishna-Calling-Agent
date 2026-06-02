"""
outbound_orchestrator.py
========================
Place in: /home/voiceagent/voice-ai/outbound_orchestrator.py

Fires calls via webhook.py's /trigger-call endpoint (already built).
Handles IST window, concurrency, and 1→2→3 day retry gaps.

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

CALL_START_HOUR = 11   # 11:00 AM IST
CALL_END_HOUR   = 22   # 10:00 PM IST

# retry_count → days to wait before next attempt
RETRY_GAPS  = {0: 1, 1: 2, 2: 3}
MAX_RETRIES = 3

POLL_INTERVAL = 60   # seconds


# ── Supabase helpers ──────────────────────────────────────────────────────────

def sb_headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


async def get_due_leads(client: httpx.AsyncClient, slots: int) -> list[dict]:
    """
    Fetch leads ready to call:
      - status = pending OR unanswered
      - next_call_at IS NULL (call ASAP) OR next_call_at <= now()
    Oldest first so no lead waits forever.
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"{SUPABASE_URL}/rest/v1/outbound_leads"
        f"?tenant_id=eq.{TENANT_ID}"
        f"&status=in.(pending,unanswered)"
        f"&or=(next_call_at.is.null,next_call_at.lte.{now_iso})"
        f"&order=created_at.asc"
        f"&limit={slots}"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200:
        log.error(f"get_due_leads failed: {r.status_code} {r.text[:200]}")
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
    retry_count: int,
):
    """
    Called when a call was not answered or failed to connect.
    Applies 1 → 2 → 3 day gaps then DNC.
    """
    new_count = retry_count + 1

    if new_count >= MAX_RETRIES:
        payload = {
            "status":       "dnc",
            "retry_count":  new_count,
            "next_call_at": None,
        }
        log.info(f"Lead {lead_id} → DNC after {new_count} unanswered attempts")
    else:
        gap_days  = RETRY_GAPS.get(retry_count, 3)
        next_call = datetime.now(timezone.utc) + timedelta(days=gap_days)
        payload = {
            "status":       "unanswered",
            "retry_count":  new_count,
            "next_call_at": next_call.isoformat(),
        }
        log.info(
            f"Lead {lead_id} unanswered "
            f"(attempt {new_count}/{MAX_RETRIES}) "
            f"→ retry in {gap_days} day(s)"
        )

    url = f"{SUPABASE_URL}/rest/v1/outbound_leads?id=eq.{lead_id}"
    await client.patch(url, headers=sb_headers(), json=payload)


# ── Call firing — uses /trigger-call in webhook.py ───────────────────────────

async def fire_call(client: httpx.AsyncClient, lead: dict) -> bool:
    """
    Hits /trigger-call on webhook.py.
    webhook.py → Vobiz → /answer-outbound → agent conversation.
    Returns True if accepted.
    """
    url  = f"{WEBHOOK_BASE_URL}/trigger-call"
    body = {
        "to":   lead["phone"],
        "name": lead.get("name") or "",
    }
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
        f"&select=id,retry_count"
    )
    r = await client.get(url, headers=sb_headers())
    if r.status_code != 200 or not r.json():
        return
    stuck = r.json()
    log.info(f"Cleaning up {len(stuck)} stuck in_progress lead(s)")
    for lead in stuck:
        await schedule_retry_or_dnc(client, lead["id"], lead.get("retry_count", 0))


async def tick(client: httpx.AsyncClient):
    await cleanup_stuck_leads(client)
    if not is_calling_window():
        return

    active = await count_active_calls(client)
    slots  = CONCURRENCY_LIMIT - active

    if slots <= 0:
        log.info(f"All {CONCURRENCY_LIMIT} slot(s) busy")
        return

    leads = await get_due_leads(client, slots)
    if not leads:
        log.info("No leads due right now")
        return

    log.info(f"Dispatching {len(leads)} lead(s) | {slots} slot(s) free")

    for lead in leads:
        lead_id     = lead["id"]
        retry_count = lead.get("retry_count", 0)

        # Lock first — prevents race if orchestrator restarts
        locked = await lock_lead(client, lead_id)
        if not locked:
            log.warning(f"Could not lock {lead_id} — skipping")
            continue

        success = await fire_call(client, lead)

        if not success:
            # /trigger-call or Vobiz rejected — schedule retry
            await schedule_retry_or_dnc(client, lead_id, retry_count)

        # If success: Vobiz fires /hangup when call ends
        # webhook.py hangup handler updates outbound_leads status automatically

        await asyncio.sleep(3)   # gap between initiating calls


async def main():
    log.info("=" * 55)
    log.info("Outbound Orchestrator started")
    log.info(f"Tenant      : {TENANT_ID}")
    log.info(f"Concurrency : {CONCURRENCY_LIMIT} simultaneous calls")
    log.info(f"Window      : {CALL_START_HOUR}:00–{CALL_END_HOUR}:00 IST")
    log.info(f"Retry gaps  : 1 day → 2 days → 3 days → DNC")
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