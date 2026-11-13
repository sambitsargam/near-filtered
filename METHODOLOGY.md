# Methodology

How every number in this repository is produced. The pre-registration in
[HYPOTHESES.md](HYPOTHESES.md) fixes *what* we test; this file describes
*how*, in enough detail to rebuild it or to find a mistake.

Known weaknesses live in [LIMITATIONS.md](LIMITATIONS.md). Sources and their
reliability live in [SOURCES.md](SOURCES.md).

---

## 1. The window

Twelve calendar months ending with the last **complete** month present in
the dataset, not the last complete month of the calendar.

The window is derived at run time from `max(partition_id)` across every
table we query (`src/near_filtered/window.py`), anchored on the
**earliest-ending** of them so no month appears in one series and not
another. A partial final month would read as a collapse in every chart, so
it is dropped unless the data runs to its last day.

The dataset's lag at the time of the run is measured and carried into
`results/metrics.json`, `THESIS.md` and the dashboard. This matters because
the upstream source that fed the dataset was retired in March 2026 and the
documentation does not say whether ingestion continued; rather than assume
either way, we measure it on every run.

Freshness is read from `INFORMATION_SCHEMA.PARTITIONS`, which is metadata
and costs nothing. A `SELECT MAX(block_date)` would answer the same question
while scanning the date column of every partition ever written.

## 2. The economic account filter

Within a 30-day window, an account is **economic** when all three hold:

| | condition | default |
|---|---|---|
| d | signed transactions on ≥ d distinct days | 4 |
| c | interacted with ≥ c distinct receiver accounts | 2 |
| b | held ≥ b NEAR (liquid + staked) at window end | 0.1 |

A 30-day window rather than a calendar month, so a February measured over 28
days is comparable with a March measured over 31.

**Balance source.** `account_changes`, taking each account's balance at its
last recorded change inside the window (amendment A2). Every transaction
burns gas, so any account that transacted appears there. Balances in that
table are **yoctoNEAR** and are divided by 1e24 — verified by probe, not
assumed, because the originally pre-registered source `ft_balances_daily` is
denominated in NEAR and covers 0.38% of signers.

**Missing balance counts as zero**, not as missing. An account with no
balance row held nothing we can observe; dropping it would bias the economic
count upward.

**Transactions counted.** Every signed transaction. `transactions.status`
describes receipt conversion rather than execution success, so filtering on
it is close to a no-op.

## 3. The sensitivity grid

Every H1–H3 result is recomputed over

```
d ∈ {2, 4, 8}   c ∈ {1, 2, 3}   b ∈ {0, 0.1, 1}   →  27 combinations
```

and **every cell is published**. Each conclusion is labelled **robust** (all
cells agree), **depends** (mixed) or **reversed** (none agree and at least
one points the other way).

The grid is affordable by construction: one query per month returns the
accounts clearing the loosest cell, and every tighter cell is a subset of
that result. The full sensitivity analysis therefore costs the same as a
single threshold, which removes any incentive to report a flattering one.

## 4. Concentration (H2)

Monthly, over transactions sent by **economic accounts only**, grouped by
receiver account:

- **top-10 share** — the fraction going to the ten busiest receivers.
- **HHI** — the sum of squared receiver shares, on the **0–1 scale**. 1.0 is
  one receiver taking everything; 1/n is n equal receivers. We state the
  scale because the alternative `0-10,000` convention differs by four orders
  of magnitude.

Restricting to economic accounts matters: an unfiltered measure would mostly
describe whichever reward application was busiest that month.

## 5. Cohorts (H3)

A cohort is the set of accounts whose **first** economic month is that
month. Retention at +k is the share of the cohort that is economic again in
the month exactly k months later — **point-in-time**, not "active at any
time since", which could only ever rise.

A cohort whose +k month falls outside the window reports **NaN**, never
zero: "we cannot see it yet" and "nobody came back" are different findings.

The window's first cohort is **left-censored** — there is no history before
the window starts, so every account active in that month appears new — and
is excluded from the headline trend (amendment A3). Both figures are
published.

## 6. Cross-chain settlement share (H4)

Two forms, both pre-registered, with the pricing-free one as the headline.

**Count form (headline).** Successful 1Click swaps in the month, over those
swaps plus NEP-141 transfers whose counterparty is an economic account.

**Value form (secondary).** The same ratio in USD. `intents_usd` is the sum
of `amountInUsd`, supplied by the API. `native_usd` covers only contracts
whose decimals and daily price can both be sourced, and its **coverage is
reported as a percentage of native transfers priced**.

If the two forms disagree in direction, H4 is **INCONCLUSIVE** and both are
shown.

**Sampling (amendment A1).** Both legs are measured on the same 48 days —
the 5th, 12th, 19th and 26th of each month — and reported as per-day rates
with an interval across the four days in each month. A census of the Intents
leg is roughly 10.5 million swaps and over fifteen hours at the documented
rate limit.

**Chain attribution.** The origin chain is read from the Intents asset id.
Four namespaces appear in real traffic and all four are parsed:
`nep141:<chain>-<addr>.omft.near` (bridged), other `nep141:` accounts
(NEAR-native), `1cs_v1:<chain>:…`, and `nep245:<contract>:<evm chain id>_…`.
An unmapped EVM chain id surfaces as `eip155:<id>` rather than being
guessed.

## 7. Value accrual (H5)

**H5a is measured from the chain, not derived from a cited rate**, because
the tokenomics record is contradictory. The accounting identity used is

```
supply_end = supply_start + minted − burned
⇒ gross issuance = (supply_end − supply_start) + burned
⇒ net issuance   =  supply_end − supply_start
```

Net issuance is therefore directly observable as the change in total supply,
and gross issuance follows. **No inflation rate is plugged in anywhere.**

Burn has two components and both are counted: gas burnt executing receipts
(`execution_outcomes.tokens_burnt`) and the fee burnt converting a
transaction into its first receipt
(`transactions.receipt_conversion_tokens_burnt`). Counting only the first
would understate it.

All three columns are yoctoNEAR, verified by probe.

**H5b is documentary** and answered only from primary sources. The
pre-registration commits in advance to treating "no documented mechanism" as
evidence *against* the claim rather than as out of scope.

## 8. Statistics

One method, applied identically everywhere: an ordinary least-squares fit of
the monthly series on a 0-based time index, with a **95% t-interval on the
slope**. The verdict rule is mechanical:

| verdict | condition |
|---|---|
| SUPPORTED | the interval lies entirely in the predicted direction, and every extra bar is met |
| REJECTED | the interval lies entirely in the opposite direction |
| INCONCLUSIVE | the interval contains zero |

With twelve monthly points these intervals are wide, and we report them wide.
A series that merely drifts the predicted way is **INCONCLUSIVE**, not
supported. No other inferential test is used, and no hypothesis was added
after seeing data.

## 9. Cost control

Every query against the public dataset must filter on a partition column
with a bounded range; `guard_sql` rejects the text otherwise, checked against
the comment-stripped SQL so a commented-out filter cannot satisfy it.
`SELECT *` is refused. Every query is dry-run first, and runs under
`maximum_bytes_billed` so BigQuery aborts server-side rather than overrunning.

Every executed query appends a row to `data/cache/bq_cost_ledger.csv`, which
is committed — so the refresh cost quoted in the README is itself a generated
number.

## 10. Reproducibility

`make rebuild` regenerates `results/metrics.json`, every chart, `THESIS.md`
and the dashboard from the committed aggregates in `data/cache/`. **No
Google Cloud account, no API keys, no network.**

`make refresh-plan` prices every query a live refresh would run, for free.
`make refresh` re-pulls live data after asking, then rebuilds; it needs `.env`.

`make verify` runs the unit tests, the number-drift check and a full rebuild,
then prints the verdict for each hypothesis.

Row-level data is never committed. The per-account results that H1 and H3 are
derived from live in `data/cache/raw_full/`, which is gitignored; only the
aggregates they reduce to are in the repository.
