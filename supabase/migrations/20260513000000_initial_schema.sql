create extension if not exists "pgcrypto";

create table listings (
  id              uuid primary key default gen_random_uuid(),
  source          text not null,
  source_id       text not null,
  url             text not null,
  title           text not null,
  description     text,
  location        text,
  remote          boolean,
  language        text,
  rate_min        numeric,
  rate_max        numeric,
  rate_unit       text,
  currency        text,
  hours_per_week  numeric,
  duration_weeks  numeric,
  posted_at       timestamptz,
  discovered_at   timestamptz not null default now(),
  raw             jsonb not null,
  score           smallint,
  score_rationale text,
  spam_score      smallint,
  status          text not null default 'new',
  unique (source, source_id)
);
create index on listings (status, score desc nulls last);
create index on listings (discovered_at desc);

create table drafts (
  id              uuid primary key default gen_random_uuid(),
  listing_id      uuid not null references listings(id) on delete cascade,
  language        text not null,
  subject         text,
  body            text not null,
  adapted_cv      text,
  model           text not null,
  prompt_version  text not null,
  created_at      timestamptz not null default now()
);
create index on drafts (listing_id, created_at desc);

create table submissions (
  id              uuid primary key default gen_random_uuid(),
  listing_id      uuid not null references listings(id),
  draft_id        uuid references drafts(id),
  submitted_at    timestamptz not null default now(),
  channel         text not null,
  response_status text not null default 'pending',
  response_at     timestamptz,
  notes           text
);
create index on submissions (response_status, submitted_at desc);

create table onboarding_targets (
  id                 uuid primary key default gen_random_uuid(),
  name               text not null unique,
  category           text not null,
  url                text,
  status             text not null default 'not_started',
  next_action        text,
  next_action_due    date,
  profile_keywords   text,
  target_rate_eur    numeric,
  notes              text,
  updated_at         timestamptz not null default now()
);

create table source_runs (
  id              bigserial primary key,
  source          text not null,
  started_at      timestamptz not null default now(),
  finished_at     timestamptz,
  listings_found  integer,
  listings_new    integer,
  error           text
);
create index on source_runs (source, started_at desc);
