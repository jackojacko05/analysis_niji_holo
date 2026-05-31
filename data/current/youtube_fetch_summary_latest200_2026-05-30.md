# YouTube Latest Videos Fetch (2026-05-30)

## Scope

- talents considered: 264
- resolved talent-channel rows: 264
- unresolved talent-channel rows: 0
- unique channels fetched: 261
- target latest videos per channel: 200
- video rows: 50261
- inferred description collaboration rows: 29653

## YouTube API Usage

- network requests made by this run: 2020
- cache hits: 13
- each `channels.list`, `playlistItems.list`, and `videos.list` request costs 1 quota unit.

## Collaboration Heuristic

- Matches only known current NIJISANJI/hololive YouTube channel IDs and @handles in video descriptions.
- Edges are evidence candidates, not final collaboration truth; descriptions often include guests, music credits, or management channels.
- Shared channels, such as grouped official channels, are kept as pipe-separated owners.
