-- Silver: the opinion about each product cited in a customer review, extracted with ai_extract.
-- Spec: specs/001-opinioes-por-produto.md. A streaming table so each review is sent to the model
-- exactly once, instead of extracting every review again on each refresh.
-- The model may cite a product twice in one review: only its first mention is kept.
-- A review without any cited product (or a failed extraction) yields one row with a NULL product,
-- dropped by cited_product so it is counted in the pipeline quality metrics.
CREATE OR REFRESH STREAMING TABLE ${medallion_catalog}.${silver_schema}.review_product_opinions (
  review_id INT NOT NULL COMMENT 'Review identifier',
  franchise_id BIGINT NOT NULL COMMENT 'Franchise the review is about',
  review_date DATE NOT NULL COMMENT 'Calendar date of the review',
  product STRING NOT NULL COMMENT 'Product cited in the review, one of the 6 products sold by the chain',
  opinion STRING NOT NULL COMMENT 'Opinion about the product, positive, negative or neutral',
  reason STRING NOT NULL COMMENT 'Main reason of the opinion, taste, texture, freshness, price, availability or other',
  _ingested_at TIMESTAMP NOT NULL COMMENT 'Time the review was sent to the model',
  CONSTRAINT known_franchise EXPECT (franchise_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_review_date EXPECT (review_date IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT cited_product EXPECT (product IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_product EXPECT (product IN ('Outback Oatmeal', 'Austin Almond Biscotti', 'Orchard Oasis', 'Golden Gate Ginger', 'Tokyo Tidbits', 'Pearly Pies')) ON VIOLATION DROP ROW,
  CONSTRAINT valid_opinion EXPECT (opinion IN ('positive', 'negative', 'neutral')) ON VIOLATION DROP ROW,
  CONSTRAINT valid_reason EXPECT (reason IN ('taste', 'texture', 'freshness', 'price', 'availability', 'other')) ON VIOLATION DROP ROW
)
COMMENT 'Opinion about each product cited in a customer review, extracted with ai_extract'
AS WITH extracted AS (
  SELECT
    review_id,
    franchise_id,
    review_date,
    ai_extract(
      review,
      '{"mentions": {"type": "array", "description": "One item per product the reviewer gives an opinion about", "items": {"type": "object", "properties": {"product": {"type": "string", "enum": ["Outback Oatmeal", "Austin Almond Biscotti", "Orchard Oasis", "Golden Gate Ginger", "Tokyo Tidbits", "Pearly Pies"]}, "opinion": {"type": "string", "enum": ["positive", "negative", "neutral"]}, "reason": {"type": "string", "enum": ["taste", "texture", "freshness", "price", "availability", "other"], "description": "Main reason of the opinion"}}}}}',
      map('version', '2.0')
    ) AS extraction
  FROM STREAM(${medallion_catalog}.${silver_schema}.reviews_sentiment)
),
mentions AS (
  SELECT
    review_id,
    franchise_id,
    review_date,
    transform(
      CAST(extraction:response:mentions AS ARRAY<VARIANT>),
      m -> named_struct('product', m:product::STRING, 'opinion', m:opinion::STRING, 'reason', m:reason::STRING)
    ) AS mentions
  FROM extracted
)
SELECT
  review_id,
  franchise_id,
  review_date,
  mention.product,
  mention.opinion,
  mention.reason,
  current_timestamp() AS _ingested_at
FROM mentions
LATERAL VIEW OUTER explode(
  filter(mentions, (m, i) -> NOT exists(slice(mentions, 1, i), p -> p.product = m.product))
) AS mention;
