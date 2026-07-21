-- BigQuery schema draft for Nijisanji / Hololive fan-art graph analysis.
-- Target project/dataset: jackojacko05.nijiholo

CREATE SCHEMA IF NOT EXISTS `jackojacko05.nijiholo`
OPTIONS(location = 'asia-northeast1');

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.seed_queries` (
  query_id STRING NOT NULL,
  query_text STRING NOT NULL,
  org_hint STRING,
  tag_type STRING,
  enabled BOOL NOT NULL,
  notes STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.ingest_runs` (
  run_id STRING NOT NULL,
  query_id STRING,
  query_text STRING NOT NULL,
  from_time TIMESTAMP,
  to_time TIMESTAMP,
  result_count INT64,
  next_token STRING,
  status STRING NOT NULL,
  error_message STRING,
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.raw_posts` (
  post_id STRING NOT NULL,
  author_id STRING,
  conversation_id STRING,
  created_at TIMESTAMP NOT NULL,
  text STRING,
  lang STRING,
  public_metrics STRUCT<
    retweet_count INT64,
    reply_count INT64,
    like_count INT64,
    quote_count INT64,
    bookmark_count INT64,
    impression_count INT64
  >,
  entities JSON,
  raw_json JSON,
  source_query_id STRING,
  source_query_text STRING,
  fetched_at TIMESTAMP NOT NULL,
  run_id STRING
)
PARTITION BY DATE(created_at)
CLUSTER BY source_query_id, author_id;

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.character_tags` (
  org STRING NOT NULL,
  character_id STRING NOT NULL,
  character_name STRING NOT NULL,
  fanart_tag STRING NOT NULL,
  fanart_tag_norm STRING NOT NULL,
  twitter_handle STRING,
  active BOOL NOT NULL,
  source_file STRING,
  updated_at TIMESTAMP NOT NULL
)
CLUSTER BY org, character_id, fanart_tag_norm;

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.hashtag_labels` (
  hashtag_norm STRING NOT NULL,
  display_hashtag STRING,
  org_hint STRING,
  tag_type STRING,
  character_id STRING,
  character_name STRING,
  manual_label BOOL NOT NULL,
  notes STRING,
  updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.post_hashtags` (
  post_id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  author_id STRING,
  hashtag STRING NOT NULL,
  hashtag_norm STRING NOT NULL,
  extraction_source STRING NOT NULL,
  fetched_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(created_at)
CLUSTER BY hashtag_norm, post_id;

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.post_characters` (
  post_id STRING NOT NULL,
  author_id STRING,
  created_at TIMESTAMP NOT NULL,
  org STRING NOT NULL,
  character_id STRING NOT NULL,
  character_name STRING NOT NULL,
  evidence_tag_norm STRING,
  evidence_source STRING NOT NULL,
  confidence FLOAT64 NOT NULL,
  fetched_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(created_at)
CLUSTER BY org, character_id, author_id;

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.hashtag_nodes` (
  hashtag_norm STRING NOT NULL,
  display_hashtag STRING,
  org_hint STRING,
  tag_type STRING,
  character_id STRING,
  character_name STRING,
  post_count INT64,
  first_seen_at TIMESTAMP,
  last_seen_at TIMESTAMP,
  updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.hashtag_cooccurrence_edges` (
  edge_id STRING NOT NULL,
  src_hashtag STRING NOT NULL,
  dst_hashtag STRING NOT NULL,
  window_start DATE NOT NULL,
  window_end DATE NOT NULL,
  post_count INT64 NOT NULL,
  src_post_count INT64 NOT NULL,
  dst_post_count INT64 NOT NULL,
  total_posts INT64 NOT NULL,
  jaccard FLOAT64,
  lift FLOAT64,
  pmi FLOAT64,
  updated_at TIMESTAMP NOT NULL
)
PARTITION BY window_end
CLUSTER BY src_hashtag, dst_hashtag;

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.character_nodes` (
  character_id STRING NOT NULL,
  org STRING NOT NULL,
  character_name STRING NOT NULL,
  post_count INT64,
  unique_author_count INT64,
  first_seen_at TIMESTAMP,
  last_seen_at TIMESTAMP,
  updated_at TIMESTAMP NOT NULL
)
CLUSTER BY org, character_id;

CREATE TABLE IF NOT EXISTS `jackojacko05.nijiholo.character_cooccurrence_edges` (
  edge_id STRING NOT NULL,
  unit_type STRING NOT NULL,
  src_character_id STRING NOT NULL,
  dst_character_id STRING NOT NULL,
  window_start DATE NOT NULL,
  window_end DATE NOT NULL,
  cooccurrence_units INT64 NOT NULL,
  src_units INT64 NOT NULL,
  dst_units INT64 NOT NULL,
  total_units INT64 NOT NULL,
  unique_authors INT64,
  post_count INT64,
  jaccard FLOAT64,
  lift FLOAT64,
  pmi FLOAT64,
  updated_at TIMESTAMP NOT NULL
)
PARTITION BY window_end
CLUSTER BY unit_type, src_character_id, dst_character_id;

