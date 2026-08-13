-- supabase_migration_call_summaries_turn_count_substantive.sql
-- Run in Supabase SQL Editor (once only — safe to re-run with IF NOT EXISTS).
--
-- What this does:
--   Adds call_summaries.turn_count_substantive — a count of turns where STT
--   returned real (non-empty) text, alongside the existing turn_count (which
--   counts every turn, including silence). Companion to the fix that also
--   stopped silence turns from being counted into avg_response_latency /
--   first_response_latency (webhook_reactivation.py's handle_reactivation_turn
--   wrapper previously recorded a "latency" for every turn unconditionally,
--   including turns where the customer said nothing at all).
--
-- MUST be applied before supabase_calling.py's finalize_call() starts writing
-- this column — PostgREST rejects an INSERT payload containing an unknown
-- column (42703), which would otherwise fail every call_summaries insert.

ALTER TABLE call_summaries
  ADD COLUMN IF NOT EXISTS turn_count_substantive INTEGER;
