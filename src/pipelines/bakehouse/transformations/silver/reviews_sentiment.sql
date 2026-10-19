-- Silver: customer reviews scored with ai_analyze_sentiment.
-- A streaming table so each review is scored exactly once, instead of calling
-- the AI function again for every review on each refresh.
-- ai_analyze_sentiment returns positive, negative, neutral, mixed or NULL.
CREATE OR REFRESH STREAMING TABLE ${medallion_catalog}.${silver_schema}.reviews_sentiment (
  CONSTRAINT valid_review_id EXPECT (review_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT non_empty_review EXPECT (length(review) > 0) ON VIOLATION DROP ROW,
  CONSTRAINT valid_franchise_id EXPECT (franchise_id IS NOT NULL),
  CONSTRAINT scored_sentiment EXPECT (sentiment IN ('positive', 'negative', 'neutral', 'mixed'))
)
COMMENT 'Bakehouse customer reviews with AI sentiment (ai_analyze_sentiment)'
AS SELECT
  new_id AS review_id,
  franchiseID AS franchise_id,
  review_date AS review_ts,
  CAST(review_date AS DATE) AS review_date,
  CAST(date_trunc('MONTH', review_date) AS DATE) AS review_month,
  trim(review) AS review,
  ai_analyze_sentiment(trim(review)) AS sentiment,
  _ingested_at
FROM STREAM(${medallion_catalog}.${bronze_schema}.reviews);
