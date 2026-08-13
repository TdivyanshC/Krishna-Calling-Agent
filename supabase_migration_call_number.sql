-- supabase_migration_call_number.sql
-- Run in Supabase SQL Editor (once only — safe to re-run with IF NOT EXISTS).
--
-- What this does:
--   Adds a `call_number` column (1/2/3) to call_summaries and call_logs.
--   Previously the call number wasn't persisted anywhere — it lived only as
--   session.call_cycle (a string query param threaded through /answer-outbound),
--   never written to the database. Confirmed during the 2026-07-15 audit: it
--   had to be reconstructed after the fact from journalctl logs
--   ("Outbound to ... call_cycle=N") to figure out which call number each
--   call_summaries row belonged to, and separately, final_state/deepest_state
--   were silently mislabeled for Call 2/3 because nothing downstream knew
--   which call-cycle handler had produced them (see
--   supabase_calling.py's _resolve_call_state()).
--
--   call_number is written at insert time by finalize_call() /
--   insert_call_log() (see supabase_calling.py's companion diff) — NULL for
--   rows inserted before this migration; going forward every row gets an
--   explicit 1/2/3 (default 1 for calls with no call_cycle set, i.e. Call 1
--   or any non-reactivation funnel).
--
-- CRM: read call_number directly off call_summaries (the richer,
-- CRM-oriented table — lead_score/lead_tier/customer_response/cta_accepted
-- all already live there). call_logs also gets the column for telephony-level
-- consistency, but call_summaries is the intended read target for the Call
-- section card.

ALTER TABLE call_summaries
  ADD COLUMN IF NOT EXISTS call_number SMALLINT;

ALTER TABLE call_logs
  ADD COLUMN IF NOT EXISTS call_number SMALLINT;

COMMENT ON COLUMN call_summaries.call_number IS 'Which call in the sequence this is for the lead: 1, 2, or 3. NULL for rows inserted before 2026-07-15.';
COMMENT ON COLUMN call_logs.call_number IS 'Which call in the sequence this is for the lead: 1, 2, or 3. NULL for rows inserted before 2026-07-15.';
