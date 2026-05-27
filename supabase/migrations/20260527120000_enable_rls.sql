-- Enable Row-Level Security on all public tables.
--
-- Resolves Supabase advisory `rls_disabled_in_public` ("table publicly
-- accessible"). The app connects with the service-role key, which bypasses
-- RLS entirely, so normal operation is unaffected and no policies are needed.
-- With RLS enabled and no permissive policies, the public `anon` role is
-- denied all access — which is the intended posture for this single-operator
-- app (nothing legitimately talks to the DB with the anon key).

alter table public.listings       enable row level security;
alter table public.drafts         enable row level security;
alter table public.apply_requests enable row level security;
alter table public.profiles       enable row level security;
alter table public.submissions    enable row level security;
alter table public.source_runs    enable row level security;
