-- Bronze: raw incremental ingestion of samples.bakehouse.sales_suppliers (read-only source).
-- Source columns are kept as-is; only ingestion metadata columns are added.
CREATE OR REFRESH STREAMING TABLE ${medallion_catalog}.${bronze_schema}.suppliers
COMMENT 'Raw suppliers ingested from samples.bakehouse.sales_suppliers'
AS SELECT
  *,
  current_timestamp() AS _ingested_at,
  'samples.bakehouse.sales_suppliers' AS _source_table
FROM STREAM(samples.bakehouse.sales_suppliers);
