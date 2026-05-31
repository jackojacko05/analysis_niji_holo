-- Build video-level features for the collaboration hypothesis report.

DROP TABLE IF EXISTS `jackojacko05.nijiholo.youtube_video_features`;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.youtube_video_features`
CLUSTER BY owner_org, content_genre, owner_talent_id, collab_flag AS
WITH videos AS (
  SELECT
    CAST(dataset_date AS STRING) AS dataset_date,
    CAST(video_id AS STRING) AS video_id,
    CAST(video_url AS STRING) AS video_url,
    CAST(channel_id AS STRING) AS channel_id,
    CAST(channel_title AS STRING) AS channel_title,
    CAST(owner_talent_ids AS STRING) AS owner_talent_ids,
    CAST(owner_names AS STRING) AS owner_names,
    CAST(owner_orgs AS STRING) AS owner_orgs,
    SAFE_CAST(CAST(published_at AS STRING) AS TIMESTAMP) AS published_at,
    SAFE_CAST(CAST(fetched_at AS STRING) AS TIMESTAMP) AS fetched_at,
    CAST(title AS STRING) AS title,
    CAST(description AS STRING) AS description,
    CAST(duration AS STRING) AS duration,
    SAFE_CAST(CAST(view_count AS STRING) AS INT64) AS view_count,
    SAFE_CAST(CAST(like_count AS STRING) AS INT64) AS like_count,
    SAFE_CAST(CAST(comment_count AS STRING) AS INT64) AS comment_count
  FROM `jackojacko05.nijiholo.youtube_videos`
),
video_owners AS (
  SELECT
    videos.*,
    owner_talent_id
  FROM videos,
  UNNEST(SPLIT(owner_talent_ids, '|')) AS owner_talent_id
  WHERE owner_talent_id IS NOT NULL
    AND owner_talent_id != ''
),
owner_meta AS (
  SELECT
    CAST(talent_id AS STRING) AS owner_talent_id,
    ANY_VALUE(CAST(name AS STRING)) AS owner_name,
    ANY_VALUE(CAST(org AS STRING)) AS owner_org,
    ANY_VALUE(CAST(affiliation AS STRING)) AS affiliation,
    ANY_VALUE(CAST(channel_id AS STRING)) AS owner_channel_id
  FROM `jackojacko05.nijiholo.youtube_channels`
  GROUP BY owner_talent_id
),
filtered_video_collabs AS (
  SELECT DISTINCT
    CAST(collabs.video_id AS STRING) AS video_id,
    owner_talent_id,
    CAST(collabs.collaborator_talent_id AS STRING) AS collaborator_talent_id,
    CAST(collabs.collaborator_name AS STRING) AS collaborator_name,
    CAST(collabs.collaborator_org AS STRING) AS collaborator_org
  FROM `jackojacko05.nijiholo.youtube_video_collaborators` AS collabs,
  UNNEST(SPLIT(CAST(collabs.owner_talent_ids AS STRING), '|')) AS owner_talent_id
  JOIN `jackojacko05.nijiholo.youtube_collab_edges_graph` AS edges
    ON edges.src_character_id = owner_talent_id
   AND edges.dst_character_id = CAST(collabs.collaborator_talent_id AS STRING)
  WHERE owner_talent_id IS NOT NULL
    AND owner_talent_id != ''
    AND owner_talent_id != CAST(collabs.collaborator_talent_id AS STRING)
),
collab_agg AS (
  SELECT
    video_id,
    owner_talent_id,
    COUNT(DISTINCT collaborator_talent_id) AS collab_count,
    COUNT(DISTINCT IF(collaborator_org != owner_org, collaborator_talent_id, NULL)) AS cross_org_collab_count,
    STRING_AGG(DISTINCT collaborator_talent_id, '|' ORDER BY collaborator_talent_id) AS collaborator_talent_ids,
    STRING_AGG(DISTINCT collaborator_name, '|' ORDER BY collaborator_name) AS collaborator_names
  FROM filtered_video_collabs
  LEFT JOIN owner_meta USING (owner_talent_id)
  GROUP BY video_id, owner_talent_id
),
features_base AS (
  SELECT
    video_owners.dataset_date,
    video_owners.video_id,
    video_owners.video_url,
    video_owners.channel_id,
    owner_meta.owner_talent_id,
    owner_meta.owner_name,
    owner_meta.owner_org,
    owner_meta.affiliation,
    video_owners.published_at,
    video_owners.fetched_at,
    GREATEST(1, DATE_DIFF(DATE(video_owners.fetched_at), DATE(video_owners.published_at), DAY)) AS age_days,
    video_owners.title,
    video_owners.duration,
    video_owners.view_count,
    video_owners.like_count,
    video_owners.comment_count,
    CASE
      WHEN REGEXP_CONTAINS(
        LOWER(video_owners.title),
        r'歌枠|歌ってみた|歌みた|karaoke|singing|弾き語り|オリジナル曲|original song|music video|cover song|踊ってみた|dance cover|3d live|birthday live|anniversary live|【mv】|\bmv\b|\bcover\b'
      ) THEN '歌'
      WHEN REGEXP_CONTAINS(
        LOWER(video_owners.title),
        r'ゲーム実況|実況|game|ゲーム|minecraft|マイクラ|valorant|ヴァロ|apex|ark|gta|gta5|mario|マリオ|マリカ|mario kart|ポケモン|pokemon|splatoon|スプラ|street fighter|スト6|ストリートファイター|elden ring|nightreign|r\.e\.p\.o|repo|lethal company|monster hunter|モンハン|雀魂|麻雀|mahjong|among us|league of legends|\blol\b|スマブラ|smash|zelda|ゼルダ|dragon quest|ドラクエ|final fantasy|ff14|rust|palworld|パルワールド|overwatch|ow2|dead by daylight|\bdbd\b|phasmophobia|fortnite|フォートナイト|holoearth|slay the spire|cursed companions|project: break out|arc raiders|nintendo|switch|steam|ps5|マーダーミステリー|マダミス'
      ) THEN 'ゲーム'
      ELSE 'その他'
    END AS content_genre,
    REGEXP_CONTAINS(LOWER(CONCAT(video_owners.title, ' ', video_owners.description)), r'#shorts|#short|youtube shorts')
      OR REGEXP_CONTAINS(video_owners.duration, r'^PT[0-9]+S$') AS is_short_like,
    COALESCE(collab_agg.collab_count, 0) AS collab_count,
    COALESCE(collab_agg.cross_org_collab_count, 0) AS cross_org_collab_count,
    COALESCE(collab_agg.collaborator_talent_ids, '') AS collaborator_talent_ids,
    COALESCE(collab_agg.collaborator_names, '') AS collaborator_names,
    COALESCE(collab_agg.collab_count, 0) > 0 AS collab_flag,
    COALESCE(collab_agg.cross_org_collab_count, 0) > 0 AS cross_org_collab_flag,
    LN(COALESCE(video_owners.view_count, 0) + 1) AS log_views,
    LN(SAFE_DIVIDE(COALESCE(video_owners.view_count, 0), GREATEST(1, DATE_DIFF(DATE(video_owners.fetched_at), DATE(video_owners.published_at), DAY))) + 1) AS log_views_per_day,
    SAFE_DIVIDE(video_owners.like_count, NULLIF(video_owners.view_count, 0)) AS like_rate,
    SAFE_DIVIDE(video_owners.comment_count, NULLIF(video_owners.view_count, 0)) AS comment_rate
  FROM video_owners
  JOIN owner_meta
    ON video_owners.owner_talent_id = owner_meta.owner_talent_id
  LEFT JOIN collab_agg
    ON video_owners.video_id = collab_agg.video_id
   AND video_owners.owner_talent_id = collab_agg.owner_talent_id
),
owner_baseline AS (
  SELECT
    owner_talent_id,
    APPROX_QUANTILES(log_views, 101)[OFFSET(50)] AS owner_median_log_views,
    APPROX_QUANTILES(log_views_per_day, 101)[OFFSET(50)] AS owner_median_log_views_per_day,
    APPROX_QUANTILES(like_rate, 101 IGNORE NULLS)[OFFSET(50)] AS owner_median_like_rate,
    APPROX_QUANTILES(comment_rate, 101 IGNORE NULLS)[OFFSET(50)] AS owner_median_comment_rate
  FROM features_base
  GROUP BY owner_talent_id
)
SELECT
  features_base.*,
  owner_baseline.owner_median_log_views,
  owner_baseline.owner_median_log_views_per_day,
  features_base.log_views - owner_baseline.owner_median_log_views AS relative_log_views,
  features_base.log_views_per_day - owner_baseline.owner_median_log_views_per_day AS relative_log_views_per_day,
  features_base.like_rate - owner_baseline.owner_median_like_rate AS relative_like_rate,
  features_base.comment_rate - owner_baseline.owner_median_comment_rate AS relative_comment_rate
FROM features_base
JOIN owner_baseline USING (owner_talent_id);
