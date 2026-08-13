-- supabase_migration_batch_id.sql
-- Run in Supabase SQL Editor (once only — safe to re-run with IF NOT EXISTS).
--
-- Adds batch_id to outbound_leads for the reactivation_leads_batched.csv
-- import (995 rows, batch_01_pilot / batch_01..batch_05), so imported rows
-- can be traced back to their source batch and queried/rolled back by batch
-- if needed.

ALTER TABLE outbound_leads
  ADD COLUMN IF NOT EXISTS batch_id TEXT;

CREATE INDEX IF NOT EXISTS idx_outbound_leads_batch_id
  ON outbound_leads(batch_id);

-- Verify:
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_name = 'outbound_leads' AND column_name = 'batch_id';
