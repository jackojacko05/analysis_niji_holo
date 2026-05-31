# Current Fan-art Tag Dataset (2026-05-30)

## Scope

- NIJISANJI roster is taken from the official `allLivers` data embedded in `https://www.nijisanji.jp/talents`.
- hololive roster and hololive fan-art hashtags are taken from official hololive production talent pages.
- NIJISANJI fan-art hashtags are supplemented from HoloList because the current official NIJISANJI profile pages expose roster/profile/social data but not fan-art hashtags.
- hololive fan-art hashtags are supplemented from HoloList only when the official talent profile does not expose a usable fan-art tag.
- Legacy `tag_niji.csv` is used only as fallback when HoloList does not provide a fan-art tag for a current official NIJISANJI talent.
- Small manual supplements are used only for remaining current talents when a traceable source is available.

## Row Counts

- talents: 264
- fanart tag rows: 265
- talents missing fanart tags: 3

## Tag Source Counts

- hololist: 213
- hololive_official_profile: 48
- legacy_csv: 3
- wikiwiki: 1

## Caveats

- `confidence=1.00` means the fan-art tag came from an official hololive profile page.
- `confidence=0.80` means the tag came from HoloList, not the agency official site.
- `confidence=0.70` means the tag came from a manual web research supplement.
- `confidence=0.60` means the tag came from the old local `tag_niji.csv` fallback.
- Some NIJISANJI EN and newer NIJISANJI JP/KR/ID-origin talents still need manual verification.
- HoloList status is not used as roster truth; official agency rosters are the roster truth.

## Source URLs

- NIJISANJI official talents: https://www.nijisanji.jp/talents
- hololive official talents: https://hololive.hololivepro.com/talents/
- HoloList NIJISANJI Project: https://hololist.net/group/nijisanji-project/
- HoloList individual profile pages: https://hololist.net/
