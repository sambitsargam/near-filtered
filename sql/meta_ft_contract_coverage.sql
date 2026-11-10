-- Feasibility probe for H4's native leg: which NEP-141 contracts carry the
-- transfers, and how much of the activity is in bridged `.omft.near` assets?
--
-- This asks what CAN be measured, not which answer looks better. It reads a
-- single day's partition and returns no time series, so it cannot reveal a
-- trend and cannot influence the direction of any hypothesis. It exists to
-- decide whether a priceable token set is feasible before H4 is frozen.
--
-- ft_events is clustered on contract_account_id, so grouping by it on one
-- partition is cheap.
SELECT
  contract_account_id,
  ENDS_WITH(contract_account_id, '.omft.near')  AS is_bridged_omft,
  COUNT(*)                                      AS transfers,
  COUNT(DISTINCT affected_account_id)           AS distinct_accounts
FROM `bigquery-public-data.crypto_near_mainnet_us.ft_events`
WHERE block_date = @probe_date
GROUP BY contract_account_id, is_bridged_omft
ORDER BY transfers DESC
LIMIT 25
