begin;

alter table public.movia_lead_profiles
  add column if not exists previous_stage text,
  add column if not exists stage_before_objection text,
  add column if not exists stage_reason_code text,
  add column if not exists stage_reason text,
  add column if not exists stage_entered_at timestamptz not null default now(),
  add column if not exists stage_updated_at timestamptz not null default now();

alter table public.movia_lead_profiles
  drop constraint if exists movia_lead_profiles_stage_check;

update public.movia_lead_profiles
set current_stage = case current_stage
  when 'recommended' then 'solution_recommended'
  when 'unknown' then 'unknown_recovery'
  else current_stage
end
where current_stage in ('recommended', 'unknown');

alter table public.movia_lead_profiles
  add constraint movia_lead_profiles_stage_check
  check (
    current_stage in (
      'new',
      'discovery',
      'educating',
      'comparing',
      'objection_handling',
      'qualified',
      'solution_recommended',
      'ready_to_start',
      'closing',
      'post_purchase',
      'handoff',
      'unknown_recovery'
    )
  ) not valid;

alter table public.movia_lead_profiles
  validate constraint movia_lead_profiles_stage_check;

alter table public.movia_lead_profiles
  drop constraint if exists movia_lead_profiles_previous_stage_check;

alter table public.movia_lead_profiles
  add constraint movia_lead_profiles_previous_stage_check
  check (
    previous_stage is null
    or previous_stage in (
      'new',
      'discovery',
      'educating',
      'comparing',
      'objection_handling',
      'qualified',
      'solution_recommended',
      'ready_to_start',
      'closing',
      'post_purchase',
      'handoff',
      'unknown_recovery'
    )
  ) not valid;

alter table public.movia_lead_profiles
  validate constraint movia_lead_profiles_previous_stage_check;

alter table public.movia_lead_profiles
  drop constraint if exists movia_lead_profiles_stage_before_objection_check;

alter table public.movia_lead_profiles
  add constraint movia_lead_profiles_stage_before_objection_check
  check (
    stage_before_objection is null
    or stage_before_objection in (
      'new',
      'discovery',
      'educating',
      'comparing',
      'objection_handling',
      'qualified',
      'solution_recommended',
      'ready_to_start',
      'closing',
      'post_purchase',
      'handoff',
      'unknown_recovery'
    )
  ) not valid;

alter table public.movia_lead_profiles
  validate constraint movia_lead_profiles_stage_before_objection_check;

create index if not exists movia_lead_profiles_stage_updated_idx
  on public.movia_lead_profiles (current_stage, stage_updated_at desc);

commit;

-- Local-only Phase 3 migration. Do not apply to production before V2 rollout.
--
-- Rollback notes:
-- 1. Map V2 stages back to the original compact vocabulary:
--    update public.movia_lead_profiles
--    set current_stage = case current_stage
--      when 'solution_recommended' then 'recommended'
--      when 'unknown_recovery' then 'unknown'
--      when 'educating' then 'qualified'
--      when 'comparing' then 'qualified'
--      when 'objection_handling' then 'qualified'
--      when 'ready_to_start' then 'closing'
--      when 'post_purchase' then 'handoff'
--      else current_stage
--    end;
-- 2. Drop this migration's index, constraints, and added columns.
-- 3. Recreate the original movia_lead_profiles_stage_check constraint:
--    current_stage in ('new', 'discovery', 'qualified', 'recommended', 'closing', 'handoff', 'unknown').
