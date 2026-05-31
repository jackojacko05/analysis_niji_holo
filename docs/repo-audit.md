# Repo Audit

## Remote

見つかった本命リポジトリ:

- `jackojacko05/analysis_niji_holo`
- URL: https://github.com/jackojacko05/analysis_niji_holo
- 説明: `analysing tweets of nijisanji and hololive`
- clone 先: `/Users/user/GitHub/analysis_niji_holo`

`gh` はローカル token が無効だったため、公開 GitHub API でリポジトリ一覧を確認した。private repository を探すには `gh auth login -h github.com` が必要。

## Existing Artifacts

Tracked files:

- `.gitignore`
- `tag_niji.csv`
- `tag_holo.csv`
- `tweets_tagged_niji.csv`
- `tweets_tagged_holo.csv`
- `co_occurrence_ranking_niji.csv`
- `co_occurrence_ranking_holo.csv`
- `にじホロ ネットワーク密度.ipynb`

Parsed row summary:

| File | Parsed rows | Notes |
| --- | ---: | --- |
| `tag_niji.csv` | 153 data rows | `name`, `tag`, `Twitter` |
| `tag_holo.csv` | 70 data rows | `name`, `tag` |
| `tweets_tagged_niji.csv` | 5,141 posts | 139 character columns, 638 multi-character posts |
| `tweets_tagged_holo.csv` | 3,403 posts | 43 character columns, 355 multi-character posts |
| `co_occurrence_ranking_holo.csv` | 9,730 data rows | Actually Nijisanji pairs |
| `co_occurrence_ranking_niji.csv` | 946 data rows | Actually Hololive pairs |

`wc -l` は tweets CSV の投稿本文内改行を行として数えるため、CSV の実レコード数とは一致しない。

## Notebook Flow

`にじホロ ネットワーク密度.ipynb` の主な処理:

1. `variables.json` から BigQuery project/table を読み込む。
2. `2021-11-22` から `2022-11-21` までの投稿を BigQuery から取得する。
3. BigQuery 側で `nijisanji_flg` / `hololive_flg` が付いた投稿だけを対象にする。
4. `tag_niji.csv` / `tag_holo.csv` を読み込む。
5. 投稿本文に各ファンアートタグが含まれるかを `str.contains` で判定し、キャラクター bool 行列を作る。
6. 同一投稿内で複数キャラクターが True の場合にキャラクター pair を加算する。
7. NetworkX で重み 2 未満の edge を落として density / degree を見る。

## Existing Top Results

既存 CSV から読むと、ファイル名を補正した上位ペアは次の通り。

Nijisanji:

- 三枝明那 - 不破湊: 91
- 叶 - 葛葉: 85
- 三枝明那 - 黛灰: 66
- 不破湊 - 黛灰: 63
- 伏見ガク - 剣持刀也: 49

Hololive:

- 戌神ころね - 猫又おかゆ: 35
- さくらみこ - 星街すいせい: 35
- 獅白ぼたん - 雪花ラミィ: 24
- 沙花叉クロヱ - 風真いろは: 24
- 沙花叉クロヱ - 鷹嶺ルイ: 22

投稿数上位:

Nijisanji:

- 甲斐田晴: 711
- 剣持刀也: 528
- 葛葉: 371
- 黛灰: 317
- 叶: 296

Hololive:

- 宝鐘マリン: 268
- 沙花叉クロヱ: 227
- 星街すいせい: 218
- 猫又おかゆ: 195
- 兎田ぺこら: 195

## Caveats

- `co_occurrence_ranking_holo.csv` / `co_occurrence_ranking_niji.csv` は Notebook の `hako = 'niji' if i == 1 else 'holo'` により出力名が逆になっている。
- `str.contains(row['tag'])` は pandas の default では regex 扱い。タグ文字列は `regex=False, na=False` で判定した方がよい。
- `tag_holo.csv` の `音乃瀬奏)` は名前に閉じ括弧が混入している。
- 投稿単位の共起だけだと「1 枚に複数キャラがいる」ケースに強く寄る。ユーザー単位・週単位の共起を追加すると「同じ絵師が描くキャラの近さ」も測れる。
- 当時の BigQuery source table 名は `variables.json` にあり、`.gitignore` で除外されているため、この repo だけでは復元できない。

## Migration Direction

既存 wide CSV をそのまま分析し続けるより、次の正規化テーブルに変換する。

- `character_tags`: character と fan-art tag の対応
- `legacy_tagged_posts`: 既存 CSV 由来の投稿 metadata
- `post_characters`: post と character の対応
- `character_cooccurrence_edges`: post / author / author-week など unit ごとの共起 edge

その後、BigQuery Graph の property graph に `Character`, `Hashtag`, `Post`, `User` を node として載せる。

`scripts/normalize_legacy_csv.py` は既存ファイルを次の正規化 CSV に変換する。

- `character_tags.csv`: 225 rows
- `legacy_posts.csv`: 8,544 rows
- `post_characters.csv`: 10,285 rows

生成先は `build/legacy-normalized/`。再作成可能なため Git では追跡しない。
