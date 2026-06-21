begin;

alter table public.movia_lead_profiles
  add column if not exists active_objection jsonb not null default '{}'::jsonb;

alter table public.movia_lead_profiles
  drop constraint if exists movia_lead_profiles_active_objection_object_check;

alter table public.movia_lead_profiles
  add constraint movia_lead_profiles_active_objection_object_check
  check (jsonb_typeof(active_objection) = 'object') not valid;

alter table public.movia_lead_profiles
  validate constraint movia_lead_profiles_active_objection_object_check;

create index if not exists movia_lead_profiles_active_objection_gin_idx
  on public.movia_lead_profiles
  using gin (active_objection)
  where active_objection <> '{}'::jsonb;

commit;

-- Local-only Phase 4 migration. Do not apply to production before V2 rollout.
--
-- Rollback notes:
--   drop index if exists public.movia_lead_profiles_active_objection_gin_idx;
--   alter table public.movia_lead_profiles
--     drop constraint if exists movia_lead_profiles_active_objection_object_check;
--   alter table public.movia_lead_profiles
--     drop column if exists active_objection;
