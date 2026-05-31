#!/usr/bin/env python3
"""Generate a rough collaboration hypothesis report from BigQuery tables."""

from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import subprocess
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = BASE_DIR / "reports"
TODAY = date.today().isoformat()
GENRE_ORDER = ("ゲーム", "歌", "その他")


QUERIES = {
    "scope": r"""
SELECT
  COUNT(*) AS owner_video_rows,
  COUNT(DISTINCT video_id) AS unique_videos,
  COUNT(DISTINCT owner_talent_id) AS talents,
  COUNTIF(collab_flag) AS collab_video_rows,
  COUNTIF(cross_org_collab_flag) AS cross_org_video_rows
FROM `jackojacko05.nijiholo.youtube_video_features`
""",
    "org_supply": r"""
SELECT
  owner_org AS org,
  COUNT(DISTINCT owner_talent_id) AS talents,
  COUNT(*) AS owner_video_rows,
  COUNTIF(collab_flag) AS collab_video_rows,
  ROUND(SAFE_DIVIDE(COUNTIF(collab_flag), COUNT(*)), 4) AS collab_share,
  ROUND(AVG(collab_count), 4) AS avg_collab_count,
  COUNTIF(cross_org_collab_flag) AS cross_org_video_rows,
  ROUND(SAFE_DIVIDE(COUNTIF(cross_org_collab_flag), COUNT(*)), 4) AS cross_org_share
FROM `jackojacko05.nijiholo.youtube_video_features`
GROUP BY owner_org
ORDER BY org
""",
    "video_demand": r"""
SELECT
  owner_org AS org,
  collab_flag,
  COUNT(*) AS videos,
  ROUND(AVG(relative_log_views), 4) AS avg_relative_log_views,
  ROUND(APPROX_QUANTILES(relative_log_views, 101)[OFFSET(50)], 4) AS median_relative_log_views,
  ROUND(AVG(relative_log_views_per_day), 4) AS avg_relative_log_views_per_day,
  ROUND(APPROX_QUANTILES(relative_log_views_per_day, 101)[OFFSET(50)], 4) AS median_relative_log_views_per_day,
  ROUND(AVG(relative_like_rate), 6) AS avg_relative_like_rate,
  ROUND(AVG(relative_comment_rate), 6) AS avg_relative_comment_rate
FROM `jackojacko05.nijiholo.youtube_video_features`
GROUP BY owner_org, collab_flag
ORDER BY owner_org, collab_flag
""",
    "genre_summary": r"""
SELECT
  owner_org AS org,
  content_genre AS genre,
  COUNT(*) AS videos,
  COUNTIF(collab_flag) AS collab_videos,
  ROUND(SAFE_DIVIDE(COUNTIF(collab_flag), COUNT(*)), 4) AS collab_share,
  COUNTIF(cross_org_collab_flag) AS cross_org_videos,
  ROUND(SAFE_DIVIDE(COUNTIF(cross_org_collab_flag), COUNT(*)), 4) AS cross_org_share,
  ROUND(APPROX_QUANTILES(IF(collab_flag, relative_log_views, NULL), 101 IGNORE NULLS)[OFFSET(50)], 4) AS collab_median_relative_log_views,
  ROUND(APPROX_QUANTILES(IF(NOT collab_flag, relative_log_views, NULL), 101 IGNORE NULLS)[OFFSET(50)], 4) AS solo_median_relative_log_views,
  ROUND(APPROX_QUANTILES(IF(collab_flag, relative_log_views_per_day, NULL), 101 IGNORE NULLS)[OFFSET(50)], 4) AS collab_median_relative_log_views_per_day,
  ROUND(APPROX_QUANTILES(IF(NOT collab_flag, relative_log_views_per_day, NULL), 101 IGNORE NULLS)[OFFSET(50)], 4) AS solo_median_relative_log_views_per_day
FROM `jackojacko05.nijiholo.youtube_video_features`
GROUP BY owner_org, content_genre
ORDER BY
  owner_org,
  CASE content_genre WHEN 'ゲーム' THEN 1 WHEN '歌' THEN 2 ELSE 3 END
""",
    "genre_uplift": r"""
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
  ROUND(AVG(collab_log_view_uplift), 4) AS avg_collab_log_view_uplift,
  ROUND(APPROX_QUANTILES(collab_log_view_uplift, 101)[OFFSET(50)], 4) AS median_collab_log_view_uplift,
  COUNTIF(collab_log_view_uplift > 0) AS positive_view_uplift_talents,
  ROUND(AVG(collab_log_view_per_day_uplift), 4) AS avg_collab_log_view_per_day_uplift,
  ROUND(APPROX_QUANTILES(collab_log_view_per_day_uplift, 101)[OFFSET(50)], 4) AS median_collab_log_view_per_day_uplift
FROM pairs
GROUP BY owner_org, genre
ORDER BY
  owner_org,
  CASE genre WHEN 'ゲーム' THEN 1 WHEN '歌' THEN 2 ELSE 3 END
""",
    "owner_uplift": r"""
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
  ROUND(AVG(collab_log_view_uplift), 4) AS avg_collab_log_view_uplift,
  ROUND(APPROX_QUANTILES(collab_log_view_uplift, 101)[OFFSET(50)], 4) AS median_collab_log_view_uplift,
  COUNTIF(collab_log_view_uplift > 0) AS positive_view_uplift_talents,
  ROUND(AVG(collab_log_view_per_day_uplift), 4) AS avg_collab_log_view_per_day_uplift,
  ROUND(APPROX_QUANTILES(collab_log_view_per_day_uplift, 101)[OFFSET(50)], 4) AS median_collab_log_view_per_day_uplift
FROM pairs
GROUP BY owner_org
ORDER BY org
""",
    "top_owner_collab_share": r"""
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
    ROUND(SAFE_DIVIDE(COUNTIF(collab_flag), COUNT(*)), 4) AS collab_share
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
LIMIT 15
""",
    "edge_org_matrix": r"""
SELECT
  src_org,
  dst_org,
  COUNT(*) AS directed_edges,
  SUM(video_count) AS weighted_video_count,
  ROUND(AVG(video_count), 3) AS avg_video_count
FROM `jackojacko05.nijiholo.youtube_collab_edges_graph`
GROUP BY src_org, dst_org
ORDER BY src_org, dst_org
""",
    "top_cross_edges": r"""
SELECT
  src_character_name AS owner_name,
  dst_character_name AS collaborator_name,
  video_count,
  sample_video_url,
  sample_title
FROM `jackojacko05.nijiholo.youtube_collab_edges_graph`
WHERE src_org != dst_org
ORDER BY video_count DESC, owner_name, collaborator_name
LIMIT 20
""",
    "top_genre_edges": r"""
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
) <= 10
ORDER BY
  CASE content_genre WHEN 'ゲーム' THEN 1 WHEN '歌' THEN 2 ELSE 3 END,
  video_count DESC,
  owner_name,
  collaborator_name
""",
}


def bq_query(name: str, sql: str, project: str, location: str) -> list[dict[str, Any]]:
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
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse bq JSON for {name}: {result.stdout[:500]}") from exc


ORG_LABELS = {
    "nijisanji": "にじさんじ",
    "hololive": "ホロライブ",
}


def org_label(value: Any) -> str:
    return ORG_LABELS.get(str(value), str(value))


def pct(value: float) -> str:
    return f"{value:.1%}"


def log_uplift_pct(value: float) -> str:
    return f"{math.expm1(value):+.1%}"


def format_cell(key: str, value: Any) -> str:
    if value is None:
        return ""
    if key in {"org", "src_org", "dst_org"}:
        return org_label(value)
    if key == "genre":
        return str(value)
    if key == "collab_flag":
        return "コラボ候補あり" if str(value).lower() == "true" else "ソロ/未検出"
    if key in {"collab_share", "cross_org_share", "video_share"}:
        return pct(float(value))
    if key.endswith("uplift"):
        return log_uplift_pct(float(value))
    if key in {
        "avg_relative_log_views",
        "median_relative_log_views",
        "avg_relative_log_views_per_day",
        "median_relative_log_views_per_day",
        "collab_median_relative_log_views",
        "solo_median_relative_log_views",
        "collab_median_relative_log_views_per_day",
        "solo_median_relative_log_views_per_day",
    }:
        return f"{float(value):+.3f}"
    if key in {"avg_video_count"}:
        return f"{float(value):.3f}"
    if key in {"avg_relative_like_rate", "avg_relative_comment_rate"}:
        return f"{float(value):+.5f}"
    return str(value)


def md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_該当行なし。_\n"
    lines = [
        "| " + " | ".join(label for _, label in columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        values = []
        for key, _ in columns:
            value = format_cell(key, row.get(key, ""))
            value = value.replace("\n", " ").replace("|", "\\|")
            values.append(value)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def scalar(rows: list[dict[str, Any]], key: str) -> str:
    return str(rows[0][key]) if rows else ""


def org_value(rows: list[dict[str, Any]], org: str, key: str) -> float:
    for row in rows:
        if row.get("org") == org:
            return float(row[key])
    return float("nan")


def genre_org_value(rows: list[dict[str, Any]], org: str, genre: str, key: str) -> float:
    for row in rows:
        if row.get("org") == org and row.get("genre") == genre:
            return float(row[key])
    return float("nan")


def genre_uplift_read(rows: list[dict[str, Any]]) -> list[str]:
    lines = []
    for genre in GENRE_ORDER:
        niji = genre_org_value(rows, "nijisanji", genre, "median_collab_log_view_uplift")
        holo = genre_org_value(rows, "hololive", genre, "median_collab_log_view_uplift")
        niji_day = genre_org_value(rows, "nijisanji", genre, "median_collab_log_view_per_day_uplift")
        holo_day = genre_org_value(rows, "hololive", genre, "median_collab_log_view_per_day_uplift")
        lines.append(
            f"- {genre}: 中央値上振れは、にじさんじ {log_uplift_pct(niji)}、ホロライブ {log_uplift_pct(holo)}。日次補正では、にじさんじ {log_uplift_pct(niji_day)}、ホロライブ {log_uplift_pct(holo_day)}。"
        )
    return lines


def render_report(results: dict[str, list[dict[str, Any]]], output: Path) -> None:
    scope = results["scope"]
    org_supply = results["org_supply"]
    video_demand = results["video_demand"]
    owner_uplift = results["owner_uplift"]

    niji_collab_share = org_value(org_supply, "nijisanji", "collab_share")
    holo_collab_share = org_value(org_supply, "hololive", "collab_share")
    niji_uplift = org_value(owner_uplift, "nijisanji", "median_collab_log_view_uplift")
    holo_uplift = org_value(owner_uplift, "hololive", "median_collab_log_view_uplift")

    rough_read = []
    diff = niji_collab_share - holo_collab_share
    if abs(diff) < 0.01:
        rough_read.append(
            f"- 供給面では、にじさんじ {niji_collab_share:.1%}、ホロライブ {holo_collab_share:.1%} でほぼ同水準。少なくともこの定義では「にじさんじの方がコラボ率が高い」はまだ支持しにくい。"
        )
    elif diff > 0:
        rough_read.append(
            f"- 供給面では、にじさんじのコラボ動画率が {niji_collab_share:.1%}、ホロライブが {holo_collab_share:.1%} で、仮説と同じ向き。"
        )
    else:
        rough_read.append(
            f"- 供給面では、ホロライブのコラボ動画率が {holo_collab_share:.1%}、にじさんじが {niji_collab_share:.1%} で、仮説と逆向き。"
        )
    rough_read.append(
        f"- 需要面の雑な中央値上振れは、にじさんじ {niji_uplift:+.3f}（概算 {log_uplift_pct(niji_uplift)}）、ホロライブ {holo_uplift:+.3f}（概算 {log_uplift_pct(holo_uplift)}）。正なら同一チャンネル内でコラボ動画が相対的に強い。"
    )
    rough_read.append(
        "- ただし概要欄リンク由来なので、定型リンク・企画告知・参加者一覧を完全には分離できていない。これは候補グラフとして読む。"
    )

    lines = [
        f"# にじさんじ / ホロライブ コラボ仮説 粗い検証レポート（{TODAY}）",
        "",
        "## 結論（暫定）",
        "",
        *rough_read,
        "",
        "## 仮説別の見立て",
        "",
        "| 仮説 | 暫定判定 | 読み方 |",
        "| --- | --- | --- |",
        "| にじさんじはコラボが多い | 保留 | 現在の検出定義では、動画行ベースのコラボ率はほぼ同水準。 |",
        "| にじさんじはコラボ需要が大きい | やや支持 | チャンネル内中央値で補正した相対再生数では、にじさんじのコラボ動画が上振れしやすい。 |",
        "| ホロライブは単体需要が強い | 弱い支持または保留 | ホロもコラボ動画はややプラスだが、にじさんじほど大きくない。単体優位とまではまだ言い切れない。 |",
        "",
        "## 使ったデータ",
        "",
        md_table(
            scope,
            [
                ("owner_video_rows", "動画行数"),
                ("unique_videos", "ユニーク動画数"),
                ("talents", "対象ライバー数"),
                ("collab_video_rows", "コラボ候補あり動画行"),
                ("cross_org_video_rows", "にじホロ横断候補動画行"),
            ],
        ),
        "",
        "## 1. 供給: 組織別のコラボ動画率",
        "",
        "概要欄に既知チャンネルIDまたは `@handle` が出た動画を、コラボ候補ありとして数えています。",
        "",
        md_table(
            org_supply,
            [
                ("org", "組織"),
                ("talents", "ライバー数"),
                ("owner_video_rows", "動画行数"),
                ("collab_video_rows", "コラボ候補あり"),
                ("collab_share", "コラボ率"),
                ("avg_collab_count", "平均共演候補数"),
                ("cross_org_video_rows", "横断候補あり"),
                ("cross_org_share", "横断率"),
            ],
        ),
        "",
        "読み: コラボ率は 12% 台でほぼ横並び。人数規模の違いをならして見ると、供給量だけで仮説を押し切るのは難しそうです。",
        "",
        "## 2. 階層別: 組織 × ジャンル × コラボ",
        "",
        "ジャンルはタイトルのルールベース分類です。歌系を先に判定し、その後ゲーム系、それ以外をその他にしています。",
        "",
        md_table(
            results["genre_summary"],
            [
                ("org", "組織"),
                ("genre", "ジャンル"),
                ("videos", "動画行数"),
                ("collab_videos", "コラボ候補あり"),
                ("collab_share", "コラボ率"),
                ("cross_org_videos", "横断候補あり"),
                ("cross_org_share", "横断率"),
                ("collab_median_relative_log_views", "コラボ中央値 相対log再生"),
                ("solo_median_relative_log_views", "単体中央値 相対log再生"),
                ("collab_median_relative_log_views_per_day", "コラボ中央値 日次"),
                ("solo_median_relative_log_views_per_day", "単体中央値 日次"),
            ],
        ),
        "",
        "読み: ゲームでは両組織ともコラボ率が高く、特にホロライブもかなりコラボ寄りに出ます。歌はホロライブの動画数が多い一方、コラボ率はゲームほど高くありません。",
        "",
        "## 3. ジャンル別: ライバー単位のコラボ上振れ",
        "",
        "同じライバー・同じジャンル内で、コラボ候補あり動画と単体/未検出動画の平均差を見ています。",
        "",
        md_table(
            results["genre_uplift"],
            [
                ("org", "組織"),
                ("genre", "ジャンル"),
                ("comparable_talents", "比較可能ライバー数"),
                ("avg_collab_log_view_uplift", "平均 上振れ"),
                ("median_collab_log_view_uplift", "中央値 上振れ"),
                ("positive_view_uplift_talents", "上振れプラス人数"),
                ("avg_collab_log_view_per_day_uplift", "平均 日次上振れ"),
                ("median_collab_log_view_per_day_uplift", "中央値 日次上振れ"),
            ],
        ),
        "",
        "読み: ここが一番見る価値があります。全体で見えた差が、ゲーム・歌・その他のどこから来ているかを分解できます。",
        "",
        *genre_uplift_read(results["genre_uplift"]),
        "",
        "## 4. 需要の代替指標: 同一チャンネル内の相対パフォーマンス",
        "",
        "`relative_log_views` は、各チャンネルの中央値を引いた相対値です。生の再生数ではなく、同じライバーの通常動画と比べて上振れたかを見るための雑な補正です。",
        "",
        md_table(
            video_demand,
            [
                ("org", "組織"),
                ("collab_flag", "分類"),
                ("videos", "動画行数"),
                ("avg_relative_log_views", "平均 相対log再生"),
                ("median_relative_log_views", "中央値 相対log再生"),
                ("avg_relative_log_views_per_day", "平均 相対log日次再生"),
                ("median_relative_log_views_per_day", "中央値 相対log日次再生"),
                ("avg_relative_like_rate", "平均 相対like率"),
                ("avg_relative_comment_rate", "平均 相対comment率"),
            ],
        ),
        "",
        "読み: にじさんじはコラボ候補あり動画の相対再生数が明確に上振れ。ホロライブはプラスだが小さい。日次補正ではホロの中央値が少し弱く出ます。",
        "",
        "## 5. ライバー単位のコラボ上振れ",
        "",
        "コラボ候補あり動画が3本以上、ソロ/未検出動画が20本以上あるライバーだけで、同一ライバー内の平均差を見ています。",
        "",
        md_table(
            owner_uplift,
            [
                ("org", "組織"),
                ("comparable_talents", "比較可能ライバー数"),
                ("avg_collab_log_view_uplift", "平均 上振れ"),
                ("median_collab_log_view_uplift", "中央値 上振れ"),
                ("positive_view_uplift_talents", "上振れプラス人数"),
                ("avg_collab_log_view_per_day_uplift", "平均 日次上振れ"),
                ("median_collab_log_view_per_day_uplift", "中央値 日次上振れ"),
            ],
        ),
        "",
        "読み: 中央値で見ると、にじさんじの上振れがホロライブより大きい。ここは「コラボへの需要がにじさんじ側で強い」仮説と同じ向きです。",
        "",
        "## 6. コラボ候補率が高いライバー",
        "",
        md_table(
            results["top_owner_collab_share"],
            [
                ("org", "組織"),
                ("owner_name", "ライバー"),
                ("videos", "動画行数"),
                ("collab_videos", "コラボ候補あり"),
                ("collab_share", "コラボ率"),
                ("unique_collaborators", "ユニーク共演候補数"),
            ],
        ),
        "",
        "## 7. 組織間 edge マトリクス",
        "",
        md_table(
            results["edge_org_matrix"],
            [
                ("src_org", "投稿者側"),
                ("dst_org", "概要欄で言及された側"),
                ("directed_edges", "有向edge数"),
                ("weighted_video_count", "動画数重み合計"),
                ("avg_video_count", "edgeあたり平均動画数"),
            ],
        ),
        "",
        "読み: edge数そのものは人数の多いにじさんじ内が大きい。にじホロ横断は存在するが、全体から見ると少数派です。",
        "",
        "## 8. ジャンル別 edge 上位",
        "",
        md_table(
            results["top_genre_edges"],
            [
                ("genre", "ジャンル"),
                ("src_org", "投稿者側"),
                ("owner_name", "投稿者"),
                ("dst_org", "言及先側"),
                ("collaborator_name", "言及先"),
                ("video_count", "動画数"),
                ("sample_video_url", "サンプルURL"),
                ("sample_title", "サンプル動画タイトル"),
            ],
        ),
        "",
        "## 9. にじホロ横断 edge 上位",
        "",
        md_table(
            results["top_cross_edges"],
            [
                ("owner_name", "投稿者"),
                ("collaborator_name", "言及先"),
                ("video_count", "動画数"),
                ("sample_video_url", "サンプルURL"),
                ("sample_title", "サンプル動画タイトル"),
            ],
        ),
        "",
        "## 注意点",
        "",
        "- 観察データなので、因果は言えません。コラボするかどうかはランダムではありません。",
        "- `collab_flag` は概要欄の既知チャンネルURL / `@handle` に基づく候補です。",
        "- Shorts、歌ってみた、大型企画、案件、ゲームタイトル差はまだ十分に分離していません。",
        "- 定型リンクはフィルタしていますが、完全ではありません。",
        "",
        "## 次にやるなら",
        "",
        "- タイトル中のライバー名・企画名も使ってコラボ判定を強化する。",
        "- Shorts / 歌 / ライブ / ゲーム実況を分ける。",
        "- 同じライバー、同じ公開経過日数帯、近いカテゴリ内でソロ動画とコラボ動画を比較する。",
        "- 組織差にブートストラップ信頼区間を付ける。",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="jackojacko05")
    parser.add_argument("--location", default="asia-northeast1")
    parser.add_argument("--output", type=Path, default=REPORTS_DIR / f"collab_hypothesis_rough_report_{TODAY}.md")
    args = parser.parse_args()

    results = {name: bq_query(name, sql, args.project, args.location) for name, sql in QUERIES.items()}
    render_report(results, args.output)
    print(f"output: {args.output}")
    print(f"scope_owner_video_rows: {scalar(results['scope'], 'owner_video_rows')}")


if __name__ == "__main__":
    main()
