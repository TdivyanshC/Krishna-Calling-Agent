-- supabase_migration_outbound_leads_status_values.sql
-- Run in Supabase SQL Editor (once only).
--
-- What this does:
--   Expands outbound_leads_status_check to add 'no_date_stalled' and
--   'max_retries_exhausted' to the allowed status values.
--
--   'no_date_stalled': the write already exists in code
--   (supabase_calling.py finalize_call(), answered_no_date_count>=3 branch,
--   non-fresh_cta campaigns) and has been silently failing with a
--   constraint-violation error on every occurrence since it was written —
--   confirmed live, 15/15 leads at call_number=3 had dnc still false and
--   status stuck at 'mid_answered' past their intended 3-attempt cap,
--   because this status value was never actually in the allowed list.
--   No code change needed once this migration runs — the existing write is
--   already correct, just blocked.
--
--   'max_retries_exhausted': new, for the pickup_attempt_count>=4 backstop
--   (see supabase_calling.py/outbound_orchestrator.py companion diff) — a
--   lead written to this status is excluded from get_due_leads()/
--   get_due_fresh_leads() (status=in.(pending,unanswered,mid_answered)),
--   same exclusion mechanism as 'dnc' or 'answered', without implying
--   either a rejection (dnc=true) or a conversion (answered).
--
-- ORDERING WARNING: same as the ivr_flag migration — code that writes either
-- of these two new values must not reach production before this runs, or
-- every such write will 400 (constraint violation) exactly as
-- 'no_date_stalled' already has been.

ALTER TABLE outbound_leads
  DROP CONSTRAINT outbound_leads_status_check;

ALTER TABLE outbound_leads
  ADD CONSTRAINT outbound_leads_status_check
  CHECK (status = ANY (ARRAY[
    'pending'::text, 'in_progress'::text, 'answered'::text, 'mid_answered'::text,
    'unanswered'::text, 'scheduled'::text, 'dnc'::text,
    'no_date_stalled'::text, 'max_retries_exhausted'::text
  ]));
