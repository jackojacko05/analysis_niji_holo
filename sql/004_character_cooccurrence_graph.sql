-- Build character co-occurrence tables and a BigQuery Graph property graph.
-- This expects post_hashtags and character_tags to exist.

DECLARE start_date DATE DEFAULT DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 30 DAY);
DECLARE end_date DATE DEFAULT CURRENT_DATE('Asia/Tokyo');

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.post_characters`
PARTITION BY DATE(created_at)
CLUSTER BY org, character_id, author_id AS
SELECT DISTINCT
  post_hashtags.post_id,
  post_hashtags.author_id,
  post_hashtags.created_at,
  character_tags.org,
  character_tags.character_id,
  character_tags.character_name,
  post_hashtags.hashtag_norm AS evidence_tag_norm,
  'fanart_tag' AS evidence_source,
  1.0 AS confidence,
  post_hashtags.fetched_at
FROM `jackojacko05.nijiholo.post_hashtags` AS post_hashtags
JOIN `jackojacko05.nijiholo.character_tags` AS character_tags
  ON post_hashtags.hashtag_norm = character_tags.fanart_tag_norm
WHERE DATE(post_hashtags.created_at) BETWEEN start_date AND end_date
  AND character_tags.active;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.character_nodes`
CLUSTER BY org, character_id AS
SELECT
  character_tags.character_id,
  character_tags.org,
  ANY_VALUE(character_tags.character_name) AS character_name,
  COUNT(DISTINCT post_characters.post_id) AS post_count,
  COUNT(DISTINCT post_characters.author_id) AS unique_author_count,
  MIN(post_characters.created_at) AS first_seen_at,
  MAX(post_characters.created_at) AS last_seen_at,
  CURRENT_TIMESTAMP() AS updated_at
FROM `jackojacko05.nijiholo.character_tags` AS character_tags
LEFT JOIN `jackojacko05.nijiholo.post_characters` AS post_characters
  ON character_tags.character_id = post_characters.character_id
GROUP BY character_tags.character_id, character_tags.org;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.character_cooccurrence_edges`
PARTITION BY window_end
CLUSTER BY unit_type, src_character_id, dst_character_id AS
WITH post_units AS (
  SELECT
    'post' AS unit_type,
    post_id AS unit_id,
    ANY_VALUE(author_id) AS author_id,
    ARRAY_AGG(DISTINCT character_id IGNORE NULLS ORDER BY character_id) AS characters,
    COUNT(DISTINCT post_id) AS post_count
  FROM `jackojacko05.nijiholo.post_characters`
  WHERE DATE(created_at) BETWEEN start_date AND end_date
  GROUP BY post_id
  HAVING ARRAY_LENGTH(characters) BETWEEN 2 AND 30
),
author_week_units AS (
  SELECT
    'author_week' AS unit_type,
    CONCAT(author_id, ':', CAST(DATE_TRUNC(DATE(created_at), WEEK(MONDAY)) AS STRING)) AS unit_id,
    author_id,
    ARRAY_AGG(DISTINCT character_id IGNORE NULLS ORDER BY character_id) AS characters,
    COUNT(DISTINCT post_id) AS post_count
  FROM `jackojacko05.nijiholo.post_characters`
  WHERE DATE(created_at) BETWEEN start_date AND end_date
    AND author_id IS NOT NULL
  GROUP BY author_id, DATE_TRUNC(DATE(created_at), WEEK(MONDAY))
  HAVING ARRAY_LENGTH(characters) BETWEEN 2 AND 50
),
author_month_units AS (
  SELECT
    'author_month' AS unit_type,
    CONCAT(author_id, ':', CAST(DATE_TRUNC(DATE(created_at), MONTH) AS STRING)) AS unit_id,
    author_id,
    ARRAY_AGG(DISTINCT character_id IGNORE NULLS ORDER BY character_id) AS characters,
    COUNT(DISTINCT post_id) AS post_count
  FROM `jackojacko05.nijiholo.post_characters`
  WHERE DATE(created_at) BETWEEN start_date AND end_date
    AND author_id IS NOT NULL
  GROUP BY author_id, DATE_TRUNC(DATE(created_at), MONTH)
  HAVING ARRAY_LENGTH(characters) BETWEEN 2 AND 80
),
units AS (
  SELECT * FROM post_units
  UNION ALL
  SELECT * FROM author_week_units
  UNION ALL
  SELECT * FROM author_month_units
),
totals AS (
  SELECT
    unit_type,
    COUNT(*) AS total_units
  FROM units
  GROUP BY unit_type
),
character_counts AS (
  SELECT
    unit_type,
    character_id,
    COUNT(*) AS units
  FROM units,
  UNNEST(characters) AS character_id
  GROUP BY unit_type, character_id
),
canonical_pairs AS (
  SELECT
    unit_type,
    unit_id,
    author_id,
    post_count,
    LEAST(character_a, character_b) AS character_a,
    GREATEST(character_a, character_b) AS character_b
  FROM units,
  UNNEST(characters) AS character_a,
  UNNEST(characters) AS character_b
  WHERE character_a < character_b
),
pair_counts AS (
  SELECT
    unit_type,
    character_a,
    character_b,
    COUNT(DISTINCT unit_id) AS cooccurrence_units,
    COUNT(DISTINCT author_id) AS unique_authors,
    SUM(post_count) AS post_count
  FROM canonical_pairs
  GROUP BY unit_type, character_a, character_b
),
metrics AS (
  SELECT
    pair_counts.unit_type,
    pair_counts.character_a,
    pair_counts.character_b,
    pair_counts.cooccurrence_units,
    pair_counts.unique_authors,
    pair_counts.post_count,
    src.units AS src_units,
    dst.units AS dst_units,
    totals.total_units,
    SAFE_DIVIDE(
      pair_counts.cooccurrence_units,
      src.units + dst.units - pair_counts.cooccurrence_units
    ) AS jaccard,
    SAFE_DIVIDE(
      pair_counts.cooccurrence_units * totals.total_units,
      src.units * dst.units
    ) AS lift
  FROM pair_counts
  JOIN character_counts AS src
    ON pair_counts.unit_type = src.unit_type
   AND pair_counts.character_a = src.character_id
  JOIN character_counts AS dst
    ON pair_counts.unit_type = dst.unit_type
   AND pair_counts.character_b = dst.character_id
  JOIN totals
    ON pair_counts.unit_type = totals.unit_type
),
directed AS (
  SELECT
    unit_type,
    character_a AS src_character_id,
    character_b AS dst_character_id,
    cooccurrence_units,
    src_units,
    dst_units,
    total_units,
    unique_authors,
    post_count,
    jaccard,
    lift
  FROM metrics
  UNION ALL
  SELECT
    unit_type,
    character_b AS src_character_id,
    character_a AS dst_character_id,
    cooccurrence_units,
    dst_units AS src_units,
    src_units AS dst_units,
    total_units,
    unique_authors,
    post_count,
    jaccard,
    lift
  FROM metrics
)
SELECT
  TO_HEX(SHA256(CONCAT(
    unit_type, '\x1f',
    src_character_id, '\x1f',
    dst_character_id, '\x1f',
    CAST(start_date AS STRING), '\x1f',
    CAST(end_date AS STRING)
  ))) AS edge_id,
  unit_type,
  src_character_id,
  dst_character_id,
  start_date AS window_start,
  end_date AS window_end,
  cooccurrence_units,
  src_units,
  dst_units,
  total_units,
  unique_authors,
  post_count,
  jaccard,
  lift,
  IF(lift > 0, LOG(lift), NULL) AS pmi,
  CURRENT_TIMESTAMP() AS updated_at
FROM directed;

CREATE OR REPLACE PROPERTY GRAPH `jackojacko05.nijiholo.character_graph`
  NODE TABLES (
    `jackojacko05.nijiholo.character_nodes` AS Character
      KEY (character_id)
      LABEL Character
      PROPERTIES (
        character_id,
        org,
        character_name,
        post_count,
        unique_author_count,
        first_seen_at,
        last_seen_at
      )
  )
  EDGE TABLES (
    `jackojacko05.nijiholo.character_cooccurrence_edges` AS CoAppears
      KEY (edge_id)
      SOURCE KEY (src_character_id) REFERENCES Character (character_id)
      DESTINATION KEY (dst_character_id) REFERENCES Character (character_id)
      LABEL CoAppears
      PROPERTIES (
        unit_type,
        window_start,
        window_end,
        cooccurrence_units,
        src_units,
        dst_units,
        total_units,
        unique_authors,
        post_count,
        jaccard,
        lift,
        pmi
      )
  );

-- Top same-post co-appearances.
SELECT *
FROM GRAPH_TABLE(
  `jackojacko05.nijiholo.character_graph`
  MATCH (a:Character)-[e:CoAppears]->(b:Character)
  WHERE a.character_id < b.character_id
    AND e.unit_type = 'post'
  RETURN
    a.org AS org_a,
    a.character_name AS character_a,
    b.org AS org_b,
    b.character_name AS character_b,
    e.cooccurrence_units AS cooccurrence_posts,
    e.unique_authors AS unique_authors,
    e.jaccard AS jaccard,
    e.lift AS lift,
    e.pmi AS pmi
)
ORDER BY cooccurrence_posts DESC
LIMIT 100;

-- Pairs with strong author-week overlap.
SELECT *
FROM GRAPH_TABLE(
  `jackojacko05.nijiholo.character_graph`
  MATCH (a:Character)-[e:CoAppears]->(b:Character)
  WHERE a.character_id < b.character_id
    AND e.unit_type = 'author_week'
    AND e.unique_authors >= 3
  RETURN
    a.org AS org_a,
    a.character_name AS character_a,
    b.org AS org_b,
    b.character_name AS character_b,
    e.cooccurrence_units AS cooccurrence_author_weeks,
    e.unique_authors AS unique_authors,
    e.lift AS lift,
    e.pmi AS pmi
)
ORDER BY pmi DESC, unique_authors DESC
LIMIT 100;

