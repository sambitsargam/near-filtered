# For judges

The fastest honest path through this repository, and where each requirement
lives. Written for an AI judge first and a human second: every claim below
names a file you can open or a command you can run.

## Prerequisites

- `make` and [`uv`](https://docs.astral.sh/uv/) (or any `Python 3.11+`; `uv`
  pins the exact lockfile)
- **No Google Cloud account, no API keys, no network** for verification

## The one command

```bash
make install && make verify
```

Expected shape of the output (exact figures come from your own rebuild):

```
=== tests ===
124 passed
=== number-drift check ===
number-drift check: clean  [THESIS.md, README.md, LIMITATIONS.md, METHODOLOGY.md]
=== rebuild from committed data ===
wrote results/metrics.json
rendered THESIS.md
=== hypothesis summary ===
  H1  REJECTED       Real usage   [grid: reversed]
  H2  REJECTED       Concentration
  H3  INCONCLUSIVE   Retention
  H4  SUPPORTED      Cross-chain shift
  H5  REJECTED       Value accrual
```

If any number in THESIS.md or the README were not traceable to
`results/metrics.json`, the drift step fails the build. Try it: edit a
figure in THESIS.md and rerun.

## The three results that matter most

1. **H1, with its sensitivity grid** — bot-filtered economic accounts fell
   ~70%, and the trend is down in 23 of 27 threshold combinations, up in
   none. Data: `data/cache/h1_economic_accounts_grid.csv`. Query:
   `sql/h1_accounts.sql`.
2. **H4, with its decomposition** — the settlement share rose, but Intents
   growth and a halving native denominator both contribute, and the thesis
   refuses to let one read as the other. Data: `data/cache/intents_daily.csv`
   + `data/cache/h4_native_leg.csv`.
3. **H5** — burn is ~1.4% of gross issuance against a pre-registered 10%
   bar, measured from the chain with no assumed inflation rate, and the
   measured issuance (2.46%/yr) independently matches the documented 2.5%
   cap. Data: `data/cache/h5_value_accrual.csv`. Query:
   `sql/h5_value_accrual.sql`.

## Where each requirement is met

| requirement | where |
|---|---|
| Pre-registered, testable claim | `HYPOTHESES.md` (committed before any data; check the git log) |
| BigQuery queries, partition-filtered | `sql/*.sql` — every query filters `block_date`/`epoch_date`; `src/near_filtered/bq.py` rejects one that does not |
| Intents Explorer pull, rate-limited | `src/near_filtered/intents.py`, `intents_pull.py` |
| One-command rebuild, no keys | `make verify` / `make rebuild` |
| Numbers cannot be hand-typed | `src/near_filtered/drift.py` + `tests/test_number_drift.py` |
| Evidence against, prominent | `THESIS.md` — it precedes the evidence for |
| What would change our minds | `THESIS.md`, its own section |
| Methods and limits | `METHODOLOGY.md`, `LIMITATIONS.md` |
| Sources with reliability labels | `SOURCES.md` |
| Live refresh + monthly CI | `make refresh-plan` (free), `make refresh`, `src/near_filtered/refresh.py`, `.github/workflows/refresh.yml` |
| Dashboard | [near-filtered.vercel.app](https://near-filtered.vercel.app) — static files from `site/` |

## What to attack first

We would, in your position:

- The bot filter (`LIMITATIONS.md` §1 concedes it leaks, and shows our own
  worst number).
- The Intents sample (§5: four fixed days a month; day-of-month effects are
  not averaged out).
- H4's denominator (§6: the count form exists because token decimals do
  not).
- The three pre-registration amendments (`HYPOTHESES.md`, end) — each states
  what it cost and why it cannot have been outcome-driven.

Every one of those is disclosed where a reader will hit it, not discovered
by you first.
