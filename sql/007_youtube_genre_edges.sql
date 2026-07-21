-- Build genre-level collaboration edge aggregates.

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.youtube_collab_edges_by_genre`
CLUSTER BY content_genre, src_org, dst_org, src_character_id AS
WITH exploded AS (
  SELECT
    features.content_genre,
    features.owner_talent_id AS src_character_id,
    collaborator_id AS dst_character_id,
    features.video_id,
    features.video_url,
    features.published_at,
    features.title
  FROM `jackojacko05.nijiholo.youtube_video_features` AS features,
  UNNEST(SPLIT(features.collaborator_talent_ids, '|')) AS collaborator_id
  WHERE collaborator_id IS NOT NULL
    AND collaborator_id != ''
    AND collaborator_id != features.owner_talent_id
),
aggregated AS (
  SELECT
    content_genre,
    src_character_id,
    dst_character_id,
    COUNT(DISTINCT video_id) AS video_count,
    ARRAY_AGG(
      STRUCT(video_id, video_url, title)
      ORDER BY published_at DESC
      LIMIT 1
    )[OFFSET(0)] AS sample
  FROM exploded
  GROUP BY content_genre, src_character_id, dst_character_id
)
SELECT
  TO_HEX(SHA256(CONCAT(
    content_genre, '\x1f',
    src_character_id, '\x1f',
    dst_character_id
  ))) AS edge_id,
  aggregated.content_genre,
  aggregated.src_character_id,
  src.character_name AS src_character_name,
  src.org AS src_org,
  aggregated.dst_character_id,
  dst.character_name AS dst_character_name,
  dst.org AS dst_org,
  src.org = dst.org AS same_org,
  aggregated.video_count,
  sample.video_id AS sample_video_id,
  sample.video_url AS sample_video_url,
  sample.title AS sample_title,
  CURRENT_TIMESTAMP() AS updated_at
FROM aggregated
LEFT JOIN `jackojacko05.nijiholo.youtube_character_nodes` AS src
  ON aggregated.src_character_id = src.character_id
LEFT JOIN `jackojacko05.nijiholo.youtube_character_nodes` AS dst
  ON aggregated.dst_character_id = dst.character_id;
