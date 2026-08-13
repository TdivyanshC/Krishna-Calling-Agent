-- supabase_migration_outbound_leads_duplicate_suppressed.sql
-- Run in Supabase SQL Editor (once only).
--
-- What this does:
--   Adds 'duplicate_suppressed' to outbound_leads_status_check, same
--   pattern as supabase_migration_outbound_leads_status_values.sql earlier
--   tonight (which added no_date_stalled/max_retries_exhausted).
--
--   Purpose: the cross-funnel contact_id backfill (2026-07-28) found phone
--   9810649832 has two outbound_leads rows for the same person — a manual
--   reactivation-import row and a proper contacts-promoted fresh_cta row.
--   Decision: suppress the lower-fidelity manual row from future dialing
--   rather than merge histories (real, hard-to-reverse risk for no
--   operational benefit — see conversation record). Reusing an existing
--   status value (no_date_stalled, dnc, answered) for this would mislabel
--   the row with an unrelated status's meaning — exactly the kind of small
--   inconsistency that confuses future readers of this table. This is a
--   distinct, precise value for exactly one purpose: "this row is a
--   confirmed duplicate of another outbound_leads row and must never be
--   dialed again" — NOT a rejection (dnc stays false), NOT a retry-cap
--   outcome (max_retries_exhausted), NOT an answered-no-date stall
--   (no_date_stalled).
--
-- ORDERING WARNING: same as every other migration tonight — the code that
-- writes this value must not reach production before this runs, or that
-- write 400s (constraint violation) exactly like no_date_stalled did for
-- months before its own migration.

ALTER TABLE outbound_leads
  DROP CONSTRAINT outbound_leads_status_check;

ALTER TABLE outbound_leads
  ADD CONSTRAINT outbound_leads_status_check
  CHECK (status = ANY (ARRAY[
    'pending'::text, 'in_progress'::text, 'answered'::text, 'mid_answered'::text,
    'unanswered'::text, 'scheduled'::text, 'dnc'::text,
    'no_date_stalled'::text, 'max_retries_exhausted'::text, 'duplicate_suppressed'::text
  ]));
