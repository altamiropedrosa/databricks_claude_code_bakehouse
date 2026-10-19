-- Bronze: raw incremental ingestion of samples.bakehouse.sales_customers (read-only source).
-- Source columns are kept as-is; only ingestion metadata columns are added.
CREATE OR REFRESH STREAMING TABLE ${medallion_catalog}.${bronze_schema}.customers
COMMENT 'Raw customers ingested from samples.bakehouse.sales_customers'
AS SELECT
  *,
  current_timestamp() AS _ingested_at,
  'samples.bakehouse.sales_customers' AS _source_table
FROM STREAM(samples.bakehouse.sales_customers);
