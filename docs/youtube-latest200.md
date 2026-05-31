# YouTube Latest 200 Fetch

Date: 2026-05-30

## What was fetched

- Scope: current `talents_current_2026-05-30.csv`
- Talent-channel rows: 264
- Unique YouTube channels: 261
- Latest videos requested per channel: 200
- Video rows fetched: 50,261
- Description-level collaboration candidate rows: 29,653
- Directed owner-to-collaborator edges: 7,301
- Filtered directed edges: 7,237

## Files

- `data/current/youtube_channels_current_2026-05-30.csv`
- `data/current/youtube_videos_latest200_2026-05-30.csv` (155MB, local-only/Git ignored)
- `data/current/youtube_video_collaborators_latest200_2026-05-30.csv`
- `data/current/youtube_collab_edges_latest200_2026-05-30.csv`
- `data/current/youtube_collab_edges_filtered_latest200_2026-05-30.csv`
- `data/current/youtube_fetch_summary_latest200_2026-05-30.md`

## API and quota

The run uses `channels.list`, `playlistItems.list`, and `videos.list`. It does
not use `search.list`.

- Full latest-200 run network requests: 2,020
- One small smoke test before the full run: 13
- Total YouTube Data API units consumed by this work: about 2,033

Google's official quota table lists `channels.list`, `playlistItems.list`, and
`videos.list` as 1 unit each, while `search.list` costs 100 units. It also
states that projects enabling the YouTube Data API have a default allocation of
10,000 units per day.

Official references:

- https://developers.google.com/youtube/v3/determine_quota_cost
- https://developers.google.com/youtube/v3/getting-started

## Collaboration heuristic

The first-pass candidate table matches only known current NIJISANJI/hololive
YouTube channel IDs and `@handle`s found in descriptions.

This is useful but noisy. Some descriptions include every wave member or
official related channel as boilerplate, so `build_youtube_collab_edges.py`
marks edges as `likely_boilerplate=true` when the same collaborator appears in
at least 20 videos and at least 40% of the owner's fetched videos. The filtered
CSV removes those rows.

The filtered top edges look much more like actual collaboration/co-appearance
candidates, but the result should still be treated as a candidate graph rather
than a clean truth dataset.

## Re-run

```bash
YOUTUBE_API_KEY=... python3 scripts/fetch_youtube_latest_videos.py --max-videos 200
python3 scripts/build_youtube_collab_edges.py
```

## BigQuery load notes

The video CSV contains quoted newlines in descriptions, so load it with
`--allow_quoted_newlines`.

```bash
bq load --project_id=jackojacko05 --source_format=CSV --skip_leading_rows=1 --allow_quoted_newlines --autodetect \
  nijiholo.youtube_videos data/current/youtube_videos_latest200_2026-05-30.csv

bq load --project_id=jackojacko05 --source_format=CSV --skip_leading_rows=1 --allow_quoted_newlines --autodetect \
  nijiholo.youtube_channels data/current/youtube_channels_current_2026-05-30.csv

bq load --project_id=jackojacko05 --source_format=CSV --skip_leading_rows=1 --allow_quoted_newlines --autodetect \
  nijiholo.youtube_collab_edges_filtered data/current/youtube_collab_edges_filtered_latest200_2026-05-30.csv
```
