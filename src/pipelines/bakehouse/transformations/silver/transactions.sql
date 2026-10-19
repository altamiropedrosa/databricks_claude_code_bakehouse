-- Silver: sales transactions with correct types, derived date columns and
-- enriched with franchise and customer attributes from the silver dimensions.
-- The raw card number is not propagated: only its last 4 digits are kept.
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${silver_schema}.transactions (
  CONSTRAINT valid_transaction_id EXPECT (transaction_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_transaction_ts EXPECT (transaction_ts IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT positive_quantity EXPECT (quantity > 0) ON VIOLATION DROP ROW,
  CONSTRAINT positive_total_price EXPECT (total_price > 0) ON VIOLATION DROP ROW,
  CONSTRAINT consistent_total_price EXPECT (total_price = quantity * unit_price),
  CONSTRAINT known_franchise EXPECT (franchise_name IS NOT NULL),
  CONSTRAINT known_customer EXPECT (customer_name IS NOT NULL),
  CONSTRAINT valid_payment_method EXPECT (payment_method IN ('visa', 'mastercard', 'amex'))
)
COMMENT 'Cleaned Bakehouse sales transactions enriched with franchise and customer'
AS SELECT
  t.transactionID AS transaction_id,
  t.dateTime AS transaction_ts,
  CAST(t.dateTime AS DATE) AS transaction_date,
  CAST(date_trunc('MONTH', t.dateTime) AS DATE) AS transaction_month,
  hour(t.dateTime) AS transaction_hour,
  date_format(t.dateTime, 'EEEE') AS transaction_weekday,
  trim(t.product) AS product,
  CAST(t.quantity AS INT) AS quantity,
  CAST(t.unitPrice AS DECIMAL(12, 2)) AS unit_price,
  CAST(t.totalPrice AS DECIMAL(12, 2)) AS total_price,
  lower(trim(t.paymentMethod)) AS payment_method,
  right(CAST(t.cardNumber AS STRING), 4) AS card_last4,
  t.franchiseID AS franchise_id,
  f.franchise_name,
  f.city AS franchise_city,
  f.country AS franchise_country,
  f.size AS franchise_size,
  t.customerID AS customer_id,
  c.full_name AS customer_name,
  c.country AS customer_country,
  c.continent AS customer_continent,
  t._ingested_at
FROM ${medallion_catalog}.${bronze_schema}.transactions t
LEFT JOIN ${medallion_catalog}.${silver_schema}.franchises f
  ON t.franchiseID = f.franchise_id
LEFT JOIN ${medallion_catalog}.${silver_schema}.customers c
  ON t.customerID = c.customer_id;
