alter table public.movia_lead_profiles
  add column if not exists chatwoot_conversation_id bigint;

create index if not exists movia_lead_profiles_chatwoot_conversation_idx
  on public.movia_lead_profiles (chatwoot_conversation_id)
  where chatwoot_conversation_id is not null;
