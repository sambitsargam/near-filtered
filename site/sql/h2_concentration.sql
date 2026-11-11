-- H2: is activity becoming less concentrated in a handful of contracts?
--
-- Monthly, over transactions sent by ECONOMIC accounts only (the staged
-- table supplies which accounts those are, at the pre-registered default
-- thresholds). Restricting to economic accounts matters here: an
-- unfiltered measure would mostly describe whichever reward application was
-- busiest that month.
--
-- Two series, both pre-registered:
--   top10_share  fraction of those transactions going to the 10 busiest
--                receiver accounts
--   hhi          Herfindahl-Hirschman Index on the 0-1 scale, the sum of
--                squared receiver shares. 1.0 is one receiver taking
--                everything; 1/n is n equal receivers. METHODOLOGY.md says
--                we use the 0-1 form, because the 0-10,000 form differs by
--                four orders of magnitude and is easy to confuse.
--
-- Partition filter: transactions on block_date, over the window.

-- The economic-account filter is recomputed here rather than read from a
-- staged table, because the Analytics Hub linked dataset forbids writing
-- query results to a destination table (see sql/h1_accounts.sql). That makes
-- this query scan account_changes a second time; there is no cheaper route
-- that keeps the same filter.
WITH per_account AS (
  SELECT
    signer_account_id                   AS account_id,
    COUNT(DISTINCT block_date)          AS active_days,
    COUNT(DISTINCT receiver_account_id) AS distinct_receivers
  FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
  WHERE block_date BETWEEN @window_start AND @window_end
  GROUP BY account_id
),

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
),

econ AS (
  SELECT p.account_id
  FROM per_account AS p
  LEFT JOIN latest_balance AS b
    ON p.account_id = b.account_id
  WHERE p.active_days        >= @min_active_days
    AND p.distinct_receivers >= @min_distinct_receivers
    AND COALESCE(b.balance_near, 0.0) >= @min_balance_near
),

econ_tx AS (
  SELECT
    t.receiver_account_id,
    COUNT(*) AS transactions
  FROM `bigquery-public-data.crypto_near_mainnet_us.transactions` AS t
  INNER JOIN econ AS e
    ON t.signer_account_id = e.account_id
  WHERE t.block_date BETWEEN @window_start AND @window_end
  GROUP BY t.receiver_account_id
),

totals AS (
  SELECT
    SUM(transactions) AS total_transactions,
    COUNT(*)          AS distinct_receivers
  FROM econ_tx
),

ranked AS (
  SELECT
    receiver_account_id,
    transactions,
    ROW_NUMBER() OVER (ORDER BY transactions DESC) AS rank
  FROM econ_tx
)

SELECT
  (SELECT total_transactions FROM totals)  AS total_transactions,
  (SELECT distinct_receivers FROM totals)  AS distinct_receivers,
  SAFE_DIVIDE(
    (SELECT SUM(transactions) FROM ranked WHERE rank <= 10),
    (SELECT total_transactions FROM totals)
  )                                        AS top10_share,
  (
    SELECT SUM(POW(SAFE_DIVIDE(transactions, (SELECT total_transactions FROM totals)), 2))
    FROM econ_tx
  )                                        AS hhi,
  -- Kept so the dashboard can name the contracts rather than show a bare
  -- share, and so a reader can sanity-check what is dominating.
  ARRAY_TO_STRING(
    ARRAY(SELECT receiver_account_id FROM ranked WHERE rank <= 10 ORDER BY rank),
    '|'
  )                                        AS top10_receivers
