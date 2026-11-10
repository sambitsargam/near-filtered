-- Enumerate the distinct values of transactions.status on a single day's
-- partition, so the economic-account filter can say "successful" in the
-- dataset's own vocabulary instead of a guessed enum string.
--
-- Cost: one partition, two columns. Cheap, and it removes a guess.
SELECT
  status,
  COUNT(*) AS transactions
FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
WHERE block_date = @probe_date
GROUP BY status
ORDER BY transactions DESC
