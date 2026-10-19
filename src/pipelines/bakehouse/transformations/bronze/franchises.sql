-- Bronze: raw incremental ingestion of samples.bakehouse.sales_franchises (read-only source).
-- Source columns are kept as-is; only ingestion metadata columns are added.
CREATE OR REFRESH STREAMING TABLE ${medallion_catalog}.${bronze_schema}.franchises
COMMENT 'Raw franchises ingested from samples.bakehouse.sales_franchises'
AS SELECT
  *,
  current_timestamp() AS _ingested_at,
  'samples.bakehouse.sales_franchises' AS _source_table
FROM STREAM(samples.bakehouse.sales_franchises);
