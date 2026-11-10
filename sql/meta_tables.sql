-- Inventory: every table in the NEAR public dataset, with its row count and
-- storage size, from the `__TABLES__` pseudo-table. This is metadata, so the
-- query is free.
--
-- Purpose: establish what actually exists before writing a single metric
-- query, rather than trusting the documentation's table list.
--
-- `__TABLES__` exposes table_id / row_count / size_bytes / creation_time /
-- last_modified_time / type, where type 1 is a table and 2 is a view. Those
-- are not the INFORMATION_SCHEMA column names; this file uses the real ones
-- and aliases table_id to table_name so the rest of the pipeline sees one
-- consistent name.
SELECT
  table_id                             AS table_name,
  CASE type WHEN 1 THEN 'TABLE' WHEN 2 THEN 'VIEW' ELSE CAST(type AS STRING) END
                                       AS table_type,
  row_count,
  size_bytes,
  TIMESTAMP_MILLIS(creation_time)      AS created_at,
  TIMESTAMP_MILLIS(last_modified_time) AS last_modified_at
FROM `bigquery-public-data.crypto_near_mainnet_us.__TABLES__`
ORDER BY size_bytes DESC
