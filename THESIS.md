# NEAR, Filtered

**Generated 2026-11-10T16:50:55+00:00 from `results/metrics.json`. Not written by hand.**

Window: **2025-11-01 to 2026-10-31** (12 months).
Dataset current to 2026-11-09, 1 day(s) before this run.

---

## The claim we tested

> Once you filter out bots and airdrop farming, NEAR's real economic usage is
> shifting toward cross-chain settlement through NEAR Intents — and that usage
> does, or does not, translate into value for NEAR token holders.

We wrote five hypotheses, the exact metric for each, and the result that would
count as rejected, and committed that file before pulling any data.

**Four of the five predictions went against us.** This document reports that.

## Verdicts

| # | Hypothesis | Predicted | Verdict |
|---|---|---|---|
| H1 | Real usage | growing or flat | **REJECTED** |
| H2 | Concentration | less concentrated | **REJECTED** |
| H3 | Retention | newer cohorts hold up | **INCONCLUSIVE** |
| H4 | Cross-chain shift | share rising | **SUPPORTED** (provisional, 5/12 months) |
| H5 | Value accrual | burn material, trending neutral | **REJECTED** |

One rule produced every row: fit an ordinary least-squares trend on the
monthly series, then read the 95% confidence interval on the slope. Entirely
in the predicted direction is SUPPORTED, entirely opposite is REJECTED, and
spanning zero is INCONCLUSIVE. No verdict was written by hand.

---

## The strongest evidence against this thesis

This section comes before the supporting evidence, not after it.

**1. Real usage did not grow. It fell by 69.6%.**
Economic accounts went from 50,158 to
15,267 over the window, a slope of
-2,699 accounts per month with a 95%
interval of [-3,959, -1,439].
The interval does not reach zero.

This is not an artefact of where we set the bar. Across the
27-cell sensitivity grid the trend is **down in
23 cells, flat in 4, and
up in 0**. The grid label is
**reversed**. Tightening the filter makes the decline steeper,
which is the opposite of what a threshold artefact looks like.

**2. Activity concentrated sharply rather than broadening.**
The top-10 receiver share rose from 14.8%
to 62.2%, and HHI rose from
0.0047 to 0.0589.
We predicted both would fall.

**3. Fee burn does not come close to offsetting issuance, and is shrinking.**
In the final month, burn was 1.42%
of gross issuance against a pre-registered materiality bar of
10%. Over the window NEAR burned
618,107 against net issuance of
31,674,541 — burn offsets
2.0% of it. Net issuance
was positive in every month.

**4. No primary source documents any Intents fee reaching NEAR holders.**
We checked the Intents fees page, the 1Click fee configuration, the FAQs, the
authentication page and the NEAR-token page. The protocol fee goes to a fee
collector; 1Click keeps its share; the near-intents.org front end routes its
fee to a DAO account. None of them describes a mechanism by which any portion
is burned, staked, or paid to NEAR holders. We pre-committed, in writing and
before looking, to treating a null here as evidence against.

**5. Our bot filter does not catch every bot.**
In 2025-11,
50,158
accounts that cleared the filter sent
113,425,819
transactions between them — a mean of
2,261
against a median of
36.
That distribution is not a population of humans.

---

## Evidence for the thesis

> **Incomplete measurement.** This verdict rests on
> 5 of 12 months. The Intents
> leg is still being pulled, and the months not yet measured are the later
> ones. Treat H4 as provisional until this notice disappears from a
> regenerated copy of this document.

**The cross-chain shift is real.** The settlement share rose from
1.73% to
4.49% across
5 measured months, with a slope of
0.839% per month and a 95% interval of
[0.078%, 1.599%].

**But read the decomposition before using that number.** Over the same months
Intents swaps grew +32.8%
while native transfers by economic accounts fell
-50.4%. The ratio is driven
by **both**. A share that rises partly because
its denominator is collapsing is a different claim from one that rises because
its numerator is growing, and we are not going to let the first be read as the
second.

**Retention did not collapse.** H3 is INCONCLUSIVE:
+3-month retention drifts from
14.7% to 8.5%, but the
95% interval spans zero. We report that as inconclusive rather than as decline.

---

## What would change our minds

| finding | what it would mean |
|---|---|
| Economic accounts rising for three consecutive months at default thresholds, robust across the grid | H1's rejection was a window artefact; the decline reversed |
| Top-10 share falling back below 14.8% while account counts hold | concentration was a transition, not a trend |
| Burn exceeding 10% of gross issuance in any month | H5a's materiality bar met; value accrual becomes arguable |
| A primary source documenting Intents fees reaching NEAR holders | H5b's null answered; the second clause of the claim becomes testable |
| The settlement share rising while native transfers are flat or growing | the shift is numerator-driven, which is the strong form of the claim |

Each is a quantity this pipeline already computes, so anyone can re-run it
next month with `make refresh`.

---

## The original metric: cross-chain settlement share

Of the economic activity NEAR settles in a month, what fraction is settled
across chains through NEAR Intents rather than natively on NEAR?

Measured on 22 sampled days, the same days on both sides
of the ratio so the two legs always cover identical periods.

| month | Intents swaps | native transfers | share |
|---|---|---|---|
| 2025-11 | 60,293 | 3,434,749 | 1.73% |
| 2025-12 | 53,866 | 3,186,169 | 1.66% |
| 2026-01 | 90,683 | 2,107,840 | 4.12% |
| 2026-02 | 83,468 | 1,762,538 | 4.52% |
| 2026-03 | 80,087 | 1,703,733 | 4.49% |

Two caveats travel with every one of these numbers. The Intents Explorer API
covers **1Click swaps only**, so the numerator is a lower bound on Intents
activity. And a sender is identifiable on only
48.9% of swaps, so unique-swapper counts cover
part of the sample rather than all of it.

The value form of this metric is **not computed**: native token coverage is
0.0%, because
`ft_events` carries no decimals column. That is why the count form, which
needs no pricing, was pre-registered as the headline.

---

## Sensitivity

H1 was recomputed across all 27 threshold
combinations and every cell is published in `results/metrics.json`.

| | cells |
|---|---|
| trend down | 23 |
| flat | 4 |
| trend up | 0 |

Label: **reversed**.

Publishing every cell costs the same as publishing one, because the grid is
a cross-join over per-account results that were computed once. There was
never an incentive to search for a flattering threshold.

---

## Amendments to the pre-registration

3 amendment(s), each with its reason and an
assessment of whether it could bias a result. The original text is never
edited.

- **A1** (2026-11-10, H4) — Intents and native legs measured from a stratified sample of 4 days per month (the 5th, 12th, 19th, 26th), 48 days total, reported as per-day rates with a confidence interval
- **A2** (2026-11-10, H1) — the b threshold's balance source moves from ft_balances_daily to account_changes, taking each account's balance at its last change inside the window; balances there are yoctoNEAR and are divided by 1e24
- **A3** (2026-11-10, H3) — the first cohort in the window (2025-11) is excluded from the headline trend; both figures are published

---

## Conclusion

On the evidence we gathered, the headline claim does not hold in the form it
was written. NEAR's bot-filtered economic activity contracted over the window
rather than growing, and did so robustly across every threshold we tested.
Activity concentrated into fewer contracts rather than broadening. Fee burn
remains a rounding error against issuance and is shrinking, and no primary
source documents any Intents fee reaching NEAR holders.
The cross-chain shift itself is real and measurable — it is the one
pre-registered prediction that survived — but on the measured months it owes
as much to NEAR's native activity shrinking as to Intents growing, and
nothing we found connects it to value for the token.

The useful version of this result is not "NEAR is failing". It is that the
single leg of the thesis that survived contact with the data is the one about
settlement moving cross-chain, and that leg currently pays nothing to
holders. Anyone underwriting NEAR on a value-accrual argument should be able
to point at the mechanism. We could not find one.

---

*Cost of the full refresh behind this document:
63 queries, 870.33 GiB billed.
Every number above is generated; `make verify` checks it.*

*This is research, not investment advice.*
