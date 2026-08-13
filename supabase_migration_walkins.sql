-- supabase_migration_walkins.sql
-- Run in Supabase SQL Editor (once only — safe to re-run, everything is
-- IF NOT EXISTS / CREATE OR REPLACE).
--
-- What this does:
--   1. Creates the `walkins` table (exact schema agreed with CRM Claude —
--      do not rename columns without updating the CRM project too).
--   2. A BEFORE INSERT trigger that resolves source/lead_id and visit_number
--      automatically, so this is correct regardless of which client writes
--      the row (this backend, or the CRM's direct Supabase inserts/CSV
--      import — the CRM project does NOT run this repo's Python, so this
--      logic has to live in the DB, not in a Python helper, to cover both
--      write paths).
--
-- Phone matching mirrors supabase_calling.py's normalize_phone() exactly:
-- last-10-digit suffix, ignoring +/country-code/formatting differences —
-- same algorithm, reimplemented in SQL since a DB trigger can't call into
-- the Python codebase. If normalize_phone() ever changes, update the
-- regexp_replace/right(...,10) expression below to match.

-- ── 1. Table ────────────────────────────────────────────────────────────────
create table if not exists walkins (
  id uuid primary key default gen_random_uuid(),
  phone text not null,
  lead_id uuid references outbound_leads(id),
  visit_date timestamp not null,
  source text not null check (source in ('system','offline')),
  visit_number int not null default 1,
  budget_manual numeric,
  budget_wa numeric,
  followup_calls_made int not null default 0,
  converted boolean not null default false,
  converted_date timestamp,
  notes text,
  created_at timestamp not null default now()
);

create index if not exists idx_walkins_phone on walkins(phone);
create index if not exists idx_walkins_lead_id on walkins(lead_id);

-- ── 2. BEFORE INSERT trigger: resolve source/lead_id + visit_number ─────────
-- 'system' means "we know this person through any channel" (call history OR
-- WhatsApp), not just outbound_leads specifically — added 2026-07-16 after a
-- CRM QA test lead exposed that a WhatsApp-only contact (no outbound_leads
-- row, only a `leads` row with source='whatsapp') was resolving to 'offline'
-- on walk-in, indistinguishable from a true walk-in stranger. `leads.id` is
-- NOT a valid walkins.lead_id (that FK targets outbound_leads specifically),
-- so a leads-only match sets source='system' but leaves lead_id null — same
-- as a genuine walk-in, just correctly tagged as a known contact.
create or replace function walkins_before_insert()
returns trigger as $$
declare
  norm_phone      text;
  matched_lead    record;
  matched_wa_lead record;
begin
  -- last-10-digit suffix, digits only — identical rule to normalize_phone()
  norm_phone := right(regexp_replace(coalesce(new.phone, ''), '[^0-9]', '', 'g'), 10);

  if norm_phone <> '' then
    select id into matched_lead
    from outbound_leads
    where right(regexp_replace(coalesce(phone, ''), '[^0-9]', '', 'g'), 10) = norm_phone
    order by created_at desc
    limit 1;
  end if;

  if matched_lead.id is not null then
    new.source  := 'system';
    new.lead_id := matched_lead.id;
  else
    if norm_phone <> '' then
      select id into matched_wa_lead
      from leads
      where right(regexp_replace(coalesce(phone, ''), '[^0-9]', '', 'g'), 10) = norm_phone
      order by created_at desc
      limit 1;
    end if;

    if matched_wa_lead.id is not null then
      new.source  := 'system';
      new.lead_id := null;
    else
      new.source  := 'offline';
      new.lead_id := null;
    end if;
  end if;

  if norm_phone <> '' then
    select coalesce(max(visit_number), 0) + 1 into new.visit_number
    from walkins
    where right(regexp_replace(coalesce(phone, ''), '[^0-9]', '', 'g'), 10) = norm_phone;
  else
    new.visit_number := 1;
  end if;

  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_walkins_before_insert on walkins;
create trigger trg_walkins_before_insert
  before insert on walkins
  for each row
  execute function walkins_before_insert();

-- ── 3. Verify ─────────────────────────────────────────────────────────────────
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'walkins'
-- ORDER BY ordinal_position;

-- ── 4. Manual smoke test (edit and uncomment) ──────────────────────────────
/*
insert into walkins (phone, visit_date, source, budget_manual, notes)
values ('+919876500000', now(), 'offline', 45000, 'test row — safe to delete');

select id, phone, source, lead_id, visit_number, followup_calls_made, created_at
from walkins
order by created_at desc
limit 1;
*/
