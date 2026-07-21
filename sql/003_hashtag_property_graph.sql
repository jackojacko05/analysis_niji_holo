-- BigQuery Graph property graph and starter analysis queries for hashtags.
-- BigQuery Graph is Preview / Pre-GA as of the 2026-05-29 docs.

CREATE OR REPLACE PROPERTY GRAPH `jackojacko05.nijiholo.hashtag_graph`
  NODE TABLES (
    `jackojacko05.nijiholo.hashtag_nodes` AS Hashtag
      KEY (hashtag_norm)
      LABEL Hashtag
      PROPERTIES (
        hashtag_norm,
        display_hashtag,
        org_hint,
        tag_type,
        character_id,
        character_name,
        post_count,
        first_seen_at,
        last_seen_at
      )
  )
  EDGE TABLES (
    `jackojacko05.nijiholo.hashtag_cooccurrence_edges` AS Cooccurs
      KEY (edge_id)
      SOURCE KEY (src_hashtag) REFERENCES Hashtag (hashtag_norm)
      DESTINATION KEY (dst_hashtag) REFERENCES Hashtag (hashtag_norm)
      LABEL Cooccurs
      PROPERTIES (
        window_start,
        window_end,
        post_count,
        src_post_count,
        dst_post_count,
        total_posts,
        jaccard,
        lift,
        pmi
      )
  );

-- Top co-occurring hashtag pairs.
SELECT *
FROM GRAPH_TABLE(
  `jackojacko05.nijiholo.hashtag_graph`
  MATCH (a:Hashtag)-[e:Cooccurs]->(b:Hashtag)
  WHERE a.hashtag_norm < b.hashtag_norm
    AND e.post_count >= 5
  RETURN
    a.display_hashtag AS tag_a,
    b.display_hashtag AS tag_b,
    e.post_count AS post_count,
    e.jaccard AS jaccard,
    e.lift AS lift,
    e.pmi AS pmi
)
ORDER BY post_count DESC
LIMIT 100;

-- Bridge tags between manually labeled Nijisanji and Hololive hashtag neighborhoods.
SELECT
  bridge_tag,
  COUNT(*) AS path_count,
  SUM(LEAST(edge_1_posts, edge_2_posts)) AS min_edge_weight_sum
FROM GRAPH_TABLE(
  `jackojacko05.nijiholo.hashtag_graph`
  MATCH
    (niji:Hashtag)-[e1:Cooccurs]->(bridge:Hashtag)-[e2:Cooccurs]->(holo:Hashtag)
  WHERE niji.org_hint = 'nijisanji'
    AND holo.org_hint = 'hololive'
    AND bridge.org_hint IS NULL
  RETURN
    niji.display_hashtag AS niji_tag,
    bridge.display_hashtag AS bridge_tag,
    holo.display_hashtag AS holo_tag,
    e1.post_count AS edge_1_posts,
    e2.post_count AS edge_2_posts
)
GROUP BY bridge_tag
ORDER BY min_edge_weight_sum DESC, path_count DESC
LIMIT 100;

