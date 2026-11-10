# Pre-registration

**Written and committed before any data was pulled.** The commit that adds
this file is the proof: compare its timestamp with the first commit that adds
anything under `data/cache/`. `README.md` step 3 tells a reader how.

This file is **frozen** once committed. If we later find a definition was
wrong, we do not edit it — we add a dated amendment at the bottom, and the
amendment is visible in the thesis. Nothing moves the goalposts quietly.

The machine-readable copy of everything below lives in
[`hypotheses/preregistration.json`](hypotheses/preregistration.json). A test
(`tests/test_preregistration.py`) fails if the two disagree, so the thresholds
the code uses cannot drift away from the thresholds published here.

---

## The claim under test

> Once you filter out bots and airdrop farming, NEAR's real economic usage is
> shifting toward cross-chain settlement through NEAR Intents — and that usage
> does, or does not, translate into value for NEAR token holders.

We are testing this claim, not defending it. Three of the five hypotheses
below could come back rejected and the project would still have done its job.
An honest "no" is the result we publish if it is the result we get.

---

## 0. Definitions fixed in advance

### 0.1 The analysis window

Twelve calendar months ending with **the last complete month present in the
dataset**, not the last complete month of the calendar.

This matters and is not a detail. NEAR Lake, the upstream source that fed the
public BigQuery dataset, was retired on 2026-03-24, and the documentation says
only that the dataset "remains available" — not that it is still being written
to. We therefore do not know, before querying, how current the data is.

So the window is derived from `max(partition_id)` across every table we query
(`src/near_filtered/window.py`), and:

- the window's dates are printed in `THESIS.md`, on the dashboard, and under
  every chart;
- the lag between the dataset's last day and the day the pipeline ran is
  reported as a number, not glossed;
- **Intents data is clipped to the same window** for every month-by-month
  comparison, so the two sides of the settlement share always cover the same
  months. Intents activity after the window is reported only in a separately
  labelled section and never enters a headline figure.

### 0.2 Economic account (the bot filter)

An account is **economic** in a 30-day window when, within that window, all
three hold:

| | Condition | Default |
|---|---|---|
| **d** | signed transactions on ≥ d distinct days | **4** |
| **c** | interacted with ≥ c distinct receiver accounts | **2** |
| **b** | held ≥ b NEAR (liquid + staked) at window end | **0.1** |

The three are ANDed. Each alone is cheap to fake: a bot clears **d** easily, an
airdrop farmer clears **c** in a single session, and a dust wallet clears **b**.
Together they are harder, and still not impossible — `LIMITATIONS.md` states
what this filter does not catch, including a funded bot that spreads calls
across contracts.

Chosen defaults and why, decided before seeing any output:

- **d = 4** of 30 days — sustained enough to exclude one-session farming,
  loose enough to keep a genuine weekly user.
- **c = 2** — the smallest threshold that excludes a single-purpose script,
  which is the dominant bot shape.
- **b = 0.1 NEAR** — above dust, below any plausible real balance floor.

Balance comes from `ft_balances_daily` (`liquid + staked`) on the window's last
day. An account with no row there is treated as holding **zero**, not as
missing: it held nothing we can observe, and dropping it would bias the count
upward.

### 0.3 The sensitivity grid

Every H1–H3 result is recomputed over the full grid

```
d ∈ {2, 4, 8}    c ∈ {1, 2, 3}    b ∈ {0, 0.1, 1}   →  27 combinations
```

and every cell is published. Each conclusion is then labelled:

- **robust** — every cell agrees with the prediction
- **depends** — some cells agree, others are flat or disagree
- **reversed** — no cell agrees and at least one points the other way

A "depends" result is reported as "depends". We do not present the single
threshold that looks best, and the grid is cheap precisely so that we cannot
be tempted to: the per-account statistics are computed once and the thresholds
are cross-joined in SQL, so all 27 cells cost the same as one.

### 0.4 The verdict rule

One rule, applied identically to all five hypotheses. We fit an ordinary
least-squares trend on the monthly series and read the 95% confidence interval
on the slope:

| Verdict | Condition |
|---|---|
| **SUPPORTED** | the 95% CI lies entirely in the predicted direction, **and** any extra bar named in the hypothesis is met |
| **REJECTED** | the 95% CI lies entirely in the opposite direction |
| **INCONCLUSIVE** | the 95% CI contains zero |

With twelve monthly points the interval is wide. We report it wide. A series
that merely drifts the right way gets **INCONCLUSIVE**, not a hopeful
"supported" — and we expect that to happen more than once.

### 0.6 What we looked at before freezing

Three probes were run against the data **before** this document was frozen.
Each asked what *can* be measured, never which answer looks better, and each
is committed so a reader can confirm that for themselves:

| probe | question | why it cannot bias a result |
|---|---|---|
| `sql/meta_partitions.sql` | how current is the dataset? | metadata only; no table data read |
| `sql/meta_balance_scale.sql` | are balances in NEAR or yoctoNEAR? | one day, one table; a unit, not an outcome |
| `sql/meta_tx_status_values.sql` | what values does `status` take? | one day; a vocabulary, not an outcome |
| `sql/meta_ft_contract_coverage.sql` | which contracts carry NEP-141 transfers? | one day, **no time series**, so no trend is observable |

The last one changed H4's definition, which is why it is disclosed here
rather than mentioned in passing. It established that an unfiltered native
denominator would be dominated by two reward-token applications. It could not
reveal whether any series is rising or falling, because it covers a single
day.

The balance probe mattered just as much: the balance columns turned out to be
denominated in NEAR, not yoctoNEAR. Had that gone unchecked, every account
would have appeared to hold nothing, and H1 through H3 would have returned
zeros across all 27 grid cells that looked exactly like real findings.

### 0.5 No new hypotheses after the data

These five are the only hypotheses tested. Anything interesting we notice
later appears under a heading reading **"Exploratory (not pre-registered)"**
and is never counted as evidence for or against the claim.

---

## H1 — Real usage

**Metric.** Count of economic accounts per 30-day window, one window per
month, at default thresholds (d=4, c=2, b=0.1). Reported alongside raw
distinct signing accounts, so the gap between "accounts" and "economic
accounts" is visible.

**Window.** The 12 monthly windows of §0.1.

**Prediction.** Growing, or at least not declining: the slope is ≥ 0.

**REJECTED if** the 95% CI of the slope lies entirely below zero at default
thresholds — economic accounts are shrinking.

**What would change our mind.** A rejection at the defaults that is also
labelled *robust* across the grid would mean the "real usage is growing" leg
of the claim is simply false, and we would say so in the first paragraph of
`THESIS.md`.

---

## H2 — Concentration

**Metric.** Two monthly series over receiver accounts, weighted by
transactions from economic accounts only: (a) share of transactions going to
the **top-10** receivers, (b) **HHI** on the 0–1 scale (sum of squared shares).
Both are also computed weighted by transferred value.

**Window.** As §0.1.

**Prediction.** Activity is becoming **less** concentrated: both series fall.

**REJECTED if** the 95% CI of either slope lies entirely **above** zero —
concentration is rising.

**What would change our mind.** Rising concentration would mean the growth in
H1, if any, is one or two contracts rather than a broadening economy. We would
report H1 and H2 together as a single qualified finding rather than letting a
rising account count stand on its own.

---

## H3 — Retention

**Metric.** Monthly cohorts by an account's **first** economic month. For each
cohort, the share still economic at exactly **+1, +3 and +6 months**
(point-in-time, not "active at any time since"). Headline series: retention at
**+3 months** by cohort.

**Window.** Cohorts whose +3 month falls inside §0.1's window. Cohorts whose
+3 month is not yet observable report **NaN**, never zero.

**Prediction.** Newer cohorts retain at least as well as older ones: the slope
of +3-month retention across cohort months is ≥ 0.

**REJECTED if** the 95% CI of that slope lies entirely below zero — newer
cohorts retain worse.

**What would change our mind.** Falling retention alongside a flat or rising
account count would say the top of the funnel is being refilled rather than
the base growing. That reading would go in the thesis's evidence-against
section regardless of how H1 came out.

---

## H4 — Cross-chain shift (our original metric)

**Metric — cross-chain settlement share**, monthly. Reported in two forms,
with the pricing-free one as the headline.

**(a) Count form — HEADLINE.**

```
settlement_share_count(month) =            intents_swaps(month)
                                ───────────────────────────────────────────
                                intents_swaps + native_economic_transfers
```

- `intents_swaps` — 1Click swaps with status `SUCCESS` in the month.
- `native_economic_transfers` — NEP-141 transfers in the month **whose
  counterparty is an economic account** by §0.2's filter, at the default
  thresholds.

**(b) Value form — secondary.** The same ratio in USD, where
`intents_usd` is the sum of `amountInUsd` (supplied by the API, so it needs
no pricing work from us) and `native_usd` covers only those NEP-141 contracts
for which decimals and a daily USD price can both be sourced from a
documented reference, by a rule fixed in advance rather than a list we pick.
Its token coverage is **reported as a percentage of native transfers
priced**, so the reader can see exactly how partial it is.

**If (a) and (b) disagree in direction, H4 is INCONCLUSIVE** and both are
shown. Written down now so neither can be chosen later for reading better.

**Why the economic filter is inside the denominator.** A pre-freeze
feasibility probe (`sql/meta_ft_contract_coverage.sql`, one day's partition,
no time series — see §0.6) found that NEP-141 transfer *counts* are
dominated by two reward-token applications, which together accounted for
roughly three quarters of the day's transfers, while the canonical NEAR
stablecoin contracts accounted for well under one percent. An unfiltered
denominator would therefore be mostly the airdrop-farming behaviour this
thesis exists to filter out, and the ratio would move with one game's reward
schedule rather than with settlement. Applying the same bot filter to both
the denominator and H1 keeps one definition of "real activity" across the
whole thesis.

**Why value is secondary rather than headline.** The dataset carries
`ft_events.delta_amount` as a raw per-token integer and **no decimals
column**, so converting native transfers to USD needs outside metadata for
every contract. The Intents side needs none. Making the priced side the
headline would rest the signature metric on the leg we can least defend, so
it is reported as the secondary and its coverage is stated as a number.

**Pre-registered caveat.** The Intents Explorer API is documented as
covering **1Click swaps only**, so `intents_swaps` and `intents_usd` are
**lower bounds** on Intents activity and are labelled as such wherever they
appear. Both legs are restricted to the same months (§0.1).

Reported alongside: unique swappers per month where the API supplies a
sender (the `senders` field is sometimes an empty array, so the share of
swaps with an identifiable sender is reported next to it rather than the gap
being hidden), and the growth rate of Intents activity against the growth
rate of native economic activity.

**Window.** As §0.1.

**Prediction.** The settlement share is rising.

**REJECTED if** the 95% CI of the slope lies entirely below zero — the share
is falling.

**Pre-registered caveat.** If the dataset's last month is far behind today,
this ratio cannot speak about the present, only about the window. We will say
that in the chart's own subtitle, not only in the limitations file.

**What would change our mind.** A flat or falling share would reject the
central "shifting toward cross-chain settlement" clause of the claim. We
would keep the metric, publish the rejection, and say which of the two legs —
numerator stalling or denominator growing — drove it.

---

## H5 — Value accrual

Two parts. Both are reported, and the second is answered from documents rather
than from data.

**H5a — measured.** Monthly **fees burned** against **new issuance**, and the
resulting **net issuance** (`new issuance − fees burned`), computed from the
dataset: tokens burnt from `execution_outcomes` and
`transactions.receipt_conversion_tokens_burnt`, and supply from `blocks` /
`circulating_supply`.

**Prediction.** Burned fees are **material** relative to issuance and the
ratio is trending toward net-neutral. Two bars, both pre-registered:

1. burned fees ≥ **10%** of gross issuance in the window's final month, and
2. the 95% CI of the slope of `burned / issuance` lies entirely above zero.

**REJECTED if** bar 1 fails **and** the slope's CI does not lie above zero —
fee burn is immaterial and not growing.

**H5b — documentary.** Does any portion of NEAR Intents fees accrue to NEAR
token holders? Answered only from primary sources, cited in `SOURCES.md`.

**Pre-registered in advance:** *if the primary documentation names no mechanism
by which Intents fees reach NEAR holders, that counts as evidence AGAINST the
claim's second clause, and we report it as such* — including if it makes the
whole "translates into value for holders" leg fail. We are writing this
sentence down now, before looking, so that a null finding cannot later be
reframed as "out of scope".

**What would change our mind.** H5a rejected plus H5b finding no accrual
mechanism would mean usage growth, however real, does not reach the token. On
an evidence-judged question that is the most important thing we could report,
and it would lead the thesis.

---

## Bull / base / bear

The three cases, their leading indicators and the levels that would confirm or
kill each, are written **after** the verdicts are in — but the rule for them
is fixed now: indicators must be quantities this pipeline already computes, so
a reader can re-run them next month. **No price targets.** This is research,
not investment advice.

---

## Amendments

*(none — any amendment is appended here with its date and reason, and the
original text above is never edited.)*
