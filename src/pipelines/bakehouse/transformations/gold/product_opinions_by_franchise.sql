-- Gold: opinions about each product per franchise and reason, extracted from customer reviews.
-- Spec: specs/001-opinioes-por-produto.md. Every measure is a count, so any aggregation is a SUM;
-- ratios such as the negative share are computed at query time, never stored.
CREATE OR REFRESH MATERIALIZED VIEW ${medallion_catalog}.${gold_schema}.product_opinions_by_franchise (
  franchise_id BIGINT NOT NULL COMMENT 'Franchise identifier',
  franchise_name STRING COMMENT 'Franchise name',
  city STRING COMMENT 'Franchise city',
  country STRING COMMENT 'Franchise country',
  product STRING NOT NULL COMMENT 'Product cited in the reviews',
  reason STRING NOT NULL COMMENT 'Main reason of the opinion, taste, texture, freshness, price, availability or other',
  mentions BIGINT NOT NULL COMMENT 'Reviews citing the product for this reason',
  positive_mentions BIGINT NOT NULL COMMENT 'Mentions with a positive opinion',
  negative_mentions BIGINT NOT NULL COMMENT 'Mentions with a negative opinion',
  neutral_mentions BIGINT NOT NULL COMMENT 'Mentions with a neutral opinion',
  CONSTRAINT valid_product EXPECT (product IN ('Outback Oatmeal', 'Austin Almond Biscotti', 'Orchard Oasis', 'Golden Gate Ginger', 'Tokyo Tidbits', 'Pearly Pies')),
  CONSTRAINT valid_reason EXPECT (reason IN ('taste', 'texture', 'freshness', 'price', 'availability', 'other')),
  CONSTRAINT known_franchise EXPECT (franchise_name IS NOT NULL)
)
COMMENT 'Customer opinions about each product per franchise and reason, extracted from reviews with AI'
AS SELECT
  o.franchise_id,
  f.franchise_name,
  f.city,
  f.country,
  o.product,
  o.reason,
  count(*) AS mentions,
  count_if(o.opinion = 'positive') AS positive_mentions,
  count_if(o.opinion = 'negative') AS negative_mentions,
  count_if(o.opinion = 'neutral') AS neutral_mentions
FROM ${medallion_catalog}.${silver_schema}.review_product_opinions o
LEFT JOIN ${medallion_catalog}.${silver_schema}.franchises f
  ON o.franchise_id = f.franchise_id
GROUP BY o.franchise_id, f.franchise_name, f.city, f.country, o.product, o.reason;
