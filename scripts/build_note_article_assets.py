#!/usr/bin/env python3
"""Generate article figures from BigQuery article_* tables as standalone SVG."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
import subprocess
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
FIGURE_DIR = BASE_DIR / "reports" / "note_figures"

ORG_LABELS = {"nijisanji": "にじさんじ", "hololive": "ホロライブ"}
ORG_COLORS = {"nijisanji": "#2563eb", "hololive": "#06b6d4"}
GENRE_ORDER = ["ゲーム", "歌", "その他"]


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


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def pct(value: float, digits: int = 1, signed: bool = False) -> str:
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value * 100:.{digits}f}%"


def fmt_int(value: Any) -> str:
    return f"{int(float(value)):,}"


def svg_page(width: int, height: int, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    .bg {{ fill: #ffffff; }}
    .title {{ font: 700 32px -apple-system, BlinkMacSystemFont, 'Hiragino Sans', 'Noto Sans JP', sans-serif; fill: #172033; }}
    .subtitle {{ font: 400 16px -apple-system, BlinkMacSystemFont, 'Hiragino Sans', 'Noto Sans JP', sans-serif; fill: #526173; }}
    .label {{ font: 600 16px -apple-system, BlinkMacSystemFont, 'Hiragino Sans', 'Noto Sans JP', sans-serif; fill: #253247; }}
    .small {{ font: 400 13px -apple-system, BlinkMacSystemFont, 'Hiragino Sans', 'Noto Sans JP', sans-serif; fill: #66758a; }}
    .value {{ font: 700 24px -apple-system, BlinkMacSystemFont, 'Hiragino Sans', 'Noto Sans JP', sans-serif; fill: #172033; }}
    .axis {{ stroke: #cbd5e1; stroke-width: 1; }}
    .panel {{ fill: #f8fafc; stroke: #dce4ef; stroke-width: 1; rx: 8; }}
    .bar-bg {{ fill: #e8eef6; rx: 7; }}
    .note {{ font: 500 14px -apple-system, BlinkMacSystemFont, 'Hiragino Sans', 'Noto Sans JP', sans-serif; fill: #334155; }}
  </style>
  <rect class="bg" width="{width}" height="{height}"/>
{body}
</svg>
"""


def bar(x: float, y: float, width: float, height: float, value: float, max_value: float, color: str) -> str:
    fill_width = 0 if max_value <= 0 else max(2, min(width, width * value / max_value))
    return f"""
  <rect class="bar-bg" x="{x}" y="{y}" width="{width}" height="{height}"/>
  <rect x="{x}" y="{y}" width="{fill_width:.1f}" height="{height}" fill="{color}" rx="{height / 2:.1f}"/>
"""


def diverging_bar(
    x: float,
    y: float,
    width: float,
    height: float,
    value: float,
    max_abs: float,
    color: str,
) -> str:
    center = x + width / 2
    fill_width = 0 if max_abs <= 0 else min(width / 2, abs(value) / max_abs * width / 2)
    fill_x = center if value >= 0 else center - fill_width
    fill = color if value >= 0 else "#dc2626"
    return f"""
  <rect class="bar-bg" x="{x}" y="{y}" width="{width}" height="{height}"/>
  <line x1="{center:.1f}" y1="{y - 3}" x2="{center:.1f}" y2="{y + height + 3}" class="axis"/>
  <rect x="{fill_x:.1f}" y="{y}" width="{fill_width:.1f}" height="{height}" fill="{fill}" rx="{height / 2:.1f}"/>
"""


def figure_supply_demand(supply: list[dict[str, Any]], uplift: list[dict[str, Any]]) -> str:
    supply_by_org = {row["org"]: row for row in supply}
    uplift_by_org = {row["org"]: row for row in uplift}
    max_supply = max(float(row["collab_share"]) for row in supply)
    max_uplift = max(float(row["median_collab_view_uplift_pct"]) for row in uplift)

    rows = []
    for org in ["nijisanji", "hololive"]:
        label = ORG_LABELS[org]
        color = ORG_COLORS[org]
        y = 185 + len(rows) * 70
        supply_value = float(supply_by_org[org]["collab_share"])
        uplift_value = float(uplift_by_org[org]["median_collab_view_uplift_pct"])
        rows.append(
            f"""
  <text class="label" x="90" y="{y + 18}">{esc(label)}</text>
  {bar(210, y, 300, 22, supply_value, max_supply, color)}
  <text class="value" x="530" y="{y + 21}">{pct(supply_value)}</text>
  {bar(720, y, 300, 22, uplift_value, max_uplift, color)}
  <text class="value" x="1040" y="{y + 21}">{pct(uplift_value, signed=True)}</text>
"""
        )

    body = f"""
  <text class="title" x="70" y="70">コラボは「供給」より「上振れ」に差が出た</text>
  <text class="subtitle" x="70" y="104">YouTube概要欄の既知チャンネル/handleから作ったコラボ候補。対象: 2025-06-01から2026-05-31まで。</text>
  <rect class="panel" x="60" y="135" width="1080" height="225"/>
  <text class="label" x="210" y="160">コラボ候補あり動画率</text>
  <text class="label" x="720" y="160">同一ライバー内のコラボ上振れ中央値</text>
  {''.join(rows)}
  <text class="note" x="90" y="325">読み: コラボ動画の比率は近い。だが、コラボ動画が通常動画より伸びる度合いはにじさんじ側が大きい。</text>
  <text class="small" x="70" y="625">source: jackojacko05.nijiholo.article_org_supply / article_owner_uplift</text>
"""
    return svg_page(1200, 675, body)


def figure_genre_uplift(rows: list[dict[str, Any]]) -> str:
    max_abs = max(abs(float(row["median_collab_view_uplift_pct"])) for row in rows)
    row_map = {(row["org"], row["genre"]): row for row in rows}
    blocks = []
    for index, genre in enumerate(GENRE_ORDER):
        y = 160 + index * 138
        blocks.append(f'<text class="label" x="80" y="{y + 28}">{esc(genre)}</text>')
        for org_index, org in enumerate(["nijisanji", "hololive"]):
            row = row_map[(org, genre)]
            value = float(row["median_collab_view_uplift_pct"])
            bar_y = y + 10 + org_index * 45
            blocks.append(f'<text class="small" x="190" y="{bar_y + 17}">{esc(ORG_LABELS[org])}</text>')
            blocks.append(diverging_bar(310, bar_y, 520, 22, value, max_abs, ORG_COLORS[org]))
            blocks.append(f'<text class="value" x="860" y="{bar_y + 22}">{pct(value, signed=True)}</text>')
            blocks.append(f'<text class="small" x="980" y="{bar_y + 19}">比較{fmt_int(row["comparable_talents"])}人</text>')
        blocks.append(f'<line class="axis" x1="80" y1="{y + 112}" x2="1120" y2="{y + 112}"/>')

    body = f"""
  <text class="title" x="70" y="70">ジャンル別に見ると、差は「歌」と「その他」で大きい</text>
  <text class="subtitle" x="70" y="104">同じライバー・同じジャンル内で、コラボ候補あり動画が通常動画よりどれだけ上振れたか。</text>
  <text class="small" x="552" y="140">0%</text>
  {''.join(blocks)}
  <text class="note" x="80" y="590">読み: ゲームは両社ともコラボが多いが、上振れ差は小さい。にじさんじ側の差は、企画・雑談・歌系の関係性消費に出やすい。</text>
  <text class="small" x="70" y="625">source: jackojacko05.nijiholo.article_genre_uplift</text>
"""
    return svg_page(1200, 675, body)


def figure_graph_flow() -> str:
    boxes = [
        (70, 190, 230, 110, "YouTube Data API", "チャンネル一覧 / 動画 / 概要欄"),
        (360, 190, 230, 110, "BigQuery raw tables", "youtube_videos など"),
        (650, 190, 230, 110, "Property Graph", "Character - MentionsChannel"),
        (940, 190, 190, 110, "Article tables", "article_* metrics"),
    ]
    box_svg = []
    for x, y, w, h, title, subtitle in boxes:
        box_svg.append(f'<rect class="panel" x="{x}" y="{y}" width="{w}" height="{h}"/>')
        box_svg.append(f'<text class="label" x="{x + 20}" y="{y + 42}">{esc(title)}</text>')
        box_svg.append(f'<text class="small" x="{x + 20}" y="{y + 74}">{esc(subtitle)}</text>')
    arrows = """
  <path d="M305 245 L350 245" stroke="#64748b" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M595 245 L640 245" stroke="#64748b" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M885 245 L930 245" stroke="#64748b" stroke-width="3" marker-end="url(#arrow)"/>
"""
    gql = esc("GRAPH_TABLE(youtube_collab_graph MATCH (a)-[e]->(b) RETURN a, e.video_count, b)")
    body = f"""
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L8,3 z" fill="#64748b" />
    </marker>
  </defs>
  <text class="title" x="70" y="70">裏テーマ: BigQuery Graphだけで関係性データを組む</text>
  <text class="subtitle" x="70" y="104">Pythonは取得と図の出力に寄せ、分析の主語はBigQueryのテーブルとGraphに置く。</text>
  {''.join(box_svg)}
  {arrows}
  <rect x="170" y="390" width="860" height="95" fill="#0f172a" rx="8"/>
  <text x="200" y="430" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="17" fill="#e2e8f0">{gql}</text>
  <text class="note" x="120" y="550">記事の本筋は「にじさんじとホロライブの違い」。補足として、BigQuery Graphの最小サンプルにもなる構成。</text>
  <text class="small" x="70" y="625">source: sql/005_youtube_collab_graph.sql / sql/008_article_collab_metrics.sql</text>
"""
    return svg_page(1200, 675, body)


def figure_edge_matrix(rows: list[dict[str, Any]]) -> str:
    matrix = {(row["src_org"], row["dst_org"]): int(row["weighted_video_count"]) for row in rows}
    max_value = max(matrix.values())
    cells = []
    for i, src in enumerate(["nijisanji", "hololive"]):
        for j, dst in enumerate(["nijisanji", "hololive"]):
            x = 340 + j * 250
            y = 205 + i * 150
            value = matrix.get((src, dst), 0)
            opacity = 0.15 + 0.70 * math.sqrt(value / max_value)
            cells.append(f'<rect x="{x}" y="{y}" width="220" height="120" fill="#2563eb" fill-opacity="{opacity:.2f}" rx="8"/>')
            cells.append(f'<text class="value" x="{x + 32}" y="{y + 54}">{fmt_int(value)}</text>')
            cells.append(f'<text class="small" x="{x + 32}" y="{y + 84}">動画数重み</text>')
    body = f"""
  <text class="title" x="70" y="70">関係性edgeは、同じ箱の中に強く集まる</text>
  <text class="subtitle" x="70" y="104">投稿者側から概要欄で言及された側への有向edgeを、動画数重みで集計。</text>
  <text class="label" x="425" y="170">言及先: にじさんじ</text>
  <text class="label" x="675" y="170">言及先: ホロライブ</text>
  <text class="label" x="110" y="270">投稿者: にじさんじ</text>
  <text class="label" x="110" y="420">投稿者: ホロライブ</text>
  {''.join(cells)}
  <text class="note" x="90" y="565">読み: 人数差の影響はあるが、箱内edgeが圧倒的に多い。にじホロ横断は見えるが、全体構造では例外的な接続として扱うのがよさそう。</text>
  <text class="small" x="70" y="625">source: jackojacko05.nijiholo.article_edge_matrix</text>
"""
    return svg_page(1200, 675, body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="jackojacko05")
    parser.add_argument("--location", default="asia-northeast1")
    parser.add_argument("--output-dir", type=Path, default=FIGURE_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    supply = bq_query("SELECT * FROM `jackojacko05.nijiholo.article_org_supply` ORDER BY org", args.project, args.location)
    uplift = bq_query("SELECT * FROM `jackojacko05.nijiholo.article_owner_uplift` ORDER BY org", args.project, args.location)
    genre_uplift = bq_query(
        """
        SELECT *
        FROM `jackojacko05.nijiholo.article_genre_uplift`
        ORDER BY CASE genre WHEN 'ゲーム' THEN 1 WHEN '歌' THEN 2 ELSE 3 END, org
        """,
        args.project,
        args.location,
    )
    edge_matrix = bq_query("SELECT * FROM `jackojacko05.nijiholo.article_edge_matrix`", args.project, args.location)

    metrics = {
        "supply": supply,
        "owner_uplift": uplift,
        "genre_uplift": genre_uplift,
        "edge_matrix": edge_matrix,
    }
    (args.output_dir / "article_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    figures = {
        "fig01_supply_vs_demand.svg": figure_supply_demand(supply, uplift),
        "fig02_genre_uplift.svg": figure_genre_uplift(genre_uplift),
        "fig03_bigquery_graph_flow.svg": figure_graph_flow(),
        "fig04_edge_matrix.svg": figure_edge_matrix(edge_matrix),
    }
    for filename, svg in figures.items():
        (args.output_dir / filename).write_text(svg, encoding="utf-8")
        print(args.output_dir / filename)


if __name__ == "__main__":
    main()
