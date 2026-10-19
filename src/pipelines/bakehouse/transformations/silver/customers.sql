-- Silver: conformed customer dimension.
-- Country is standardized: the source uses 'USA' here and 'US' for franchises,
-- both are mapped to 'United States' (same rule as silver/franchises.sql).
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${silver_schema}.customers (
  CONSTRAINT valid_customer_id EXPECT (customer_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_country EXPECT (country IS NOT NULL),
  CONSTRAINT valid_email EXPECT (email_address LIKE '%@%')
)
COMMENT 'Cleaned and conformed Bakehouse customers'
AS SELECT
  customerID AS customer_id,
  trim(first_name) AS first_name,
  trim(last_name) AS last_name,
  concat_ws(' ', trim(first_name), trim(last_name)) AS full_name,
  lower(trim(email_address)) AS email_address,
  trim(phone_number) AS phone_number,
  trim(address) AS address,
  trim(city) AS city,
  trim(state) AS state,
  CASE
    WHEN upper(trim(country)) IN ('US', 'USA', 'UNITED STATES', 'UNITED STATES OF AMERICA') THEN 'United States'
    ELSE trim(country)
  END AS country,
  trim(continent) AS continent,
  CAST(postal_zip_code AS STRING) AS postal_zip_code,
  lower(trim(gender)) AS gender,
  _ingested_at
FROM ${medallion_catalog}.${bronze_schema}.customers;
