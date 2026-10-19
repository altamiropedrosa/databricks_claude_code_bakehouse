-- Silver: conformed franchise dimension, enriched with its supplier.
-- Country is standardized: the source uses 'US' here and 'USA' for customers,
-- both are mapped to 'United States' (same rule as silver/customers.sql).
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${silver_schema}.franchises (
  CONSTRAINT valid_franchise_id EXPECT (franchise_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_country EXPECT (country IS NOT NULL),
  CONSTRAINT valid_latitude EXPECT (latitude BETWEEN -90 AND 90),
  CONSTRAINT valid_longitude EXPECT (longitude BETWEEN -180 AND 180),
  CONSTRAINT known_supplier EXPECT (supplier_name IS NOT NULL)
)
COMMENT 'Cleaned and conformed Bakehouse franchises with supplier attributes'
AS SELECT
  f.franchiseID AS franchise_id,
  trim(f.name) AS franchise_name,
  trim(f.city) AS city,
  trim(f.district) AS district,
  trim(f.zipcode) AS zipcode,
  CASE
    WHEN upper(trim(f.country)) IN ('US', 'USA', 'UNITED STATES', 'UNITED STATES OF AMERICA') THEN 'United States'
    ELSE trim(f.country)
  END AS country,
  upper(trim(f.size)) AS size,
  f.latitude,
  f.longitude,
  f.supplierID AS supplier_id,
  trim(s.name) AS supplier_name,
  trim(s.ingredient) AS supplier_ingredient,
  s.approved = 'Y' AS supplier_approved,
  f._ingested_at
FROM ${medallion_catalog}.${bronze_schema}.franchises f
LEFT JOIN ${medallion_catalog}.${bronze_schema}.suppliers s
  ON f.supplierID = s.supplierID;
