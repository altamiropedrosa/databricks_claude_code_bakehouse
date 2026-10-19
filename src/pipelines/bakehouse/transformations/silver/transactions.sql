-- Silver: sales transactions with correct types, derived date columns and
-- enriched with franchise and customer attributes from the silver dimensions.
-- The raw card number is not propagated: only its last 4 digits are kept.
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${silver_schema}.transactions (
  transaction_id BIGINT NOT NULL COMMENT 'Sales transaction identifier',
  transaction_ts TIMESTAMP NOT NULL COMMENT 'Date and time of the sale',
  transaction_date DATE NOT NULL COMMENT 'Calendar date of the sale',
  transaction_month DATE NOT NULL COMMENT 'First day of the month of the sale',
  transaction_hour INT NOT NULL COMMENT 'Hour of the day of the sale, 0 to 23',
  transaction_weekday STRING NOT NULL COMMENT 'Weekday name of the sale, e.g. Monday',
  product STRING COMMENT 'Product name',
  quantity INT NOT NULL COMMENT 'Units sold, always greater than zero',
  unit_price DECIMAL(12, 2) COMMENT 'Price per unit',
  total_price DECIMAL(12, 2) NOT NULL COMMENT 'Transaction amount, always greater than zero',
  payment_method STRING COMMENT 'Payment method in lower case, expected visa, mastercard or amex',
  card_last4 STRING COMMENT 'Last 4 digits of the payment card, the full number is never stored',
  franchise_id BIGINT COMMENT 'Franchise where the sale happened',
  franchise_name STRING COMMENT 'Franchise name',
  franchise_city STRING COMMENT 'Franchise city',
  franchise_country STRING COMMENT 'Franchise country, where the sale happened',
  franchise_size STRING COMMENT 'Franchise size',
  customer_id BIGINT COMMENT 'Customer identifier',
  customer_name STRING COMMENT 'Customer full name (personal data)',
  customer_country STRING COMMENT 'Customer country',
  customer_continent STRING COMMENT 'Customer continent',
  _ingested_at TIMESTAMP NOT NULL COMMENT 'Time the source row was ingested into bronze',
  CONSTRAINT valid_transaction_id EXPECT (transaction_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_transaction_ts EXPECT (transaction_ts IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT positive_quantity EXPECT (quantity IS NOT NULL AND quantity > 0) ON VIOLATION DROP ROW,
  CONSTRAINT positive_total_price EXPECT (total_price IS NOT NULL AND total_price > 0) ON VIOLATION DROP ROW,
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
