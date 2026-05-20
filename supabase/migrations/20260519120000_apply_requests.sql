create table apply_requests (
  id                 uuid primary key default gen_random_uuid(),
  listing_id         uuid not null references listings(id) on delete cascade,
  source             text not null,
  status             text not null default 'pending',
  error              text,
  requested_at       timestamptz not null default now(),
  claimed_at         timestamptz,
  completed_at       timestamptz,
  executed_draft_id  uuid references drafts(id),
  notes              text
);
create index on apply_requests (status, requested_at);
