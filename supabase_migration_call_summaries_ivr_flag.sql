-- supabase_migration_call_summaries_ivr_flag.sql
-- Run in Supabase SQL Editor (once only — safe to re-run with IF NOT EXISTS).
--
-- What this does:
--   Adds call_summaries.ivr_flag (boolean, default false) so the CRM can
--   eventually distinguish a carrier-IVR/voicemail-loop call from a real
--   conversation instead of both showing as plain "Answered". Written by
--   finalize_call() (supabase_calling.py) as
--   getattr(session, "ivr_fragment_count", 0) >= 3 — true when the
--   phonetic-Devanagari IVR-fragment pattern (_is_ivr_fragment(),
--   webhook_reactivation.py) matched 3+ times in a single call. CRM read
--   side is a separate, later change — this migration only adds the column.
--
-- ORDERING WARNING: finalize_call()'s insert payload will include
-- "ivr_flag" as soon as the companion code change (supabase_calling.py)
-- ships. If that code reaches production before this migration runs,
-- PostgREST will reject every call_summaries insert with an unknown-column
-- error (PGRST204) — i.e. this must be applied BEFORE that deploy, not
-- alongside or after it.

ALTER TABLE call_summaries
  ADD COLUMN IF NOT EXISTS ivr_flag boolean NOT NULL DEFAULT false;
