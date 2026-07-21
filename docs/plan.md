# BigQuery Graph Plan

## Goal

にじさんじ / ホロライブのファンアート投稿から、ハッシュタグとキャラクターの共起関係を BigQuery Graph で分析する。

当時の Notebook は pandas + NetworkX で tweet-level co-occurrence を計算していた。今後は BigQuery を正とし、BigQuery Graph は探索用の graph view として使う。

## Confirmed State

- GitHub remote: `jackojacko05/analysis_niji_holo`
- Local clone: `/Users/user/GitHub/analysis_niji_holo`
- Existing method: BigQuery から期間内 tweets を取得し、fan-art tag list で character bool matrix を作り、同一投稿内 pair を NetworkX 化
- Google Cloud project: `jackojacko05`
- Existing datasets checked earlier: `health`, `keiba`, `test`
- New target dataset: `jackojacko05.nijiholo`

## Current External Constraints

X API:

- Recent Search is last 7 days and available to all developers.
- Full-Archive Search goes back to 2006 but is pay-per-use / Enterprise.
- Recent Search supports up to 100 posts per request and pagination.
- Useful query operators include hashtag, mention, `has:images`, `lang`, `-is:retweet`, and `-is:reply`.
- Rate limit docs list `/2/tweets/search/recent` as 450 app requests / 15 min and 100 max results.

References:

- https://docs.x.com/x-api/posts/search/introduction
- https://docs.x.com/x-api/fundamentals/rate-limits
- https://docs.x.com/x-api/getting-started/pricing
- https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/graph-schema-statements
- https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/graph-sql-queries

最近データの候補は [recent-data-options.md](recent-data-options.md) に分離した。

## Recommended Data Model

Raw:

- `raw_posts`: X API response per post
- `ingest_runs`: run metadata, query, time bounds, pagination, status
- `seed_queries`: query definitions

Reference:

- `character_tags`: character-to-fanart-tag mapping
- `hashtag_labels`: hashtag classification

Derived:

- `post_hashtags`: post-to-hashtag relation
- `post_characters`: post-to-character relation, inferred from fan-art tags
- `hashtag_nodes`
- `hashtag_cooccurrence_edges`
- `character_nodes`
- `character_cooccurrence_edges`

Graph:

- `hashtag_graph`: Hashtag nodes + Cooccurs edges
- `character_graph`: Character nodes + CoAppears edges

## First Implementation Path

1. Create `jackojacko05.nijiholo`.
2. Load `tag_niji.csv` and `tag_holo.csv` into `character_tags`.
3. Normalize old `tweets_tagged_*.csv` into `post_characters` for a legacy baseline.
4. Recompute old rankings in BigQuery and verify against existing CSV.
5. Add new X ingestion only after baseline matches.
6. Build BigQuery Graph DDL.
7. Add analysis queries:
   - top character pairs by post-level cooccurrence
   - top character pairs by unique author overlap
   - cross-org bridge characters / tags
   - weekly trend deltas
   - centrality-ready edge exports for Python / Gephi

## Why This Shape

The old analysis directly projected post-character membership into a character-character graph. That is valid, but it loses the original bipartite structure. Keeping `Post`, `User`, `Character`, and `Hashtag` relations lets us ask multiple questions without re-ingesting:

- Which characters appear together in the same fan-art post?
- Which characters are drawn by the same users within the same week?
- Which tags bridge Nijisanji and Hololive communities?
- Which pairs are simply popular, and which are unexpectedly associated after normalizing by base rates?
