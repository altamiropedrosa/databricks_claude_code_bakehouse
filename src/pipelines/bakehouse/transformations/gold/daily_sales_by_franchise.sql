-- Gold: daily sales per franchise.
-- Grain: transaction_date x franchise x payment_method. Measures are additive, so
-- any roll-up (daily totals, payment mix, per franchise) is a plain SUM; compute
-- average ticket downstream as SUM(revenue) / SUM(orders).
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${gold_schema}.daily_sales_by_franchise
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
