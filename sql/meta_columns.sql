-- Inventory: the real column names and types for the tables we intend to
-- query, plus whether each column is the partition or a clustering key.
-- INFORMATION_SCHEMA is metadata, so this query is free.
--
-- Purpose: the published docs give column names but no types and no
-- clustering information. We write SQL against this output, not the docs.
SELECT
  c.table_name,
  c.ordinal_position,
  c.column_name,
  c.data_type,
  c.is_nullable,
  c.is_partitioning_column,
  c.clustering_ordinal_position
FROM `bigquery-public-data.crypto_near_mainnet_us.INFORMATION_SCHEMA.COLUMNS` AS c
WHERE c.table_name IN (
  'transactions',
  'receipts',
  'receipt_details',
  'receipt_actions',
  'execution_outcomes',
  'account_changes',
  'ft_events',
  'ft_balances_daily',
  'blocks',
  'circulating_supply'
)
ORDER BY c.table_name, c.ordinal_position
