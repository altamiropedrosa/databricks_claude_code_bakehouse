-- Gold: product mix.
-- Grain: product x transaction_date x country (franchise country), so the product
-- mix can be sliced by period and country. Measures are additive.
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${gold_schema}.sales_by_product
COMMENT 'Sales per product, day and franchise country (additive measures)'
AS SELECT
  product,
  transaction_date,
  transaction_month,
  franchise_country AS country,
  count(*) AS orders,
  sum(quantity) AS units_sold,
  sum(total_price) AS revenue
FROM ${medallion_catalog}.${silver_schema}.transactions
GROUP BY ALL;
