-- Gold: customer ranking by revenue. One row per customer with purchases;
-- filter on customer_rank for a top-N view.
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${gold_schema}.top_customers
COMMENT 'Customers ranked by revenue, with favorite product'
AS WITH product_units AS (
  SELECT
    customer_id,
    product,
    row_number() OVER (PARTITION BY customer_id ORDER BY sum(quantity) DESC, product) AS product_rank
  FROM ${medallion_catalog}.${silver_schema}.transactions
  GROUP BY customer_id, product
),
customer_sales AS (
  SELECT
    customer_id,
    first(customer_name) AS customer_name,
    first(customer_country) AS country,
    first(customer_continent) AS continent,
    count(*) AS orders,
    sum(quantity) AS units_sold,
    sum(total_price) AS revenue,
    count(DISTINCT franchise_id) AS franchises_visited,
    min(transaction_date) AS first_purchase_date,
    max(transaction_date) AS last_purchase_date
  FROM ${medallion_catalog}.${silver_schema}.transactions
  GROUP BY customer_id
)
SELECT
  row_number() OVER (ORDER BY c.revenue DESC, c.customer_id) AS customer_rank,
  c.customer_id,
  c.customer_name,
  c.country,
  c.continent,
  c.orders,
  c.units_sold,
  c.revenue,
  CAST(c.revenue / c.orders AS DECIMAL(12, 2)) AS avg_ticket,
  p.product AS favorite_product,
  c.franchises_visited,
  c.first_purchase_date,
  c.last_purchase_date
FROM customer_sales c
LEFT JOIN product_units p
  ON c.customer_id = p.customer_id AND p.product_rank = 1;
