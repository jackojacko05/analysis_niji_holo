# Recent Data Options

昔の BigQuery は baseline として使い、最近データは別 ingest として足す。

## Recommendation

最初の現実解はこの 3 層。

1. X official recent search
   - fan-art tag の精度が一番高い。
   - ただし pay-per-use なので小さく、毎日差分で取る。
2. Bluesky search / Jetstream
   - 無料寄りで公開 post を取りやすい。
   - X より投稿量は少ないが、ハッシュタグとテキスト検索の side channel として優秀。
3. Holodex / YouTube
   - fan art ではないが、最近のコラボ・同時出演・動画文脈を取れる。
   - キャラ共起の「公式/配信側の近さ」として使える。

X に未練はある。分析品質だけ見るなら X がまだ本命。ただし、費用と将来の制約変化を考えると X だけの設計にしない方がいい。

## Candidate Matrix

| Source | Recentness | Fan-art signal | Character co-occurrence use | Cost / friction | Verdict |
| --- | --- | --- | --- | --- | --- |
| X Recent Search | Very high | Very high | Same post, same author-week, hashtag bridge | Paid per read | Best, but cap it |
| Bluesky Search | High | Medium | Same post, same author-week, migration trend | Public endpoints available | Strong backup |
| Holodex | High | Low | Collab/video co-appearance graph | API key, friendly | Great context layer |
| YouTube Data API | High | Low-medium | Comments, titles, descriptions, channel/video graph | Quota-based | Useful but quota-aware |
| Misskey.io | High | Medium | Japanese fediverse fan-art hashtags | Instance-specific | Good experiment |
| Mastodon | High | Low-medium | Hashtag timelines by instance | Instance-specific | Secondary |
| Pixiv | High | Very high | Artwork tag co-occurrence, artist overlap | Official public API unclear | Good if handled carefully |
| Danbooru | High | High | Tag co-occurrence, character/copyright tags | Public API, adult/copyright caveats | Useful proxy, not primary |
| Google Trends | High | None | Macro interest only | Easy-ish, not post-level | Background signal |

## X Plan

Use X only where it is strongest:

- Query fan-art tags directly.
- Prefer image posts: `has:images lang:ja -is:retweet`.
- Avoid broad `#にじさんじ` / `#ホロライブ` alone.
- Use a daily Cloud Run job with a strict maximum post read budget.
- Store only metadata needed for analysis: post id, author id, created_at, text, entities.hashtags, public_metrics, source query, raw JSON.

Suggested first budget:

- 30-50 seed queries
- 7-day rolling recent search
- max 100-300 posts per query per day
- daily cap around 3,000-5,000 post reads until signal quality is known

Rough cost at X post read `$0.005`:

- 1,000 reads: `$5`
- 5,000 reads: `$25`
- 30,000 reads: `$150`

Use X for:

- same-post character co-appearance
- same-author week/month character overlap
- tag bridge discovery
- event spike detection

## Bluesky Plan

Bluesky has an official `app.bsky.feed.searchPosts` endpoint with tag filtering. The public AppView endpoint can be called without auth for public endpoints.

Use it for:

- fan-art tag search against the same `character_tags`
- full-text alias search for character names
- migration/comparison layer: which X fan-art tags are active on Bluesky?
- low-cost daily collection while X budget is limited

BigQuery source fields:

- `platform = 'bluesky'`
- `post_uri`
- `cid`
- `author_did`
- `author_handle`
- `indexed_at`
- `text`
- `tags`
- `like_count`, `reply_count`, `repost_count`, if available

Expected weakness:

- fewer Japanese VTuber fan-art posts than X
- hashtag usage norms differ from X
- search completeness should be treated as platform-specific, not a full replacement

## Holodex / YouTube Plan

Holodex is useful for a different graph:

- Channel nodes
- Video nodes
- Character/channel appearance edges
- Clip/reference edges
- Org/generation metadata

This gives a recent co-appearance baseline independent of fan-art posts.

Use cases:

- “These two characters co-occur in fan-art because they recently collaborated”
- “This edge is fan-driven but not official-collab-driven”
- “Hololive/Nijisanji cross-org bridge is video/collab context vs fan-art context”

YouTube Data API can add:

- video title/description co-mentions
- comments mentioning multiple characters
- official channel upload metadata

But comment crawling can burn quota quickly, so it should come after Holodex/video metadata.

## Pixiv / Danbooru Plan

Pixiv is semantically excellent for fan art, but official API access is not as clean as X/Bluesky/YouTube. Because this repo already has `pixiv_crawling` nearby in the account history, it is worth revisiting, but only if the access method is acceptable.

Use Pixiv carefully for:

- artwork tag co-occurrence
- artist-character overlap
- recent fan-art volume per character

Danbooru is easier as a tag API proxy, but it is not the same community and has adult/copyright moderation caveats.

Use Danbooru only for:

- character tag normalization hints
- coarse fan-art co-tag network
- “external imageboard proxy” comparison, clearly labeled

## Misskey / Mastodon Plan

Misskey.io has `notes/search-by-tag`. Mastodon has hashtag timeline APIs. These are good experiments because Japanese illustrators do post on fediverse services, but each instance is its own world.

Use for:

- specific fan-art tags
- image-only notes/statuses where supported
- comparison with X/Bluesky, not as canonical counts

## BigQuery Shape

Keep the source-specific raw tables, then normalize into common tables:

- `social_posts`
- `social_post_hashtags`
- `social_post_characters`
- `video_appearances`
- `character_cooccurrence_edges`

Add these fields everywhere:

- `platform`
- `source_method`
- `retrieved_at`
- `confidence`
- `evidence_source`

Do not mix platforms blindly. Compute edges per platform first, then create a cross-platform rollup.

## First Experiment

Run a 7-day comparison:

1. Pick 20 Nijisanji and 20 Hololive characters from the old top lists.
2. Use each character's fan-art tag as seed.
3. Collect:
   - X recent search, capped
   - Bluesky search, uncapped within polite limits
   - Holodex recent videos for channels in both orgs
4. Build three edge types:
   - `post`: same post includes both characters
   - `author_week`: same author posts both in the same week
   - `video_context`: same video/collab context
5. Compare top edges and disagreements.

The interesting findings will be disagreements:

- high X/post, low Holodex: fan pairing or art trend
- high Holodex, low fan-art: official collab not reflected in art
- high Bluesky but low X: platform migration niche
- high author_week, low post: same artists like both, but not drawn together

## References

- X API overview and pricing: https://docs.x.com/x-api
- X usage / post cap: https://docs.x.com/x-api/fundamentals/post-cap
- X rate limits: https://docs.x.com/x-api/fundamentals/rate-limits
- Bluesky search posts: https://docs.bsky.app/docs/api/app-bsky-feed-search-posts
- YouTube Data API overview and quota: https://developers.google.com/youtube/v3/getting-started
- Holodex API docs: https://docs.holodex.net/
- Mastodon hashtag timeline: https://docs.joinmastodon.org/methods/timelines/
- Misskey.io API docs: https://misskey.io/api-doc
- pixiv search help: https://www.pixiv.help/hc/ja/articles/235646387
- Danbooru API reference: https://pybooru.readthedocs.io/en/stable/api_danbooru.html

