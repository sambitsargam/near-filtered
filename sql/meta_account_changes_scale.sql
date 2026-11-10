-- Probe: coverage and units of account_changes balance columns.
--
-- ft_balances_daily turned out to cover 0.38% of signers, so H1's balance
-- criterion needs a source that tracks every account. account_changes
-- records a balance on every change, including the gas burn of any
-- transaction, so an account that transacted must appear. This checks that,
-- and checks whether the columns are yoctoNEAR or NEAR, which differ by 1e24.
SELECT
  COUNT(*)                                            AS rows_in_partition,
  COUNT(DISTINCT affected_account_id)                 AS distinct_accounts,
  APPROX_QUANTILES(affected_account_nonstaked_balance, 100)[OFFSET(50)] AS median_nonstaked,
  MAX(affected_account_nonstaked_balance)             AS max_nonstaked,
  LOG10(NULLIF(MAX(affected_account_nonstaked_balance), 0)) AS log10_max_nonstaked,
  LOG10(NULLIF(MAX(affected_account_staked_balance), 0))    AS log10_max_staked
FROM `bigquery-public-data.crypto_near_mainnet_us.account_changes`
WHERE block_date = @probe_date
