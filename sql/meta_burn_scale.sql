-- Probe: units of the burn and supply columns, before H5 is built on them.
--
-- execution_outcomes.tokens_burnt, transactions.receipt_conversion_tokens_burnt
-- and blocks.total_supply are all FLOAT64 with no documented unit. H5 divides
-- burn by issuance, so a unit error in one and not the other would produce a
-- ratio that is wrong by 1e24 while still looking like a number.
--
-- Cost: one day's partition of each. Negligible.
SELECT
  (SELECT SUM(tokens_burnt)
   FROM `bigquery-public-data.crypto_near_mainnet_us.execution_outcomes`
   WHERE block_date = @probe_date)                       AS outcomes_burnt_raw,
  (SELECT SUM(receipt_conversion_tokens_burnt)
   FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
   WHERE block_date = @probe_date)                       AS conversion_burnt_raw,
  (SELECT MAX(total_supply)
   FROM `bigquery-public-data.crypto_near_mainnet_us.blocks`
   WHERE block_date = @probe_date)                       AS total_supply_raw,
  (SELECT COUNT(*)
   FROM `bigquery-public-data.crypto_near_mainnet_us.blocks`
   WHERE block_date = @probe_date)                       AS blocks_that_day
