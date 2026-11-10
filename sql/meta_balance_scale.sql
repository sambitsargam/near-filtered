-- Probe: what units are ft_balances_daily.liquid / .staked expressed in?
--
-- The column is a FLOAT64 and the published docs give no unit. If the values
-- are yoctoNEAR the magnitudes sit around 1e24; if they are already NEAR they
-- sit in the single and double digits. The economic-account filter divides by
-- 1e24, so getting this wrong would silently make every account look broke
-- and collapse the economic-account count to zero.
--
-- Cost: one epoch partition of a 4.6 GiB table. Negligible.
SELECT
  COUNT(*)                                            AS rows_in_partition,
  COUNT(DISTINCT epoch_block_height)                  AS epochs_on_this_date,
  APPROX_QUANTILES(liquid, 100)[OFFSET(50)]           AS median_liquid,
  APPROX_QUANTILES(liquid, 100)[OFFSET(99)]           AS p99_liquid,
  MAX(liquid)                                         AS max_liquid,
  MAX(staked)                                         AS max_staked,
  LOG10(NULLIF(MAX(liquid), 0))                       AS log10_max_liquid
FROM `bigquery-public-data.crypto_near_mainnet_us.ft_balances_daily`
WHERE epoch_date = @probe_date
