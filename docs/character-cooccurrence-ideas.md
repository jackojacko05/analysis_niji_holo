# Character Co-occurrence Ideas

## Core Idea

Character co-occurrence should not be a single metric. Use multiple units of observation and compare them:

| Unit | Edge means | Best for | Main bias |
| --- | --- | --- | --- |
| Post | same post tags multiple characters | actual multi-character fan art | misses same artist drawing characters separately |
| Author-day | same author posts both characters on same day | daily drawing / event behavior | active authors dominate |
| Author-week | same author posts both characters in same week | creator affinity / audience overlap | weak temporal relation |
| Conversation | same thread/conversation references both | discussion-level relation | replies and quotes can be noisy |
| Hashtag | character fan-art tags co-occur with same generic tags | semantic neighborhood | hashtag spam / trend latching |

Build all of them into `character_cooccurrence_edges.unit_type`.

## Metrics

For each pair `(a, b)` and unit type:

- `cooccurrence_units`: number of units containing both characters
- `src_units`, `dst_units`: number of units containing each character
- `total_units`: all units in the window
- `jaccard = both / (src + dst - both)`
- `lift = both * total / (src * dst)`
- `pmi = log(lift)`
- `unique_authors`: number of distinct authors involved
- `post_count`: raw post count, retained for interpretability

Use `post_count` for intuitive ranking, but use `lift` / `pmi` to find pairs that are stronger than popularity alone predicts.

## Better User-post Based Analyses

1. Same-post co-appearance
   - Existing analysis already does this.
   - Query shape: one post has fan-art tags for character A and B.
   - Strongest evidence for true co-drawn fan art.

2. Same-author co-interest
   - A user who posts `#A_art` and `#B_art` within the same month contributes one edge.
   - This captures artists who draw both characters even when the characters do not appear in the same image.
   - Rank by unique authors, not raw posts, to reduce prolific-user domination.

3. Same-author temporal proximity
   - Use author-week or author-day as the unit.
   - Good for events, collabs, birthdays, and pair/fan unit surges.
   - More robust than whole-period author overlap.

4. Cross-org bridge score
   - Restrict one side to Nijisanji, the other to Hololive.
   - Score by `PMI * log(unique_authors + 1)` or by top 2-hop paths through shared tags.
   - Useful for finding fan communities that draw across orgs.

5. Generic tag bridge
   - Character -> post -> hashtag -> character.
   - Example bridge tags: event names, game titles, unit names, anniversary tags, meme tags.
   - This often explains why two characters co-occur.

6. Collab/event alignment
   - Maintain a small event table: `event_name`, `start_date`, `end_date`, `characters`.
   - Compare edge weights before / during / after events.
   - Distinguishes standing pair popularity from event-driven spikes.

7. Text fallback with aliases
   - Fan-art tags are high precision but miss posts that only mention names.
   - Add a low-confidence alias table for display names, nicknames, unit names.
   - Keep `source = fanart_tag | alias_text | manual_seed` and do not mix confidence levels blindly.

8. Image-post focus
   - For X ingestion, prefer queries with `has:images lang:ja -is:retweet`.
   - This aligns better with fan-art analysis than general discussion posts.

9. User graph layer
   - Nodes: users and characters.
   - Edge: user posted fan art for character.
   - Character-character graph can be a projection of this bipartite graph, matching common hashtag co-occurrence methodology.

10. Old data baseline
   - Use the 2021-11-22 to 2022-11-21 CSVs to validate SQL.
   - Reproduce old top pairs first, then add new unit types.

## Method Notes From Literature

Hashtag co-occurrence networks are commonly built by extracting hashtags from posts and projecting a post/user-tag bipartite relation into a weighted one-mode graph. The same pattern maps cleanly to characters:

- post-character bipartite graph -> character co-appearance graph
- user-character bipartite graph -> creator/audience overlap graph
- hashtag-character bipartite graph -> semantic bridge graph

Relevant sources:

- https://journals.sagepub.com/doi/full/10.1177/2056305118764437
- https://www.cambridge.org/core/journals/memory-mind-and-media/article/latent-and-explicit-mnemonic-communities-on-social-media-studying-digital-memory-formation-through-hashtag-cooccurrence-analysis/431483384325BAC46DD21B8A4008179B
- https://link.springer.com/article/10.1007/s13278-025-01415-0

## Practical Recommendation

Start with three edge tables in one BigQuery job:

- `unit_type = 'post'`
- `unit_type = 'author_week'`
- `unit_type = 'author_month'`

Then compare top 50 edges across all three. Pairs that rank high in `post` are likely actual co-drawn fan art. Pairs that rank high in `author_week` or `author_month` but not `post` are likely creator/audience overlap or adjacent fandoms.

