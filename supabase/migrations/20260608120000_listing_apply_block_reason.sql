-- A listing whose external apply page can't be auto-filled (login wall,
-- account-creation step, non-standard widget). NULL = fillable / not yet tried.
-- The dashboard badges these for manual apply; the worker won't re-attempt them.
alter table listings add column if not exists apply_block_reason text;
