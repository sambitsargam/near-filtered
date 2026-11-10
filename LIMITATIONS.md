# Limitations

What this study cannot tell you, and where it could be wrong. Written to be
read by someone trying to find the weak joint, because that is what a
reader should be doing.

Nothing here is hedging about results we dislike. Every item below was
either found while building the pipeline or was a known cost of a decision
we took deliberately.

---

## 1. The bot filter is a filter, not a truth

**It does not catch a funded bot that spreads its calls.** The pre-registered
definition — active on ≥ d days, touching ≥ c distinct receivers, holding
≥ b NEAR — is cheap to satisfy deliberately. The evidence is in our own
output: in 2025-11, 50,158 "economic" accounts sent 113,425,819 transactions
between them, a mean of about 2,261 each against a **median of 36**. That
distribution is not a population of humans. Some accounts clearing the bar
are plainly automated.

What rescues the conclusion is not the filter's precision but the
**sensitivity grid**: the H1 result holds in 23 of 27 threshold
combinations and reverses in none, and the decline is *steeper* at tighter
thresholds. A result that only appeared at one setting would not be
reportable.

**It measures signers, not humans.** One person may control thousands of
accounts; one account may serve thousands of people. We count accounts
because that is what the chain records.

## 2. Raw account counts are extremely noisy

Distinct signing accounts per 30-day window swing wildly: 556,744 in
2025-11, 3,804,774 in 2026-02, 212,932 in 2026-08, 816,171 in 2026-10. We do
not have an explanation for the February figure. It is reported as measured
and is **not** used as a denominator for any verdict — it appears only
alongside the filtered series so a reader can see the gap between "accounts"
and "economic accounts".

## 3. Balance is measured at the last change inside the window

Amendment A2 moved the balance source to `account_changes`, which records a
balance on every change. That means the balance used is the account's
balance at **its last activity inside the window**, not at midnight on the
window's final day. For an active account the two are close; for an
inactive one no balance is observable at all.

The source we originally pre-registered, `ft_balances_daily`, turned out to
cover **3,064 of 816,171 signers (0.38%)**. Anyone reusing that table for
balance should check its coverage first.

## 4. Transaction status is not execution success

`transactions.status` describes whether a transaction converted into a
receipt, not whether execution succeeded, and held a single value
(`SUCCESS_RECEIPT_ID`) across 502,649 rows on the probe date. True
execution outcomes live in `execution_outcomes`, four times the size. We
pre-registered counting every signed transaction — a fee was paid and intent
was real — and did not join the larger table. A failed-but-paid transaction
therefore counts.

## 5. The Intents numbers are a lower bound, twice over

**Scope.** The Explorer API is documented as covering **1Click swaps only**.
Any Intents activity settled another way is invisible to us. Every Intents
figure is a floor, not a measurement of total Intents activity.

**Sampling.** Amendment A1: a census is about 10.5 million swaps and over
fifteen hours at the documented one-request-per-five-seconds limit, which
does not fit before the deadline. We sample four whole days a month — the
5th, 12th, 19th and 26th — and report per-day rates with an interval. Two
consequences:

- sampling error, which is reported rather than hidden; and
- **any day-of-month effect is not averaged out**, because the same four
  dates recur in every month. If swap activity has a monthly cycle aligned
  to those dates, we would not see it.

**Identifiable swappers.** The `senders` field is sometimes an empty array,
so unique-swapper counts cover only part of the sample. The share of swaps
with an identifiable sender is published next to the count.

## 6. The value form of the settlement share has partial token coverage

`ft_events.delta_amount` is a raw per-token integer and the dataset carries
**no decimals column**, so converting native transfers to USD needs outside
metadata for every contract. The Intents side needs none — the API supplies
`amountInUsd`.

That asymmetry is why the **count form is the headline** and the value form
is secondary, with its token coverage reported as a percentage. A reader
who only takes the value number is taking the weaker of the two.

## 7. Bridged assets are classified by asset id, not by economics

`parse_chain` reads the origin chain out of the Intents asset id. Four
namespaces appear in real traffic and all four are handled, but
**Rainbow-Bridge style tokens such as `*.factory.bridge.near` and
`nbtc.bridge.near` are counted as NEAR**, because their account ids encode
no origin chain. They are NEAR-side representations of foreign assets, so
some genuinely cross-chain value is counted on the native side. This makes
the settlement share **conservative**, not inflated.

## 8. Twelve points is not many

Every trend is an ordinary least-squares fit on twelve monthly
observations, and the resulting intervals are wide. That is why a series
drifting the predicted way is reported **INCONCLUSIVE** rather than
supported. H3 is inconclusive for exactly this reason, and we would rather
say so than reach for a method that makes twelve points look like more.

The cohort analysis has fewer still: eight observations after excluding the
left-censored first cohort (amendment A3).

## 9. The window is historical by construction

The window ends with the last **complete** month in the dataset. Nothing
here speaks to the days since. The window's dates, and the dataset's lag at
the time of the run, are printed in `THESIS.md`, on the dashboard and in
`results/metrics.json`.

## 10. An unexplained structural break in April 2026

Burn falls from 2.9% to 0.9% of gross issuance between March and April 2026,
and transaction volumes drop by a comparable factor at the same point. Two
independent measures move together, so it is unlikely to be an artefact of
our pipeline — but **we do not know the cause**, and we did not
pre-register a hypothesis about it. It is noted under "Exploratory (not
pre-registered)" and is not used as evidence for or against any hypothesis.

## 11. Reproducibility: you cannot stage this dataset

`crypto_near_mainnet_us` is shared as an **Analytics Hub linked dataset**.
A query may read it but may **not** write its results to a destination
table: the identical query succeeds with no destination and returns
`403 Access Denied` the moment one is set. Anyone rebuilding this work
cannot cache intermediate results in their own project, which is why some
scans are repeated and why a full refresh costs what it does.

## 12. Tokenomics parameters are cited, the measurements are not

Where the documentation and the chain could disagree, we measured the chain:
H5a derives gross issuance from `minted = Δsupply + burned` and plugs in no
inflation rate. The cited parameters in `SOURCES.md` carry their own flags —
the widely repeated 5% issuance is superseded by a documented 2.5%, the 30%
developer gas rebate was removed at a protocol version whose mainnet
activation we could not confirm, and HSP-029's own status is
self-contradictory.

Our measured gross issuance of 2.46% of ending supply agrees with the
documented 2.5% cap, which is a check on the method, not a coincidence we
arranged.

## 13. What we did not measure at all

- **Peer chains.** No comparison against Solana, Ethereum or any other
  chain. The same bot-filtered metric on a peer dataset was scoped and cut.
- **Why** economic accounts fell. We measure that they fell, robustly. We
  do not identify a cause.
- **Off-chain activity**, bridges outside Intents, and anything settled on
  chains we do not read.
- **Price.** Used only for USD conversion and context, never as evidence of
  usage, and never as a target.

---

*This is research, not investment advice.*
