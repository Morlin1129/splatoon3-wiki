# Wiki 知識統合（Subtopic Consolidation）設計書

- **日付**: 2026-04-26
- **対象**: サブプロジェクト #1 への変更（既存 stage 修正 + 新 stage 追加）
- **関連 spec**:
  - [2026-04-23-llm-wiki-pipeline-design.md](2026-04-23-llm-wiki-pipeline-design.md)
  - [2026-04-24-wiki-index-design.md](2026-04-24-wiki-index-design.md)

## 1. 背景と目的

現状のパイプラインは、新しいスニペットが追加されると `wiki/02-rule-stage/2026-04-26-baigai-area-left-drop-visibility.md` のような **日付プレフィックス付きの単発ページ** を量産する傾向がある。本来 Wiki は「ログの積み重ね」ではなく「**普遍的な知識の集合体**」であるべきだが、現在の生成挙動は前者に近い。

本設計は、Wiki ページが「日付付き個別事象」ではなく「**長期的に成長・統合される知識単位**」となるよう、subtopic の管理機構を見直す。

### 1.1 上位の目的（プロジェクト方針）

- **自動化重視**: 社内に散らばる情報を自動収集・統合して参照性を高める。手動承認やレビューゲートは入れない。
- **原典トレーサビリティ**: 多少の情報ゆらぎは許容する。原典に立ち戻れる原則（既存の `sources` frontmatter）が維持されていればよい。
- **AI 検索適性**: AI が Wiki を読み、RAG とは違う検索アプローチで活用できる構造を保つ。
- **YAGNI**: 監査ログ・承認ワークフロー・role separation 等のエンタープライズ重装備は今は入れない。

## 2. 現状の挙動と問題

### 2.1 観察された症状

`state/clusters.json` に以下の二極化が生じている:

**良い例（汎用 slug）:**
- `01-principles/dakai-fundamentals` ← 2 snippets を集約
- `03-weapon-role/splash-shield-usage`

**悪い例（日付付き slug、singleton）:**
- `01-principles/2026-04-26-general-dakai-home-base-clearing`
- `02-rule-stage/2026-04-26-baigai-area-left-drop-visibility`

### 2.2 根本原因

[pipeline/stages/classify.py:46-48](../../../pipeline/stages/classify.py) で classify ステージが LLM に渡す「既存サブトピック」の内容が誤っている:

```python
known_subtopics = [
    p.stem for cat_dir in classified_dir.glob("*/") for p in cat_dir.glob("*.md")
]
```

これは **classified ファイルの stem**（= snippet ファイル名と同一、つまり `2026-04-26-...` 形式）を返している。本来は frontmatter の `subtopic` 値を集めて渡すべき。

LLM はこのリストを「既存サブトピック」と解釈し、「再利用可能ならする」と指示されるので、日付プレフィックス付き名前を「既存パターン」として模倣・再生産する。

加えて、classify プロンプトに「日付・個別事象を含めない」「既存に類似なら必ず再利用」という保守的判断の指示がない。

### 2.3 設計レベルの不足

技術的バグ以外に、以下の機構が不在:

- **subtopic の重複・類似を統合する工程がない**（classify は per-snippet 判断のみ）
- **subtopic 改名時の URL 維持手段がない**（廃止 subtopic は単に消えるとリンク切れ）

## 3. 設計方針

### 3.1 採用する方向性

- **subtopic 命名は LLM による自動拡張型**（手動キュレーションは運用負荷が高い）
- **専用の consolidate stage を追加** し、subtopic の統合・改名を自動化
- **「保守的に判断せよ」を LLM プロンプトに明記** し、無闇な改名を抑止
- **廃止 subtopic は tombstone md として残す**（Wikipedia リダイレクトと同様）

### 3.2 採用しないもの（YAGNI）

- 承認ワークフロー（dry-run → approval → apply 方式）
- 監査ログ（`state/audit/*.jsonl` 等）
- frontmatter `aliases` フィールドによるリダイレクト（tombstone で代替）
- 閾値ベースの consolidate トリガー（毎回実行で十分、保守判断は LLM 側で吸収）
- 役割分離（actor identity / SSO 統合）

## 4. スコープと非スコープ

### スコープ

- classify stage のバグ修正（`known_subtopics` の生成方法を frontmatter ベースに変更）
- classify プロンプトの強化（保守的命名指示の追加）
- 新ステージ `consolidate` の追加
- consolidate プロンプトの作成（保守的判断を強く促す）
- tombstone md の生成機構
- 既存の日付付き subtopic（7 件）の移行（consolidate を一度走らせて整理）
- pipeline.yaml への consolidate stage 設定追加

### 非スコープ

- snippet ファイル名・classified ファイル名の変更（ingest 由来の不変 ID として維持）
- wiki frontmatter スキーマの拡張（`aliases` 等）
- 監査ログ機構
- 承認ワークフロー機構
- consolidate の閾値トリガー
- 静的サイト側でのリダイレクト処理（サブプロ #3 で対応）

## 5. CLI / パイプライン位置

新ステージ `consolidate` を classify と cluster の間に追加する:

```
ingest → classify → consolidate → cluster → compile → index → diff
```

理由:

- classify が新規 subtopic を生成した直後に consolidate が判断する流れが自然
- consolidate が classified の frontmatter `subtopic` を書き換えると、後続の cluster がその新しい subtopic でグルーピングする
- compile はクラスタ単位で wiki ページを生成するので、consolidate の結果が自動で wiki に反映される

`pipeline/main.py` の `STAGE_NAMES` に `"consolidate"` を追加し、`_run_stage("consolidate", root)` を実装する。`pipeline.yaml` の `stages` セクションに consolidate のモデル設定を追加する。

## 6. 各コンポーネントの変更

### 6.1 classify stage の修正

**バグ修正**: [pipeline/stages/classify.py](../../../pipeline/stages/classify.py) の `known_subtopics` 生成を、frontmatter から読むように変更:

```python
known_subtopics = []
for cat_dir in classified_dir.glob("*/"):
    for p in cat_dir.glob("*.md"):
        fm, _ = read_frontmatter(p, ClassifiedFrontmatter)
        if fm is not None:
            known_subtopics.append(fm.subtopic)
```

**プロンプト強化**: [pipeline/prompts/classify.md](../../../pipeline/prompts/classify.md) に以下を追加:

- subtopic は「**普遍的・長期的に成長しうる知識単位**」を表す名前にする
- **日付・個別事象・session 情報を slug に含めない**（例: `2026-04-26-general-...` ❌、`dakai-fundamentals` ✅）
- 既存 subtopic に類似する場合は **必ず再利用** する
- 既存に類似がなく、明らかに新規概念の場合のみ新規生成する

### 6.2 consolidate stage の新設

新規ファイル: `pipeline/stages/consolidate.py`、`pipeline/prompts/consolidate.md`。

#### 入力

- 全 classified MD（`classified/<category>/*.md`）の frontmatter `subtopic` 一覧
- 各 subtopic に属する snippet 数

#### 処理

1. カテゴリごとに、現在の subtopic 一覧 + snippet 数を集計
2. LLM に保守的判断プロンプトで送信、rename map（JSON）を取得
3. rename map が空でなければ:
   - 該当 classified MD の frontmatter `subtopic` を新値に書き換え
   - 統合元の wiki ページを tombstone に置き換え（後述）
   - `state/consolidate_log.md` に追記（人間可読）

#### 出力

- 修正された classified MD（frontmatter のみ書き換え、本文は不変）
- tombstone wiki MD（旧 subtopic の wiki ページを上書き）
- `state/consolidate_log.md`（追記、Markdown 形式）

#### LLM 出力フォーマット

JSON のみ:

```json
{
  "renames": [
    {
      "category": "01-principles",
      "from": "2026-04-26-general-dakai-home-base-clearing",
      "to": "dakai-fundamentals",
      "reason": "打開時の自陣処理は dakai-fundamentals の範疇"
    }
  ]
}
```

`renames` が空配列の場合は何も変更しない（保守的判断の正常結果）。

### 6.3 tombstone 機構

統合元の wiki ページ（例: `wiki/01-principles/2026-04-26-general-dakai-home-base-clearing.md`）を以下のテンプレートで上書きする:

```markdown
---
title: "統合済み: 2026-04-26-general-dakai-home-base-clearing"
category: 01-principles
subtopic: 2026-04-26-general-dakai-home-base-clearing
sources: []
updated_at: 2026-04-26T14:32:00+00:00
tombstone: true
merged_into: dakai-fundamentals
merged_at: 2026-04-26T14:32:00+00:00
---

# 統合済み: 2026-04-26-general-dakai-home-base-clearing

このページは [dakai-fundamentals](dakai-fundamentals.md) に統合されました。

統合理由: 打開時の自陣処理は dakai-fundamentals の範疇
```

要件:

- ファイルパスは保持（既存 URL を壊さない）
- frontmatter `tombstone: true` は機械判別用フラグ
- 統合先へのリンクは Markdown 相対リンク（GitHub UI ・各種 viewer で動作）
- index stage は tombstone を「ページ一覧」から除外する（後述 6.5）

### 6.4 wiki frontmatter モデルの拡張

[pipeline/models.py](../../../pipeline/models.py) の `WikiFrontmatter` に optional フィールドを追加（既存の `title` フィールドは維持）:

```python
class WikiFrontmatter(BaseModel):
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    subtopic: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    updated_at: datetime
    tombstone: bool = False
    merged_into: str | None = None
    merged_at: datetime | None = None
```

通常の wiki ページは `tombstone=False` のまま、tombstone ページは `tombstone=True` + 関連フィールドが入る。

tombstone ページの `title` は consolidate stage が `"統合済み: <旧 subtopic>"` 形式で構築する（LLM 不使用）。

### 6.5 index stage の修正

[pipeline/stages/index.py](../../../pipeline/stages/index.py) で「ページ一覧」生成時に **tombstone を除外** する:

```python
for path in sorted(category_dir.glob("*.md")):
    if path.name == "README.md":
        continue
    fm, _ = read_frontmatter(path, WikiFrontmatter)
    if fm is not None and fm.tombstone:
        continue
    # ... 通常処理
```

トップレベル `wiki/README.md` のページ数カウントも tombstone を除外する。

### 6.6 compile stage への影響

[pipeline/stages/compile.py](../../../pipeline/stages/compile.py) は subtopic ごとに wiki ページを上書き生成するため、consolidate により subtopic が変わった classified MD は次の compile で正しい統合先ページに合流する。

ただし **tombstone ページ自身は compile の対象外** にする必要がある:

- compile の入力は `state/clusters.json`
- cluster は classified の frontmatter `subtopic` でグルーピングするので、廃止 subtopic はもはや cluster に出現しない
- → compile が tombstone を上書きすることはない（自然に保護される）

ただし「以前は compile が生成していたが、もう cluster に存在しない subtopic」の wiki ページが残ることがある。これが consolidate stage で tombstone に書き換えるべきページであり、consolidate stage が責任を持つ。

## 7. データフロー

```
[新スニペット追加]
        ↓
ingest      （snippet MD 生成、ファイル名は date-prefix のまま）
        ↓
classify    （category + subtopic を frontmatter に書く。
             既存 subtopic 一覧は frontmatter から正しく取得）
        ↓
consolidate （新規 subtopic を含む全体を LLM が見て、
             保守的に統合判断。renames.json を生成、
             classified frontmatter を書き換え、
             統合元 wiki ページを tombstone 化）
        ↓
cluster     （classified の subtopic でグルーピング、clusters.json）
        ↓
compile     （cluster ごとに wiki ページ生成。
             tombstone ページには触れない）
        ↓
index       （README 生成。tombstone をページ一覧から除外）
        ↓
diff        （git commit）
```

## 8. プロンプト戦略

### 8.1 classify プロンプト追記内容

```
subtopic 命名のルール（重要）:

- subtopic は「普遍的で長期的に成長しうる知識単位」を表す名前にする
- 日付・個別事象・session 情報を slug に含めない:
  - ❌ "2026-04-26-general-dakai-home-base-clearing"
  - ✅ "dakai-fundamentals"
- 既存 subtopic に類似する内容なら、必ず既存を再利用する
- 既存に類似がなく、明らかに新規概念の場合のみ新規生成する
- 迷ったら、最も近い既存 subtopic を選ぶ
```

### 8.2 consolidate プロンプト全文（新規作成）

```
あなたは Wiki の subtopic 一覧を見て、統合や改名が必要かを判断する。

入力:
- カテゴリ ID
- 現在の subtopic 一覧（各 subtopic に属する snippet 数つき）

タスク: 統合や改名すべき subtopic を判定し、rename map を返す。

【統合・改名が望ましい強い基準】
- 明らかに同じ概念を別名で呼んでいる
  （例: "dakai-fundamentals" と "dakai-principles"）
- 一方が他方の完全な部分集合で、独立した粒度を持たない
- 日付や個別事象を含む slug が、既存の汎用 slug に明確に該当する
  （例: "2026-04-26-general-dakai-home-base-clearing" が
        "dakai-fundamentals" の範疇）

【統合してはいけない弱い基準】
- 「似ている気がする」程度の主観的判断
- 概念の重複が部分的にしかない
- 統合先の wiki ページが大きくなりすぎる懸念がある
- 判断に迷う

迷ったら「変更なし」を選ぶ。Wiki の安定性は変更の活発さより重要。

出力形式: JSON のみ、以下の形式で返す。

{"renames": [
  {
    "category": "<category-id>",
    "from": "<old-subtopic>",
    "to": "<new-subtopic>",
    "reason": "<1 文で統合理由>"
  }
]}

統合・改名が不要な場合は {"renames": []} を返す。
```

### 8.3 consolidate_log.md フォーマット

`state/consolidate_log.md` に毎回の実行結果を追記:

```markdown
## 2026-04-26T14:32:00+00:00

3 件の subtopic を統合した。

- `01-principles/2026-04-26-general-dakai-home-base-clearing` → `01-principles/dakai-fundamentals`
  - 理由: 打開時の自陣処理は dakai-fundamentals の範疇
- `01-principles/2026-04-26-general-osae-waiting-actions` → `01-principles/osae-fundamentals`
  - 理由: 抑え時の待機行動は新規トピックとして集約

---
```

renames が空の場合は追記しない（ノイズを避ける）。

## 9. 既存データの移行

現在 7 件の日付付き subtopic が存在する（`state/clusters.json` 参照）。本機能のリリース後、`uv run python -m pipeline.main --stage consolidate` を一度走らせて整理する。LLM 判断で統合不要となった subtopic は、現状の名前のままで残る（必要に応じて手動でリネーム）。

移行用の専用スクリプトは作らない。consolidate stage 自体が冪等な再実行可能ツールとなるため、それを使う。

## 10. ファイル構成

### 新規追加

- `pipeline/stages/consolidate.py` — `run(*, provider, stage_cfg, ...)` を提供
- `pipeline/prompts/consolidate.md` — システムプロンプト
- `tests/stages/test_consolidate.py` — ユニットテスト

### 既存変更

- `pipeline/stages/classify.py` — `known_subtopics` 生成のバグ修正
- `pipeline/prompts/classify.md` — 命名ルール追記
- `pipeline/main.py` — `STAGE_NAMES` に `"consolidate"` 追加、`_run_stage` 分岐追加
- `pipeline/stages/index.py` — tombstone 除外ロジック追加
- `pipeline/models.py` — `WikiFrontmatter` に tombstone 関連フィールド追加
- `config/pipeline.yaml` — `stages.consolidate` 設定追加（provider / model / max_tokens）
- `tests/stages/test_classify.py` — `known_subtopics` 修正に伴うテスト更新
- `tests/stages/test_index.py` — tombstone 除外のテスト追加

### 既存維持

- snippet ファイル名・classified ファイル名は触らない（ingest 由来 ID）
- frontmatter モデル `SnippetFrontmatter` / `ClassifiedFrontmatter` は変更なし
- `state/clusters.json` の構造は変更なし（cluster stage の出力フォーマットそのまま）

## 11. テスト方針

### 11.1 classify stage のテスト更新

- `known_subtopics` が frontmatter の `subtopic` から取得されることを検証
- 既存テストの fixture が classified MD の frontmatter を正しく持つよう調整

### 11.2 consolidate stage のテスト

`tests/stages/test_consolidate.py`:

1. **renames が空の場合の no-op**
   - LLM が `{"renames": []}` を返したとき、ファイル変更がないこと

2. **統合の正常系**
   - 2 つの subtopic A, B のうち A→B の rename map を LLM が返したとき:
     - A に属する classified MD の frontmatter `subtopic` が B に書き換わる
     - 旧 wiki ページ A.md が tombstone に書き換わる
     - tombstone の `merged_into` が B である
     - `state/consolidate_log.md` に追記される

3. **複数カテゴリの混在**
   - 異なるカテゴリの rename が同時に処理されること

4. **冪等性**
   - 1 回目で統合された後、2 回目実行で再度 LLM が `{"renames": []}` を返せば変更がないこと

5. **無効な rename の拒否**
   - LLM が存在しない subtopic を `from` に指定したとき、`ValueError` を送出してパイプラインを止める
   - LLM が存在しないカテゴリを指定したとき、`ValueError` を送出

### 11.3 index stage のテスト追加

- tombstone wiki ページがページ一覧から除外されること
- カテゴリのページ数カウントが tombstone を除外すること

### 11.4 E2E テスト

[tests/test_end_to_end.py](../../../tests/test_end_to_end.py) に consolidate stage を含むフローを追加。FakeProvider に consolidate 用の応答を加え、`--all` 実行で全ステージが順に走ることを検証。

## 12. 受入基準

- `uv run python -m pipeline.main --stage consolidate` が成功する
- `uv run python -m pipeline.main --all` が ingest → classify → consolidate → cluster → compile → index → diff の順で実行される
- 既存テスト（〜45 件）+ 新規 consolidate / index / classify テストがすべて pass
- `ruff check` / `ruff format --check` がクリーン
- 既存 7 件の日付付き subtopic に対して `--stage consolidate` を一度走らせ、`state/consolidate_log.md` に統合結果が記録される（実行は本実装後に手動で行う）
- tombstone 化された wiki ページが `wiki/<category>/` 配下に残り、index 生成時に「ページ一覧」から除外される
- 既存の URL（`wiki/01-principles/2026-04-26-general-dakai-home-base-clearing.md` 等）にアクセスしても 404 にならず、tombstone 経由で統合先に誘導される

## 13. 既知の制約と将来課題

- **LLM 判断のゆらぎ**: consolidate プロンプトで保守的判断を強く促すが、サンプリング温度等で同じ入力でも異なる判定が出る可能性がある。tombstone 機構が最終防衛線となるため、実害は URL 維持の範囲で吸収される。
- **tombstone の無限増殖**: 長期運用で tombstone が増えると `wiki/<category>/` のファイル数が膨らむ可能性がある。index は除外するため目視ノイズは最小だが、将来的に「N か月以上前の tombstone は削除」等のポリシーが必要になるかもしれない（今は YAGNI）。
- **連鎖的統合**: A→B、B→C と段階的に統合された場合、A の tombstone は B を指すが B の tombstone は C を指す。読者は 2 ホップで C にたどり着くが、tombstone を再 consolidate して直接 C を指す形に書き換える機構は今は持たない（必要なら将来追加）。
