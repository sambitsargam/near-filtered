-- H5a: do fees burned matter against new issuance, and is the ratio
-- trending toward net-neutral?
--
-- Measured from the chain rather than from cited parameters. The tokenomics
-- record is contradictory (SOURCES.md): the widely repeated 5% issuance is
-- superseded by a documented 2.5%, the 30% developer gas rebate was removed
-- at a protocol version whose mainnet activation we could not confirm, and
-- HSP-029's own status is self-contradictory. So nothing here assumes a
-- rate; supply and burn are both read from the chain.
--
-- The accounting identity used:
--     supply_end = supply_start + minted - burned
--  => minted (gross issuance) = (supply_end - supply_start) + burned
--  => net issuance            =  supply_end - supply_start
--
-- Net issuance is therefore directly observable as the change in total
-- supply, and gross issuance follows from it and the burn. No inflation
-- rate is plugged in anywhere.
--
-- Burn has two parts and both are counted: gas burnt executing receipts
-- (execution_outcomes.tokens_burnt) and the fee burnt converting a
-- transaction into its first receipt
-- (transactions.receipt_conversion_tokens_burnt). Taking only the first
-- would understate the burn.
--
-- All three columns are yoctoNEAR, verified by sql/meta_burn_scale.sql
-- (total_supply ~1.31e33 raw = 1.31e9 NEAR), so all are divided by 1e24.
--
-- One query covers the whole window: execution_outcomes is the large table
-- here at roughly 5 GiB a month for one column, which stays under the cap.
--
-- Partition filters: all three tables on block_date, over the window.

WITH burn_outcomes AS (
  SELECT
    DATE_TRUNC(block_date, MONTH) AS month,
    SUM(tokens_burnt)             AS burnt_raw
  FROM `bigquery-public-data.crypto_near_mainnet_us.execution_outcomes`
  WHERE block_date BETWEEN @window_start AND @window_end
  GROUP BY month
),

burn_conversion AS (
  SELECT
    DATE_TRUNC(block_date, MONTH)             AS month,
    SUM(receipt_conversion_tokens_burnt)      AS burnt_raw
  FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
  WHERE block_date BETWEEN @window_start AND @window_end
  GROUP BY month
),

-- First and last observed total_supply in each month, by block height.
supply AS (
  SELECT
    DATE_TRUNC(block_date, MONTH) AS month,
    ARRAY_AGG(total_supply ORDER BY block_height ASC  LIMIT 1)[OFFSET(0)] AS supply_start_raw,
    ARRAY_AGG(total_supply ORDER BY block_height DESC LIMIT 1)[OFFSET(0)] AS supply_end_raw,
    COUNT(*) AS blocks_in_month
  FROM `bigquery-public-data.crypto_near_mainnet_us.blocks`
  WHERE block_date BETWEEN @window_start AND @window_end
  GROUP BY month
)

SELECT
  FORMAT_DATE('%Y-%m', s.month)                              AS month,
  s.blocks_in_month,
  s.supply_start_raw / 1e24                                  AS supply_start_near,
  s.supply_end_raw   / 1e24                                  AS supply_end_near,
  (COALESCE(bo.burnt_raw, 0) + COALESCE(bc.burnt_raw, 0)) / 1e24  AS burned_near,
  COALESCE(bo.burnt_raw, 0) / 1e24                           AS burned_execution_near,
  COALESCE(bc.burnt_raw, 0) / 1e24                           AS burned_conversion_near,
  (s.supply_end_raw - s.supply_start_raw) / 1e24             AS net_issuance_near,
  ((s.supply_end_raw - s.supply_start_raw)
    + COALESCE(bo.burnt_raw, 0) + COALESCE(bc.burnt_raw, 0)) / 1e24 AS gross_issuance_near,
  -- The headline ratio for H5a's materiality bar and its trend.
  SAFE_DIVIDE(
    COALESCE(bo.burnt_raw, 0) + COALESCE(bc.burnt_raw, 0),
    (s.supply_end_raw - s.supply_start_raw)
      + COALESCE(bo.burnt_raw, 0) + COALESCE(bc.burnt_raw, 0)
  )                                                          AS burn_over_gross_issuance
FROM supply AS s
LEFT JOIN burn_outcomes   AS bo ON bo.month = s.month
LEFT JOIN burn_conversion AS bc ON bc.month = s.month
ORDER BY month
