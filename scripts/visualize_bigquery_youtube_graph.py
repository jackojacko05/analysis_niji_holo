#!/usr/bin/env python3
"""Build a readable Japanese HTML dashboard from the BigQuery graph."""

from __future__ import annotations

import argparse
from datetime import date
import html
import json
import math
from pathlib import Path
import random
import subprocess
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = BASE_DIR / "reports"
TODAY = date.today().isoformat()
GENRE_ORDER = ("ゲーム", "歌", "その他")


NETWORK_SQL = r"""
WITH base AS (
  SELECT *
  FROM GRAPH_TABLE(
    `jackojacko05.nijiholo.youtube_collab_graph`
    MATCH (a:Character)-[e:MentionsChannel]->(b:Character)
    RETURN
      a.character_id AS src_id,
      a.character_name AS src_name,
      a.org AS src_org,
      b.character_id AS dst_id,
      b.character_name AS dst_name,
      b.org AS dst_org,
      e.video_count AS video_count,
      e.video_share AS video_share,
      e.evidence_types AS evidence_types,
      e.sample_video_url AS sample_video_url,
      e.sample_title AS sample_title
  )
),
same_edges AS (
  SELECT *
  FROM base
  WHERE src_org = dst_org
    AND video_count >= 2
  ORDER BY video_count DESC, src_name, dst_name
  LIMIT 100
),
cross_edges AS (
  SELECT *
  FROM base
  WHERE src_org != dst_org
  ORDER BY video_count DESC, src_name, dst_name
  LIMIT 80
)
SELECT DISTINCT *
FROM (
  SELECT * FROM same_edges
  UNION ALL
  SELECT * FROM cross_edges
)
ORDER BY video_count DESC, src_org, src_name, dst_org, dst_name
"""

ORG_SUPPLY_SQL = r"""
SELECT
  owner_org AS org,
  COUNT(DISTINCT owner_talent_id) AS talents,
  COUNT(*) AS owner_video_rows,
  COUNTIF(collab_flag) AS collab_video_rows,
  SAFE_DIVIDE(COUNTIF(collab_flag), COUNT(*)) AS collab_share,
  COUNTIF(cross_org_collab_flag) AS cross_org_video_rows,
  SAFE_DIVIDE(COUNTIF(cross_org_collab_flag), COUNT(*)) AS cross_org_share
FROM `jackojacko05.nijiholo.youtube_video_features`
GROUP BY owner_org
ORDER BY org
"""

OWNER_UPLIFT_SQL = r"""
WITH per_mode AS (
  SELECT
    owner_org,
    owner_talent_id,
    owner_name,
    collab_flag,
    COUNT(*) AS videos,
    AVG(relative_log_views) AS avg_relative_log_views,
    AVG(relative_log_views_per_day) AS avg_relative_log_views_per_day
  FROM `jackojacko05.nijiholo.youtube_video_features`
  GROUP BY owner_org, owner_talent_id, owner_name, collab_flag
),
pairs AS (
  SELECT
    collab.owner_org,
    collab.owner_talent_id,
    collab.owner_name,
    collab.videos AS collab_videos,
    solo.videos AS solo_videos,
    collab.avg_relative_log_views - solo.avg_relative_log_views AS collab_log_view_uplift,
    collab.avg_relative_log_views_per_day - solo.avg_relative_log_views_per_day AS collab_log_view_per_day_uplift
  FROM per_mode AS collab
  JOIN per_mode AS solo
    ON collab.owner_talent_id = solo.owner_talent_id
  WHERE collab.collab_flag
    AND NOT solo.collab_flag
    AND collab.videos >= 3
    AND solo.videos >= 20
)
SELECT
  owner_org AS org,
  COUNT(*) AS comparable_talents,
  AVG(collab_log_view_uplift) AS avg_collab_log_view_uplift,
  APPROX_QUANTILES(collab_log_view_uplift, 101)[OFFSET(50)] AS median_collab_log_view_uplift,
  COUNTIF(collab_log_view_uplift > 0) AS positive_view_uplift_talents,
  AVG(collab_log_view_per_day_uplift) AS avg_collab_log_view_per_day_uplift,
  APPROX_QUANTILES(collab_log_view_per_day_uplift, 101)[OFFSET(50)] AS median_collab_log_view_per_day_uplift
FROM pairs
GROUP BY owner_org
ORDER BY org
"""

GENRE_SUMMARY_SQL = r"""
SELECT
  owner_org AS org,
  content_genre AS genre,
  COUNT(*) AS videos,
  COUNTIF(collab_flag) AS collab_videos,
  SAFE_DIVIDE(COUNTIF(collab_flag), COUNT(*)) AS collab_share,
  COUNTIF(cross_org_collab_flag) AS cross_org_videos,
  SAFE_DIVIDE(COUNTIF(cross_org_collab_flag), COUNT(*)) AS cross_org_share,
  APPROX_QUANTILES(IF(collab_flag, relative_log_views, NULL), 101 IGNORE NULLS)[OFFSET(50)] AS collab_median_relative_log_views,
  APPROX_QUANTILES(IF(NOT collab_flag, relative_log_views, NULL), 101 IGNORE NULLS)[OFFSET(50)] AS solo_median_relative_log_views,
  APPROX_QUANTILES(IF(collab_flag, relative_log_views_per_day, NULL), 101 IGNORE NULLS)[OFFSET(50)] AS collab_median_relative_log_views_per_day,
  APPROX_QUANTILES(IF(NOT collab_flag, relative_log_views_per_day, NULL), 101 IGNORE NULLS)[OFFSET(50)] AS solo_median_relative_log_views_per_day
FROM `jackojacko05.nijiholo.youtube_video_features`
GROUP BY owner_org, content_genre
ORDER BY
  CASE content_genre WHEN 'ゲーム' THEN 1 WHEN '歌' THEN 2 ELSE 3 END,
  owner_org
"""

GENRE_UPLIFT_SQL = r"""
WITH per_mode AS (
  SELECT
    owner_org,
    content_genre AS genre,
    owner_talent_id,
    owner_name,
    collab_flag,
    COUNT(*) AS videos,
    AVG(relative_log_views) AS avg_relative_log_views,
    AVG(relative_log_views_per_day) AS avg_relative_log_views_per_day
  FROM `jackojacko05.nijiholo.youtube_video_features`
  GROUP BY owner_org, genre, owner_talent_id, owner_name, collab_flag
),
pairs AS (
  SELECT
    collab.owner_org,
    collab.genre,
    collab.owner_talent_id,
    collab.owner_name,
    collab.videos AS collab_videos,
    solo.videos AS solo_videos,
    collab.avg_relative_log_views - solo.avg_relative_log_views AS collab_log_view_uplift,
    collab.avg_relative_log_views_per_day - solo.avg_relative_log_views_per_day AS collab_log_view_per_day_uplift
  FROM per_mode AS collab
  JOIN per_mode AS solo
    ON collab.owner_talent_id = solo.owner_talent_id
   AND collab.genre = solo.genre
  WHERE collab.collab_flag
    AND NOT solo.collab_flag
    AND collab.videos >= 2
    AND solo.videos >= 8
)
SELECT
  owner_org AS org,
  genre,
  COUNT(*) AS comparable_talents,
  AVG(collab_log_view_uplift) AS avg_collab_log_view_uplift,
  APPROX_QUANTILES(collab_log_view_uplift, 101)[OFFSET(50)] AS median_collab_log_view_uplift,
  COUNTIF(collab_log_view_uplift > 0) AS positive_view_uplift_talents,
  AVG(collab_log_view_per_day_uplift) AS avg_collab_log_view_per_day_uplift,
  APPROX_QUANTILES(collab_log_view_per_day_uplift, 101)[OFFSET(50)] AS median_collab_log_view_per_day_uplift
FROM pairs
GROUP BY owner_org, genre
ORDER BY
  CASE genre WHEN 'ゲーム' THEN 1 WHEN '歌' THEN 2 ELSE 3 END,
  owner_org
"""

EDGE_MATRIX_SQL = r"""
SELECT
  src_org,
  dst_org,
  COUNT(*) AS directed_edges,
  SUM(video_count) AS weighted_video_count,
  AVG(video_count) AS avg_video_count
FROM `jackojacko05.nijiholo.youtube_collab_edges_graph`
GROUP BY src_org, dst_org
ORDER BY src_org, dst_org
"""

TOP_CROSS_SQL = r"""
SELECT
  src_character_name AS owner_name,
  dst_character_name AS collaborator_name,
  video_count,
  sample_video_url,
  sample_title
FROM `jackojacko05.nijiholo.youtube_collab_edges_graph`
WHERE src_org != dst_org
ORDER BY video_count DESC, owner_name, collaborator_name
LIMIT 18
"""

TOP_OWNERS_SQL = r"""
WITH collabs AS (
  SELECT
    owner_talent_id,
    collaborator
  FROM `jackojacko05.nijiholo.youtube_video_features`,
  UNNEST(SPLIT(collaborator_talent_ids, '|')) AS collaborator
  WHERE collaborator IS NOT NULL
    AND collaborator != ''
),
per_owner AS (
  SELECT
    owner_org,
    owner_talent_id,
    ANY_VALUE(owner_name) AS owner_name,
    COUNT(*) AS videos,
    COUNTIF(collab_flag) AS collab_videos,
    SAFE_DIVIDE(COUNTIF(collab_flag), COUNT(*)) AS collab_share
  FROM `jackojacko05.nijiholo.youtube_video_features`
  GROUP BY owner_org, owner_talent_id
),
unique_collabs AS (
  SELECT
    owner_talent_id,
    COUNT(DISTINCT collaborator) AS unique_collaborators
  FROM collabs
  GROUP BY owner_talent_id
)
SELECT
  owner_org AS org,
  owner_name,
  videos,
  collab_videos,
  collab_share,
  COALESCE(unique_collaborators, 0) AS unique_collaborators
FROM per_owner
LEFT JOIN unique_collabs USING (owner_talent_id)
WHERE videos >= 50
ORDER BY collab_share DESC, unique_collaborators DESC
LIMIT 12
"""

TOP_GENRE_EDGES_SQL = r"""
SELECT
  content_genre AS genre,
  src_org,
  src_character_name AS owner_name,
  dst_org,
  dst_character_name AS collaborator_name,
  video_count,
  sample_video_url,
  sample_title
FROM `jackojacko05.nijiholo.youtube_collab_edges_by_genre`
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY content_genre
  ORDER BY video_count DESC, src_character_name, dst_character_name
) <= 8
ORDER BY
  CASE content_genre WHEN 'ゲーム' THEN 1 WHEN '歌' THEN 2 ELSE 3 END,
  video_count DESC,
  owner_name,
  collaborator_name
"""


def bq_query(sql: str, project: str, location: str) -> list[dict[str, Any]]:
    cmd = [
        "bq",
        "query",
        f"--project_id={project}",
        f"--location={location}",
        "--nouse_legacy_sql",
        "--quiet",
        "--format=json",
        "--max_rows=1000",
        sql,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def org_label(value: Any) -> str:
    return {"nijisanji": "にじさんじ", "hololive": "ホロライブ"}.get(str(value), str(value))


def org_color(org: str) -> str:
    return {"nijisanji": "#2563eb", "hololive": "#06b6d4"}.get(org, "#64748b")


def genre_label(value: Any) -> str:
    return str(value)


def pct(value: Any, digits: int = 1) -> str:
    return f"{float(value):.{digits}%}"


def signed_pct_from_log(value: Any) -> str:
    return f"{math.expm1(float(value)):+.1%}"


def fmt_int(value: Any) -> str:
    return f"{int(float(value)):,}"


def clipped(value: Any, limit: int = 90) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "..."


def stable_random(key: str) -> random.Random:
    seed = sum((i + 1) * ord(ch) for i, ch in enumerate(key))
    return random.Random(seed)


def row_for(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    for row in rows:
        if row.get(key) == value:
            return row
    return {}


def genre_row(rows: list[dict[str, Any]], org: str, genre: str) -> dict[str, Any]:
    for row in rows:
        if row.get("org") == org and row.get("genre") == genre:
            return row
    return {}


def build_graph(edges: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    normalized_edges: list[dict[str, Any]] = []
    for edge in edges:
        src_id = str(edge["src_id"])
        dst_id = str(edge["dst_id"])
        nodes.setdefault(src_id, {"id": src_id, "name": edge["src_name"], "org": edge["src_org"], "degree": 0, "weight": 0})
        nodes.setdefault(dst_id, {"id": dst_id, "name": edge["dst_name"], "org": edge["dst_org"], "degree": 0, "weight": 0})
        video_count = int(edge["video_count"])
        nodes[src_id]["degree"] += 1
        nodes[dst_id]["degree"] += 1
        nodes[src_id]["weight"] += video_count
        nodes[dst_id]["weight"] += video_count
        normalized_edges.append(
            {
                "src": src_id,
                "dst": dst_id,
                "video_count": video_count,
                "video_share": float(edge["video_share"] or 0),
                "sample_video_url": edge["sample_video_url"],
                "sample_title": edge["sample_title"],
                "cross_org": edge["src_org"] != edge["dst_org"],
            }
        )
    return nodes, normalized_edges


def layout(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]], width: int, height: int) -> None:
    centers = {
        "nijisanji": (width * 0.36, height * 0.54),
        "hololive": (width * 0.70, height * 0.50),
    }
    default_center = (width * 0.52, height * 0.52)

    for node in nodes.values():
        rng = stable_random(node["id"])
        cx, cy = centers.get(node["org"], default_center)
        node["x"] = cx + rng.uniform(-160, 160)
        node["y"] = cy + rng.uniform(-210, 210)
        node["vx"] = 0.0
        node["vy"] = 0.0

    node_list = list(nodes.values())
    for _ in range(360):
        for node in node_list:
            cx, cy = centers.get(node["org"], default_center)
            node["vx"] += (cx - node["x"]) * 0.0024
            node["vy"] += (cy - node["y"]) * 0.0024

        for i, a in enumerate(node_list):
            for b in node_list[i + 1 :]:
                dx = a["x"] - b["x"]
                dy = a["y"] - b["y"]
                dist2 = max(dx * dx + dy * dy, 49.0)
                force = 2600.0 / dist2
                dist = math.sqrt(dist2)
                fx = force * dx / dist
                fy = force * dy / dist
                a["vx"] += fx
                a["vy"] += fy
                b["vx"] -= fx
                b["vy"] -= fy

        for edge in edges:
            src = nodes[edge["src"]]
            dst = nodes[edge["dst"]]
            dx = dst["x"] - src["x"]
            dy = dst["y"] - src["y"]
            dist = max(math.sqrt(dx * dx + dy * dy), 1.0)
            target = 180 if edge["cross_org"] else 105
            strength = 0.010 * min(4.0, 1.0 + math.log1p(edge["video_count"]) / 2.0)
            force = (dist - target) * strength
            fx = force * dx / dist
            fy = force * dy / dist
            src["vx"] += fx
            src["vy"] += fy
            dst["vx"] -= fx
            dst["vy"] -= fy

        for node in node_list:
            node["vx"] *= 0.82
            node["vy"] *= 0.82
            node["x"] = min(width - 44, max(44, node["x"] + node["vx"]))
            node["y"] = min(height - 50, max(64, node["y"] + node["vy"]))


def network_svg(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]], width: int = 1180, height: int = 680) -> str:
    max_weight = max((node["weight"] for node in nodes.values()), default=1)
    max_edge = max((edge["video_count"] for edge in edges), default=1)

    edge_parts = []
    for edge in sorted(edges, key=lambda e: e["video_count"]):
        src = nodes[edge["src"]]
        dst = nodes[edge["dst"]]
        stroke = "#f97316" if edge["cross_org"] else "#94a3b8"
        opacity = 0.28 + 0.50 * (edge["video_count"] / max_edge)
        width_px = 0.7 + 4.4 * math.sqrt(edge["video_count"] / max_edge)
        title = html.escape(f"{src['name']} -> {dst['name']} / {edge['video_count']}本 / {edge['sample_title']}")
        edge_parts.append(
            f'<line x1="{src["x"]:.1f}" y1="{src["y"]:.1f}" x2="{dst["x"]:.1f}" y2="{dst["y"]:.1f}" '
            f'stroke="{stroke}" stroke-width="{width_px:.2f}" stroke-opacity="{opacity:.2f}"><title>{title}</title></line>'
        )

    node_parts = []
    label_parts = []
    for node in sorted(nodes.values(), key=lambda n: n["weight"], reverse=True):
        radius = 5.0 + 12.0 * math.sqrt(node["weight"] / max_weight)
        title = html.escape(f"{node['name']} / {org_label(node['org'])} / edge={node['degree']} / weight={node['weight']}")
        node_parts.append(
            f'<circle cx="{node["x"]:.1f}" cy="{node["y"]:.1f}" r="{radius:.1f}" fill="{org_color(node["org"])}" '
            f'stroke="#ffffff" stroke-width="1.7"><title>{title}</title></circle>'
        )
        if node["weight"] >= max_weight * 0.15 or node["degree"] >= 7:
            label_parts.append(
                f'<text x="{node["x"] + radius + 4:.1f}" y="{node["y"] + 4:.1f}">{html.escape(str(node["name"]))}</text>'
            )

    return f"""
<svg viewBox="0 0 {width} {height}" role="img" aria-label="コラボ候補ネットワーク">
  <rect width="{width}" height="{height}" fill="#ffffff"/>
  <text x="48" y="42" class="area-label">にじさんじ</text>
  <text x="{width - 205}" y="42" class="area-label">ホロライブ</text>
  <g>{''.join(edge_parts)}</g>
  <g>{''.join(node_parts)}</g>
  <g>{''.join(label_parts)}</g>
</svg>
"""


def metric_bar(label: str, value: float, max_value: float, color: str, value_text: str) -> str:
    width = 0 if max_value <= 0 else max(2, min(100, value / max_value * 100))
    return f"""
<div class="metric-row">
  <div class="metric-label">{html.escape(label)}</div>
  <div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%; background:{color};"></div></div>
  <div class="metric-value">{html.escape(value_text)}</div>
</div>
"""


def diverging_bar(label: str, value: float, max_abs_value: float, color: str, value_text: str) -> str:
    width = 0 if max_abs_value <= 0 else min(50, abs(value) / max_abs_value * 50)
    left = 50 if value >= 0 else 50 - width
    fill = color if value >= 0 else "#dc2626"
    return f"""
<div class="uplift-row">
  <div class="metric-label">{html.escape(label)}</div>
  <div class="diverging-track">
    <div class="zero-axis"></div>
    <div class="diverging-fill" style="left:{left:.1f}%; width:{width:.1f}%; background:{fill};"></div>
  </div>
  <div class="metric-value">{html.escape(value_text)}</div>
</div>
"""


def genre_hierarchy(rows: list[dict[str, Any]]) -> str:
    max_share = max((float(row["collab_share"] or 0) for row in rows), default=0.0)
    tiles = []
    for genre in GENRE_ORDER:
        niji = genre_row(rows, "nijisanji", genre)
        holo = genre_row(rows, "hololive", genre)
        bars = "".join(
            [
                metric_bar(
                    "にじさんじ",
                    float(niji.get("collab_share", 0) or 0),
                    max_share,
                    org_color("nijisanji"),
                    pct(niji.get("collab_share", 0) or 0),
                ),
                metric_bar(
                    "ホロライブ",
                    float(holo.get("collab_share", 0) or 0),
                    max_share,
                    org_color("hololive"),
                    pct(holo.get("collab_share", 0) or 0),
                ),
            ]
        )
        details = "".join(
            [
                f'<div><strong>にじさんじ</strong><span>{fmt_int(niji.get("videos", 0))}本 / 横断 {pct(niji.get("cross_org_share", 0) or 0)}</span></div>',
                f'<div><strong>ホロライブ</strong><span>{fmt_int(holo.get("videos", 0))}本 / 横断 {pct(holo.get("cross_org_share", 0) or 0)}</span></div>',
            ]
        )
        tiles.append(
            f"""
<article class="genre-tile">
  <h3>{html.escape(genre_label(genre))}</h3>
  {bars}
  <div class="mini-stats">{details}</div>
</article>
"""
        )
    return '<div class="genre-grid">' + "".join(tiles) + "</div>"


def genre_uplift_cards(rows: list[dict[str, Any]]) -> str:
    median_values = [
        math.expm1(float(row.get("median_collab_log_view_uplift", 0) or 0))
        for row in rows
    ]
    max_abs = max((abs(value) for value in median_values), default=0.01)
    tiles = []
    for genre in GENRE_ORDER:
        niji = genre_row(rows, "nijisanji", genre)
        holo = genre_row(rows, "hololive", genre)
        niji_median = math.expm1(float(niji.get("median_collab_log_view_uplift", 0) or 0))
        holo_median = math.expm1(float(holo.get("median_collab_log_view_uplift", 0) or 0))
        bars = "".join(
            [
                diverging_bar(
                    "にじさんじ",
                    niji_median,
                    max_abs,
                    org_color("nijisanji"),
                    signed_pct_from_log(niji.get("median_collab_log_view_uplift", 0) or 0),
                ),
                diverging_bar(
                    "ホロライブ",
                    holo_median,
                    max_abs,
                    org_color("hololive"),
                    signed_pct_from_log(holo.get("median_collab_log_view_uplift", 0) or 0),
                ),
            ]
        )
        details = "".join(
            [
                f'<div><strong>にじさんじ</strong><span>比較 {fmt_int(niji.get("comparable_talents", 0))}人 / 日次 {signed_pct_from_log(niji.get("median_collab_log_view_per_day_uplift", 0) or 0)}</span></div>',
                f'<div><strong>ホロライブ</strong><span>比較 {fmt_int(holo.get("comparable_talents", 0))}人 / 日次 {signed_pct_from_log(holo.get("median_collab_log_view_per_day_uplift", 0) or 0)}</span></div>',
            ]
        )
        tiles.append(
            f"""
<article class="genre-tile">
  <h3>{html.escape(genre_label(genre))}</h3>
  {bars}
  <div class="mini-stats">{details}</div>
</article>
"""
        )
    return '<div class="genre-grid">' + "".join(tiles) + "</div>"


def render_rows(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    body = []
    for row in rows:
        cells = []
        for key, _ in columns:
            value = row.get(key, "")
            if key in {"org", "src_org", "dst_org"}:
                value = org_label(value)
            elif key == "genre":
                value = genre_label(value)
            elif key in {"collab_share", "cross_org_share"}:
                value = pct(value)
            elif key in {
                "avg_collab_log_view_uplift",
                "median_collab_log_view_uplift",
                "avg_collab_log_view_per_day_uplift",
                "median_collab_log_view_per_day_uplift",
                "collab_median_relative_log_views",
                "solo_median_relative_log_views",
                "collab_median_relative_log_views_per_day",
                "solo_median_relative_log_views_per_day",
            }:
                value = signed_pct_from_log(value)
            elif key in {"videos", "collab_videos", "cross_org_videos", "directed_edges", "weighted_video_count", "video_count"}:
                value = fmt_int(value)
            elif key == "avg_video_count":
                value = f"{float(value):.3f}"
            elif key == "sample_title":
                value = clipped(value)
            elif key == "sample_video_url":
                value = f'<a href="{html.escape(str(value))}">動画</a>'
                cells.append(f"<td>{value}</td>")
                continue
            cells.append(f"<td>{html.escape(str(value))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    header = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_html(
    *,
    scope_label: str,
    supply: list[dict[str, Any]],
    uplift: list[dict[str, Any]],
    genre_summary: list[dict[str, Any]],
    genre_uplift: list[dict[str, Any]],
    matrix: list[dict[str, Any]],
    top_cross: list[dict[str, Any]],
    top_owners: list[dict[str, Any]],
    top_genre_edges: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    output: Path,
) -> None:
    niji_supply = row_for(supply, "org", "nijisanji")
    holo_supply = row_for(supply, "org", "hololive")
    niji_uplift = row_for(uplift, "org", "nijisanji")
    holo_uplift = row_for(uplift, "org", "hololive")
    niji_share = float(niji_supply["collab_share"])
    holo_share = float(holo_supply["collab_share"])
    niji_uplift_log = float(niji_uplift["median_collab_log_view_uplift"])
    holo_uplift_log = float(holo_uplift["median_collab_log_view_uplift"])
    max_share = max(niji_share, holo_share)
    max_uplift = max(math.expm1(niji_uplift_log), math.expm1(holo_uplift_log))
    cross_edges = sum(1 for edge in edges if edge["cross_org"])
    niji_game = genre_row(genre_summary, "nijisanji", "ゲーム")
    holo_game = genre_row(genre_summary, "hololive", "ゲーム")
    niji_song = genre_row(genre_summary, "nijisanji", "歌")
    holo_song = genre_row(genre_summary, "hololive", "歌")

    supply_bars = "".join(
        [
            metric_bar("にじさんじ", niji_share, max_share, org_color("nijisanji"), pct(niji_share)),
            metric_bar("ホロライブ", holo_share, max_share, org_color("hololive"), pct(holo_share)),
        ]
    )
    uplift_bars = "".join(
        [
            metric_bar("にじさんじ", max(0, math.expm1(niji_uplift_log)), max_uplift, org_color("nijisanji"), signed_pct_from_log(niji_uplift_log)),
            metric_bar("ホロライブ", max(0, math.expm1(holo_uplift_log)), max_uplift, org_color("hololive"), signed_pct_from_log(holo_uplift_log)),
        ]
    )
    network = network_svg(nodes, edges)
    genre_cards = genre_hierarchy(genre_summary)
    genre_uplift_cards_html = genre_uplift_cards(genre_uplift)

    genre_summary_table = render_rows(
        genre_summary,
        [
            ("org", "組織"),
            ("genre", "ジャンル"),
            ("videos", "動画行数"),
            ("collab_videos", "コラボ候補"),
            ("collab_share", "コラボ率"),
            ("cross_org_videos", "横断候補"),
            ("cross_org_share", "横断率"),
            ("collab_median_relative_log_views", "コラボ中央値(概算%)"),
            ("solo_median_relative_log_views", "単体中央値(概算%)"),
        ],
    )
    genre_uplift_table = render_rows(
        genre_uplift,
        [
            ("org", "組織"),
            ("genre", "ジャンル"),
            ("comparable_talents", "比較可能人数"),
            ("avg_collab_log_view_uplift", "平均上振れ"),
            ("median_collab_log_view_uplift", "中央値上振れ"),
            ("positive_view_uplift_talents", "プラス人数"),
            ("median_collab_log_view_per_day_uplift", "日次中央値"),
        ],
    )

    matrix_table = render_rows(
        matrix,
        [
            ("src_org", "投稿者側"),
            ("dst_org", "言及先"),
            ("directed_edges", "edge数"),
            ("weighted_video_count", "動画数重み"),
            ("avg_video_count", "平均動画数"),
        ],
    )
    cross_table = render_rows(
        top_cross,
        [
            ("owner_name", "投稿者"),
            ("collaborator_name", "言及先"),
            ("video_count", "動画数"),
            ("sample_video_url", "URL"),
            ("sample_title", "サンプル動画"),
        ],
    )
    owner_table = render_rows(
        top_owners,
        [
            ("org", "組織"),
            ("owner_name", "ライバー"),
            ("videos", "動画行数"),
            ("collab_videos", "コラボ候補"),
            ("collab_share", "コラボ率"),
            ("unique_collaborators", "相手人数"),
        ],
    )
    genre_edges_table = render_rows(
        top_genre_edges,
        [
            ("genre", "ジャンル"),
            ("src_org", "投稿者側"),
            ("owner_name", "投稿者"),
            ("dst_org", "言及先側"),
            ("collaborator_name", "言及先"),
            ("video_count", "動画数"),
            ("sample_video_url", "URL"),
            ("sample_title", "サンプル動画"),
        ],
    )

    page = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>にじさんじ / ホロライブ コラボ仮説ダッシュボード</title>
  <style>
    :root {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #172033;
      background: #f6f8fb;
    }}
    body {{ margin: 0; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 28px; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; letter-spacing: 0; }}
    h2 {{ margin: 26px 0 10px; font-size: 18px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 12px; font-size: 15px; letter-spacing: 0; }}
    p {{ margin: 0 0 14px; color: #506176; line-height: 1.65; }}
    code {{ background: #eef2f7; padding: 1px 5px; border-radius: 5px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 18px 0; }}
    .card, .panel {{ background: #fff; border: 1px solid #dce4ef; border-radius: 8px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }}
    .card {{ padding: 14px; }}
    .card .label {{ color: #65758b; font-size: 12px; }}
    .card .value {{ margin-top: 6px; font-size: 25px; font-weight: 700; }}
    .card .note {{ margin-top: 5px; color: #64748b; font-size: 12px; line-height: 1.45; }}
    .panel {{ padding: 16px; margin-top: 14px; }}
    .finding {{ display: grid; grid-template-columns: 130px 1fr; gap: 12px; padding: 12px 0; border-top: 1px solid #edf2f7; }}
    .finding:first-child {{ border-top: 0; }}
    .badge {{ display: inline-flex; align-items: center; justify-content: center; border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 700; background: #eef2ff; color: #1d4ed8; }}
    .metric-row {{ display: grid; grid-template-columns: 96px 1fr 82px; gap: 10px; align-items: center; margin: 10px 0; }}
    .metric-label {{ font-size: 13px; color: #334155; }}
    .metric-value {{ font-variant-numeric: tabular-nums; text-align: right; font-weight: 700; }}
    .bar-track {{ height: 13px; background: #e8eef6; border-radius: 999px; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 999px; }}
    .columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    .block {{ margin-top: 26px; }}
    .genre-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 14px 0; }}
    .genre-tile {{ background: #fff; border: 1px solid #dce4ef; border-radius: 8px; padding: 14px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }}
    .genre-tile .metric-row {{ grid-template-columns: 86px 1fr 70px; }}
    .uplift-row {{ display: grid; grid-template-columns: 86px 1fr 74px; gap: 10px; align-items: center; margin: 10px 0; }}
    .diverging-track {{ position: relative; height: 13px; background: #e8eef6; border-radius: 999px; overflow: hidden; }}
    .zero-axis {{ position: absolute; left: 50%; top: 0; width: 1px; height: 100%; background: #94a3b8; }}
    .diverging-fill {{ position: absolute; top: 0; height: 100%; border-radius: 999px; }}
    .mini-stats {{ display: grid; gap: 7px; margin-top: 12px; padding-top: 11px; border-top: 1px solid #edf2f7; color: #506176; font-size: 12px; }}
    .mini-stats div {{ display: flex; justify-content: space-between; gap: 10px; }}
    .table-scroll {{ overflow-x: auto; margin: 10px 0 16px; }}
    .viz {{ background: #fff; border: 1px solid #dce4ef; border-radius: 8px; overflow: auto; }}
    svg {{ display: block; width: 100%; min-width: 960px; height: auto; }}
    text {{ font-size: 11px; paint-order: stroke; stroke: #fff; stroke-width: 3px; fill: #162033; }}
    .area-label {{ font-size: 16px; font-weight: 700; fill: #64748b; stroke-width: 0; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #dce4ef; border-radius: 8px; overflow: hidden; }}
    th, td {{ text-align: left; padding: 8px 9px; border-bottom: 1px solid #e8eef6; font-size: 13px; vertical-align: top; }}
    th {{ background: #f1f5f9; color: #334155; }}
    a {{ color: #1d4ed8; text-decoration: none; }}
    .legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 10px 0 14px; color: #506176; font-size: 13px; }}
    .swatch {{ display: inline-block; width: 12px; height: 12px; border-radius: 999px; vertical-align: -1px; margin-right: 5px; }}
    @media (max-width: 880px) {{
      main {{ padding: 18px; }}
      .grid, .columns, .genre-grid {{ grid-template-columns: 1fr; }}
      .finding {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>にじさんじ / ホロライブ コラボ仮説ダッシュボード</h1>
  <p>BigQuery Graph <code>jackojacko05.nijiholo.youtube_collab_graph</code> と動画特徴量から作った暫定可視化です。対象期間は{html.escape(scope_label)}。概要欄の既知チャンネルID / @handle を使った「コラボ候補」なので、実コラボ確定ではなく分析の入口として見ます。</p>

  <div class="grid">
    <div class="card"><div class="label">にじさんじ コラボ率</div><div class="value">{pct(niji_share)}</div><div class="note">{html.escape(scope_label)}の owner-video 行。</div></div>
    <div class="card"><div class="label">ホロライブ コラボ率</div><div class="value">{pct(holo_share)}</div><div class="note">供給量はほぼ同水準。</div></div>
    <div class="card"><div class="label">にじさんじ 需要上振れ</div><div class="value">{signed_pct_from_log(niji_uplift_log)}</div><div class="note">同一ライバー内の中央値差を概算%化。</div></div>
    <div class="card"><div class="label">表示ネットワーク</div><div class="value">{len(nodes)} nodes</div><div class="note">{len(edges)} edges / 横断 {cross_edges} edges。</div></div>
  </div>

  <section class="panel">
    <h2>まず読むところ</h2>
    <div class="finding"><div><span class="badge">供給</span></div><div>コラボ率は、にじさんじ {pct(niji_share)}、ホロライブ {pct(holo_share)}。この定義では「にじさんじの方がコラボが多い」とはまだ言いにくいです。</div></div>
    <div class="finding"><div><span class="badge">需要</span></div><div>チャンネル内中央値で補正した相対再生数では、にじさんじのコラボ動画上振れが {signed_pct_from_log(niji_uplift_log)}、ホロライブが {signed_pct_from_log(holo_uplift_log)}。需要側はにじさんじコラボ優位っぽく見えます。</div></div>
    <div class="finding"><div><span class="badge">ジャンル</span></div><div>ゲームのコラボ率は、にじさんじ {pct(niji_game.get("collab_share", 0) or 0)}、ホロライブ {pct(holo_game.get("collab_share", 0) or 0)}。歌は、にじさんじ {pct(niji_song.get("collab_share", 0) or 0)}、ホロライブ {pct(holo_song.get("collab_share", 0) or 0)}。供給差はジャンルでかなり表情が変わります。</div></div>
    <div class="finding"><div><span class="badge">横断</span></div><div>にじホロ横断edgeは全体では少数。大型企画・歌ってみた・イベント参加で局所的に出ます。</div></div>
  </section>

  <section class="columns">
    <div class="panel">
      <h2>コラボ供給率</h2>
      {supply_bars}
    </div>
    <div class="panel">
      <h2>コラボ動画の需要上振れ</h2>
      {uplift_bars}
    </div>
  </section>

  <section class="block">
    <h2>階層別: 組織 × ジャンル × コラボ</h2>
    <p>ジャンルはタイトルのルールベース分類です。歌系を先に判定し、その後ゲーム系、それ以外をその他にしています。</p>
    {genre_cards}
    <div class="table-scroll">{genre_summary_table}</div>

    <h2>ジャンル別の需要上振れ</h2>
    <p>同じライバー・同じジャンル内で、コラボ候補あり動画が単体/未検出動画よりどれだけ上振れたかを見ます。</p>
    {genre_uplift_cards_html}
    <div class="table-scroll">{genre_uplift_table}</div>
  </section>

  <section>
    <h2>コラボ候補ネットワーク</h2>
    <p>上位の同組織edgeと横断edgeを抜粋。青がにじさんじ、水色がホロライブ、オレンジ線がにじホロ横断です。線が太いほど、その投稿者の対象期間内動画で同じ相手が概要欄に出た回数が多いです。</p>
    <div class="legend">
      <span><span class="swatch" style="background:#2563eb"></span>にじさんじ</span>
      <span><span class="swatch" style="background:#06b6d4"></span>ホロライブ</span>
      <span><span class="swatch" style="background:#f97316"></span>にじホロ横断edge</span>
    </div>
    <div class="viz">{network}</div>
  </section>

  <section>
    <h2>組織間edgeマトリクス</h2>
    {matrix_table}
  </section>

  <section>
    <h2>コラボ候補率が高いライバー</h2>
    {owner_table}
  </section>

  <section>
    <h2>ジャンル別edge上位</h2>
    <div class="table-scroll">{genre_edges_table}</div>
  </section>

  <section>
    <h2>にじホロ横断edge上位</h2>
    {cross_table}
  </section>
</main>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="jackojacko05")
    parser.add_argument("--location", default="asia-northeast1")
    parser.add_argument("--scope-label", default=f"2025-06-01から{TODAY}まで")
    parser.add_argument("--output", type=Path, default=REPORTS_DIR / f"youtube_collab_graph_2025-06-01_to_{TODAY}.html")
    args = parser.parse_args()

    network_edges = bq_query(NETWORK_SQL, args.project, args.location)
    supply = bq_query(ORG_SUPPLY_SQL, args.project, args.location)
    uplift = bq_query(OWNER_UPLIFT_SQL, args.project, args.location)
    genre_summary = bq_query(GENRE_SUMMARY_SQL, args.project, args.location)
    genre_uplift = bq_query(GENRE_UPLIFT_SQL, args.project, args.location)
    matrix = bq_query(EDGE_MATRIX_SQL, args.project, args.location)
    top_cross = bq_query(TOP_CROSS_SQL, args.project, args.location)
    top_owners = bq_query(TOP_OWNERS_SQL, args.project, args.location)
    top_genre_edges = bq_query(TOP_GENRE_EDGES_SQL, args.project, args.location)

    nodes, edges = build_graph(network_edges)
    layout(nodes, edges, width=1180, height=680)
    render_html(
        scope_label=args.scope_label,
        supply=supply,
        uplift=uplift,
        genre_summary=genre_summary,
        genre_uplift=genre_uplift,
        matrix=matrix,
        top_cross=top_cross,
        top_owners=top_owners,
        top_genre_edges=top_genre_edges,
        nodes=nodes,
        edges=edges,
        output=args.output,
    )
    print(f"nodes: {len(nodes)}")
    print(f"edges: {len(edges)}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
