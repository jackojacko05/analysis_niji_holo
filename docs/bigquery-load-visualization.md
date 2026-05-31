# BigQuery Load and Visualization

Date: 2026-05-31

## BigQuery target

- Project: `jackojacko05`
- Dataset: `nijiholo`
- Location: `asia-northeast1`

## Loaded tables

| table | rows |
|---|---:|
| `talents_current` | 264 |
| `fanart_tags_current` | 265 |
| `tag_missing_current` | 3 |
| `x_search_queries_recent` | 7 |
| `youtube_channels` | 264 |
| `youtube_videos` | 61,325 |
| `youtube_video_collaborators` | 35,974 |
| `youtube_collab_edges` | 7,557 |
| `youtube_collab_edges_filtered` | 7,492 |

## Graph objects

Built by `sql/005_youtube_collab_graph.sql`.

- `youtube_character_nodes`: 264 rows
- `youtube_collab_edges_graph`: 7,492 rows
- `youtube_video_features`: 61,821 owner-video rows
- `youtube_collab_edges_by_genre`: 10,273 rows
- にじホロ横断edge: 209 rows
- property graph: `jackojacko05.nijiholo.youtube_collab_graph`

Article-ready tables were built by `sql/008_article_collab_metrics.sql`:

- `article_scope`
- `article_org_supply`
- `article_video_demand_by_mode`
- `article_owner_uplift`
- `article_genre_summary`
- `article_genre_uplift`
- `article_edge_matrix`
- `article_top_cross_edges`
- `article_graph_sample_edges`

The property graph was verified by running `GRAPH_TABLE` queries against
`youtube_collab_graph`.

## Visualization

Generated from the BigQuery property graph:

- `reports/youtube_collab_graph_latest200.html`
- `reports/youtube_collab_graph_2025-06-01_to_2026-05-31.html`
- `reports/note_draft_collab_niji_holo.md`
- `reports/note_figures/*.png`
- 表示ノード数: 107
- 表示edge数: 180

The visualization is a standalone HTML/SVG file. It uses:

- 同一組織edgeは `video_count >= 2` の上位を表示
- にじホロ横断edgeは1本だけの候補も含めて上位を表示
- ノード色は組織別
- オレンジ線はにじホロ横断edge
- 線の太さは `video_count`
- ゲーム / 歌 / その他のジャンル階層別に、組織別コラボ率、需要上振れ、edge上位を表示

Genre classification:

- `歌`: タイトルに歌枠、歌ってみた、karaoke、MV、cover、3D live などを含む
- `ゲーム`: タイトルにゲーム実況、ゲーム名、主要ゲーム略称などを含む
- `その他`: 上記以外

The genre rule is intentionally rough. It should be treated as a first-pass
slice for hypothesis testing, not as a final content taxonomy.

Regenerate:

```bash
python3 scripts/visualize_bigquery_youtube_graph.py
```
