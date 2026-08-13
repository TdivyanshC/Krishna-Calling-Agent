"""
walkin_followup.py
===================
Additive module — schedules follow-up calls for walk-in visits logged in the
`walkins` table (see supabase_migration_walkins.sql). Does NOT touch the live
call state machine (webhook_reactivation.py, fresh_cta scripts, orchestrator
polling loop) — it only creates rows that the existing orchestrator dispatch
already knows how to pick up and dial (same pattern as fresh_cta/reactivation:
a `campaigns` row + `outbound_leads` rows).

No auto-fire timing logic here by design (confirmed with the requester) —
call schedule_next_walkin_followup_call() explicitly (e.g. from a CRM button
via the /walkin-followup/{walkin_id} endpoint in webhook.py, or manually)
whenever a follow-up call should be queued. Caps at 3 scheduled follow-ups
per walk-in via walkins.followup_calls_made.
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
TENANT_ID            = os.getenv("TENANT_ID", "krishna_furniture")

WALKIN_FOLLOWUP_CAMPAIGN_NAME = "walkin_followup"
MAX_FOLLOWUP_CALLS = 3


def _headers() -> dict:
    return {
        "apikey":        SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


async def _ensure_walkin_followup_campaign(client: httpx.AsyncClient) -> str | None:
    """Returns the id of the (single) active walkin_followup campaign row, creating it if missing."""
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/campaigns",
        headers=_headers(),
        params={
            "tenant_id": f"eq.{TENANT_ID}",
            "name":      f"eq.{WALKIN_FOLLOWUP_CAMPAIGN_NAME}",
            "select":    "id,status",
            "limit":     "1",
        },
    )
    if r.status_code == 200 and r.json():
        return r.json()[0]["id"]

    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/campaigns",
        headers=_headers(),
        json={"tenant_id": TENANT_ID, "name": WALKIN_FOLLOWUP_CAMPAIGN_NAME, "status": "active"},
    )
    if r.status_code in (200, 201) and r.json():
        return r.json()[0]["id"]

    logger.error(f"_ensure_walkin_followup_campaign failed: {r.status_code} {r.text[:200]}")
    return None


async def schedule_next_walkin_followup_call(walkin_id: str) -> dict:
    """
    Queues one follow-up call for a walk-in, capped at MAX_FOLLOWUP_CALLS
    total per walk-in (walkins.followup_calls_made). Creates an
    outbound_leads row with funnel_type/campaign_type='walkin_followup' —
    the existing orchestrator dispatches it exactly like any other campaign
    lead (10am-8pm IST clamp included, for free, since that's a process-wide
    gate in outbound_orchestrator.py's tick()).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {"error": "Supabase not configured"}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/walkins",
            headers=_headers(),
            params={
                "id":     f"eq.{walkin_id}",
                "select": "id,phone,lead_id,followup_calls_made",
                "limit":  "1",
            },
        )
        if r.status_code != 200 or not r.json():
            return {"error": "walkin not found"}
        walkin = r.json()[0]

        calls_made = walkin.get("followup_calls_made") or 0
        if calls_made >= MAX_FOLLOWUP_CALLS:
            return {"error": f"follow-up cap reached ({calls_made}/{MAX_FOLLOWUP_CALLS})"}

        # outbound_leads has a UNIQUE(phone, tenant_id) constraint — one row
        # per phone across ALL campaigns, mutated in place as a lead moves
        # between funnels (confirmed live: a blind INSERT here 409s on any
        # second call, and would just as easily collide with a phone's
        # *other* active campaign row, e.g. someone mid-reactivation who
        # also walks in). So: reuse the walkin's row if the trigger already
        # matched one (walkins.lead_id), else look one up by phone directly
        # (covers a prior walkin_followup call for the same offline walk-in
        # having already created one) — UPDATE if found, INSERT only if not.
        existing = None
        lead_id = walkin.get("lead_id")
        if lead_id:
            lr = await client.get(
                f"{SUPABASE_URL}/rest/v1/outbound_leads",
                headers=_headers(),
                params={"id": f"eq.{lead_id}", "select": "id,name,dnc,status", "limit": "1"},
            )
            if lr.status_code == 200 and lr.json():
                existing = lr.json()[0]
        else:
            lr = await client.get(
                f"{SUPABASE_URL}/rest/v1/outbound_leads",
                headers=_headers(),
                params={
                    "tenant_id": f"eq.{TENANT_ID}",
                    "phone":     f"eq.{walkin['phone']}",
                    "select":    "id,name,dnc,status",
                    "limit":     "1",
                },
            )
            if lr.status_code == 200 and lr.json():
                existing = lr.json()[0]

        if existing and existing.get("dnc"):
            return {"error": "phone is on the do-not-call list"}
        if existing and existing.get("status") == "in_progress":
            return {"error": "a call is currently in progress for this lead — try again shortly"}

        name = (existing or {}).get("name") or ""

        campaign_id = await _ensure_walkin_followup_campaign(client)
        if not campaign_id:
            return {"error": "could not resolve walkin_followup campaign"}

        payload = {
            "tenant_id":     TENANT_ID,
            "phone":         walkin["phone"],
            "name":          name,
            "campaign_id":   campaign_id,
            "campaign_type": WALKIN_FOLLOWUP_CAMPAIGN_NAME,
            "funnel_type":   WALKIN_FOLLOWUP_CAMPAIGN_NAME,
            "status":        "pending",
            "dnc":           False,
            "cooldown_until": None,
            "pickup_attempt_count": 0,
        }

        if existing:
            cr = await client.patch(
                f"{SUPABASE_URL}/rest/v1/outbound_leads",
                headers=_headers(),
                params={"id": f"eq.{existing['id']}"},
                json=payload,
            )
        else:
            cr = await client.post(
                f"{SUPABASE_URL}/rest/v1/outbound_leads",
                headers=_headers(),
                json=payload,
            )
        if cr.status_code not in (200, 201) or not cr.json():
            logger.error(f"schedule_next_walkin_followup_call: outbound_leads {'update' if existing else 'insert'} failed: {cr.status_code} {cr.text[:200]}")
            return {"error": "failed to schedule outbound_leads row"}
        outbound_lead_id = cr.json()[0]["id"]

        pr = await client.patch(
            f"{SUPABASE_URL}/rest/v1/walkins",
            headers=_headers(),
            params={"id": f"eq.{walkin_id}"},
            json={"followup_calls_made": calls_made + 1},
        )
        if pr.status_code not in (200, 204):
            logger.error(f"schedule_next_walkin_followup_call: failed to bump followup_calls_made: {pr.status_code} {pr.text[:200]}")

        logger.info(f"Scheduled walkin follow-up call {calls_made + 1}/{MAX_FOLLOWUP_CALLS} for walkin {walkin_id} -> outbound_leads {outbound_lead_id}")
        return {"scheduled": True, "outbound_lead_id": outbound_lead_id, "call_number": calls_made + 1}
