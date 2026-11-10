-- Per-account facts for one 30-day window: the single scan that H1's
-- threshold grid and H3's cohorts are both derived from.
--
-- WHY THIS RETURNS ROWS RATHER THAN AGGREGATES.
-- The usual approach would stage these facts in a table of our own and read
-- it cheaply many times. That is not permitted here: the NEAR dataset is
-- shared as an Analytics Hub linked dataset, so a query may read it but may
-- not write its results to a destination table. The identical query
-- succeeds with no destination and returns
--   403 Access Denied ... account_changes
-- the moment one is set. Materialising is blocked; returning rows to the
-- client is not.
--
-- So this returns one row per account that clears the LOOSEST cell of the
-- pre-registered grid (d>=2, c>=1, b>=0). Every other cell is tighter, so
-- all 27 can be counted from this result without scanning again, and the
-- cohort membership H3 needs comes from the same rows. The alternative is
-- twelve more scans of account_changes at about 50 GiB each.
--
-- The heavy aggregation still happens in SQL: 5.5 billion transactions and
-- billions of account changes are reduced to roughly 120,000 rows here.
-- Only the threshold cross-join, which is arithmetic on those rows, happens
-- in Python, against the tested functions in transforms.py.
--
-- Partition filters: both tables on block_date, over the same window.

WITH window_tx AS (
  SELECT
    signer_account_id,
    block_date,
    receiver_account_id
  FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
  WHERE block_date BETWEEN @window_start AND @window_end
    -- Pre-registered: every signed transaction counts. transactions.status
    -- describes receipt conversion rather than execution success and held a
    -- single value across 502,649 rows on the probe date. See LIMITATIONS.md.
    AND (@success_status IS NULL OR status = @success_status)
),

per_account AS (
  SELECT
    signer_account_id                   AS account_id,
    COUNT(DISTINCT block_date)          AS active_days,
    COUNT(DISTINCT receiver_account_id) AS distinct_receivers,
    COUNT(*)                            AS tx_count
  FROM window_tx
  GROUP BY account_id
),

-- Balance at the account's last recorded change inside the window.
-- Amendment A2: account_changes, not ft_balances_daily, which matched only
-- 0.38% of signers. Balances here are yoctoNEAR (verified by
-- sql/meta_account_changes_scale.sql), so they are divided by 1e24.
latest_balance AS (
  SELECT
    account_id,
    (nonstaked + staked) / 1e24 AS balance_near
  FROM (
    SELECT
      affected_account_id                AS account_id,
      affected_account_nonstaked_balance AS nonstaked,
      affected_account_staked_balance    AS staked,
      ROW_NUMBER() OVER (
        PARTITION BY affected_account_id
        ORDER BY block_height DESC, index_in_block DESC
      ) AS rn
    FROM `bigquery-public-data.crypto_near_mainnet_us.account_changes`
    WHERE block_date BETWEEN @window_start AND @window_end
  )
  WHERE rn = 1
)

SELECT
  p.account_id,
  p.active_days,
  p.distinct_receivers,
  p.tx_count,
  -- No balance row means nothing we can observe, which is 0, not missing.
  COALESCE(b.balance_near, 0.0) AS balance_near,
  -- Carried on every row so the headline count can be read against the whole
  -- signing population without a second query.
  (SELECT COUNT(*) FROM per_account) AS all_signing_accounts
FROM per_account AS p
LEFT JOIN latest_balance AS b
  ON p.account_id = b.account_id
WHERE p.active_days        >= @loosest_days
  AND p.distinct_receivers >= @loosest_receivers
  AND COALESCE(b.balance_near, 0.0) >= @loosest_balance
