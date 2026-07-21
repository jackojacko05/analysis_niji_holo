#!/usr/bin/env python3
"""Build current talent and fan-art hashtag CSVs.

Sources:
- NIJISANJI official site for the current roster.
- hololive official site for active talent roster and official hashtags.
- HoloList for NIJISANJI fan-art hashtags, because the current NIJISANJI
  official profile pages do not expose fan-art hashtags.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import html
import json
from pathlib import Path
import re
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import unicodedata


BASE_DIR = Path(__file__).resolve().parents[1]
BUILD_DIR = BASE_DIR / "build" / "current-source-cache"
DATA_DIR = BASE_DIR / "data" / "current"
TODAY = date.today().isoformat()
USER_AGENT = "analysis-niji-holo/0.1 (+https://github.com/jackojacko05/analysis_niji_holo)"

NIJISANJI_TALENTS_URL = "https://www.nijisanji.jp/talents"
HOLOLIVE_TALENTS_URL = "https://hololive.hololivepro.com/talents/"
HOLLIST_NIJI_GROUP_URL = "https://hololist.net/group/nijisanji-project/"

LEGACY_NAME_FIXES = {
    "音乃瀬奏)": "音乃瀬奏",
    "ギルザレンIII世": "ギルザレンⅢ世",
}

STATUS_PREFIX_TO_STATUS = {
    "【卒業生】": "graduated",
    "【退職】": "retired_staff",
    "【配信活動終了】": "streaming_ended",
}

MANUAL_TAG_OVERRIDES = {
    "nijisanji:Rei7": [
        {
            "tag": "#Rei0ut",
            "tag_kind": "fanart",
            "source_label": "ファンアート",
            "source_url": "https://wikiwiki.jp/nijisanji/Rei7",
            "source_type": "wikiwiki",
            "confidence": "0.70",
            "notes": "community wiki manual supplement; official NIJISANJI profile does not expose fan-art hashtags",
        }
    ],
}


def normalize_name(value: str) -> str:
    value = LEGACY_NAME_FIXES.get(value.strip(), value.strip())
    return unicodedata.normalize("NFKC", value)


def split_status_prefix(value: str) -> tuple[str, str]:
    text = value.strip()
    for prefix, status in STATUS_PREFIX_TO_STATUS.items():
        if text.startswith(prefix):
            return text.replace(prefix, "", 1).strip(), status
    return text, ""


def normalize_tag(tag: str) -> str:
    tag = tag.strip()
    while tag.startswith("#") or tag.startswith("＃"):
        tag = tag[1:]
    return unicodedata.normalize("NFKC", tag).lower()


def strip_tags(value: str) -> str:
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).replace("\xa0", " ").strip()


def compact_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slug_from_url(url: str) -> str:
    return urlparse(url).path.strip("/").split("/")[-1]


def safe_filename(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "__") or "index"
    return f"{parsed.netloc}__{path}.html"


def slugify_latin_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()


def hololist_candidate_urls_for_talent(talent: dict[str, str]) -> list[str]:
    slugs = []
    for slug in [talent.get("slug", ""), slugify_latin_name(talent.get("en_name", ""))]:
        if slug and slug not in slugs:
            slugs.append(slug)
    return [f"https://hololist.net/{slug}/" for slug in slugs]


def fetch(url: str, cache_path: Path, *, force: bool = False, sleep_s: float = 0.0) -> str:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists() and not force:
        return cache_path.read_text(encoding="utf-8", errors="replace")

    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as res:
        body = res.read().decode("utf-8", errors="replace")
    cache_path.write_text(body, encoding="utf-8")
    if sleep_s:
        time.sleep(sleep_s)
    return body


def fetch_optional(url: str, cache_path: Path, *, force: bool = False, sleep_s: float = 0.0) -> str | None:
    try:
        return fetch(url, cache_path, force=force, sleep_s=sleep_s)
    except (HTTPError, URLError, TimeoutError):
        return None


def parse_next_data(page_html: str) -> dict:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        page_html,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ script")
    return json.loads(html.unescape(match.group(1)))


def load_legacy_niji_tags() -> dict[str, list[dict[str, str]]]:
    path = BASE_DIR / "tag_niji.csv"
    tags: dict[str, list[dict[str, str]]] = {}
    if not path.exists():
        return tags

    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = normalize_name(row["name"])
            tag = row["tag"].strip()
            tags.setdefault(name, []).append(
                {
                    "tag": tag,
                    "tag_norm": normalize_tag(tag),
                    "source_label": "legacy tag_niji.csv",
                    "source_url": str(path.relative_to(BASE_DIR)),
                    "source_type": "legacy_csv",
                    "confidence": "0.60",
                    "notes": "legacy 2023-era local mapping; use only when HoloList tag is unavailable",
                }
            )
    return tags


def character_id(org: str, name: str) -> str:
    return f"{org}:{normalize_name(name)}"


def parse_nijisanji_roster(page_html: str) -> list[dict[str, str]]:
    data = parse_next_data(page_html)
    livers = data["props"]["pageProps"]["allLivers"]
    rows: list[dict[str, str]] = []

    for liver in livers:
        affiliations = liver.get("profile", {}).get("affiliation", [])
        name = normalize_name(liver["name"])
        org = "nijisanji"
        rows.append(
            {
                "dataset_date": TODAY,
                "org": org,
                "agency": "ANYCOLOR",
                "affiliation": "|".join(affiliations),
                "generation": "",
                "talent_id": character_id(org, name),
                "name": name,
                "en_name": liver.get("enName", ""),
                "slug": liver.get("slug", ""),
                "active_status": "active_official",
                "profile_url": f"https://www.nijisanji.jp/talents/l/{liver.get('slug', '')}",
                "official_source_url": NIJISANJI_TALENTS_URL,
                "x_url": "",
                "youtube_url": "",
                "source": "nijisanji_official_allLivers",
            }
        )
    return rows


def parse_hololive_roster(list_html: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pattern = re.compile(
        r'<li>\s*<a href="(?P<url>https://hololive\.hololivepro\.com/talents/[^"]+/)".*?'
        r"<h3>\s*(?P<name>.*?)<span>(?P<en>.*?)</span>\s*</h3>",
        re.DOTALL,
    )
    for match in pattern.finditer(list_html):
        raw_name = strip_tags(match.group("name"))
        en_name = strip_tags(match.group("en"))
        name_text, prefixed_status = split_status_prefix(raw_name)
        status = prefixed_status or "active_official"
        name = normalize_name(name_text)
        org = "hololive"
        rows.append(
            {
                "dataset_date": TODAY,
                "org": org,
                "agency": "COVER",
                "affiliation": "",
                "generation": "",
                "talent_id": character_id(org, name),
                "name": name,
                "en_name": en_name,
                "slug": slug_from_url(match.group("url")),
                "active_status": status,
                "profile_url": match.group("url"),
                "official_source_url": HOLOLIVE_TALENTS_URL,
                "x_url": "",
                "youtube_url": "",
                "source": "hololive_official_talents_page",
            }
        )
    return rows


def parse_hololive_detail(talent: dict[str, str], page_html: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    updated = dict(talent)

    breadcrumb = re.findall(r'<span property="name"[^>]*>(.*?)</span>', page_html, re.DOTALL)
    crumbs = []
    for crumb_html in breadcrumb:
        crumb = strip_tags(crumb_html)
        if not crumb or "Go to" in crumb:
            continue
        crumb_text, _ = split_status_prefix(crumb)
        crumbs.append(normalize_name(crumb_text))
    categories = []
    talent_names = {talent["name"], normalize_name(talent["en_name"])} if talent["en_name"] else {talent["name"]}
    for crumb in crumbs:
        if crumb in {"TALENTS", "hololive(ホロライブ)公式サイト"} or crumb in talent_names:
            continue
        if crumb not in categories:
            categories.append(crumb)
    if categories:
        updated["affiliation"] = categories[0]
        updated["generation"] = "|".join(categories[1:])

    sns_block = re.search(r'<ul class="(?:sns_list|t_sns)[^"]*">(.*?)</ul>', page_html, re.DOTALL)
    if sns_block:
        for href, label in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', sns_block.group(1), re.DOTALL):
            label_text = strip_tags(label).lower()
            if "youtube" in label_text:
                updated["youtube_url"] = href
            if label_text == "x":
                updated["x_url"] = href

    hashtags_match = re.search(r"<dt>ハッシュタグ</dt>\s*<dd>(.*?)</dd>", page_html, re.DOTALL)
    tag_rows: list[dict[str, str]] = []
    if hashtags_match:
        text = strip_tags(hashtags_match.group(1))
        for line in [x.strip() for x in text.splitlines() if x.strip()]:
            label, _, rest = line.partition("：")
            if not rest:
                label, _, rest = line.partition(":")
            source_label = compact_space(label if rest else line)
            tag_text = rest if rest else line
            tag_kind = classify_tag_kind(source_label)
            if tag_kind not in {"fanart", "ai_art"}:
                continue
            for tag in extract_hashtags(tag_text):
                tag_rows.append(make_tag_row(updated, tag, tag_kind, source_label, talent["profile_url"], "hololive_official_profile", "1.00", ""))

    return updated, tag_rows


def classify_tag_kind(label: str) -> str:
    lowered = label.lower()
    if "ai" in lowered and ("art" in lowered or "イラスト" in label):
        return "ai_art"
    if (
        "fan art" in lowered
        or "fanart" in lowered
        or "art tag" in lowered
        or "ファンアート" in label
        or "アートタグ" in label
        or "イラスト" in label
    ):
        return "fanart"
    return "other"


def extract_hashtags(text: str) -> list[str]:
    tags = []
    for match in re.finditer(r"[#＃][^\s#＃,，、/／<>()（）\[\]「」]+", text):
        tag = match.group(0).strip().rstrip("。.;；")
        if tag not in tags:
            tags.append(tag)
    return tags


def make_tag_row(
    talent: dict[str, str],
    tag: str,
    tag_kind: str,
    source_label: str,
    source_url: str,
    source_type: str,
    confidence: str,
    notes: str,
) -> dict[str, str]:
    return {
        "dataset_date": TODAY,
        "org": talent["org"],
        "agency": talent["agency"],
        "affiliation": talent["affiliation"],
        "talent_id": talent["talent_id"],
        "name": talent["name"],
        "en_name": talent["en_name"],
        "tag": tag,
        "tag_norm": normalize_tag(tag),
        "tag_kind": tag_kind,
        "source_label": source_label,
        "source_url": source_url,
        "source_type": source_type,
        "confidence": confidence,
        "notes": notes,
    }


def extract_hololist_candidate_links(group_pages: Iterable[str]) -> list[str]:
    links: list[str] = []
    for page_html in group_pages:
        for href in re.findall(r'href="(https://hololist\.net/[^"/]+/)"', page_html):
            path = slug_from_url(href)
            if path in {
                "top",
                "newest",
                "latest",
                "upcoming",
                "random",
                "type",
                "category",
                "content",
                "group",
                "gender",
                "zodiac",
                "language",
                "model",
                "tag",
                "birthday",
                "debut",
                "retirement",
                "gallery",
                "news",
                "about",
                "announcement",
                "contact",
                "donate",
                "cookie-policy",
                "privacy-policy",
                "terms-of-service",
            }:
                continue
            if href not in links:
                links.append(href)
    return links


def extract_section_text(page_html: str, heading: str) -> str:
    pattern = re.compile(
        rf"<section[^>]*>.*?<h2[^>]*>{re.escape(heading)}</h2>(.*?)</section>",
        re.DOTALL,
    )
    match = pattern.search(page_html)
    return strip_tags(match.group(1)) if match else ""


def extract_hololist_title_name(page_html: str) -> str:
    match = re.search(r'<h1[^>]*>(.*?)</h1>', page_html, re.DOTALL)
    return normalize_name(strip_tags(match.group(1))) if match else ""


def parse_hololist_detail(page_html: str, url: str) -> dict[str, object] | None:
    original_name = normalize_name(extract_section_text(page_html, "Original Name")) or extract_hololist_title_name(page_html)
    if not original_name:
        return None
    return {
        "url": url,
        "original_name": original_name,
        "status": compact_space(extract_section_text(page_html, "Status")),
        "affiliation": compact_space(extract_section_text(page_html, "Affiliation")),
        "hashtags": parse_hololist_hashtags(extract_section_text(page_html, "Hashtags")),
    }


def parse_hololist_hashtags(text: str) -> list[dict[str, str]]:
    rows = []
    for line in [x.strip() for x in text.splitlines() if x.strip()]:
        match = re.match(r"(?P<tag>[#＃]\S+)\s*-\s*(?P<label>.+)$", line)
        if not match:
            continue
        label = compact_space(match.group("label"))
        kind = classify_hololist_label(label)
        if kind not in {"fanart", "ai_art"}:
            continue
        rows.append(
            {
                "tag": match.group("tag"),
                "tag_norm": normalize_tag(match.group("tag")),
                "tag_kind": kind,
                "source_label": label,
            }
        )
    return rows


def classify_hololist_label(label: str) -> str:
    lowered = label.lower()
    if "ai" in lowered and "art" in lowered:
        return "ai_art"
    if "fan art" in lowered or "fanart" in lowered:
        return "fanart"
    return "other"


def comparable_name(value: str) -> str:
    value = normalize_name(value)
    value = value.replace("―", "ー")
    return re.sub(r"\s+", "", value).casefold()


def hololist_name_matches_talent(parsed: dict[str, object], talent: dict[str, str]) -> bool:
    original_name = normalize_name(str(parsed.get("original_name", "")))
    if slug_from_url(str(parsed.get("url", ""))) == talent.get("slug"):
        return True
    candidates = {comparable_name(talent["name"])}
    if talent.get("en_name"):
        candidates.add(comparable_name(talent["en_name"]))
    return comparable_name(original_name) in candidates


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_sources_doc(path: Path, *, talents: list[dict[str, str]], tags: list[dict[str, str]], missing: list[dict[str, str]]) -> None:
    source_counts: dict[str, int] = {}
    for row in tags:
        source_counts[row["source_type"]] = source_counts.get(row["source_type"], 0) + 1

    lines = [
        f"# Current Fan-art Tag Dataset ({TODAY})",
        "",
        "## Scope",
        "",
        "- NIJISANJI roster is taken from the official `allLivers` data embedded in `https://www.nijisanji.jp/talents`.",
        "- hololive roster and hololive fan-art hashtags are taken from official hololive production talent pages.",
        "- NIJISANJI fan-art hashtags are supplemented from HoloList because the current official NIJISANJI profile pages expose roster/profile/social data but not fan-art hashtags.",
        "- hololive fan-art hashtags are supplemented from HoloList only when the official talent profile does not expose a usable fan-art tag.",
        "- Legacy `tag_niji.csv` is used only as fallback when HoloList does not provide a fan-art tag for a current official NIJISANJI talent.",
        "- Small manual supplements are used only for remaining current talents when a traceable source is available.",
        "",
        "## Row Counts",
        "",
        f"- talents: {len(talents)}",
        f"- fanart tag rows: {len(tags)}",
        f"- talents missing fanart tags: {len(missing)}",
        "",
        "## Tag Source Counts",
        "",
    ]
    for key, value in sorted(source_counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- `confidence=1.00` means the fan-art tag came from an official hololive profile page.",
            "- `confidence=0.80` means the tag came from HoloList, not the agency official site.",
            "- `confidence=0.70` means the tag came from a manual web research supplement.",
            "- `confidence=0.60` means the tag came from the old local `tag_niji.csv` fallback.",
            "- Some NIJISANJI EN and newer NIJISANJI JP/KR/ID-origin talents still need manual verification.",
            "- HoloList status is not used as roster truth; official agency rosters are the roster truth.",
            "",
            "## Source URLs",
            "",
            f"- NIJISANJI official talents: {NIJISANJI_TALENTS_URL}",
            f"- hololive official talents: {HOLOLIVE_TALENTS_URL}",
            f"- HoloList NIJISANJI Project: {HOLLIST_NIJI_GROUP_URL}",
            "- HoloList individual profile pages: https://hololist.net/",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="Fetch remote source pages instead of relying only on cache.")
    parser.add_argument("--sleep", type=float, default=0.05, help="Sleep seconds between fetches.")
    parser.add_argument("--include-virtuareal", action="store_true", help="Include VirtuaReal rows in the NIJISANJI output.")
    args = parser.parse_args()

    niji_html = fetch(
        NIJISANJI_TALENTS_URL,
        BUILD_DIR / "nijisanji-talents.html",
        force=args.fetch,
        sleep_s=args.sleep,
    )
    holo_html = fetch(
        HOLOLIVE_TALENTS_URL,
        BUILD_DIR / "hololive-talents.html",
        force=args.fetch,
        sleep_s=args.sleep,
    )

    niji_talents_all = parse_nijisanji_roster(niji_html)
    if args.include_virtuareal:
        niji_talents = niji_talents_all
    else:
        niji_talents = [
            row
            for row in niji_talents_all
            if row["affiliation"] in {"にじさんじ", "NIJISANJI EN"}
        ]

    holo_talents_all = parse_hololive_roster(holo_html)
    holo_talents = [
        row
        for row in holo_talents_all
        if row["active_status"] in {"active_official", "streaming_ended"}
    ]

    holo_tags: list[dict[str, str]] = []
    holo_talents_enriched: list[dict[str, str]] = []
    for talent in holo_talents:
        page_html = fetch(
            talent["profile_url"],
            BUILD_DIR / safe_filename(talent["profile_url"]),
            force=args.fetch,
            sleep_s=args.sleep,
        )
        enriched, tags = parse_hololive_detail(talent, page_html)
        holo_talents_enriched.append(enriched)
        holo_tags.extend(tags)

    holo_talent_ids_with_tags = {row["talent_id"] for row in holo_tags if row["tag_kind"] == "fanart"}
    for talent in holo_talents_enriched:
        if talent["talent_id"] in holo_talent_ids_with_tags:
            continue
        hololist_url = f"https://hololist.net/{talent['slug']}/"
        page_html = fetch_optional(
            hololist_url,
            BUILD_DIR / safe_filename(hololist_url),
            force=args.fetch,
            sleep_s=args.sleep,
        )
        if not page_html:
            continue
        parsed = parse_hololist_detail(page_html, hololist_url)
        if not parsed or not hololist_name_matches_talent(parsed, talent):
            continue
        added = False
        for tag in parsed["hashtags"]:  # type: ignore[index]
            holo_tags.append(
                make_tag_row(
                    talent,
                    tag["tag"],  # type: ignore[index]
                    tag["tag_kind"],  # type: ignore[index]
                    tag["source_label"],  # type: ignore[index]
                    str(parsed["url"]),
                    "hololist",
                    "0.80",
                    "hololive official profile lacks fan-art hashtag; HoloList used as supplemental source",
                )
            )
            added = True
        if added:
            holo_talent_ids_with_tags.add(talent["talent_id"])

    hololist_group_pages = []
    first_group = fetch(
        HOLLIST_NIJI_GROUP_URL,
        BUILD_DIR / "hololist__nijisanji-project__page-1.html",
        force=args.fetch,
        sleep_s=args.sleep,
    )
    hololist_group_pages.append(first_group)
    page_numbers = {1}
    for page in re.findall(r"https://hololist\.net/group/nijisanji-project/page/(\d+)/", first_group):
        page_numbers.add(int(page))
    if page_numbers:
        page_numbers.update(range(1, max(page_numbers) + 1))
    for page_number in sorted(page_numbers - {1}):
        hololist_group_pages.append(
            fetch(
                f"https://hololist.net/group/nijisanji-project/page/{page_number}/",
                BUILD_DIR / f"hololist__nijisanji-project__page-{page_number}.html",
                force=args.fetch,
                sleep_s=args.sleep,
            )
        )

    official_niji_names = {row["name"] for row in niji_talents}
    official_niji_en_names = {row["en_name"] for row in niji_talents if row["en_name"]}
    hololist_by_name: dict[str, dict[str, object]] = {}

    for url in extract_hololist_candidate_links(hololist_group_pages):
        page_html = fetch(
            url,
            BUILD_DIR / safe_filename(url),
            force=args.fetch,
            sleep_s=args.sleep,
        )
        parsed = parse_hololist_detail(page_html, url)
        if not parsed:
            continue
        original_name = str(parsed["original_name"])
        if original_name not in official_niji_names and original_name not in official_niji_en_names:
            continue
        hololist_by_name[original_name] = parsed

    legacy_niji_tags = load_legacy_niji_tags()
    niji_tags: list[dict[str, str]] = []
    for talent in niji_talents:
        hlist = hololist_by_name.get(talent["name"]) or hololist_by_name.get(talent["en_name"])
        if not hlist:
            for hololist_url in hololist_candidate_urls_for_talent(talent):
                page_html = fetch_optional(
                    hololist_url,
                    BUILD_DIR / safe_filename(hololist_url),
                    force=args.fetch,
                    sleep_s=args.sleep,
                )
                if not page_html:
                    continue
                parsed = parse_hololist_detail(page_html, hololist_url)
                if parsed and hololist_name_matches_talent(parsed, talent):
                    hlist = parsed
                    break
        added = False
        if hlist:
            for tag in hlist["hashtags"]:  # type: ignore[index]
                niji_tags.append(
                    make_tag_row(
                        talent,
                        tag["tag"],  # type: ignore[index]
                        tag["tag_kind"],  # type: ignore[index]
                        tag["source_label"],  # type: ignore[index]
                        str(hlist["url"]),
                        "hololist",
                        "0.80",
                        "NIJISANJI official profile lacks fan-art hashtags; HoloList used as supplemental source",
                    )
                )
                added = True
        if not added:
            for tag in legacy_niji_tags.get(talent["name"], []):
                niji_tags.append(
                    make_tag_row(
                        talent,
                        tag["tag"],
                        "fanart",
                        tag["source_label"],
                        tag["source_url"],
                        tag["source_type"],
                        tag["confidence"],
                        tag["notes"],
                    )
                )
                added = True
        if not added:
            for tag in MANUAL_TAG_OVERRIDES.get(talent["talent_id"], []):
                niji_tags.append(
                    make_tag_row(
                        talent,
                        tag["tag"],
                        tag["tag_kind"],
                        tag["source_label"],
                        tag["source_url"],
                        tag["source_type"],
                        tag["confidence"],
                        tag["notes"],
                    )
                )

    talents = sorted(niji_talents + holo_talents_enriched, key=lambda r: (r["org"], r["affiliation"], r["name"]))
    tags = sorted(niji_tags + holo_tags, key=lambda r: (r["org"], r["name"], r["tag_norm"]))
    talent_ids_with_tags = {row["talent_id"] for row in tags if row["tag_kind"] == "fanart"}
    missing = [row for row in talents if row["talent_id"] not in talent_ids_with_tags]

    talent_fields = [
        "dataset_date",
        "org",
        "agency",
        "affiliation",
        "generation",
        "talent_id",
        "name",
        "en_name",
        "slug",
        "active_status",
        "profile_url",
        "official_source_url",
        "x_url",
        "youtube_url",
        "source",
    ]
    tag_fields = [
        "dataset_date",
        "org",
        "agency",
        "affiliation",
        "talent_id",
        "name",
        "en_name",
        "tag",
        "tag_norm",
        "tag_kind",
        "source_label",
        "source_url",
        "source_type",
        "confidence",
        "notes",
    ]
    missing_fields = talent_fields

    write_csv(DATA_DIR / f"talents_current_{TODAY}.csv", talents, talent_fields)
    write_csv(DATA_DIR / f"fanart_tags_current_{TODAY}.csv", tags, tag_fields)
    write_csv(DATA_DIR / f"tag_missing_current_{TODAY}.csv", missing, missing_fields)
    write_sources_doc(DATA_DIR / f"sources_current_{TODAY}.md", talents=talents, tags=tags, missing=missing)

    print(f"talents: {len(talents)}")
    print(f"fanart tag rows: {len(tags)}")
    print(f"missing fanart tags: {len(missing)}")
    print(f"output_dir: {DATA_DIR}")


if __name__ == "__main__":
    main()
