-- supabase_migration_call_lead_score.sql
-- Run in Supabase SQL Editor (once only — safe to re-run with IF NOT EXISTS).
--
-- What this does:
--   Adds voice-pipeline-only score columns to the shared `leads` table, so
--   this codebase's _update_lead_score() (supabase_calling.py) stops writing
--   into lead_score/lead_status — the same columns the WhatsApp/CRM side
--   reads for its Hot/Warm/Cold bucketing. Confirmed live 2026-07-12: this
--   pipeline was overwriting lead_score/lead_status on shared `leads` rows
--   (get_or_create_lead_id() attaches to an existing row by phone if one
--   already exists, so a WhatsApp-only lead with zero chat history could end
--   up scored hot/warm purely from a voice call).
--
-- lead_score/lead_status themselves are untouched by this migration — the
-- WhatsApp/CRM side keeps writing them exactly as before. Only this
-- pipeline's write target changes (see supabase_calling.py's companion diff).

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS call_lead_score  TEXT,
  ADD COLUMN IF NOT EXISTS call_lead_status TEXT;
