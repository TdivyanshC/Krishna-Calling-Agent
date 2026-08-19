-- supabase_migration_callback_requested_at.sql
-- Run in Supabase SQL Editor (once only — safe to re-run with IF NOT EXISTS).
--
-- Adds callback_requested_at to outbound_leads -- stores the concrete
-- UTC timestamp a customer's stated callback time ("kal subah call karna")
-- resolves to (webhook_reactivation.py's _parse_callback_time_bucket()),
-- so outbound_orchestrator.py can poll for leads whose promised callback
-- window has arrived and actually fire the call, rather than only
-- acknowledging the request verbally (session.awaiting_callback_time /
-- obj_callback_time_noted_* -- an in-memory-only flag, added 2026-08-19,
-- that never persisted anywhere). Nullable -- most leads never say this.

ALTER TABLE outbound_leads
  ADD COLUMN IF NOT EXISTS callback_requested_at TIMESTAMPTZ;

-- Partial index -- almost every row has this NULL, only the (rare) rows
-- with an actual pending callback are ever queried by
-- get_due_callback_leads()'s `callback_requested_at <= now()` filter.
CREATE INDEX IF NOT EXISTS idx_outbound_leads_callback_requested_at
  ON outbound_leads(callback_requested_at)
  WHERE callback_requested_at IS NOT NULL;

-- Verify:
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_name = 'outbound_leads' AND column_name = 'callback_requested_at';
