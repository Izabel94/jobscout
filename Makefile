# `poetry run` does not auto-load .env. dotenv-cli wraps the command so any
# target below that needs Supabase / LLM credentials reads them from .env.
RUN = poetry run dotenv run --

.PHONY: install lint type test ui discover filter score draft smoke bootstrap-profile
install: ; poetry install
lint:    ; poetry run ruff check . && poetry run ruff format --check .
type:    ; poetry run mypy jobscout
test:    ; $(RUN) pytest -q
ui:      ; PYTHONPATH=. $(RUN) streamlit run jobscout/ui/app.py
discover:; $(RUN) python -m jobscout.discover
filter:  ; $(RUN) python -m jobscout.filter
score:   ; $(RUN) python -m jobscout.score
draft:   ; $(RUN) python -m jobscout.draft
smoke:   ; $(RUN) python -m jobscout.discover --limit 5 --dry-run
bootstrap-profile:
	PYTHONPATH=. $(RUN) python scripts/bootstrap_profile_from_linkedin.py "$(LINKEDIN_URL)"
