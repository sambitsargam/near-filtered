-- Diagnostic: does ft_balances_daily actually cover the accounts that
-- transact, or only a subset?
--
-- H1's balance criterion joins signers to ft_balances_daily. If that table is
-- a partial snapshot rather than a full balance set, the join silently turns
-- "held >= b NEAR" into "happens to appear in this table", which is not the
-- pre-registered filter at all.
SELECT
  (SELECT COUNT(DISTINCT signer_account_id)
   FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
   WHERE block_date BETWEEN @window_start AND @window_end)        AS distinct_signers,
  (SELECT COUNT(DISTINCT account_id)
   FROM `bigquery-public-data.crypto_near_mainnet_us.ft_balances_daily`
   WHERE epoch_date = @balance_date)                              AS accounts_with_balance_row,
  (SELECT COUNT(DISTINCT t.signer_account_id)
   FROM `bigquery-public-data.crypto_near_mainnet_us.transactions` AS t
   WHERE t.block_date BETWEEN @window_start AND @window_end
     AND t.signer_account_id IN (
       SELECT account_id
       FROM `bigquery-public-data.crypto_near_mainnet_us.ft_balances_daily`
       WHERE epoch_date = @balance_date
     ))                                                           AS signers_matched
