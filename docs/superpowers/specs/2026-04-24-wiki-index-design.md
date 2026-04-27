# Wiki インデックス（README）ステージ 設計書

- **日付**: 2026-04-24
- **対象**: サブプロジェクト #1 への小規模追加
- **関連 spec**: [2026-04-23-llm-wiki-pipeline-design.md](2026-04-23-llm-wiki-pipeline-design.md)

## 1. 背景と目的

現在のパイプラインは Wiki ページ MD（`wiki/<category>/<subtopic>.md`）を生成するが、それらを横断的にナビゲートする手段がない。ページ数が増えると目視で全体像を把握しにくい。

GitHub の Web UI でディレクトリを開いたとき自動的に表示される `README.md` を各階層に置き、Wiki 全体の目次として機能させる。

## 2. スコープと非スコープ

### スコープ
- 新ステージ `index` の追加（CLI フローに組み込み）
- トップレベル `wiki/README.md` の自動生成
- 各カテゴリ `wiki/<category>/README.md` の自動生成
- タイトル・サマリの抽出ロジック（コードのみ、LLM 不使用）

### 非スコープ
- `wiki/<category>/<subtopic>.md` 自体への目次追加
- GitHub Pages 用 `index.md`（サブプロ #3 で対応）
- 検索／フィルタ機能
- ページ間相互リンク（"関連ページ"）

## 3. CLI / パイプライン位置

新ステージを Compile と Diff の間に追加する：

```
ingest → classify → cluster → compile → index → diff
```

`index` は code-only（LLM 呼び出しなし）。`pipeline.yaml` の `stages` には登録しない（cluster と同じ扱い）。

`pipeline/main.py` の `STAGE_NAMES` に `"index"` を追加し、`_run_stage("index", root)` を実装する。

## 4. 出力ファイルの仕様

### 4.1 `wiki/README.md`（トップレベル）

```markdown
# Splatoon 3 Wiki

LLM が生成・編纂したナレッジ集。

## カテゴリ

- [01-principles](01-principles/) — 原理原則 — N ページ
- [02-rule-stage](02-rule-stage/) — ルール×ステージ — N ページ
- [03-weapon-role](03-weapon-role/) — ブキ・役割 — N ページ
- [04-stepup](04-stepup/) — ステップアップガイド — N ページ
- [05-glossary](05-glossary/) — 用語集 — N ページ
```

要件：

- **カテゴリ順**は `config/categories.yaml` の宣言順（id 昇順と一致）
- **ラベルと説明文**は `categories.yaml` から取得
- **ページ数**は `wiki/<category>/` 配下の `*.md` から `README.md` を除いた数
- **ページ数 0 のカテゴリも表示**（"0 ページ" と明示）
- カテゴリディレクトリ自体が存在しない場合も 0 ページとして表示

### 4.2 `wiki/<category>/README.md`（カテゴリ別）

```markdown
# 02-rule-stage — ルール×ステージ

ルール×ステージ固有の定石

## ページ一覧

- [海女美術 右高台の制圧](2026-04-05-amabi-right-high-suppression.md) — 右高台はリスクと裏取り誘発を伴うため慎重に判断する。
- ...
```

要件：

- **見出し**: `# <category-id> — <category-label>`
- **説明文**: `categories.yaml` の `description`
- **ページ一覧**は `wiki/<category>/*.md`（`README.md` を除く）をファイル名アルファベット順
- **各エントリ**: `- [<title>](<filename>) — <summary>`
- **0 ページの場合**: 「ページ一覧」の下に "(まだページがありません)" を表示

## 5. タイトルとサマリの抽出ロジック

### 5.1 タイトル

> **Superseded 2026-04-26**: 本文 `##` 見出しから抽出する方式は廃止。compile stage で LLM が生成したタイトルを `WikiFrontmatter.title`（必須）に保持し、index stage はそれを直接参照する。理由: 最初の section 見出し（例「立ち回りモードの明確な切り分け」）がページタイトルとして INDEX に並び、ページの主題が読み取れず参照性が低下したため。`_extract_title` ヘルパーは削除済み。以下は旧設計の記録。

順に試行する：

1. 本文の最初の `## ` 見出し（行頭マッチ）の見出しテキスト
2. 本文の最初の `# ` 見出し（行頭マッチ）の見出しテキスト
3. frontmatter の `subtopic` の値（フォールバック）

`## ` で始まる行があれば、その後の文字列（先頭・末尾の空白を `strip`）をタイトルとする。

### 5.2 サマリ

タイトル抽出に使った見出し行の直後から走査し、最初の非空・非見出し段落を取得。

その段落から **最初の 1 文** を切り出す。文末は以下のいずれか：
- 日本語句点 `。`
- ASCII ピリオド `.`（後ろが空白または改行）

最終文字列が **120 文字を超える場合**（Python `len()` による Unicode コードポイント数で計測）、先頭 120 文字を残し末尾に `…` を付与する（結果 121 文字）。

本文が空、または非空段落が見つからない場合のサマリは `(本文なし)`。

### 5.3 例

入力（本文）：
```
## 海女美術 右高台の制圧

右高台はリスクと裏取り誘発を伴うため慎重に判断する。守備時の応用は別途。

## セクション
...
```

抽出結果：
- タイトル: `海女美術 右高台の制圧`
- サマリ: `右高台はリスクと裏取り誘発を伴うため慎重に判断する。`

## 6. 再生成の方針

- **毎回フル再生成**（差分マニフェストを使わない）
- すべての `README.md` を毎回上書き
- カテゴリディレクトリが空でも README は生成（「ページ一覧」が空状態のテンプレで）
- ステージ実行が冪等（同じ入力なら同じ出力）

理由：

- ページ数や追加・削除のたびに再生成コストはミリ秒オーダー（LLM 不要）
- マニフェスト管理のオーバーヘッドが価値を上回らない
- diff_commit ステージが `git status` で変更検知するため、READMEs に変化なければコミット差分は出ない

## 7. ファイル構成

新規追加：

- `pipeline/stages/index.py` — `run(*, wiki_dir, categories)` を提供
- `tests/stages/test_index.py` — ユニットテスト

既存変更：

- `pipeline/main.py` — `STAGE_NAMES` に `"index"` 追加、`_run_stage` に分岐追加
- `tests/test_main_cli.py` — `--stage index` を受理することのテスト追加（任意）

## 8. テスト方針

`tests/stages/test_index.py`：

1. **複数カテゴリ・複数ページの正常系**
   - fixture: 2 カテゴリ × 各 2 ページ + 1 カテゴリ × 0 ページ
   - 期待: トップレベル README にカテゴリ 3 件、各カテゴリ README が正しく生成

2. **タイトル抽出のフォールバック**
   - 本文に `##` 見出しなし → frontmatter の `subtopic` を使用

3. **サマリ抽出**
   - 120 文字超過のサマリが切り詰められること
   - 本文空のページが `(本文なし)` を返すこと

4. **空カテゴリ**
   - `wiki/<category>/` ディレクトリが存在しない場合も "0 ページ" 表示

5. **再生成の冪等性**
   - 2 回連続実行しても出力が同一

## 9. 受入基準

- `uv run python -m pipeline.main --stage index` が成功し、`wiki/README.md` と `wiki/<category>/README.md` が生成される
- 既存テスト（42 件）+ 新規 index テストがすべて pass
- `ruff check` / `ruff format --check` がクリーン
- `--all` で実行したとき、`compile` の後・`diff` の前に index が走る
