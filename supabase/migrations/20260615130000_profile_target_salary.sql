-- Annual gross salary expectation (EUR) for full-time roles — fills
-- "Gehaltsvorstellung" / "salary expectation" fields. Distinct from
-- target_rate_floor_eur, which is an hourly freelance rate.
alter table profiles add column if not exists target_salary_eur numeric;
