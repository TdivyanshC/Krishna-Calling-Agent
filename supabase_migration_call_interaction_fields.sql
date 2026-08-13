-- supabase_migration_call_interaction_fields.sql
-- Run in Supabase SQL Editor (once only — safe to re-run with IF NOT EXISTS).
--
-- What this does:
--   Adds voice-pipeline-only interaction-tracking columns to the shared
--   `leads` table, so this codebase's _update_lead_score() (supabase_calling.py)
--   stops writing into interaction_count/last_contact — the same columns the
--   WhatsApp/CRM side owns. Same root cause as
--   supabase_migration_call_lead_score.sql (which split lead_score/lead_status);
--   confirmed live 2026-07-12 on 919582622123: interaction_count=1 and
--   last_contact set from a voice call, despite zero WhatsApp messages.
--
-- interaction_count/last_contact themselves are untouched by this migration —
-- the WhatsApp/CRM side keeps writing them exactly as before. Only this
-- pipeline's write target changes (see supabase_calling.py's companion diff).

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS call_interaction_count INTEGER,
  ADD COLUMN IF NOT EXISTS call_last_contact       TIMESTAMPTZ;
