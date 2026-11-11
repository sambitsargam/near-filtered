-- H4's native leg: NEP-141 transfers on the sampled days whose counterparty
-- is an economic account.
--
-- Amendment A1 fixes the sample to four whole days a month, and the Intents
-- leg uses the same days, so both sides of the settlement share cover
-- identical periods.
--
-- The economic account set is passed in as an array parameter rather than
-- recomputed here. We already hold it: sql/h1_accounts.sql returned it, and
-- recomputing it would mean a second scan of account_changes at roughly
-- 50 GiB a month purely to rediscover a set sitting on disk. The linked
-- dataset forbids staging it in a table (see sql/h1_accounts.sql), so an
-- array parameter is the remaining route.
--
-- Counted both ways so the headline count form needs no pricing:
--   native_transfers   every qualifying NEP-141 transfer
--   bridged_transfers  those in `.omft.near` assets, which are foreign
--                      assets represented on NEAR
--
-- Partition filter: ft_events on block_date, restricted to the sampled days.

SELECT
  COUNT(*)                                                    AS native_transfers,
  COUNT(DISTINCT affected_account_id)                         AS distinct_accounts,
  COUNT(DISTINCT contract_account_id)                         AS distinct_contracts,
  COUNTIF(ENDS_WITH(contract_account_id, '.omft.near'))       AS bridged_transfers,
  -- Kept so a reader can see how much of the native leg is one application.
  APPROX_TOP_COUNT(contract_account_id, 5)                    AS top_contracts
FROM `bigquery-public-data.crypto_near_mainnet_us.ft_events`
WHERE block_date IN UNNEST(@days)
  AND affected_account_id IN UNNEST(@economic_accounts)
