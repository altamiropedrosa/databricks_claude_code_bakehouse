-- Gold: product mix.
-- Grain: product x transaction_date x country (franchise country), so the product
-- mix can be sliced by period and country. Measures are additive.
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${gold_schema}.sales_by_product (
  product STRING COMMENT 'Product name',
  transaction_date DATE NOT NULL COMMENT 'Calendar date of the sales',
  transaction_month DATE NOT NULL COMMENT 'First day of the month of the sales',
  country STRING COMMENT 'Franchise country',
  orders BIGINT NOT NULL COMMENT 'Number of sales transactions',
  units_sold BIGINT NOT NULL COMMENT 'Total units sold',
  revenue DECIMAL(22, 2) NOT NULL COMMENT 'Total revenue, sum of total_price'
)
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
