# NEAR, Filtered

**Status: work in progress. Submission target Nov 14, 2026.**

A pre-registered, reproducible test of one claim about NEAR — not a pitch for it.

> **The claim under test:** once you filter out bots and airdrop farming, NEAR's
> real economic usage is shifting toward cross-chain settlement through NEAR
> Intents — and that usage does, or does not, translate into value for NEAR
> token holders.

We wrote down five hypotheses, the exact metric for each, and the result that
would count as **rejected**, and committed that file *before* pulling any data.
The git history is the proof. We report whatever the data says; a negative
result gets published with the same care as a positive one.

Every number in this thesis is generated from the data. `make verify` checks it.

---

## 1. Verdict per hypothesis

<!-- GENERATED:scoreboard — filled from results/metrics.json by `make rebuild`. -->
> Not yet computed. This table is generated; it stays empty until the pipeline
> has run. No number in this repository is typed by hand.

| # | Hypothesis | Metric | Verdict |
|---|------------|--------|---------|
| H1 | Real usage | — | pending |
| H2 | Concentration | — | pending |
| H3 | Retention | — | pending |
| H4 | Cross-chain shift | — | pending |
| H5 | Value accrual | — | pending |

See [HYPOTHESES.md](HYPOTHESES.md) for the frozen pre-registration.

## 2. Check our work in 2 minutes

<!-- Filled in once `make verify` is wired up. -->
1. `make verify` — runs the unit tests, the number-drift test and a full
   rebuild from cached data. **No Google Cloud account and no API keys needed.**
2. Open the dashboard — `TBD`.
3. Open the commit that added `HYPOTHESES.md` and compare its timestamp with
   the first commit that added data. The hypotheses came first.

## 3. The strongest evidence against this thesis

<!-- GENERATED:evidence_against — deliberately near the top, not buried. -->
> Pending. This section is generated from the results and is given the same
> prominence as the supporting evidence.

## 4. Our original metric: cross-chain settlement share

Of the economic value NEAR settles in a month, what fraction is settled
*across chains* through NEAR Intents rather than natively on NEAR? Exact
definition, units and caveats: [METHODOLOGY.md](METHODOLOGY.md).

## 5. Data sources, cost and limits

- NEAR public dataset on BigQuery: `bigquery-public-data.crypto_near_mainnet_us`
- NEAR Intents Explorer API — 1Click swaps only, so a **lower bound** on Intents activity
- Price data for USD conversion and value accrual context only, never as evidence of usage
- Tokenomics parameters from primary sources — see [SOURCES.md](SOURCES.md)

Cost of a full live refresh and every known limitation:
[LIMITATIONS.md](LIMITATIONS.md).

## 6. Rerunning it live

`make refresh` re-pulls everything (needs `.env`; see `.env.example`). It
dry-runs every query and prints the bytes it would scan before asking you to
confirm. A scheduled monthly refresh keeps the thesis living.

## 7. Built with

<!-- Completed before submission; the hackathon rules require listing
     libraries, templates and AI-assisted code. -->
AI coding tools were used during development of this project.

Full dependency, dataset and API list: pending.

## 8. Also submitted at NEAR HACKATHON by the same team

**Proving Ground** — `PROVING_GROUND_REPO_URL` *(link to be filled in)*.
The two projects are independent.

## 9. License

MIT — see [LICENSE](LICENSE).

---

*This is research, not investment advice.*
