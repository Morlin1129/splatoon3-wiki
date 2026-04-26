# splatoon3-wiki

LLM が生成する Splatoon 3 ナレッジ Wiki。原典（Discord チャットログ・議事録など）から普遍化ナレッジを抽出・編纂して公開する仕組みの、**サブプロジェクト #1: 生成パイプライン**。

## 全体構成（将来の 4 サブプロジェクト）

1. **LLM Wiki 生成パイプライン**（本リポジトリ）
2. Discord クローラ（Docker）
3. 静的サイト／GitHub Pages 土台
4. E2E 最小版

## 前提

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Anthropic API キー（Claude）と Google Gen AI API キー（Gemini）

## セットアップ

```bash
uv sync --extra dev
cp .env.example .env
# ANTHROPIC_API_KEY と GEMINI_API_KEY を記入
```

## パイプライン実行

6 ステージ構成：Ingest → Classify → Cluster → Compile → Index → Diff。中間成果物はすべて Markdown。

```bash
# 単一ステージ
uv run python -m pipeline.main --stage ingest
uv run python -m pipeline.main --stage classify
uv run python -m pipeline.main --stage cluster
uv run python -m pipeline.main --stage compile
uv run python -m pipeline.main --stage index
uv run python -m pipeline.main --stage diff

# 全ステージ一括
uv run python -m pipeline.main --all
```

プロバイダ・モデルは `config/pipeline.yaml` で切替可能（stage ごとに anthropic / gemini / fake を指定）。

## ディレクトリ構造

```
pipeline/            # パイプライン本体
  stages/            # Ingest, Classify, Cluster, Compile, Index, Diff
  llm/               # Anthropic / Gemini / Fake プロバイダ抽象
  prompts/           # 各ステージのシステムプロンプト
config/              # categories.yaml (①〜⑤ 固定), pipeline.yaml (stage 設定)
sample_raw/          # サンプル原典 MD
snippets/            # Stage 1 出力（ナレッジ断片）
classified/          # Stage 2 出力（カテゴリ付与済み）
wiki/                # Stage 4 出力（公開 Wiki ページ）
state/               # 差分再生成用マニフェスト
tests/               # pytest スイート
```

## テスト／lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 設計ドキュメント

- 設計 spec: [docs/superpowers/specs/2026-04-23-llm-wiki-pipeline-design.md](docs/superpowers/specs/2026-04-23-llm-wiki-pipeline-design.md)
- 実装プラン: [docs/superpowers/plans/2026-04-24-llm-wiki-pipeline.md](docs/superpowers/plans/2026-04-24-llm-wiki-pipeline.md)
