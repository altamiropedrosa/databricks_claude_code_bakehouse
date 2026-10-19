-- Gold: sales per country where the sale happened (franchise country).
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${gold_schema}.sales_by_country
COMMENT 'Sales per franchise country with revenue share'
AS SELECT
  franchise_country AS country,
  count(DISTINCT franchise_id) AS active_franchises,
  count(*) AS orders,
  sum(quantity) AS units_sold,
  sum(total_price) AS revenue,
  CAST(sum(total_price) / count(*) AS DECIMAL(12, 2)) AS avg_ticket,
  count(DISTINCT customer_id) AS unique_customers,
  CAST(sum(total_price) / sum(sum(total_price)) OVER () AS DECIMAL(7, 4)) AS revenue_share
FROM ${medallion_catalog}.${silver_schema}.transactions
GROUP BY franchise_country;
