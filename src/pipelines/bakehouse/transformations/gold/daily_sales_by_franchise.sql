-- Gold: daily sales per franchise.
-- Grain: transaction_date x franchise x payment_method. Measures are additive, so
-- any roll-up (daily totals, payment mix, per franchise) is a plain SUM; compute
-- average ticket downstream as SUM(revenue) / SUM(orders).
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${gold_schema}.daily_sales_by_franchise (
  transaction_date DATE NOT NULL COMMENT 'Calendar date of the sales',
  transaction_month DATE NOT NULL COMMENT 'First day of the month of the sales',
  franchise_id BIGINT COMMENT 'Franchise identifier',
  franchise_name STRING COMMENT 'Franchise name',
  city STRING COMMENT 'Franchise city',
  country STRING COMMENT 'Franchise country',
  payment_method STRING COMMENT 'Payment method in lower case',
  orders BIGINT NOT NULL COMMENT 'Number of sales transactions',
  units_sold BIGINT NOT NULL COMMENT 'Total units sold',
  revenue DECIMAL(22, 2) NOT NULL COMMENT 'Total revenue, sum of total_price'
)
COMMENT 'Daily sales per franchise and payment method (additive measures)'
AS SELECT
  transaction_date,
  transaction_month,
  franchise_id,
  franchise_name,
  franchise_city AS city,
  franchise_country AS country,
  payment_method,
  count(*) AS orders,
  sum(quantity) AS units_sold,
  sum(total_price) AS revenue
FROM ${medallion_catalog}.${silver_schema}.transactions
GROUP BY ALL;
