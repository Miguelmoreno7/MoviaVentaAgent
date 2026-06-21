create extension if not exists pgcrypto;
create extension if not exists vector;

create table if not exists public.movia_products (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  status text not null default 'needs_clarification',
  setup_price_mxn numeric(10,2),
  monthly_price_mxn numeric(10,2),
  delivery_time text,
  included_meetings jsonb not null default '{}'::jsonb,
  short_description text,
  source_path text,
  source_version text not null default 'v1',
  approved boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint movia_products_status_check
    check (status in ('available', 'not_available', 'coming_soon', 'needs_clarification'))
);

create table if not exists public.movia_product_features (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.movia_products(id) on delete cascade,
  feature_type text not null,
  position integer not null default 0,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  source_path text,
  created_at timestamptz not null default now(),
  constraint movia_product_features_type_check
    check (feature_type in ('include', 'exclude', 'recommended_when', 'ideal_customer', 'important_rule'))
);

create table if not exists public.movia_channels (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  status text not null,
  description text,
  requirements jsonb not null default '[]'::jsonb,
  source_path text,
  approved boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint movia_channels_status_check
    check (status in ('available', 'in_progress', 'not_available', 'needs_clarification'))
);

create table if not exists public.movia_integrations (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  status text not null,
  provider text,
  description text,
  requirements jsonb not null default '[]'::jsonb,
  source_path text,
  approved boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint movia_integrations_status_check
    check (status in ('available', 'in_progress', 'not_available', 'needs_clarification'))
);

create table if not exists public.movia_official_links (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  label text not null,
  url text not null,
  link_type text not null,
  status text not null default 'official',
  source_path text,
  created_at timestamptz not null default now(),
  constraint movia_official_links_status_check
    check (status in ('official', 'needs_clarification'))
);

create table if not exists public.movia_policies (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  title text not null,
  policy_type text not null,
  status text not null default 'official',
  content text not null,
  data jsonb not null default '{}'::jsonb,
  source_path text,
  approved boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint movia_policies_status_check
    check (status in ('official', 'policy_draft', 'needs_clarification'))
);

create table if not exists public.movia_project_statuses (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  label text not null,
  position integer not null default 0,
  description text,
  is_terminal boolean not null default false,
  source_path text,
  created_at timestamptz not null default now()
);

create table if not exists public.movia_lead_profiles (
  id uuid primary key default gen_random_uuid(),
  external_user_id text not null,
  channel text not null default 'local',
  business_type text,
  main_channel text,
  pain text,
  urgency text,
  buying_signal text,
  current_stage text not null default 'new',
  last_action text,
  profile_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint movia_lead_profiles_channel_user_unique unique (channel, external_user_id),
  constraint movia_lead_profiles_stage_check
    check (current_stage in ('new', 'discovery', 'qualified', 'recommended', 'closing', 'handoff', 'unknown'))
);

create table if not exists public.movia_conversation_messages (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references public.movia_lead_profiles(id) on delete cascade,
  external_message_id text,
  role text not null,
  content text not null,
  analysis jsonb not null default '{}'::jsonb,
  retrieval_metadata jsonb not null default '{}'::jsonb,
  token_usage jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint movia_conversation_messages_role_check
    check (role in ('user', 'assistant', 'system', 'tool'))
);

create table if not exists public.movia_conversation_summaries (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references public.movia_lead_profiles(id) on delete cascade,
  summary text not null,
  stage text,
  facts jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.movia_knowledge_documents (
  id uuid primary key default gen_random_uuid(),
  source_path text not null unique,
  title text not null,
  source_type text not null,
  content_hash text not null,
  metadata jsonb not null default '{}'::jsonb,
  approved boolean not null default true,
  last_ingested_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  constraint movia_knowledge_documents_source_type_check
    check (source_type in ('rag', 'official_doc', 'config', 'needs_clarification'))
);

create table if not exists public.movia_knowledge_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.movia_knowledge_documents(id) on delete cascade,
  chunk_index integer not null,
  content text not null,
  token_estimate integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector(1536),
  created_at timestamptz not null default now(),
  constraint movia_knowledge_chunks_document_index_unique unique (document_id, chunk_index)
);

create or replace function public.set_movia_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_movia_products_updated_at on public.movia_products;
create trigger set_movia_products_updated_at
before update on public.movia_products
for each row execute function public.set_movia_updated_at();

drop trigger if exists set_movia_channels_updated_at on public.movia_channels;
create trigger set_movia_channels_updated_at
before update on public.movia_channels
for each row execute function public.set_movia_updated_at();

drop trigger if exists set_movia_integrations_updated_at on public.movia_integrations;
create trigger set_movia_integrations_updated_at
before update on public.movia_integrations
for each row execute function public.set_movia_updated_at();

drop trigger if exists set_movia_policies_updated_at on public.movia_policies;
create trigger set_movia_policies_updated_at
before update on public.movia_policies
for each row execute function public.set_movia_updated_at();

drop trigger if exists set_movia_lead_profiles_updated_at on public.movia_lead_profiles;
create trigger set_movia_lead_profiles_updated_at
before update on public.movia_lead_profiles
for each row execute function public.set_movia_updated_at();

drop trigger if exists set_movia_conversation_summaries_updated_at on public.movia_conversation_summaries;
create trigger set_movia_conversation_summaries_updated_at
before update on public.movia_conversation_summaries
for each row execute function public.set_movia_updated_at();

create index if not exists movia_products_status_idx
  on public.movia_products (status);
create index if not exists movia_product_features_product_type_idx
  on public.movia_product_features (product_id, feature_type, position);
create index if not exists movia_channels_status_idx
  on public.movia_channels (status);
create index if not exists movia_integrations_status_idx
  on public.movia_integrations (status);
create index if not exists movia_policies_type_status_idx
  on public.movia_policies (policy_type, status);
create index if not exists movia_lead_profiles_external_idx
  on public.movia_lead_profiles (channel, external_user_id);
create index if not exists movia_conversation_messages_lead_created_idx
  on public.movia_conversation_messages (lead_id, created_at desc);
create unique index if not exists movia_conversation_messages_external_unique_idx
  on public.movia_conversation_messages (external_message_id)
  where external_message_id is not null;
create index if not exists movia_knowledge_documents_hash_idx
  on public.movia_knowledge_documents (content_hash);
create index if not exists movia_knowledge_documents_metadata_gin_idx
  on public.movia_knowledge_documents using gin (metadata);
create index if not exists movia_knowledge_chunks_document_idx
  on public.movia_knowledge_chunks (document_id, chunk_index);
create index if not exists movia_knowledge_chunks_metadata_gin_idx
  on public.movia_knowledge_chunks using gin (metadata);
create index if not exists movia_knowledge_chunks_embedding_idx
  on public.movia_knowledge_chunks using ivfflat (embedding vector_cosine_ops)
  with (lists = 100)
  where embedding is not null;

create or replace function public.match_movia_knowledge(
  query_embedding vector(1536),
  match_count integer default 5,
  filter jsonb default '{}'::jsonb
)
returns table (
  id uuid,
  document_id uuid,
  source_path text,
  title text,
  content text,
  metadata jsonb,
  similarity double precision
)
language sql
stable
as $$
  select
    c.id,
    c.document_id,
    d.source_path,
    d.title,
    c.content,
    c.metadata,
    1 - (c.embedding <=> query_embedding) as similarity
  from public.movia_knowledge_chunks c
  join public.movia_knowledge_documents d on d.id = c.document_id
  where c.embedding is not null
    and d.approved is true
    and (filter = '{}'::jsonb or c.metadata @> filter)
  order by c.embedding <=> query_embedding
  limit least(greatest(match_count, 1), 20);
$$;

alter table public.movia_products enable row level security;
alter table public.movia_product_features enable row level security;
alter table public.movia_channels enable row level security;
alter table public.movia_integrations enable row level security;
alter table public.movia_official_links enable row level security;
alter table public.movia_policies enable row level security;
alter table public.movia_project_statuses enable row level security;
alter table public.movia_lead_profiles enable row level security;
alter table public.movia_conversation_messages enable row level security;
alter table public.movia_conversation_summaries enable row level security;
alter table public.movia_knowledge_documents enable row level security;
alter table public.movia_knowledge_chunks enable row level security;

alter table public.movia_products force row level security;
alter table public.movia_product_features force row level security;
alter table public.movia_channels force row level security;
alter table public.movia_integrations force row level security;
alter table public.movia_official_links force row level security;
alter table public.movia_policies force row level security;
alter table public.movia_project_statuses force row level security;
alter table public.movia_lead_profiles force row level security;
alter table public.movia_conversation_messages force row level security;
alter table public.movia_conversation_summaries force row level security;
alter table public.movia_knowledge_documents force row level security;
alter table public.movia_knowledge_chunks force row level security;

