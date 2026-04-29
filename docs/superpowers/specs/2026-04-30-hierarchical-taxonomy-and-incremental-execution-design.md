# 階層タクソノミー × 差分実行 設計書

- **日付**: 2026-04-30
- **対象**: サブプロジェクト #1（LLM Wiki 生成パイプライン）のコア機構刷新
- **関連 spec**:
  - [2026-04-23-llm-wiki-pipeline-design.md](2026-04-23-llm-wiki-pipeline-design.md)
  - [2026-04-24-wiki-index-design.md](2026-04-24-wiki-index-design.md)
  - [2026-04-26-wiki-knowledge-consolidation-design.md](2026-04-26-wiki-knowledge-consolidation-design.md)

## 1. 背景と目的

本パイプラインの本質は **「LLM 駆動の汎用ナレッジ集約パイプライン」** であり、Splatoon Wiki は最初のテナント（PoC 対象）に過ぎない。将来は社内ナレッジ（例: `業務マニュアル → 経理 → 売掛管理`）のような**深さ可変の階層**を扱うことになる。

現状は以下 2 点で将来要件を満たさない:

1. **階層が 2 段固定**: `category(固定5種) × subtopic(LLM が命名する自由文字列)` の 2 階層しか表現できない。深いツリーが必要なドメインでは、subtopic 名にスラッシュやコロンを詰め込む擬似階層になりがち。

2. **差分実行が部分的**: ingest と compile は manifest／fingerprint で増分対応済みだが、**consolidate は毎回全カテゴリ・全 subtopic を LLM に投げ直す**。classify も起動時に全 classified ファイルを走査して `known_subtopics` を構築する。数百〜数千ファイル規模で破綻する。

本設計はこの 2 つを同時に解決する。両者は補完関係にあり（後述 3.3）、別々に設計するより統合した方が筋が通る。

### 1.1 上位の目的（変更なし）

- **自動化重視**: 自動収集・統合・参照性。手動承認ゲートは入れない。
- **原典トレーサビリティ**: `sources` frontmatter は維持。
- **AI 検索適性**: 階層化により AI が文脈を理解しやすい構造に。
- **YAGNI**: エンタープライズ重装備は今は入れない。

## 2. スコープと非スコープ

### スコープ

- データモデル変更: `subtopic: str` → `path: list[str]`
- `categories.yaml` のスキーマ刷新（固定層・mode・enumerated 値を表現可能に）
- 各ステージ（classify/consolidate/cluster/compile/index）の path 対応
- 中間ノードの **静的索引 README** 自動生成（再帰）
- consolidate ステージの**カテゴリ単位スキップ**（path 頻度ハッシュベース）
- classify ステージの **`known_paths_cache`** 導入
- CLI に `--rebuild` フラグ追加
- Splatoon の `02-rule-stage` と `03-weapon-role` の多層化（PoC 検証）
- 既存データの自動移行

### 非スコープ（YAGNI として明確に除外）

- **中間ノードの LLM 生成ページ**（READMEは静的索引のみ）
- **プロンプト/モデルハッシュ追跡による自動再生成**（将来 TODO 化）
- **categories.yaml 値追加時の影響範囲ピンポイント再生成**（将来 TODO 化）
- **AI による更新範囲の自律選択**（究極形、超 YAGNI）
- **並列化 / 非同期化**（差分実行で十分速いはず。観測してから判断）
- **第 2 テナント（社内ナレッジ）の動作検証**（B のスコープ確立後に C として並走）
- **ローカル埋め込み・類似度ベースの絞り込み**

## 3. 設計方針

### 3.1 階層モデル: 案 3（ハイブリッド）

各カテゴリの **固定層を YAML で表現**し、それより深い層は LLM が自由命名する。固定層の各層は `enumerated`（値を列挙、LLM は選ぶだけ）または `open`（LLM が命名、consolidate で正規化）のいずれか。

**選択理由**:
- 案 1（全列挙）は Splatoon に最適だが、エンタープライズ用途で「中分類が 100 個」のようなケースで運用が破綻する
- 案 2（深さだけ宣言）は YAML が極小だが、Splatoon のような既知の閉集合タクソノミー（ブキ・ステージ）では LLM の名寄れに過剰依存する
- 案 3 は両方をカバーでき、「Splatoon は厳密、エンタープライズは緩く」を 1 つのスキーマで両立する

### 3.2 中間ノード: 静的索引 README のみ（案 C）

各中間階層には `README.md` を **index ステージが機械生成**する（リンク一覧 + メタ情報）。LLM は呼ばない。

**選択理由**:
- 案 A（フォルダのみ）は閲覧体験が弱い
- 案 B（LLM 生成）はノード数だけ LLM コールが増え、パフォーマンス問題と直撃する
- 案 C は閲覧性とコストのバランスが最良

将来「中間ノードに LLM 概要が欲しい」と判明したら、案 B を後付けで足せる。

### 3.3 差分実行を一等市民に

「全段全実行」前提を、各ステージが**自分の再実行範囲を判定**する設計に変える。

判定の単位は **データ単位のみ**（snippet hash, path 集合, cluster fingerprint）。設定単位（プロンプト/モデル/yaml）は追跡しない。設定変更時は明示的に `--rebuild` で全部やり直す方針（メンタルモデルが明確、実装軽い）。

#### 3.3.1 階層化と差分実行の補完関係

階層化で path 数は増えるが:
- **enumerated 層は consolidate 対象外** → 大半のカテゴリでスキップ可能
- **`path_frequency_hash` でカテゴリ単位のスキップ** → 変動のないカテゴリは LLM コールゼロ
- **`known_paths_cache`** → classify 起動時の全文走査を削除

結果として、階層化しても性能は悪化せず、むしろ差分実行の効果が際立つ。

## 4. データモデルの変更

### 4.1 Frontmatter

```python
# pipeline/models.py
class ClassifiedFrontmatter(SnippetFrontmatter):
    category: str            # 既存（トップ固定層 ID）
    path: list[str]          # 新: category 配下のフルパス
    # subtopic フィールドは削除
```

例:
```yaml
---
source_file: 2026-04-21-shooter-gear.md
content_hash: ...
category: 03-weapon-role
path:
  - シューター
  - スプラシューター
  - ギア構成
---
```

### 4.2 ファイル配置

```
wiki/
  03-weapon-role/
    シューター/
      README.md                    # 静的索引（index ステージ生成）
      スプラシューター/
        README.md                  # 静的索引
        ギア構成.md               # リーフ（compile ステージ生成）
        立ち回り.md
      ボールドマーカー/
        ...
```

### 4.3 Slug 化

固定層は `id`（半角英数）を YAML に持ち、それをパスに使う。LLM 自由層は **日本語のままディレクトリ名** にする（macOS / Linux / Git ともに UTF-8 で問題なし）。Windows サポートは現状非スコープ。

## 5. YAML スキーマ刷新

### 5.1 新スキーマ

```yaml
# config/categories.yaml
categories:
  - id: 01-principles
    label: 原理原則
    description: ルール・ステージ・ブキ非依存の普遍理論
    fixed_levels: []                     # 固定層なし、全部 LLM 任せ

  - id: 02-rule-stage
    label: ルール×ステージ
    description: ルール×ステージ固有の定石
    fixed_levels:
      - name: ルール
        mode: enumerated
        values:
          - id: area
            label: ガチエリア
          - id: yagura
            label: ガチヤグラ
          - id: hoko
            label: ガチホコ
          - id: asari
            label: ガチアサリ
          - id: nawabari
            label: ナワバリ
      - name: ステージ
        mode: enumerated
        # 親非依存: 全ステージは全ルールの子になりうる
        values:
          - id: zatou
            label: ザトウマーケット
          - id: kinme
            label: キンメダイ美術館
          # ... 既存ステージを列挙

  - id: 03-weapon-role
    label: ブキ・役割
    description: ブキ／サブ／スペシャル／ロール固有のノウハウ
    fixed_levels:
      - name: ブキ種別
        mode: enumerated
        values:
          - id: shooter
            label: シューター
          - id: roller
            label: ローラー
          # ...
      - name: 個別ブキ
        mode: enumerated
        # 親依存: ブキ種別ごとに有効なブキが決まる
        values_by_parent:
          shooter:
            - id: splash-shooter
              label: スプラシューター
            - id: bold-marker
              label: ボールドマーカー
          roller:
            - id: splat-roller
              label: スプラローラー
          # ...

  - id: 04-stepup
    label: ステップアップガイド
    description: XP1800-2400 向けエッセンス集
    fixed_levels: []

  - id: 05-glossary
    label: 用語集
    description: スプラトゥーン用語／FPS・TPS 用語
    fixed_levels:
      - name: 用語カテゴリ
        mode: open                       # LLM が命名、consolidate で正規化
```

### 5.2 mode のセマンティクス

| mode | LLM の挙動 | consolidate 対象 |
|---|---|---|
| `enumerated` | YAML の値リストから選ぶのみ | 対象外（YAML が真実） |
| `open` | 自由命名、`known_paths_cache` を参考にする | 対象 |
| 固定層を超えた深部 | 自由命名、`known_paths_cache` を参考にする | 対象 |

### 5.3 親依存値（`values_by_parent`）

親ノードの `id` をキーとして、子の値リストを宣言。親が enumerated の場合のみ有効。

`values_by_parent` のキーは**親層の `values[].id` 全集合と完全一致**しなければならない。未宣言の親があれば起動時バリデーションエラー（= 部分宣言は許可しない）。「ある親には enumerated 子層を持たせない」を表現したい場合は、その親自体を別カテゴリに切り出すか、子層を `mode: open` に変更する。

### 5.4 設定検証

`pipeline/config.py` の `load_categories()` に以下のバリデーションを追加:

- `fixed_levels` が空でないとき、各層に `name` と `mode` がある
- `mode: enumerated` のとき `values` または `values_by_parent` のいずれか一方が存在
- `mode: open` のとき `values` 系は存在しない
- `values_by_parent` のキーが親層の `values[].id` の集合と一致

## 6. 各ステージの変更

### 6.1 classify

**変更内容**:
1. 出力 JSON: `{"category": "...", "subtopic": "..."}` → `{"category": "...", "path": ["...", "..."]}`
2. プロンプトに以下を含める:
   - 各 enumerated 層の値リスト（`values_by_parent` の場合は親選択に応じた絞り込み）
   - open 層と自由層の `known_paths_cache` 内容
   - 「固定層の選択は YAML の値からのみ」「open 層・自由層は再利用優先」の指示
3. **`known_paths_cache` の利用**: 起動時に `state/ingest_manifest.json` から読込（全 classified ファイル走査を廃止）
4. snippet 1 件処理ごとに cache を追記更新

**疑似コード**:
```python
def run(...):
    manifest = Manifest.load(manifest_path)
    known_paths = manifest.known_paths_cache  # カテゴリ別 dict[str, list[str]]

    for snippet_path in sorted(snippets_dir.glob("*.md")):
        rel = str(snippet_path.relative_to(root))
        if manifest.snippets.get(rel, {}).get("classified"):
            continue

        prompt = _build_user_prompt(categories, body, known_paths)
        reply = provider.complete(...)
        parsed = parse_json_response(reply, ...)
        category_id = parsed["category"]
        path = parsed["path"]

        _validate_path(category_id, path, categories)  # enumerated 層の値検証

        # write classified file
        classified_fm = ClassifiedFrontmatter(..., category=category_id, path=path)
        write_frontmatter(out, classified_fm, body)

        # update manifest
        manifest.snippets[rel] = {
            "source_hash": fm.content_hash,
            "classified": True,
            "classified_path": path,
        }
        # cache 更新（open 層・自由層 path のみ記録）
        _add_to_known_paths_cache(manifest, category_id, path, categories)

    manifest.save(manifest_path)
```

### 6.2 consolidate

**変更内容**:
1. **カテゴリごと**に「open 層・自由層 path 頻度」のハッシュを計算
2. 前回 manifest の `consolidate.<cat_id>.path_frequency_hash` と一致 → スキップ
3. enumerated-only のカテゴリ（`fixed_levels` がすべて enumerated、深部使用なし）は最初からスキップ
4. rename 対象は **open 層と自由層 path のみ**。enumerated 層の rename は提案させない
5. プロンプトには「path 一覧と頻度」を渡し、rename 提案 `[{"category": ..., "from_path": [...], "to_path": [...]}]` を返してもらう

**疑似コード**:
```python
def run(...):
    manifest = Manifest.load(manifest_path)
    by_cat = _collect_path_frequencies(classified_dir)  # {cat_id: {path_tuple: count}}

    for cat_id, freq_map in by_cat.items():
        if _is_enumerated_only(cat_id, categories) and not _has_free_tail(freq_map):
            continue  # スキップ

        new_hash = _hash_frequency_map(freq_map)
        prior = manifest.consolidate.get(cat_id, {}).get("path_frequency_hash")
        if prior == new_hash:
            continue  # スキップ

        prompt = _build_consolidate_prompt(cat_id, freq_map, categories)
        reply = provider.complete(...)
        renames = parse_json_response(reply, ...)["renames"]

        for r in renames:
            _validate_rename(r, categories)  # enumerated 層が対象になっていないか
        _apply_renames(classified_dir, wiki_dir, renames, ts)

        manifest.consolidate[cat_id] = {
            "path_frequency_hash": new_hash,
            "last_run_at": ts.isoformat(),
        }

    manifest.save(manifest_path)
```

### 6.3 cluster

**変更内容**:
- key を `f"{category}/{'/'.join(path)}"` のフルパス形式に
- ロジックは現状維持（LLM コールなし、軽量）

```python
key = f"{fm.category}/{'/'.join(fm.path)}"
clusters.setdefault(key, []).append(rel)
```

### 6.4 compile

**変更内容**:
- key の解析: `category, *path = key.split("/")` で path を復元
- 出力先: `wiki_dir / category / Path(*path).with_suffix(".md")`
- それ以外（fingerprint スキップ等）は現状維持

### 6.5 index

**変更内容**:
1. **再帰化**: `wiki/<cat>/.../README.md` を全中間ノードに生成
2. 各 README の内容: 配下のサブツリーへのリンク + 直下リーフのタイトル一覧
3. tombstone を含むリーフは README から除外（既存仕様の継承）
4. LLM コールなし

**README フォーマット例**:
```markdown
# シューター

`03-weapon-role > シューター`

## サブカテゴリ

- [スプラシューター](スプラシューター/)
- [ボールドマーカー/](ボールドマーカー/)

## 直接配下のページ

（リーフがあれば列挙、ない場合はこのセクション自体を省略）
```

### 6.6 ingest, diff

変更なし。既に増分対応済み。

## 7. Manifest スキーマ拡張

`state/ingest_manifest.json` を拡充:

```python
# pipeline/state.py
class Manifest(BaseModel):
    snippets: dict[str, SnippetEntry]      # 既存（拡張）
    wiki: dict[str, WikiEntry]              # 既存
    consolidate: dict[str, ConsolidateEntry]  # 新
    known_paths_cache: dict[str, list[list[str]]]  # 新（カテゴリID → path リスト）

class SnippetEntry(BaseModel):
    source_hash: str           # 既存
    classified: bool           # 既存
    classified_path: list[str] | None  # 新

class ConsolidateEntry(BaseModel):
    path_frequency_hash: str
    last_run_at: str

class WikiEntry(BaseModel):
    cluster_fingerprint: str    # 既存
```

### 7.1 `path_frequency_hash` の計算

```python
def _hash_frequency_map(freq_map: dict[tuple[str, ...], int]) -> str:
    # path tuple をソートして deterministic に
    canonical = sorted((list(path), count) for path, count in freq_map.items())
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
```

### 7.2 `known_paths_cache` の更新タイミング

- classify ステージで snippet 1 件処理ごとに追記
- consolidate ステージの apply 後に再構築（rename で path が変わるため）

## 8. CLI 変更

```bash
# 差分実行（デフォルト）
uv run python -m pipeline.main --all
uv run python -m pipeline.main --stage consolidate

# 全部やり直し（manifest クリア）
uv run python -m pipeline.main --all --rebuild
uv run python -m pipeline.main --stage consolidate --rebuild
```

`--rebuild` フラグ:
- `--all --rebuild`: manifest 全体をクリアして全ステージを実行
- `--stage X --rebuild`: そのステージに関連する manifest フィールドだけクリアして実行
  - `--stage classify --rebuild`: 全 snippet の `classified` を false にする
  - `--stage consolidate --rebuild`: `consolidate` 全エントリをクリア
  - `--stage compile --rebuild`: `wiki` 全エントリの `cluster_fingerprint` をクリア

## 9. 移行計画

### 9.1 既存 Splatoon データの移行（フェーズ 1: スキーマ刷新）

現状の `classified/*/*.md` の `subtopic: <flat string>` を新スキーマへ変換するワンショットスクリプト `scripts/migrate_to_path.py` を用意:

1. 既存 frontmatter から `subtopic` を読み、`path: [<subtopic>]` に変換（1 要素配列）
2. **wiki/ 側のファイル位置は変更しない**: 1 層パスの場合、`wiki/<cat>/<subtopic>.md` は新ロジックでも同じパスに出力される（`compile` の出力先 = `wiki_dir / category / Path(*path).with_suffix(".md")` で path=[<subtopic>] なら `<cat>/<subtopic>.md`）。frontmatter のみ更新。
3. tombstone ページの `merged_into: <str>` も `merged_into_path: [<str>]` に変換（`pipeline/models.py` の `WikiFrontmatter` の改修と整合）
4. `state/ingest_manifest.json` に `classified_path` を全 snippet 分追記、`known_paths_cache` を初回構築

このフェーズ完了時点で、Splatoon は「1 層パスで動く新スキーマ」になっており、新コードと既存出力が両立する。

### 9.2 Splatoon を多層化（フェーズ 2: B 案の実装検証）

フェーズ 1 後、`02-rule-stage` と `03-weapon-role` を多層化する:

**選択肢 A（推奨）**: classify 再実行
- `categories.yaml` を新スキーマに更新（02 / 03 に enumerated 固定層を定義）
- `uv run python -m pipeline.main --stage classify --rebuild` で再分類
- LLM が新スキーマに沿って path を割り当て直す
- 続けて `--all` で残段を流せば、cluster / compile / index が新パスに沿った wiki ツリーを生成

**選択肢 B**: 手動分配
- 既存の各 classified ファイルを目視で適切な path に編集
- LLM 利用なしで確定的だが、件数が少ないうちのみ現実的

PoC スコープでは A を採用。汎用パイプラインの「自己ドッグフード」になる。

なお、フェーズ 2 の前に**旧 wiki/ ディレクトリは削除**する（多層化で配置が変わるため、古いファイルが取り残される）。git で履歴は残るので消して問題ない。

## 10. テスト戦略

### 10.1 ユニットテスト

- `tests/test_config.py`: 新スキーマのバリデーション（enumerated/open、values_by_parent の整合性）
- `tests/test_classify.py`: path 出力、enumerated 層の値検証、known_paths_cache 利用
- `tests/test_consolidate.py`: カテゴリ単位スキップ、enumerated 層を rename 対象から除外、path ベース rename
- `tests/test_index.py`: 再帰 README 生成、tombstone 除外
- `tests/test_state.py`: 新 Manifest フィールドの読み書き

### 10.2 E2E テスト

`tests/test_end_to_end.py` を新シナリオで強化:
- 多層パスを含むスニペット 1 件: ingest → classify → cluster → compile → index
- 既存スニペット + 新規スニペット混在: consolidate がカテゴリ単位スキップで動作
- `--rebuild` フラグ: manifest がクリアされ全段が走り直すこと
- 中間ノード README が再帰的に生成されること

### 10.3 既存テスト互換性

既存テストの fixture（snippet → classified → wiki の最小例）は path 形式へ移行。`subtopic: foo` を `path: [foo]` に置換するだけで通る想定。

## 11. 段階的実装

実装プランで詳細化されるが、想定する大ブロック:

1. **データモデル & スキーマ**（型定義、バリデーション、移行スクリプト）
2. **classify** の path 対応 + `known_paths_cache`
3. **cluster, compile** の path 対応
4. **consolidate** のカテゴリ単位スキップ + path ベース rename
5. **index** の再帰 README 生成
6. **CLI `--rebuild` フラグ**
7. **Splatoon 多層化（02, 03）と E2E テスト追加**

各ブロックは独立してテスト可能。1 → 2 → 3 → 4 → 5 → 6 → 7 の順で実装することで、各時点でパイプラインが動く状態を維持できる。

## 12. 設計判断の理由（ADR 風メモ）

### なぜ案 3（ハイブリッド）か

エンタープライズ用途を見据えると、ドメインによって「タクソノミーが完全に閉じている（ブキ）」か「中分類は緩く LLM に任せたい（社内中分類）」かが分かれる。1 つのスキーマで両方をカバーする必要があり、層ごとの mode 切替が最もシンプルな解。案 1（全列挙）と案 2（深さのみ宣言）はそれぞれ片方しか満たさない。

### なぜ案 C（静的索引）か

中間ノードに LLM 生成ページを持たせる案 B は、ノード数 × LLM コール = O(階層深度 × ブランチ数)で性能を悪化させる。差分実行で改善しようとしても、新規 snippet が増えるたびに親ノードの README も再生成する必要があり、partial invalidation のロジックが複雑化する。LLM 不使用の案 C は実装も検証もシンプルで、UX 損失も限定的。

### なぜ設定変更追跡を YAGNI 退避するか

プロンプトハッシュや categories.yaml の値追加検出を実装しても、ユーザーは「設定変えたのに反映されない」事故を恐れて結局 `--rebuild` を打つ運用になりがち。明示的な `--rebuild` の方がメンタルモデルが単純で、運用事故を生まない。コストはほぼゼロ。

### なぜ並列化を非スコープにするか

差分実行が効けば、初回以降の実行時間は「変動分」だけになる。1000 ファイルあっても日次変動が 10 件なら LLM コール 10 回で済む。並列化（asyncio + rate limiting）は実装複雑度が高く、エラー処理も難しい。差分実行の効果を観測してから判断すべき。

## 13. 将来 TODO（YAGNI 退避）

`TODO.md` に以下を追記する:

```markdown
### N. 設定変更時の自動再生成（YAGNI、将来検討）

**背景**: 差分実行はデータ変更のみ追従。プロンプト・モデル・categories.yaml の
変更時は `--rebuild` で明示的にやり直す前提（spec 2026-04-30 §3.3）。

**改善余地（段階的に重い順）**:
1. プロンプト/モデルハッシュを manifest に記録、変わったら自動再生成
2. categories.yaml の enumerated 値追加 → 該当ブランチだけ再 classify
3. AI が更新範囲を判断して必要部分だけ再生成（究極形、超 YAGNI）

**いつ対処するか**: 運用で「設定変えたのに反映されない」事故が頻発したら。

### N+1. 中間ノードの LLM 生成 README（YAGNI）

**背景**: 現状は静的索引（リンク一覧）のみ。LLM が「シューターという種別の概要」
のような説明文を書けば閲覧体験は向上する。ただしノード数だけ LLM コールが増える。

**いつ対処するか**: ユーザーが中間ノードの説明を欲しがる事象が観測されたら。

### N+2. 並列化 / 非同期化（YAGNI）

**背景**: 差分実行で十分速いはず。観測してから判断する。

**いつ対処するか**: 差分実行下でも実行時間が運用許容を超えるとき。

### N+3. 第 2 テナント（社内ナレッジ）並走（YAGNI）

**背景**: spec 2026-04-30 §2 で C 案として提示。Splatoon 多層化（B）の見通しが
立ってから取り組む。

**いつ対処するか**: B 案の実運用がしばらく回り、汎用化の証明が必要なとき。
```

## 14. 未解決事項

- **values_by_parent の表現が冗長になる**: ブキは 100 種類以上ある。YAML を分割（`config/categories/03-weapon-role.yaml`）するか、外部 CSV から生成するかは実装時に判断。
- **path に含まれる文字の制約**: `/` は禁止（パス区切りと衝突）、その他 OS 依存の禁則文字は要列挙。実装時に slug ルールを確定させる。
- **consolidate プロンプトの設計**: path ベースの rename 提案を LLM にどう書かせるか、JSON スキーマの最終形は実装時に詰める。基本方針は「from_path / to_path / reason」の 3 フィールド。
- **リーフが将来中間ノードに変わるケース**: 既存リーフ `wiki/X/foo.md` に対して、後から path `[X, foo, bar]` の snippet が追加されたら `foo` は中間ノードに昇格する。このとき:
  - 旧 `wiki/X/foo.md`（リーフ）と新 `wiki/X/foo/` ディレクトリは衝突する。OS によっては作成できない（同名 file と dir）。
  - 想定対応: compile ステージで衝突検知 → 旧リーフを `wiki/X/foo/_index.md` のような名前に退避し、`wiki/X/foo/` ディレクトリを作成。index ステージは `_index.md` を「直接配下のページ」として扱う。
  - 実装時に詳細決定。E2E テストで該当シナリオをカバーすること。
- **同名ノードの衝突**: 異なる親配下に同名の自由層ノードが生まれた場合（例: `[A, common]` と `[B, common]`）。これはパス全体が違うので衝突しないが、consolidate プロンプトで別ノード扱いになることを LLM に明示する必要がある。
