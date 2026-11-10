-- H1 / sensitivity grid: how many accounts clear the "economic account"
-- bar in one 30-day window, for every combination of thresholds at once.
--
-- The bot filter (pre-registered in HYPOTHESES.md): within the window, an
-- account signed transactions on >= d distinct days, touched >= c distinct
-- receiver accounts, and held >= b NEAR at window end.
--
-- Why the grid is computed in the same pass: the expensive part is reading
-- the window's transactions. Deriving per-account statistics once and then
-- CROSS JOINing a 3x3x3 threshold grid costs no extra table scan, so the
-- full sensitivity analysis is as cheap as a single threshold. That is what
-- makes it affordable to publish every cell instead of a chosen one.
--
-- Partition filters: transactions by block_date (the window),
-- ft_balances_daily by epoch_date (one day only, at window end).

WITH window_tx AS (
  SELECT
    signer_account_id,
    block_date,
    receiver_account_id
  FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
  WHERE block_date BETWEEN @window_start AND @window_end
    -- @success_status is resolved from sql/meta_tx_status_values.sql, never
    -- guessed. Passing NULL counts every signed transaction, which we report
    -- as a robustness variant rather than the headline.
    AND (@success_status IS NULL OR status = @success_status)
),

per_account AS (
  SELECT
    signer_account_id                        AS account_id,
    COUNT(DISTINCT block_date)               AS active_days,
    COUNT(DISTINCT receiver_account_id)      AS distinct_receivers,
    COUNT(*)                                 AS tx_count
  FROM window_tx
  GROUP BY account_id
),

-- NEAR balance at window end. Epochs are sub-daily, so a single date can
-- hold more than one epoch per account; keep only the latest.
balances_at_window_end AS (
  SELECT
    account_id,
    (liquid + staked) / 1e24 AS balance_near   -- yoctoNEAR -> NEAR
  FROM (
    SELECT
      account_id,
      liquid,
      staked,
      ROW_NUMBER() OVER (
        PARTITION BY account_id ORDER BY epoch_block_height DESC
      ) AS rn
    FROM `bigquery-public-data.crypto_near_mainnet_us.ft_balances_daily`
    WHERE epoch_date = @balance_date
  )
  WHERE rn = 1
),

joined AS (
  SELECT
    p.account_id,
    p.active_days,
    p.distinct_receivers,
    p.tx_count,
    -- An account with no balance row held nothing we can observe. Treating
    -- that as 0 rather than dropping the row keeps the count from drifting up.
    COALESCE(b.balance_near, 0.0) AS balance_near
  FROM per_account AS p
  LEFT JOIN balances_at_window_end AS b
    ON p.account_id = b.account_id
),

grid AS (
  SELECT d, c, b
  FROM UNNEST([2, 4, 8])        AS d,
       UNNEST([1, 2, 3])        AS c,
       UNNEST([0.0, 0.1, 1.0])  AS b
)

SELECT
  @window_end                              AS window_end,
  @window_start                            AS window_start,
  g.d                                      AS min_active_days,
  g.c                                      AS min_distinct_receivers,
  g.b                                      AS min_balance_near,
  COUNT(*)                                 AS economic_accounts,
  SUM(j.tx_count)                          AS economic_transactions,
  APPROX_QUANTILES(j.tx_count, 100)[OFFSET(50)] AS median_tx_per_account
FROM joined AS j
CROSS JOIN grid AS g
WHERE j.active_days         >= g.d
  AND j.distinct_receivers  >= g.c
  AND j.balance_near        >= g.b
GROUP BY window_end, window_start, min_active_days, min_distinct_receivers, min_balance_near
ORDER BY min_active_days, min_distinct_receivers, min_balance_near
