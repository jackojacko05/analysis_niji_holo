-- Build a BigQuery property graph from YouTube description collaboration edges.
--
-- Load these CSVs first:
--   data/current/youtube_channels_current_2026-05-30.csv
--   data/current/youtube_collab_edges_filtered_latest200_2026-05-30.csv
--
-- Example bq load flags for the videos/collabs CSVs:
--   --source_format=CSV --skip_leading_rows=1 --allow_quoted_newlines

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.youtube_character_nodes`
CLUSTER BY org, character_id AS
SELECT
  talent_id AS character_id,
  ANY_VALUE(name) AS character_name,
  ANY_VALUE(en_name) AS en_name,
  ANY_VALUE(org) AS org,
  ANY_VALUE(agency) AS agency,
  ANY_VALUE(affiliation) AS affiliation,
  ANY_VALUE(channel_id) AS channel_id,
  ANY_VALUE(channel_title) AS channel_title,
  ANY_VALUE(channel_custom_url) AS channel_custom_url,
  ANY_VALUE(SAFE_CAST(NULLIF(CAST(subscriber_count AS STRING), '') AS INT64)) AS subscriber_count,
  ANY_VALUE(SAFE_CAST(NULLIF(CAST(video_count AS STRING), '') AS INT64)) AS channel_video_count,
  CURRENT_TIMESTAMP() AS updated_at
FROM `jackojacko05.nijiholo.youtube_channels`
WHERE talent_id IS NOT NULL
GROUP BY talent_id;

CREATE OR REPLACE TABLE `jackojacko05.nijiholo.youtube_collab_edges_graph`
CLUSTER BY src_character_id, dst_character_id AS
SELECT
  TO_HEX(SHA256(CONCAT(
    owner_talent_id, '\x1f',
    collaborator_talent_id, '\x1f',
    dataset_date
  ))) AS edge_id,
  owner_talent_id AS src_character_id,
  collaborator_talent_id AS dst_character_id,
  owner_name AS src_character_name,
  collaborator_name AS dst_character_name,
  owner_org AS src_org,
  collaborator_org AS dst_org,
  SAFE_CAST(CAST(same_org AS STRING) AS BOOL) AS same_org,
  SAFE_CAST(CAST(owner_video_count AS STRING) AS INT64) AS owner_video_count,
  SAFE_CAST(CAST(video_count AS STRING) AS INT64) AS video_count,
  SAFE_CAST(CAST(video_share AS STRING) AS FLOAT64) AS video_share,
  SAFE_CAST(CAST(likely_boilerplate AS STRING) AS BOOL) AS likely_boilerplate,
  SAFE_CAST(CAST(evidence_count AS STRING) AS INT64) AS evidence_count,
  evidence_types,
  TIMESTAMP(CAST(first_published_at AS STRING)) AS first_published_at,
  TIMESTAMP(CAST(last_published_at AS STRING)) AS last_published_at,
  sample_video_id,
  sample_video_url,
  sample_title,
  CURRENT_TIMESTAMP() AS updated_at
FROM `jackojacko05.nijiholo.youtube_collab_edges_filtered`
WHERE owner_talent_id IS NOT NULL
  AND collaborator_talent_id IS NOT NULL
  AND owner_talent_id != collaborator_talent_id;

CREATE OR REPLACE PROPERTY GRAPH `jackojacko05.nijiholo.youtube_collab_graph`
  NODE TABLES (
    `jackojacko05.nijiholo.youtube_character_nodes` AS Character
      KEY (character_id)
      LABEL Character
      PROPERTIES (
        character_id,
        character_name,
        en_name,
        org,
        agency,
        affiliation,
        channel_id,
        channel_title,
        channel_custom_url,
        subscriber_count,
        channel_video_count
      )
  )
  EDGE TABLES (
    `jackojacko05.nijiholo.youtube_collab_edges_graph` AS MentionsChannel
      KEY (edge_id)
      SOURCE KEY (src_character_id) REFERENCES Character (character_id)
      DESTINATION KEY (dst_character_id) REFERENCES Character (character_id)
      LABEL MentionsChannel
      PROPERTIES (
        same_org,
        owner_video_count,
        video_count,
        video_share,
        evidence_count,
        evidence_types,
        first_published_at,
        last_published_at,
        sample_video_id,
        sample_video_url,
        sample_title
      )
  );

-- Strongest directed description-link edges.
SELECT *
FROM GRAPH_TABLE(
  `jackojacko05.nijiholo.youtube_collab_graph`
  MATCH (a:Character)-[e:MentionsChannel]->(b:Character)
  RETURN
    a.org AS owner_org,
    a.character_name AS owner_name,
    b.org AS collaborator_org,
    b.character_name AS collaborator_name,
    e.video_count AS video_count,
    e.video_share AS video_share,
    e.evidence_types AS evidence_types,
    e.sample_video_url AS sample_video_url,
    e.sample_title AS sample_title
)
ORDER BY video_count DESC
LIMIT 100;

-- Cross-organization edges are rarer and useful to inspect manually.
SELECT *
FROM GRAPH_TABLE(
  `jackojacko05.nijiholo.youtube_collab_graph`
  MATCH (a:Character)-[e:MentionsChannel]->(b:Character)
  WHERE a.org != b.org
  RETURN
    a.org AS owner_org,
    a.character_name AS owner_name,
    b.org AS collaborator_org,
    b.character_name AS collaborator_name,
    e.video_count AS video_count,
    e.sample_video_url AS sample_video_url,
    e.sample_title AS sample_title
)
ORDER BY video_count DESC
LIMIT 100;
