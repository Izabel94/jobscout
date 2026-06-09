-- Salary estimate columns. German full-time postings rarely state salary, so
-- the salary stage estimates a range from Kununu. These are kept separate from
-- rate_min/rate_max (which the scraper owns and re-discovery overwrites) so an
-- estimate survives re-discovery. salary_source records provenance; salary_note
-- holds the basis (e.g. "14 Kununu salaries for similar Hamburg roles").
alter table listings add column if not exists salary_min numeric;
alter table listings add column if not exists salary_max numeric;
alter table listings add column if not exists salary_source text;
alter table listings add column if not exists salary_note text;
