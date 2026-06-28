-- supabase_migration_reactivation.sql
-- Run in Supabase SQL Editor (once only — safe to re-run with IF NOT EXISTS).
--
-- What this does:
--   1. Adds campaign_type column to outbound_leads (default 'fresh_lead')
--   2. Adds index for the orchestrator's filter query
--   3. Adds wa_sent tracking columns
--
-- After running this, insert reactivation leads with campaign_type='reactivation'.
-- The orchestrator reads CAMPAIGN_TYPE env var to decide which bucket to work.

-- ── 1. campaign_type column ────────────────────────────────────────────────────
ALTER TABLE outbound_leads
  ADD COLUMN IF NOT EXISTS campaign_type TEXT NOT NULL DEFAULT 'fresh_lead';

-- ── 2. wa_sent tracking ────────────────────────────────────────────────────────
ALTER TABLE outbound_leads
  ADD COLUMN IF NOT EXISTS wa_sent    BOOLEAN   DEFAULT FALSE;

ALTER TABLE outbound_leads
  ADD COLUMN IF NOT EXISTS wa_sent_at TIMESTAMPTZ;

-- ── 3. Index for orchestrator polling query ────────────────────────────────────
-- (tenant_id, campaign_type, status) matches the WHERE clause exactly
CREATE INDEX IF NOT EXISTS idx_outbound_leads_campaign_status
  ON outbound_leads(tenant_id, campaign_type, status, next_call_at ASC NULLS FIRST);

-- ── 4. Verify ─────────────────────────────────────────────────────────────────
-- Run this SELECT to confirm the columns exist:
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'outbound_leads'
--   AND column_name IN ('campaign_type', 'wa_sent', 'wa_sent_at')
-- ORDER BY column_name;


-- ── 5. Insert sample reactivation leads (edit and uncomment to seed) ──────────
/*
INSERT INTO outbound_leads (tenant_id, phone, name, campaign_type, status)
VALUES
  ('krishna_furniture', '+919876543210', 'Rajesh Sharma',   'reactivation', 'pending'),
  ('krishna_furniture', '+919123456789', 'Sunita Agarwal',  'reactivation', 'pending'),
  ('krishna_furniture', '+918800001234', 'Manoj Verma',     'reactivation', 'pending')
ON CONFLICT DO NOTHING;
*/
