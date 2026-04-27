# Follow-ups — LLM Wiki Pipeline

サブプロジェクト #1（本リポジトリ）の最終コードレビューで挙がった、未対処の項目を記録する。優先度別に整理。

## Important（次サブプロの接続前に対処）

### 1. `main.py` の `source_urls={}` ハードコード

**所在**: [pipeline/main.py](pipeline/main.py) の Compile ステージ呼び出し (`_run_stage("compile", ...)`) で `source_urls={}` が固定で渡される。

**影響**: Compile の出力 `wiki/<category>/<subtopic>.md` は `## 出典` セクションが常に空。フロントマターの `sources` フィールドも空リストのまま。

**いつ対処するか**: サブプロ #2（Discord クローラ／Drive 連携）で Drive URL マップが利用可能になったとき。CLI に `--source-urls-file <path>` オプションを追加するか、`config/pipeline.yaml` に `source_urls_file` を追記してそこから読む想定。

## Important（次サブプロの接続前に対処）

### 1b. consolidate stage の操作順序: tombstone → frontmatter rewrite に反転

**所在**: [pipeline/stages/consolidate.py](pipeline/stages/consolidate.py) の `run()` 内 apply ループ。現状は `_rewrite_classified_subtopic` → `_tombstone_wiki_page` の順。

**影響**: tombstone 書き込みでディスクエラー等が発生した場合、classified frontmatter は新 subtopic に書き換わっているのに古い wiki ページがそのまま残る → URL は古い内容を返し続ける（「stale page」状態）。次回 consolidate 実行では rename 対象自体が消えているのでリトライもされない。

**いつ対処するか**: consolidate stage を次に触るタイミング。順序反転のみ（コード行数は不変）。順序反転後は tombstone 書き込み失敗時に classified が変更されないため、次回実行で全リネームがリトライされ整合性が回復する。

## Minor（いつでも良いが覚えておく）

### 2. `tests/conftest.py` が未作成

**背景**: 実装プランではファイル構造に `tests/conftest.py` が列挙されていたが、結果的にどのテストも共通 fixture を必要としなかったため作成されていない。

**いつ対処するか**: サブプロ #4（E2E 最小版）で `git_repo` / `workspace` など複数テストで使う fixture を共有するタイミング。

### 3. ディレクトリ作成責務が `frontmatter_io` に漏れている

**背景**: 各ステージの `run()` は出力ディレクトリを事前に作成せず、`write_frontmatter()` 内の `path.parent.mkdir(parents=True, exist_ok=True)` に依存している。動作はするが、ステージの責務境界としては不自然。

**いつ対処するか**: 次にステージコードを触るとき。各 `run()` の先頭で `snippets_dir.mkdir(...)` / `classified_dir.mkdir(...)` / `wiki_dir.mkdir(...)` を明示すると意図が明瞭になる。

### 4. E2E テストがハッピーパスのみ

**所在**: [tests/test_end_to_end.py](tests/test_end_to_end.py)。1 スニペット 1 カテゴリのみ。

**不足シナリオ**:
- 複数カテゴリ・複数 subtopic 混在
- 同じ subtopic に属する複数スニペット（Cluster 集約の検証）
- Ingest 2 回目（hash 一致 → スキップ）の検証
- 変更ありスニペットだけ Compile が走ることの検証
- consolidate が実 rename を返すケース（現状は `{"renames": []}` のみ）
- consolidate が tombstone 化したページを index が wiki/<cat>/README.md から除外することの統合検証
- consolidate の冪等性（連続実行で 2 回目は no-op になること、spec 11.2 item 4）
- index ステージが E2E に含まれていない（`--all` の最後から 2 番目だが test_end_to_end.py は呼ばない）

**いつ対処するか**: サブプロ #4 で実 LLM と接続する前。バグが出るとコストがかさむ領域なので、その前に固めておく。

### 5. `tests/test_llm_parsing.py:45` の E501（line too long）

**所在**: [tests/test_llm_parsing.py:45](tests/test_llm_parsing.py)。`ruff check .` で唯一残る既存違反。

**いつ対処するか**: lint 完全クリーン化のついで。1 行を 2 行に分割するか `# noqa: E501` を理由付きで付ける。

### 6. consolidate stage の `--dry-run` オプション

**背景**: 現状 `--stage consolidate` は即時に classified frontmatter と wiki ページを書き換える。「Manual Migration」の運用は git checkout で revert する前提だが、適用前にリネーム計画を見たいケースで `--dry-run` フラグがあると安心感が出る。

**いつ対処するか**: 運用で「予期せぬリネーム」が一度でも起きたら追加を検討。現状は YAGNI として保留。

---

## 対処済み（履歴）

- **Important #1: AnthropicProvider が `response_format="json"` を無視** — 2026-04-24 修正。システムプロンプトに JSON 強制指示を追記するフォールバックを追加。Gemini は `response_mime_type` で native 対応済み。
- **Important #2: `assert fm is not None` の本番利用** — 2026-04-24 修正。3 箇所（classify.py / cluster.py / compile.py）を `if fm is None: raise RuntimeError(...)` に置換。`-O` フラグ対策。
