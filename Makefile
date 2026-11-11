# NEAR, Filtered — one command per thing a reader might want to do.
#
#   make verify     the command for a judge: tests, then a rebuild from
#                   committed data. No Google Cloud account, no API keys.
#   make rebuild    regenerate results, charts, THESIS.md and the dashboard
#                   from data/cache/. No network.
#   make refresh    re-pull live data (needs .env). Prints a byte estimate
#                   for every query and asks before spending anything.
#
# Anything that can cost money says so in its name or asks first.

UV ?= uv
RUN := $(UV) run

.DEFAULT_GOAL := help
.PHONY: help install env test lint fmt verify rebuild refresh inventory sample-cost window cost clean

help:
	@echo "NEAR, Filtered"
	@echo ""
	@echo "  No keys needed:"
	@echo "    make install      create the virtualenv from the pinned lockfile"
	@echo "    make env          create or repair .env (never overwrites a set value)"
	@echo "    make test         unit tests on the transforms"
	@echo "    make verify       tests + number-drift check + rebuild from cache"
	@echo "    make rebuild      regenerate results, charts, THESIS.md, dashboard"
	@echo "    make window       print the analysis window in use"
	@echo ""
	@echo "  Needs .env (Google Cloud + Intents JWT):"
	@echo "    make inventory    dataset tables, schemas and freshness (free)"
	@echo "    make sample-cost  dry-run one metric query and price it (free)"
	@echo "    make refresh      re-pull everything live (costs money, asks first)"
	@echo "    make cost         total BigQuery bytes and USD spent so far"

install:
	$(UV) sync --all-groups --frozen

# Safe alternative to `cp .env.example .env`, which destroys a working config.
env:
	$(RUN) python scripts/setup_env.py

test:
	$(RUN) pytest

lint:
	$(RUN) ruff check src tests
	$(RUN) ruff format --check src tests

fmt:
	$(RUN) ruff format src tests
	$(RUN) ruff check --fix src tests

# --- the judge's command -------------------------------------------------
# Rebuild FIRST, then test. The tests include the number-drift check against
# the rendered documents, so they must run against what the pipeline just
# regenerated, not against whatever happened to be committed. A fresh clone
# once failed here because metrics.json and THESIS.md were committed out of
# step; this ordering makes that impossible to miss locally and CI also
# checks that the committed documents match the regenerated ones.
verify:
	@echo "=== rebuild from committed data =================================="
	@$(MAKE) --no-print-directory rebuild
	@echo ""
	@echo "=== tests (includes the number-drift check) ======================"
	@$(MAKE) --no-print-directory test
	@echo ""
	@echo "=== hypothesis summary ==========================================="
	@$(RUN) python scripts/scoreboard.py

# Needs no network and no keys: everything comes from data/cache/.
rebuild:
	$(RUN) python -m near_filtered.metrics
	$(RUN) python -m near_filtered.render
	$(RUN) python scripts/build_site.py

# --- live data -----------------------------------------------------------
inventory:
	$(RUN) nf inventory

sample-cost:
	$(RUN) nf sample-cost

window:
	$(RUN) nf window

refresh:
	@echo "refresh: not yet wired - lands Nov 11 with the H1-H5 queries."

cost:
	$(RUN) python scripts/cost_report.py

# Regenerate the og:image social card from the live scoreboard. Needs Chrome;
# the card is data-driven, so rerun this whenever the verdicts change.
og:
	@python3 -m http.server 8129 --directory site & SERVER=$$!; sleep 1; \
	"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
	  --disable-gpu --screenshot=site/og.png --window-size=1200,630 \
	  --hide-scrollbars --virtual-time-budget=4000 http://localhost:8129/og.html; \
	kill $$SERVER; ls -la site/og.png

clean:
	rm -rf results/* .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
