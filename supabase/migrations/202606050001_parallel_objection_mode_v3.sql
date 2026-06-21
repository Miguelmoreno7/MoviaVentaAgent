begin;

alter table public.movia_lead_profiles
  add column if not exists conversation_mode text not null default 'normal';

alter table public.movia_lead_profiles
  drop constraint if exists movia_lead_profiles_conversation_mode_check;

alter table public.movia_lead_profiles
  add constraint movia_lead_profiles_conversation_mode_check
  check (conversation_mode in ('normal', 'handling_objection')) not valid;

alter table public.movia_lead_profiles
  validate constraint movia_lead_profiles_conversation_mode_check;

create index if not exists movia_lead_profiles_conversation_mode_idx
  on public.movia_lead_profiles (conversation_mode)
  where conversation_mode = 'handling_objection';

commit;

-- Local/evaluation Phase V3.2 migration. Do not apply to production before the full V3 rollout.
--
-- Rollback notes:
--   drop index if exists public.movia_lead_profiles_conversation_mode_idx;
--   alter table public.movia_lead_profiles
--     drop constraint if exists movia_lead_profiles_conversation_mode_check;
--   alter table public.movia_lead_profiles
--     drop column if exists conversation_mode;
