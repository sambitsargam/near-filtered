# Sources

Every fact in this project that we did **not** compute ourselves is listed
here with a link, a date, and a label saying how much weight it carries.
Figures are paraphrased rather than quoted; follow the link for the original
wording.

Labels:

- **PRIMARY** — NEAR or NEAR Intents' own documentation, an NEP, or an
  official governance record.
- **SECONDARY** — anything else, including community measurements and blog
  posts. Used for context only, never as the basis for a verdict.
- **UNVERIFIED** — we found a claim but could not confirm it in a primary
  record. Flagged in the text wherever it is used, or not used at all.

All pages below were retrieved **2026-11-10** unless a different date is
given. Most NEAR docs pages carry no visible publication date, which is
itself a limitation and is noted in `LIMITATIONS.md`.

---

## 1. Hackathon rules

| What | Source | Label |
|---|---|---|
| Track ids, submission window, rules Q-000–Q-017, prize structure | <https://nearhackathon.com/HACKATHON.md> | PRIMARY |
| Submission deadline 2026-11-14T23:59:00Z; judging opens 2026-11-16 | same | PRIMARY |
| Libraries, templates and AI-assisted code are allowed and must be listed in the README (Q-005) | same | PRIMARY |
| Each README must name the team's other submission; max 2 projects per person (Q-015) | same | PRIMARY |
| Any licence is acceptable; a LICENSE file is required (Q-014) | same | PRIMARY |
| Thesis track is judged on evidence rather than conviction | same | PRIMARY |

---

## 2. The dataset

| What | Source | Label |
|---|---|---|
| NEAR public BigQuery dataset, architecture and table list | <https://docs.near.org/data-infrastructure/big-query.md> | PRIMARY |
| NEAR pays dataset storage; the reader pays only for bytes their queries scan | same | PRIMARY |
| Recommendation to select only needed columns and partitions | same | PRIMARY |
| On-demand analysis price of $6.25/TiB, with the first TiB per month free — quoted on the NEAR page as of Sep 2023 | same | SECONDARY (a price, restated; used only to convert bytes to an indicative USD figure) |
| **NEAR Lake (the AWS S3 ingestion source) was retired 2026-03-24 and no longer indexes new blocks.** The page says the dataset remains *available* and points to the lakehouse repo for the current ingestion source. | same | PRIMARY |
| Ingestion pipeline source; last visible commit 2025-03-21; repo public, not archived | <https://github.com/near/near-public-lakehouse> | PRIMARY |
| NEAR now points at Neardata and the nearcore indexer for block streams; no named BigQuery successor | <https://docs.near.org/data-infrastructure/> | PRIMARY |
| Column names per table (types and clustering are **not** published) | lakehouse data dictionary, `src/lakehouse/notebooks/` in the repo above | PRIMARY |

**Open and material.** Whether `crypto_near_mainnet_us` is still receiving new
blocks is **not determinable from the documentation**. The docs confirm the
upstream source was retired and name no replacement. We resolve it by
querying `INFORMATION_SCHEMA.PARTITIONS` (free) as the first step of the
pipeline, and the measured answer is carried into every output. See
`sql/meta_partitions.sql` and §0.1 of `HYPOTHESES.md`.

Column types and clustering keys are published nowhere we could find, so
`sql/meta_columns.sql` reads them from `INFORMATION_SCHEMA.COLUMNS` rather
than our assuming them.

---

## 3. NEAR Intents

| What | Source | Label |
|---|---|---|
| Explorer API base URL, Bearer JWT auth, partner dashboard | <https://docs.near-intents.org/integration/distribution-channels/1click-api/explorer/introduction.md> | PRIMARY |
| **The Explorer API is read-only and covers 1Click swap transactions only** | same, and the OpenAPI spec below | PRIMARY |
| Rate limit of one request per 5 seconds per partner; 429 on breach | <https://explorer.near-intents.org/api/v0/openapi.yaml> | PRIMARY |
| Endpoint list (`/transactions`, `/partner-any-quotes`), response fields, keyset pagination via `lastDepositAddress`/`lastDepositMemo`, page size max 1000, timestamp and chain/token/USD filters | same | PRIMARY |
| Asset id format `nep141:<chain>-<address>.omft.near` and the chain enum | same | PRIMARY |
| `amountInUsd` / `amountOutUsd` are provided by the API | same | PRIMARY |

### Intents fees — the input to H5b

| What | Source | Label |
|---|---|---|
| Protocol fee of 0.0001% (1 pip) per transaction, collected on-chain by `intents.near` and sent to a `fee_collector` account | <https://docs.near-intents.org/resources/fees.md> | PRIMARY |
| A 0.2% fee on swaps routed through the near-intents.org front end, sent to `fefundsadmin.sputnik-dao.near` | same | PRIMARY |
| 1Click API fees: 25 bps without an API key; 20 bps with one (1 bp for stablecoin pairs); integrator `appFees` split 50/50 with 1Click, which keeps at least 20 bps; combined cap 500 bps | same, and <https://docs.near-intents.org/integration/distribution-channels/1click-api/fee-config.md> | PRIMARY |
| 0.1% withdrawal fee on NEAR, ZEC and STRK withdrawn to Solana; destination not stated | <https://docs.near-intents.org/resources/fees.md> | PRIMARY |
| **No primary page we read names any mechanism by which Intents fees are burned, staked, or routed to NEAR token holders.** The pages checked were the fees page, the fee-config page, the FAQs, the authentication page and the NEAR-token wrapping page. | the pages above | PRIMARY (an absence, recorded as an absence) |

**Not yet read.** `https://docs.near-intents.org/security-compliance/treasury-addresses.md`
may describe what the `fee_collector` does with collected fees. H5b is not
final until this page is read; the pre-registration already commits us to how
we will report either answer.

---

## 4. NEAR tokenomics

| What | Source | Label |
|---|---|---|
| Yearly reward budget of 2.5% of total supply, with 10% of that going to the protocol treasury; validator yield around 2.25% of total supply over total stake | <https://docs.near.org/protocol/network/validators.md> | PRIMARY |
| Unearned validator rewards are not minted | same | PRIMARY |
| Transaction fees collected in each epoch are burned | same | PRIMARY |
| Gas: on protocol version 86 and earlier, contracts also received 30% of the gas they burned; **from protocol version 87 (nearcore 2.14.0) all of it is burned** | <https://docs.near.org/protocol/transactions/gas.md> | PRIMARY |
| Storage staking priced at 1e19 yoctoNEAR per byte (~100 KB per NEAR) | <https://docs.near.org/protocol/storage/storage-staking.md> | PRIMARY |
| Non-refundable storage tokens are removed from circulating supply, i.e. burnt | NEP-491, Final, created 2023-07-24 <https://github.com/near/NEPs/blob/master/neps/nep-0491.md> | PRIMARY |
| Genesis supply of 1 billion NEAR; original design of ~5% issuance with a 90/10 split and a 30% contract rebate | <https://near.org/blog/near-protocol-economics/>, 2020-04-23 | **SUPERSEDED** — do not cite for current parameters |

### Governance changes (forum records, not NEPs)

| What | Source | Label |
|---|---|---|
| Proposal to cut maximum inflation from 5% to 2.5%, posted 2025-06-24 | <https://gov.near.org/t/reduce-inflation-for-near-protocol/41140> | PRIMARY (a proposal) |
| Context on the 2.9.0 inflation vote: announced 2025-10-14, voting from 2025-10-28 for up to 30 days | <https://gov.near.org/t/abstaining-from-the-near-2-9-0-inflation-vote-prioritizing-economic-fundamentals/41715>, 2025-10-23 | SECONDARY (an abstention post) |
| HSP-027, removing the 30% developer gas rebate (30% → 0%). Frontmatter status Final; opened 2026-06-15 | <https://gov.near.org/t/hsp-027-remove-the-near-developer-gas-rebate/42213> | PRIMARY |
| HSP-029, a 24-month ramp from 2.5% to a 1.6% issuance target, retaining the 90/10 split; posted 2026-10-07 | <https://gov.near.org/t/hsp-029-establish-a-24-month-issuance-ramp-to-a-1-6-target-rate-of-near-token-emissions/42644> | PRIMARY for the text; **UNVERIFIED** for its status |

### Flags we are carrying forward

1. **Issuance is 2.5%, not 5%.** The widely repeated 5% figure comes from the
   2020 economics blog and is superseded by the current validators page. Any
   number we publish uses 2.5% as the documented cap — and H5a measures
   realised issuance from the chain rather than assuming either figure.
2. **The 30% gas rebate is historical.** The gas docs state that from
   protocol v87 all gas is burned. We could not find a nearcore release note
   confirming v87/v2.14 activation on mainnet, so the *activation date* is
   UNVERIFIED. H5a therefore measures tokens actually burnt per month from
   `execution_outcomes` instead of applying a burn share.
3. **HSP-029's status is contradictory.** Its frontmatter reads as having
   succeeded while replies dated 2026-10-09/10 speak of ratification as still
   to come. We do not describe it as ratified.
4. **NEAR docs pages carry no visible last-updated date**, so "current" means
   "as published on 2026-11-10".

Points 1–3 are the reason H5a is computed from the chain rather than from
cited parameters. Where a cited parameter and a measured value disagree, the
thesis reports both and says which is which.

---

## 5. Price data

| What | Source | Label |
|---|---|---|
| NEAR price history for USD conversion and value-accrual context | CoinGecko API <https://www.coingecko.com/en/api> | SECONDARY |

Price data is used for USD conversion and for context on value accrual. It is
**never** used as evidence of usage. The exact conversion method, including
which day's price is applied to which transfer, is stated in `METHODOLOGY.md`.

---

## 6. Tools and libraries

Listed in the README's "Built with" section, which the hackathon rules
require.
