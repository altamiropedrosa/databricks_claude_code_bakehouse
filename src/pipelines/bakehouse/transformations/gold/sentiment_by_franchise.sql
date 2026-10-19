-- Gold: review sentiment per franchise.
-- net_sentiment = (positive - negative) / scored reviews, in [-1, 1].
-- Franchises without reviews are kept with zero counts and NULL ratios.
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${gold_schema}.sentiment_by_franchise
COMMENT 'Customer review sentiment counts and ratios per franchise'
AS WITH reviews AS (
  SELECT
    franchise_id,
    count(*) AS reviews,
    count_if(sentiment = 'positive') AS positive_reviews,
    count_if(sentiment = 'negative') AS negative_reviews,
    count_if(sentiment = 'neutral') AS neutral_reviews,
    count_if(sentiment = 'mixed') AS mixed_reviews,
    count_if(sentiment IS NULL) AS unscored_reviews,
    max(review_date) AS last_review_date
  FROM ${medallion_catalog}.${silver_schema}.reviews_sentiment
  GROUP BY franchise_id
)
SELECT
  f.franchise_id,
  f.franchise_name,
  f.city,
  f.country,
  f.latitude,
  f.longitude,
  coalesce(r.reviews, 0) AS reviews,
  coalesce(r.positive_reviews, 0) AS positive_reviews,
  coalesce(r.negative_reviews, 0) AS negative_reviews,
  coalesce(r.neutral_reviews, 0) AS neutral_reviews,
  coalesce(r.mixed_reviews, 0) AS mixed_reviews,
  coalesce(r.unscored_reviews, 0) AS unscored_reviews,
  CAST(r.positive_reviews / nullif(r.reviews - r.unscored_reviews, 0) AS DECIMAL(5, 4)) AS positive_ratio,
  CAST((r.positive_reviews - r.negative_reviews) / nullif(r.reviews - r.unscored_reviews, 0) AS DECIMAL(5, 4)) AS net_sentiment,
  r.last_review_date
FROM ${medallion_catalog}.${silver_schema}.franchises f
LEFT JOIN reviews r
  ON f.franchise_id = r.franchise_id;
