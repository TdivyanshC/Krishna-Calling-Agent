-- supabase_migration_whatsapp_cta_sent.sql
-- Run in Supabase SQL Editor (once only — safe to re-run with IF NOT EXISTS).
--
-- What this does:
--   Adds whatsapp_cta_sent (bool) and whatsapp_cta_sent_at (timestamptz) to
--   outbound_leads, for the CRM/dashboard card to show "WhatsApp CTA" instead
--   of "fresh" once the WhatsApp offer/exchange message has actually gone out
--   for this lead.
--

--   Deliberately a SEPARATE pair of columns from the existing wa_sent/
--   wa_sent_at (which already exist and are written by the same call site) --
--   the business wants a dashboard-specific field distinct from the general
--   wa_sent flag, so both get set together rather than reusing one for two
--   purposes.
--
--   Written at the same point wa_sent/wa_sent_at already get written --
--   webhook_reactivation.py's _mark_wa_sent(), called from fire_whatsapp()
--   the moment a WhatsApp send actually succeeds (not on inquiry alone --
--   the WA CTA still only fires once a call reaches a state that triggers
--   fire_whatsapp(), same as it always has; this migration only adds where
--   that fact gets recorded for the dashboard to read).

ALTER TABLE outbound_leads
  ADD COLUMN IF NOT EXISTS whatsapp_cta_sent BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE outbound_leads
  ADD COLUMN IF NOT EXISTS whatsapp_cta_sent_at TIMESTAMPTZ;

COMMENT ON COLUMN outbound_leads.whatsapp_cta_sent IS 'True once the WhatsApp offer/exchange CTA message has actually been sent for this lead (set alongside wa_sent by fire_whatsapp()/_mark_wa_sent()). Dashboard: show "WhatsApp CTA" instead of "fresh" when true.';
COMMENT ON COLUMN outbound_leads.whatsapp_cta_sent_at IS 'Timestamp of the WhatsApp CTA send. NULL until whatsapp_cta_sent flips true.';
