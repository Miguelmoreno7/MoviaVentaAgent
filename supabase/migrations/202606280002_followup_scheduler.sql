create table if not exists public.movia_followup_attempts (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references public.movia_lead_profiles(id) on delete cascade,
  trigger_user_message_id uuid not null references public.movia_conversation_messages(id) on delete cascade,
  followup_type text not null default 'standard',
  status text not null default 'claimed',
  message_text text,
  send_result jsonb not null default '{}'::jsonb,
  error_text text,
  attempt_count integer not null default 0,
  claimed_at timestamptz,
  sent_at timestamptz,
  skipped_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint movia_followup_attempts_type_check
    check (followup_type in ('standard')),
  constraint movia_followup_attempts_status_check
    check (status in ('claimed', 'sent', 'failed', 'skipped')),
  constraint movia_followup_attempts_attempt_count_check
    check (attempt_count >= 0),
  constraint movia_followup_attempts_lead_trigger_type_unique
    unique (lead_id, trigger_user_message_id, followup_type)
);

create index if not exists movia_followup_attempts_status_idx
  on public.movia_followup_attempts (status, updated_at);

create index if not exists movia_followup_attempts_lead_idx
  on public.movia_followup_attempts (lead_id, created_at desc);

create index if not exists movia_followup_attempts_trigger_idx
  on public.movia_followup_attempts (trigger_user_message_id);

alter table public.movia_followup_attempts enable row level security;
