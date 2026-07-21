-- Build derived hashtag tables and directed co-occurrence edges.
-- Set date bounds before running.

DECLARE start_date DATE DEFAULT DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 30 DAY);
DECLARE end_date DATE DEFAULT CURRENT_DATE('Asia/Tokyo');

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.post_hashtags`
PARTITION BY DATE(created_at)
CLUSTER BY hashtag_norm, post_id AS
WITH entity_tags AS (
  SELECT
    post_id,
    created_at,
    author_id,
    JSON_VALUE(hashtag_json, '$.tag') AS hashtag,
    'x_entities' AS extraction_source,
    fetched_at
  FROM `jackojacko05.nijiholo.raw_posts`,
  UNNEST(COALESCE(JSON_QUERY_ARRAY(entities, '$.hashtags'), ARRAY<JSON>[])) AS hashtag_json
  WHERE DATE(created_at) BETWEEN start_date AND end_date
),
regex_tags AS (
  SELECT
    post_id,
    created_at,
    author_id,
    hashtag,
    'regex' AS extraction_source,
    fetched_at
  FROM `jackojacko05.nijiholo.raw_posts`,
  UNNEST(REGEXP_EXTRACT_ALL(text, r'[#＃]([A-Za-z0-9_ぁ-んァ-ヶ一-龠々ー]+)')) AS hashtag
  WHERE DATE(created_at) BETWEEN start_date AND end_date
),
all_tags AS (
  SELECT * FROM entity_tags WHERE hashtag IS NOT NULL
  UNION ALL
  SELECT * FROM regex_tags WHERE hashtag IS NOT NULL
)
SELECT DISTINCT
  post_id,
  created_at,
  author_id,
  hashtag,
  NORMALIZE(LOWER(hashtag), NFKC) AS hashtag_norm,
  extraction_source,
  fetched_at
FROM all_tags
WHERE hashtag != '';

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.hashtag_nodes` AS
WITH stats AS (
  SELECT
    hashtag_norm,
    ARRAY_AGG(hashtag ORDER BY created_at DESC LIMIT 1)[OFFSET(0)] AS display_hashtag,
    COUNT(DISTINCT post_id) AS post_count,
    MIN(created_at) AS first_seen_at,
    MAX(created_at) AS last_seen_at
  FROM `jackojacko05.nijiholo.post_hashtags`
  WHERE DATE(created_at) BETWEEN start_date AND end_date
  GROUP BY hashtag_norm
)
SELECT
  stats.hashtag_norm,
  COALESCE(labels.display_hashtag, stats.display_hashtag) AS display_hashtag,
  labels.org_hint,
  labels.tag_type,
  labels.character_id,
  labels.character_name,
  stats.post_count,
  stats.first_seen_at,
  stats.last_seen_at,
  CURRENT_TIMESTAMP() AS updated_at
FROM stats
LEFT JOIN `jackojacko05.nijiholo.hashtag_labels` AS labels
USING (hashtag_norm);

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.hashtag_cooccurrence_edges`
PARTITION BY window_end
CLUSTER BY src_hashtag, dst_hashtag AS
WITH post_tag_arrays AS (
  SELECT
    post_id,
    ARRAY_AGG(DISTINCT hashtag_norm IGNORE NULLS ORDER BY hashtag_norm) AS tags
  FROM `jackojacko05.nijiholo.post_hashtags`
  WHERE DATE(created_at) BETWEEN start_date AND end_date
  GROUP BY post_id
  HAVING ARRAY_LENGTH(tags) BETWEEN 2 AND 50
),
total AS (
  SELECT COUNT(*) AS total_posts
  FROM post_tag_arrays
),
tag_counts AS (
  SELECT
    tag AS hashtag_norm,
    COUNT(*) AS post_count
  FROM post_tag_arrays,
  UNNEST(tags) AS tag
  GROUP BY hashtag_norm
),
canonical_pairs AS (
  SELECT
    LEAST(tag_a, tag_b) AS tag_a,
    GREATEST(tag_a, tag_b) AS tag_b,
    post_id
  FROM post_tag_arrays,
  UNNEST(tags) AS tag_a,
  UNNEST(tags) AS tag_b
  WHERE tag_a < tag_b
),
pair_counts AS (
  SELECT
    tag_a,
    tag_b,
    COUNT(DISTINCT post_id) AS pair_post_count
  FROM canonical_pairs
  GROUP BY tag_a, tag_b
),
metrics AS (
  SELECT
    pair_counts.tag_a,
    pair_counts.tag_b,
    pair_counts.pair_post_count,
    src.post_count AS src_post_count,
    dst.post_count AS dst_post_count,
    total.total_posts,
    SAFE_DIVIDE(
      pair_counts.pair_post_count,
      src.post_count + dst.post_count - pair_counts.pair_post_count
    ) AS jaccard,
    SAFE_DIVIDE(
      pair_counts.pair_post_count * total.total_posts,
      src.post_count * dst.post_count
    ) AS lift
  FROM pair_counts
  JOIN tag_counts AS src
    ON pair_counts.tag_a = src.hashtag_norm
  JOIN tag_counts AS dst
    ON pair_counts.tag_b = dst.hashtag_norm
  CROSS JOIN total
),
directed AS (
  SELECT
    tag_a AS src_hashtag,
    tag_b AS dst_hashtag,
    pair_post_count AS post_count,
    src_post_count,
    dst_post_count,
    total_posts,
    jaccard,
    lift
  FROM metrics
  UNION ALL
  SELECT
    tag_b AS src_hashtag,
    tag_a AS dst_hashtag,
    pair_post_count AS post_count,
    dst_post_count AS src_post_count,
    src_post_count AS dst_post_count,
    total_posts,
    jaccard,
    lift
  FROM metrics
)
SELECT
  TO_HEX(SHA256(CONCAT(
    src_hashtag, '\x1f',
    dst_hashtag, '\x1f',
    CAST(start_date AS STRING), '\x1f',
    CAST(end_date AS STRING)
  ))) AS edge_id,
  src_hashtag,
  dst_hashtag,
  start_date AS window_start,
  end_date AS window_end,
  post_count,
  src_post_count,
  dst_post_count,
  total_posts,
  jaccard,
  lift,
  IF(lift > 0, LOG(lift), NULL) AS pmi,
  CURRENT_TIMESTAMP() AS updated_at
FROM directed;

