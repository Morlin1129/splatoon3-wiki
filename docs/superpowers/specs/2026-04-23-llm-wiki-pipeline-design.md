# LLM Wiki 生成パイプライン 設計書

- **日付**: 2026-04-23
- **リポジトリ**: git@github.com:Morlin1129/splatoon3-wiki.git
- **対象**: サブプロジェクト #1 ／全 4 サブプロジェクト中の最初

## 1. 背景と全体ロードマップ

本プロジェクトは、Splatoon 3 のナレッジを Karpathy の LLM Wiki 思想に沿って運用する Wiki システムである。原典（Discord チャットログ／議事録／コーチング記録）から LLM が普遍的ナレッジを抽出・編纂し、GitHub Pages として公開する。

### 全体サブプロジェクト（優先順）

1. **LLM Wiki 生成パイプライン**（本設計書）
2. Discord クローラ（Docker）
3. 静的サイト／GitHub Pages 土台
4. E2E 最小版（#1〜#3 の接続）

### 本サブプロジェクトのゴール

Python 製パイプラインが、手元のサンプル原典 MD から Wiki ページ MD を生成できること。次サブプロジェクトで Google Drive 連携・Discord クローラ・GitHub Pages を接続する受け皿となる MD 構造とディレクトリ規約を確立する。

### 非スコープ

- Google Drive API 連携
- Discord クローラ実装
- GitHub Pages デプロイ設定
- GitHub Actions ワークフロー
- Tier 表、パッチ履歴、サーモンラン、大会・プレイヤー情報、個別コーチングページ

## 2. カテゴリ体系（MECE）

### 一次コンテンツ（原典から直接生成）

- **① 原理原則** — ルール・ステージ・ブキ非依存の普遍理論（人数有利の作り方と維持／ヘイト管理／オブジェクト関与）
- **② ルール×ステージ** — ルール×ステージ固有の定石（初動の動き／打開・固めのルート／リスポーン復帰ルート）
- **③ ブキ・役割** — ブキ／サブ／スペシャル／ロール固有のノウハウ（立ち回り、スペ合わせ、ギアパワー構成を含む）

### 二次コンテンツ（①②③の参照で構成されるキュレーション）

- **④ ステップアップガイド** — XP1800-2400 向けに ①②③ から抽出したエッセンス集

### リファレンス

- **⑤ 用語集** — スプラトゥーン用語／FPS・TPS 用語

### 分類戦略

- **大カテゴリ（①〜⑤）は固定**。`config/categories.yaml` に定義。
- **サブトピック（ページ単位）は LLM が発見・命名**。例: ②配下に `海女美術_ガチエリア.md` が LLM 判断で生成される。

### Wiki に載せないもの（原典側にのみ保持）

- 個別コーチング記録（特定メンバー宛てのフィードバック）
- プレイヤー個別評価・プロフィール
- Discord での生発言（実名・ハンドル付き）

Ingest ステージで LLM が普遍化・匿名化した上で抽出するため、Wiki 側には個人特定情報が残らない。

## 3. データフロー

```
Drive (raw)          Repo                                  GitHub Pages
─────────────        ────────────────────────────────      ────────────
原典データ     →     [1] Ingest (LLM)
(chat/議事録)          ↓
                     snippets/*.md   ← 中間物①
                       ↓
                     [2] Classify (LLM)
                       ↓
                     classified/<カテゴリ>/*.md  ← 中間物②
                       ↓
                     [3] Cluster (code)
                       ↓
                     state/clusters.json
                       ↓
                     [4] Compile (LLM)
                       ↓
                     wiki/<カテゴリ>/<subtopic>.md  ← 最終物
                       ↓
                     [5] Diff & Commit                    → (将来) deploy
```

### 設計原則

- **中間生成物は Markdown**。JSON で内部状態化せず、目視レビュー・手直しが容易な形を保つ。
- **各ステージは独立に再実行可能**。失敗したステージから再開可能。
- **LLM 呼び出しはステージごとにプロバイダ／モデルを切替可能**。コスト最適化。

## 4. ディレクトリ構造

```
splatoon3-wiki/
├── pipeline/                  # Python パイプライン本体
│   ├── stages/
│   │   ├── ingest.py
│   │   ├── classify.py
│   │   ├── cluster.py
│   │   └── compile.py
│   ├── llm/                   # LLM プロバイダ抽象
│   │   ├── base.py
│   │   ├── anthropic_provider.py
│   │   └── gemini_provider.py
│   ├── prompts/               # 各ステージのシステムプロンプト (MD)
│   │   ├── ingest.md
│   │   ├── classify.md
│   │   └── compile.md
│   └── main.py                # エントリポイント
├── config/
│   ├── categories.yaml        # ①〜⑤ の定義
│   └── pipeline.yaml          # ステージ別プロバイダ・モデル指定
├── raw_cache/                 # (.gitignore) Drive 取得物の一時キャッシュ
├── sample_raw/                # MVP 用サンプル原典 MD（コミット対象）
├── snippets/                  # Stage 1 出力
├── classified/                # Stage 2 出力
│   ├── 01-principles/
│   ├── 02-rule-stage/
│   ├── 03-weapon-role/
│   ├── 04-stepup/
│   └── 05-glossary/
├── wiki/                      # Stage 4 出力（将来の Pages ソース）
│   └── 01-principles/ ...
├── state/
│   ├── ingest_manifest.json   # 処理済み原典 ID + hash
│   └── clusters.json          # subtopic → snippet paths
├── tests/
└── pyproject.toml
```

### ポイント

- `snippets/` と `classified/` もコミット対象。差分レビューが容易。
- `wiki/` は将来の静的サイトがそのまま読むディレクトリ。
- Drive 連携は `pipeline/stages/ingest.py` の入力部を差し替えるだけで対応可能。

## 5. 各ステージの仕様

### Stage 1: Ingest（LLM）

- **入力**: `sample_raw/*.md`（MVP）／将来は Drive から取得した `raw_cache/*.md`
- **LLM タスク**: 原典 MD を読み、ナレッジに関わる断片を抽出して複数の短文 MD に分割する
- **出力**: `snippets/YYYY-MM-DD-<slug>.md`
  - frontmatter: `source_file`, `source_date`, `extracted_at`, `content_hash`
  - 本文: 1 テーマに関する簡潔な記述
- **システムプロンプト方針**: 「原典から普遍化可能な知見のみを抽出する。個人名・Discord ハンドル・実名・固有 ID は含めない。特定個人への助言は普遍的原則として書き換える」
- **機微情報ハンドリング**: MVP では LLM プロンプト任せ。運用で漏れが見つかった段階で post-filter（正規表現）を追加する。

### Stage 2: Classify（LLM）

- **入力**: `snippets/` の未分類 MD（manifest と突き合わせて未処理のもの）
- **LLM タスク**: 各スニペットに `category`（① 〜 ⑤）と `subtopic`（LLM 命名のスラッグ）を付与
- **出力**: `classified/<カテゴリ>/<同 slug>.md`
  - frontmatter に `category`, `subtopic` を追記。本文は不変。

### Stage 3: Cluster（コードのみ、LLM 不使用）

- **入力**: `classified/` 全体
- **処理**: 各 `(category, subtopic)` ごとにスニペットファイルパス一覧を集約
- **出力**: `state/clusters.json` — `{ "02-rule-stage/海女美術_ガチエリア": ["classified/02-rule-stage/2026-04-22-xxx.md", ...] }`

### Stage 4: Compile（LLM）

- **入力**: `state/clusters.json` から「前回以降にスニペット集合が変化した subtopic」を選択。そのスニペット群をまとめて読み込む。
- **LLM タスク**: subtopic ごとに Wiki ページ MD を生成する。構成・見出し・要点を整理し、出典一覧を末尾に付ける。
- **出力**: `wiki/<カテゴリ>/<subtopic>.md`
  - frontmatter: `category`, `subtopic`, `sources`（Drive URL 配列）, `updated_at`
  - 本文末尾: 出典セクション（frontmatter の `sources` を Markdown リンクに展開したもの。読み手が URL にクリックで飛べるようにするための冗長化）
  - 閲覧には Drive の権限が必要

### Stage 5: Diff & Commit

- **処理**: `wiki/` 配下の Git 差分を検出し、変更があればコミット。
- **MVP**: 手動 push まで。本サブプロジェクトでは GitHub Actions 化は行わない。
- **将来**: push → Pages 自動デプロイを次サブプロジェクトで接続。

### 差分再生成ロジック

- `state/ingest_manifest.json` の構造:
  ```json
  {
    "raw": { "<raw_path>": { "content_hash": "...", "ingested_at": "..." } },
    "snippets": { "<snippet_path>": { "source_hash": "...", "classified": true } },
    "wiki": { "<wiki_path>": { "cluster_fingerprint": "..." } }
  }
  ```
- 各ステージの更新タイミング: ステージ完了時に自身の担当セクションを更新。ステージ失敗時は manifest を更新せず、再実行で同じ入力から再試行。
- 判定:
  - Ingest: `raw` セクションに無い or `content_hash` が変わった原典のみ処理
  - Classify: `snippets` セクションで `classified: false` のスニペットのみ処理
  - Compile: クラスタ内スニペットパス集合のハッシュ（`cluster_fingerprint`）が前回と異なる subtopic のみ再生成

## 6. LLM プロバイダ抽象

### インターフェース

```python
# pipeline/llm/base.py
from typing import Protocol, Literal

class LLMProvider(Protocol):
    def complete(
        self,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        response_format: Literal["text", "json"] = "text",
    ) -> str: ...
```

### 実装

- `anthropic_provider.py` — Anthropic SDK (`anthropic` パッケージ) 経由
- `gemini_provider.py` — Google Gen AI SDK (`google-genai` パッケージ) 経由
- OpenAI は将来追加（同インターフェースを実装するだけ）

### 設定例（`config/pipeline.yaml`）

```yaml
stages:
  ingest:
    provider: gemini          # Flash で安価に大量処理
    model: gemini-2.5-flash
    max_tokens: 4096
  classify:
    provider: gemini
    model: gemini-2.5-flash
    max_tokens: 512
  compile:
    provider: anthropic       # Sonnet で品質重視
    model: claude-sonnet-4-6
    max_tokens: 8192
```

- API キーは環境変数から読む: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`。
- ステージ単位で provider / model を切替可能。

## 7. テスト戦略

- **Stage 単体テスト**: 各ステージに固定 fixture を渡し、出力 MD のスキーマと frontmatter 必須フィールドを検証。
- **LLM モック**: 単体テスト内では `LLMProvider` のスタブ実装を使い、決定的に。
- **E2E ゴールデンテスト**: `sample_raw/` を数件用意し、実 LLM で全ステージを走行。生成 MD の存在・カテゴリ分布を確認（内容の厳密比較はしない）。
- **手動スモーク**: `make run-sample`（または同等コマンド）で `sample_raw/` を流し、`wiki/` の git diff を目視確認。

## 8. 技術スタック

- **言語**: Python 3.12+
- **依存管理**: `uv`
- **主要ライブラリ**:
  - `anthropic` — Claude API
  - `google-genai` — Gemini API
  - `pydantic` — frontmatter スキーマ定義
  - `python-frontmatter` — MD frontmatter の読み書き
  - `pyyaml` — 設定ファイル
  - `pytest` — テスト
- **Lint / Format**: `ruff`
- **エントリポイント**:
  - 単一ステージ: `uv run python -m pipeline.main --stage <ingest|classify|cluster|compile|diff>`
  - 全ステージ一括: `uv run python -m pipeline.main --all`

## 9. セキュリティと運用

- Drive の原典には個人名・ハンドルが含まれるため、**Wiki リポジトリからは Drive URL を出典として載せるのみ**。URL はアクセス権があれば閲覧可、無ければ 404。
- API キーは `.env` で管理し、`.gitignore` に含める。
- `raw_cache/` も `.gitignore`。MVP でコミットする原典サンプルは個人情報を含まない合成データを用いる。
