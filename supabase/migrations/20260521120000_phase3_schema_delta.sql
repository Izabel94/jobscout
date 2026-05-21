-- Phase 3 UI deltas.
-- `discovered_at` gets clobbered on every re-upsert, so sorting by it is
-- meaningless. `first_discovered_at` is set ONCE at insert via DEFAULT
-- and explicitly excluded from upsert payloads in jobscout/db.py.
alter table listings
  add column if not exists first_discovered_at timestamptz not null default now(),
  add column if not exists viewed_at timestamptz;

update listings set first_discovered_at = discovered_at;

create index if not exists listings_first_discovered_at_idx on listings (first_discovered_at desc);
create index if not exists listings_viewed_at_idx on listings (viewed_at) where viewed_at is null;

-- Free-text scoring guidance editable in the Settings tab.
alter table profiles
  add column if not exists scorer_notes text;
