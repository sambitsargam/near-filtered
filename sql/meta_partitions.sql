-- FRESHNESS CHECK. This is the first query we run and the most important
-- one, because it decides whether the thesis window is even available.
--
-- It reads INFORMATION_SCHEMA.PARTITIONS, which is metadata: it returns the
-- newest and oldest partition of every table WITHOUT scanning any table
-- data, so it costs nothing. A `SELECT MAX(block_date) FROM transactions`
-- would answer the same question but would scan the date column of every
-- partition ever written, so we do not use it.
--
-- `latest_partition` is the answer to "how far behind mainnet is this
-- dataset?". Anything more than a few days behind today gets disclosed.
SELECT
  table_name,
  COUNT(*)                                   AS partition_count,
  MIN(partition_id)                          AS earliest_partition,
  MAX(partition_id)                          AS latest_partition,
  SUM(total_rows)                            AS total_rows,
  SUM(total_logical_bytes)                   AS total_logical_bytes,
  MAX(last_modified_time)                    AS last_modified_at
FROM `bigquery-public-data.crypto_near_mainnet_us.INFORMATION_SCHEMA.PARTITIONS`
WHERE partition_id IS NOT NULL
  AND partition_id != '__NULL__'
GROUP BY table_name
ORDER BY table_name
