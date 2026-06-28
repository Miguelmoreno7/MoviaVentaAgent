alter table public.movia_lead_profiles
  add column if not exists meta_ctwa_clid text,
  add column if not exists meta_ctwa_clid_received_at timestamptz,
  add column if not exists meta_referral jsonb not null default '{}'::jsonb;

create index if not exists movia_lead_profiles_meta_ctwa_clid_idx
  on public.movia_lead_profiles (meta_ctwa_clid)
  where meta_ctwa_clid is not null;

create table if not exists public.movia_meta_conversion_events (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references public.movia_lead_profiles(id) on delete cascade,
  event_name text not null,
  event_id text not null unique,
  status text not null default 'pending',
  payload jsonb not null default '{}'::jsonb,
  response_json jsonb not null default '{}'::jsonb,
  error_text text,
  attempt_count integer not null default 0,
  sent_at timestamptz,
  last_attempted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint movia_meta_conversion_events_event_name_check
    check (event_name in ('LeadSubmitted', 'ViewContent', 'QualifiedLead', 'InitiateCheckout')),
  constraint movia_meta_conversion_events_status_check
    check (status in ('pending', 'sent', 'failed', 'skipped')),
  constraint movia_meta_conversion_events_lead_event_unique unique (lead_id, event_name)
);

create index if not exists movia_meta_conversion_events_lead_idx
  on public.movia_meta_conversion_events (lead_id, created_at desc);

create index if not exists movia_meta_conversion_events_status_idx
  on public.movia_meta_conversion_events (status, last_attempted_at);

alter table public.movia_meta_conversion_events enable row level security;
