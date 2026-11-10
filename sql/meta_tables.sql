-- Inventory: every table in the NEAR public dataset, with its row count and
-- storage size. INFORMATION_SCHEMA is metadata, so this query is free.
--
-- Purpose: establish what actually exists before writing a single metric
-- query, rather than trusting the documentation's table list.
SELECT
  table_name,
  table_type,
  row_count,
  size_bytes,
  TIMESTAMP_MILLIS(creation_time)     AS created_at,
  TIMESTAMP_MILLIS(last_modified_time) AS last_modified_at
FROM `bigquery-public-data.crypto_near_mainnet_us.__TABLES__`
ORDER BY size_bytes DESC
