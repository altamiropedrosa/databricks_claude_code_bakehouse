-- Bronze: raw incremental ingestion of samples.bakehouse.media_customer_reviews (read-only source).
-- Source columns are kept as-is; only ingestion metadata columns are added.
CREATE OR REFRESH STREAMING TABLE ${medallion_catalog}.${bronze_schema}.reviews
COMMENT 'Raw customer reviews ingested from samples.bakehouse.media_customer_reviews'
AS SELECT
  *,
  current_timestamp() AS _ingested_at,
  'samples.bakehouse.media_customer_reviews' AS _source_table
FROM STREAM(samples.bakehouse.media_customer_reviews);
