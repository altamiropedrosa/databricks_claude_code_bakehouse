-- Gold: one row per franchise with location (for maps) and lifetime performance.
-- Franchises without sales are kept with zero measures.
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${gold_schema}.franchise_performance
COMMENT 'Lifetime performance per franchise with city, country and coordinates'
AS WITH sales AS (
  SELECT
    franchise_id,
    count(*) AS orders,
    sum(quantity) AS units_sold,
    sum(total_price) AS revenue,
    count(DISTINCT customer_id) AS unique_customers,
    count(DISTINCT transaction_date) AS active_days,
    min(transaction_date) AS first_sale_date,
    max(transaction_date) AS last_sale_date
  FROM ${medallion_catalog}.${silver_schema}.transactions
  GROUP BY franchise_id
)
SELECT
  f.franchise_id,
  f.franchise_name,
  f.city,
  f.district,
  f.country,
  f.size,
  f.latitude,
  f.longitude,
  f.supplier_name,
  coalesce(s.orders, 0) AS orders,
  coalesce(s.units_sold, 0) AS units_sold,
  coalesce(s.revenue, 0) AS revenue,
  CAST(s.revenue / s.orders AS DECIMAL(12, 2)) AS avg_ticket,
  coalesce(s.unique_customers, 0) AS unique_customers,
  coalesce(s.active_days, 0) AS active_days,
  s.first_sale_date,
  s.last_sale_date,
  coalesce(s.orders, 0) > 0 AS is_active,
  rank() OVER (ORDER BY coalesce(s.revenue, 0) DESC) AS revenue_rank
FROM ${medallion_catalog}.${silver_schema}.franchises f
LEFT JOIN sales s
  ON f.franchise_id = s.franchise_id;
