# analysis_niji_holo

にじさんじ / ホロライブのファンアート投稿をもとに、キャラクター・ハッシュタグの共起関係を分析する作業リポジトリです。

## 現状

このリポジトリは、2023 年時点の Notebook と CSV を含んでいます。

- `にじホロ ネットワーク密度.ipynb`: 当時の BigQuery 読み込み、タグ付け、共起ランキング、NetworkX 分析
- `tag_niji.csv`, `tag_holo.csv`: キャラクター名とファンアートタグの対応表
- `tweets_tagged_niji.csv`, `tweets_tagged_holo.csv`: 投稿ごとのキャラクター bool 行列
- `co_occurrence_ranking_niji.csv`, `co_occurrence_ranking_holo.csv`: キャラクター共起ランキング

追加した設計資料と SQL:

- [docs/repo-audit.md](docs/repo-audit.md): 既存コード・CSV の調査結果
- [docs/plan.md](docs/plan.md): BigQuery Graph 化の実装計画
- [docs/character-cooccurrence-ideas.md](docs/character-cooccurrence-ideas.md): キャラ同士の共起を測る案
- [docs/recent-data-options.md](docs/recent-data-options.md): 最近データの取得候補と推奨構成
- [docs/youtube-latest200.md](docs/youtube-latest200.md): YouTube 直近 200 本取得結果と quota メモ
- [docs/youtube-2025-06-01-to-2026-05-31.md](docs/youtube-2025-06-01-to-2026-05-31.md): YouTube 2025-06-01 から 2026-05-31 までの取得結果
- [docs/bigquery-load-visualization.md](docs/bigquery-load-visualization.md): BigQuery ロード結果と可視化メモ
- [data/current](data/current): 現所属タレント・ファンアートタグの抽出結果
- [sql/001_schema.sql](sql/001_schema.sql): BigQuery テーブル定義案
- [sql/002_build_hashtag_edges.sql](sql/002_build_hashtag_edges.sql): ハッシュタグ共起 edge 生成
- [sql/003_hashtag_property_graph.sql](sql/003_hashtag_property_graph.sql): ハッシュタグ graph 定義
- [sql/004_character_cooccurrence_graph.sql](sql/004_character_cooccurrence_graph.sql): キャラクター共起 graph 定義
- [sql/005_youtube_collab_graph.sql](sql/005_youtube_collab_graph.sql): YouTube 概要欄の共演候補 graph 定義
- [sql/006_youtube_video_features.sql](sql/006_youtube_video_features.sql): コラボ仮説検証用の動画単位特徴量
- [sql/007_youtube_genre_edges.sql](sql/007_youtube_genre_edges.sql): ジャンル別の共演候補 edge 集計
- [sql/008_article_collab_metrics.sql](sql/008_article_collab_metrics.sql): 記事・Notebook 用の集計テーブル
- [scripts/normalize_legacy_csv.py](scripts/normalize_legacy_csv.py): 既存 wide CSV を正規化 CSV に変換
- [scripts/build_current_fanart_dataset.py](scripts/build_current_fanart_dataset.py): 現所属タレント・ファンアートタグ CSV を生成
- [scripts/build_x_search_queries.py](scripts/build_x_search_queries.py): ファンアートタグから X recent search 用 OR クエリ CSV を生成
- [scripts/test_x_query_cost.py](scripts/test_x_query_cost.py): X API クエリ 1 本の試行とコスト概算
- [scripts/fetch_youtube_latest_videos.py](scripts/fetch_youtube_latest_videos.py): 現所属タレントの YouTube チャンネルと直近動画メタデータを取得
- [scripts/build_youtube_collab_edges.py](scripts/build_youtube_collab_edges.py): 概要欄の既知チャンネル URL / @handle から共演候補 edge を集計
- [scripts/visualize_bigquery_youtube_graph.py](scripts/visualize_bigquery_youtube_graph.py): BigQuery Graph から可視化 HTML を生成
- [scripts/build_collab_hypothesis_report.py](scripts/build_collab_hypothesis_report.py): コラボ仮説の粗い検証レポートを生成
- [scripts/build_note_article_assets.py](scripts/build_note_article_assets.py): note 記事用の図解 SVG/PNG を生成
- [notebooks/niji_holo_collab_bigquery_graph.ipynb](notebooks/niji_holo_collab_bigquery_graph.ipynb): BigQuery Graph と記事用集計を再現する Notebook

## 現所属タレント・ファンアートタグデータ

2026-05-30 時点の抽出結果を [data/current](data/current) に置いています。

- `talents_current_2026-05-30.csv`: 264 人（にじさんじ 196 / ホロライブ 68）
- `fanart_tags_current_2026-05-30.csv`: 265 タグ行
- `x_search_queries_recent_2026-05-30.csv`: X recent search 用 OR クエリ 7 本
- `tag_missing_current_2026-05-30.csv`: タグ未確認 3 人（holoAN の 3 名）
- `sources_current_2026-05-30.md`: データソース、件数、confidence の説明

再生成:

```bash
python3 scripts/build_current_fanart_dataset.py
python3 scripts/build_x_search_queries.py
```

X API クエリを 1 本だけ試す:

```bash
X_BEARER_TOKEN=... python3 scripts/test_x_query_cost.py --batch-id hololive-001 --mode counts
X_BEARER_TOKEN=... python3 scripts/test_x_query_cost.py --batch-id hololive-001 --mode search --max-results 10
```

## YouTube 2025-06-01 から 2026-05-31 までのデータ

2026-05-31 に YouTube Data API で取得した、2025-06-01 から 2026-05-31 までのデータを BigQuery にロードしています。

- `youtube_channels`: 264 talent-channel rows / 261 unique channels
- `youtube_videos`: 61,325 videos, title, published timestamp, description, stats（195MB のため Git 管理外）
- `youtube_video_collaborators`: description match candidates, 35,974 rows
- `youtube_collab_edges`: directed owner -> collaborator edges, 7,557 rows
- `youtube_collab_edges_filtered`: boilerplate-like recurring links filtered out, 7,492 rows
- `youtube_video_features`: 61,821 owner-video rows
- `youtube_collab_edges_by_genre`: 10,273 genre-level edges
- `article_*`: note 記事・Notebook 用の集計テーブル
- `reports/note_draft_collab_niji_holo.md`: note 記事ドラフト
- `reports/note_figures/*.png`: note 記事用図解
- `reports/youtube_collab_graph_2025-06-01_to_2026-05-31.html`: BigQuery Graph から生成した日本語ダッシュボード
- `reports/collab_hypothesis_report_2025-06-01_to_2026-05-31.md`: コラボ仮説の日本語検証レポート

再取得:

```bash
YOUTUBE_API_KEY=... python3 scripts/fetch_youtube_latest_videos.py \
  --start-date 2025-06-01 \
  --end-date 2026-05-31 \
  --date-timezone Asia/Tokyo \
  --force-api

python3 scripts/build_youtube_collab_edges.py \
  --channels data/current/youtube_channels_current_2025-06-01_to_2026-05-31_2026-05-31.csv \
  --videos data/current/youtube_videos_2025-06-01_to_2026-05-31_2026-05-31.csv \
  --collabs data/current/youtube_video_collaborators_2025-06-01_to_2026-05-31_2026-05-31.csv
```

詳細は [docs/youtube-2025-06-01-to-2026-05-31.md](docs/youtube-2025-06-01-to-2026-05-31.md) を参照。

## YouTube 直近 200 本データ（旧）

2026-05-30 に YouTube Data API で取得した直近 200 本ベースのデータを [data/current](data/current) に置いています。

- `youtube_channels_current_2026-05-30.csv`: 264 talent-channel rows / 261 unique channels
- `youtube_videos_latest200_2026-05-30.csv`: 50,261 videos, title, published timestamp, description, stats（155MB のため Git 管理外）
- `youtube_video_collaborators_latest200_2026-05-30.csv`: description match candidates, 29,653 rows
- `youtube_collab_edges_latest200_2026-05-30.csv`: directed owner -> collaborator edges, 7,301 rows
- `youtube_collab_edges_filtered_latest200_2026-05-30.csv`: boilerplate-like recurring links filtered out, 7,237 rows
- `youtube_fetch_summary_latest200_2026-05-30.md`: fetch summary and heuristic notes
- `reports/youtube_collab_graph_latest200.html`: BigQuery Graph から生成した日本語ダッシュボード（ゲーム / 歌 / その他のジャンル階層つき）
- `reports/collab_hypothesis_rough_report_2026-05-31.md`: コラボ仮説の日本語検証レポート（ジャンル別の供給・需要分解つき）

再取得:

```bash
YOUTUBE_API_KEY=... python3 scripts/fetch_youtube_latest_videos.py --max-videos 200
python3 scripts/build_youtube_collab_edges.py
```

## 重要な注意

既存 Notebook の `co_occurrence_ranking_*` 出力はファイル名が入れ替わっています。

- `co_occurrence_ranking_holo.csv` には、にじさんじキャラクターの共起が入っています。
- `co_occurrence_ranking_niji.csv` には、ホロライブキャラクターの共起が入っています。

次に実装するなら、既存 CSV を正規化して BigQuery にロードし、`post_characters` と `character_cooccurrence_edges` を作ってから BigQuery Graph で分析するのが最短です。

旧 CSV の正規化:

```bash
python3 scripts/normalize_legacy_csv.py
```
