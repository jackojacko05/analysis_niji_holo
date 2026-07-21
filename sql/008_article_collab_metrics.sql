-- Article-ready metrics for:
-- 「コラボ」のデータから見るにじさんじとホロライブの違い
--
-- Source scope:
--   YouTube videos published from 2025-06-01 through 2026-05-31 in Asia/Tokyo.
--   Collaboration candidates are inferred from known channel IDs / @handles in
--   video descriptions, then filtered for recurring boilerplate edges.

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.article_scope` AS
SELECT
  DATE '2025-06-01' AS analysis_start_date,
  DATE '2026-05-31' AS analysis_end_date,
  'Asia/Tokyo' AS analysis_timezone,
  COUNT(*) AS owner_video_rows,
  COUNT(DISTINCT video_id) AS unique_videos,
  COUNT(DISTINCT owner_talent_id) AS talents,
  COUNTIF(collab_flag) AS collab_owner_video_rows,
  COUNTIF(cross_org_collab_flag) AS cross_org_owner_video_rows,
  CURRENT_TIMESTAMP() AS updated_at
FROM `jackojacko05.nijiholo.youtube_video_features`;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.article_org_supply` AS
SELECT
  owner_org AS org,
  COUNT(DISTINCT owner_talent_id) AS talents,
  COUNT(*) AS owner_video_rows,
  COUNTIF(collab_flag) AS collab_owner_video_rows,
  SAFE_DIVIDE(COUNTIF(collab_flag), COUNT(*)) AS collab_share,
  COUNTIF(cross_org_collab_flag) AS cross_org_owner_video_rows,
  SAFE_DIVIDE(COUNTIF(cross_org_collab_flag), COUNT(*)) AS cross_org_share,
  AVG(collab_count) AS avg_collab_count,
  CURRENT_TIMESTAMP() AS updated_at
FROM `jackojacko05.nijiholo.youtube_video_features`
GROUP BY owner_org;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.article_video_demand_by_mode` AS
SELECT
  owner_org AS org,
  collab_flag,
  COUNT(*) AS owner_video_rows,
  AVG(relative_log_views) AS avg_relative_log_views,
  APPROX_QUANTILES(relative_log_views, 101)[OFFSET(50)] AS median_relative_log_views,
  AVG(relative_log_views_per_day) AS avg_relative_log_views_per_day,
  APPROX_QUANTILES(relative_log_views_per_day, 101)[OFFSET(50)] AS median_relative_log_views_per_day,
  CURRENT_TIMESTAMP() AS updated_at
FROM `jackojacko05.nijiholo.youtube_video_features`
GROUP BY owner_org, collab_flag;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.article_owner_uplift` AS
WITH per_mode AS (
  SELECT
    owner_org,
    owner_talent_id,
    owner_name,
    collab_flag,
    COUNT(*) AS videos,
    AVG(relative_log_views) AS avg_relative_log_views,
    AVG(relative_log_views_per_day) AS avg_relative_log_views_per_day
  FROM `jackojacko05.nijiholo.youtube_video_features`
  GROUP BY owner_org, owner_talent_id, owner_name, collab_flag
),
pairs AS (
  SELECT
    collab.owner_org,
    collab.owner_talent_id,
    collab.owner_name,
    collab.videos AS collab_videos,
    solo.videos AS solo_videos,
    collab.avg_relative_log_views - solo.avg_relative_log_views AS collab_log_view_uplift,
    collab.avg_relative_log_views_per_day - solo.avg_relative_log_views_per_day AS collab_log_view_per_day_uplift
  FROM per_mode AS collab
  JOIN per_mode AS solo
    ON collab.owner_talent_id = solo.owner_talent_id
  WHERE collab.collab_flag
    AND NOT solo.collab_flag
    AND collab.videos >= 3
    AND solo.videos >= 20
),
org_summary AS (
  SELECT
    owner_org AS org,
    COUNT(*) AS comparable_talents,
    AVG(collab_log_view_uplift) AS avg_collab_log_view_uplift,
    APPROX_QUANTILES(collab_log_view_uplift, 101)[OFFSET(50)] AS median_collab_log_view_uplift,
    COUNTIF(collab_log_view_uplift > 0) AS positive_view_uplift_talents,
    AVG(collab_log_view_per_day_uplift) AS avg_collab_log_view_per_day_uplift,
    APPROX_QUANTILES(collab_log_view_per_day_uplift, 101)[OFFSET(50)] AS median_collab_log_view_per_day_uplift
  FROM pairs
  GROUP BY owner_org
)
SELECT
  *,
  EXP(avg_collab_log_view_uplift) - 1 AS avg_collab_view_uplift_pct,
  EXP(median_collab_log_view_uplift) - 1 AS median_collab_view_uplift_pct,
  EXP(avg_collab_log_view_per_day_uplift) - 1 AS avg_collab_view_per_day_uplift_pct,
  EXP(median_collab_log_view_per_day_uplift) - 1 AS median_collab_view_per_day_uplift_pct,
  CURRENT_TIMESTAMP() AS updated_at
FROM org_summary;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.article_genre_summary` AS
SELECT
  owner_org AS org,
  content_genre AS genre,
  COUNT(*) AS owner_video_rows,
  COUNTIF(collab_flag) AS collab_owner_video_rows,
  SAFE_DIVIDE(COUNTIF(collab_flag), COUNT(*)) AS collab_share,
  COUNTIF(cross_org_collab_flag) AS cross_org_owner_video_rows,
  SAFE_DIVIDE(COUNTIF(cross_org_collab_flag), COUNT(*)) AS cross_org_share,
  APPROX_QUANTILES(IF(collab_flag, relative_log_views, NULL), 101 IGNORE NULLS)[OFFSET(50)] AS collab_median_relative_log_views,
  APPROX_QUANTILES(IF(NOT collab_flag, relative_log_views, NULL), 101 IGNORE NULLS)[OFFSET(50)] AS solo_median_relative_log_views,
  CURRENT_TIMESTAMP() AS updated_at
FROM `jackojacko05.nijiholo.youtube_video_features`
GROUP BY owner_org, content_genre;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.article_genre_uplift` AS
WITH per_mode AS (
  SELECT
    owner_org,
    content_genre AS genre,
    owner_talent_id,
    owner_name,
    collab_flag,
    COUNT(*) AS videos,
    AVG(relative_log_views) AS avg_relative_log_views,
    AVG(relative_log_views_per_day) AS avg_relative_log_views_per_day
  FROM `jackojacko05.nijiholo.youtube_video_features`
  GROUP BY owner_org, genre, owner_talent_id, owner_name, collab_flag
),
pairs AS (
  SELECT
    collab.owner_org,
    collab.genre,
    collab.owner_talent_id,
    collab.owner_name,
    collab.videos AS collab_videos,
    solo.videos AS solo_videos,
    collab.avg_relative_log_views - solo.avg_relative_log_views AS collab_log_view_uplift,
    collab.avg_relative_log_views_per_day - solo.avg_relative_log_views_per_day AS collab_log_view_per_day_uplift
  FROM per_mode AS collab
  JOIN per_mode AS solo
    ON collab.owner_talent_id = solo.owner_talent_id
   AND collab.genre = solo.genre
  WHERE collab.collab_flag
    AND NOT solo.collab_flag
    AND collab.videos >= 2
    AND solo.videos >= 8
),
genre_summary AS (
  SELECT
    owner_org AS org,
    genre,
    COUNT(*) AS comparable_talents,
    AVG(collab_log_view_uplift) AS avg_collab_log_view_uplift,
    APPROX_QUANTILES(collab_log_view_uplift, 101)[OFFSET(50)] AS median_collab_log_view_uplift,
    COUNTIF(collab_log_view_uplift > 0) AS positive_view_uplift_talents,
    AVG(collab_log_view_per_day_uplift) AS avg_collab_log_view_per_day_uplift,
    APPROX_QUANTILES(collab_log_view_per_day_uplift, 101)[OFFSET(50)] AS median_collab_log_view_per_day_uplift
  FROM pairs
  GROUP BY owner_org, genre
)
SELECT
  *,
  EXP(avg_collab_log_view_uplift) - 1 AS avg_collab_view_uplift_pct,
  EXP(median_collab_log_view_uplift) - 1 AS median_collab_view_uplift_pct,
  EXP(avg_collab_log_view_per_day_uplift) - 1 AS avg_collab_view_per_day_uplift_pct,
  EXP(median_collab_log_view_per_day_uplift) - 1 AS median_collab_view_per_day_uplift_pct,
  CURRENT_TIMESTAMP() AS updated_at
FROM genre_summary;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.article_edge_matrix` AS
SELECT
  src_org,
  dst_org,
  COUNT(*) AS directed_edges,
  SUM(video_count) AS weighted_video_count,
  AVG(video_count) AS avg_video_count,
  CURRENT_TIMESTAMP() AS updated_at
FROM `jackojacko05.nijiholo.youtube_collab_edges_graph`
GROUP BY src_org, dst_org;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.article_top_cross_edges` AS
SELECT
  src_character_name AS owner_name,
  src_org AS owner_org,
  dst_character_name AS collaborator_name,
  dst_org AS collaborator_org,
  video_count,
  sample_video_url,
  sample_title,
  CURRENT_TIMESTAMP() AS updated_at
FROM `jackojacko05.nijiholo.youtube_collab_edges_graph`
WHERE src_org != dst_org
ORDER BY video_count DESC, owner_name, collaborator_name
LIMIT 30;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.article_graph_sample_edges` AS
SELECT *
FROM GRAPH_TABLE(
  `jackojacko05.nijiholo.youtube_collab_graph`
  MATCH (a:Character)-[e:MentionsChannel]->(b:Character)
  RETURN
    a.character_id AS owner_id,
    a.character_name AS owner_name,
    a.org AS owner_org,
    b.character_id AS collaborator_id,
    b.character_name AS collaborator_name,
    b.org AS collaborator_org,
    e.video_count AS video_count,
    e.video_share AS video_share,
    e.evidence_types AS evidence_types,
    e.sample_video_url AS sample_video_url,
    e.sample_title AS sample_title
)
ORDER BY video_count DESC, owner_name, collaborator_name
LIMIT 100;
