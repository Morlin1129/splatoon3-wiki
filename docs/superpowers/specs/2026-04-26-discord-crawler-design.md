# Discord クローラ 設計書

- **日付**: 2026-04-26
- **リポジトリ**: 同 `splatoon3-wiki`（モジュール `crawler/` を新規追加）
- **対象**: サブプロジェクト #2 ／全 4 サブプロジェクト中の 2 番目

## 1. 背景と位置付け

サブプロジェクト #1（LLM Wiki 生成パイプライン）は手元のサンプル原典 MD から Wiki ページ MD を生成できる状態にある。本サブプロジェクトはその上流、Discord サーバから原典素材を自動取得する週次バッチクローラを実装する。

### 全体ロードマップ上の位置

1. ✅ LLM Wiki 生成パイプライン（完了）
2. **Discord クローラ（本設計書）**
3. 静的サイト／GitHub Pages 土台
4. E2E 最小版

### 本サブプロジェクトのゴール

設定ファイルで指定した複数サーバ × 複数チャンネルの Discord メッセージを、週 1 回バッチで取得し、ローカル `raw_cache/discord/...` に Markdown ファイルとして保存する Docker 実行可能ツールを作る。

### スコープ内

- discord.py を使った Bot トークン認証でのメッセージ取得
- 複数サーバ × 複数チャンネルの設定ファイル駆動
- ISO 週（JST）境界での「先週分」取得
- メッセージ本文・タイムスタンプ・投稿者情報・スレッド構造・添付 URL・リアクション
- 週 × チャンネル単位の Markdown 出力（フロントマター + メッセージブロック列）
- Docker イメージ + `crontab.example`
- 既存ファイルがあるとデフォルトでスキップ、`--force` で上書き

### スコープ外（後続サブプロ）

- Google Drive アップロード（ローカル `raw_cache/` までで止める）
- Ingest との接続（パイプライン #1 は引き続き `sample_raw/` から読む）
- 匿名化／PII 除去（Ingest LLM の責務）
- 自動スケジューラ環境構築（`crontab.example` を提供するのみ、実際の cron 設置はユーザ責任）
- 編集履歴・削除済みメッセージの追跡
- アーカイブ済みスレッドの取得（v2 以降）
- 実 Discord API を叩く E2E テスト

## 2. アーキテクチャ概要

```
                    ┌─────────────────────────────────────────┐
                    │         crawler/ (Python module)        │
                    │                                         │
config/discord.yaml ─▶│  config.py     ─ load CrawlConfig    │
                    │       │                                 │
.env (BOT_TOKEN) ───▶│  client.py     ─ discord.py wrapper   │
                    │       │                                 │
                    │  week.py       ─ ISO 週境界 (JST)      │
                    │       │                                 │
                    │  fetch.py      ─ 1 channel × 1 week   │
                    │       │   をメッセージ列に                  │
                    │       ▼                                 │
                    │  writer.py     ─ Markdown 整形・書き込み │
                    │       │                                 │
                    │  main.py       ─ CLI / asyncio エントリ │
                    └───────┼─────────────────────────────────┘
                            ▼
              raw_cache/discord/<server>/<channel>/2026-W17.md
```

### モジュール責務

| モジュール | 責務 | 依存 |
|---|---|---|
| `crawler/config.py` | `config/discord.yaml` を pydantic モデルにロード。サーバ／チャンネル ID リスト、出力ディレクトリ、タイムゾーン等 | pydantic, PyYAML |
| `crawler/week.py` | 「与えられた datetime に対する『先週』の (start, end) JST」を返す純粋関数。ISO 週番号文字列も生成 | 標準ライブラリのみ |
| `crawler/client.py` | discord.py の `Client` を薄くラップ。`login → fetch → close` の lifecycle を管理。テスト用の `FakeDiscordClient` プロトコルもここで定義 | discord.py |
| `crawler/fetch.py` | 1 チャンネル × 1 週の取得ロジック。`channel.history()` をループ、スレッド・リアクション・添付を構造化 dict で返す | client.py, week.py |
| `crawler/writer.py` | dict 列を Markdown に整形して書き込み。フロントマター生成、既存ファイル skip/force 判定 | 標準のみ |
| `crawler/models.py` | pydantic: `Message`, `Author`, `Reaction`, `Attachment`, `ThreadInfo` | pydantic |
| `crawler/main.py` | argparse で CLI、`asyncio.run` でエントリ、設定ロード → 全 (server×channel) を順次クロール → 集計ログ出力 | 全部 |

### 設計原則

- **同期⇄非同期境界は main.py に閉じる** — `client.py` 以下は async、`writer.py` は sync。テストしやすい単位を保つ。
- **discord.py 依存は client.py のみ** — fetch.py 以下はメッセージ dict のみ扱い、Discord ライブラリ知識を持たない。プロバイダ差し替え（パイプライン #1 の LLM 抽象と同思想）。
- **state ファイルなし** — 週境界が固定なので「前回どこまで」は不要。冪等性はファイル名で担保。

## 3. ディレクトリ構造

```
splatoon3-wiki/
├── crawler/                       # 新規モジュール
│   ├── __init__.py
│   ├── config.py
│   ├── week.py
│   ├── client.py
│   ├── fetch.py
│   ├── writer.py
│   ├── models.py
│   └── main.py
│
├── config/
│   └── discord.yaml               # サーバ／チャンネル設定（新規）
│
├── tests/
│   └── crawler/
│       ├── __init__.py
│       ├── test_config.py
│       ├── test_week.py
│       ├── test_fetch.py          # FakeDiscordClient で 1 週取得検証
│       ├── test_writer.py         # 出力 MD のフォーマット検証
│       ├── test_main_cli.py       # argparse 受け入れ
│       └── test_e2e_fake.py       # 設定 → fetch → 書き込みの一気通貫
│
├── docker/
│   └── crawler/
│       ├── Dockerfile             # python:3.12-slim ベース
│       └── crontab.example        # 週 1 cron 設定例
│
├── raw_cache/                     # ★ .gitignore (Drive 同期前提のローカルキャッシュ)
│   └── discord/
│       └── <server>/
│           └── <channel>/
│               └── 2026-W17.md
│
└── pyproject.toml                 # discord.py を [project.optional-dependencies] crawler に追加
```

### 補足

- **依存分離**: `discord.py` は `pyproject.toml` の `[project.optional-dependencies] crawler` に入れ、`uv sync --extra crawler` でインストール。パイプライン #1 のみ動かすユーザは入れなくて済む。
- **Docker 配置**: `docker/crawler/` 配下にまとめる。将来別クローラ（Slack 等）が増えても `docker/<source>/` で並列に管理できる。
- **`.gitignore` 追加**: `raw_cache/`（既存に無ければ）。

## 4. データフォーマット

### `config/discord.yaml`

```yaml
output_dir: raw_cache/discord
timezone: Asia/Tokyo

servers:
  - id: "123456789012345678"
    name: "Splatoon道場"            # 出力パス用 slug にも使う
    channels:
      - id: "234567890123456789"
        name: "戦術談義"
      - id: "234567890123456790"
        name: "海女美術"

  - id: "987654321098765432"
    name: "別サーバ"
    channels:
      - id: "876543210987654321"
        name: "雑談"
```

- **id は文字列**（Discord の snowflake は 64bit、JSON/YAML 数値で精度落ちる）。
- **name は出力パス用 slug**。日本語可だが、ファイルシステム的に安全な文字に正規化する（`/`、`\` などを `_` に置換）。
- **設定ファイルにないチャンネルは無視**。Bot がサーバに参加していてもクロール対象外。

### 出力 Markdown（`raw_cache/discord/<server>/<channel>/2026-W17.md`）

```markdown
---
server_id: "123456789012345678"
server_name: "Splatoon道場"
channel_id: "234567890123456789"
channel_name: "戦術談義"
week: "2026-W17"
week_start: "2026-04-20T00:00:00+09:00"
week_end:   "2026-04-27T00:00:00+09:00"
fetched_at: "2026-04-27T09:00:00+09:00"
message_count: 42
---

## msg-1234567890123456789

- author_id: "111111111111111111"
- author_username: "alice"
- author_display_name: "Alice@道場"
- timestamp: "2026-04-22T14:32:11+09:00"
- edited_at: "2026-04-22T14:35:02+09:00"   # 無ければ省略
- reply_to: "msg-1234567890123456788"      # 無ければ省略
- thread_id: "345678901234567890"          # スレッド内なら付与、無ければ省略
- attachments:
  - "https://cdn.discordapp.com/attachments/.../scene.png"
- embeds:
  - "https://www.youtube.com/watch?v=xxx"
- reactions:
  - "👍": 5
  - "🎯": 2

本文ここに。改行もそのまま保持。

---

## msg-1234567890123456790
...
```

### スレッドの扱い

- スレッドは Discord 上「親チャンネルから派生する別チャンネル」扱い。
- クローラは **設定で指定された親チャンネルに紐づく全アクティブスレッドも自動追跡**し、スレッド内メッセージは親チャンネルのファイルに `thread_id` 付きでマージ。
- アーカイブ済みスレッドは v1 ではスキップ（discord.py の `archived_threads()` を使えば対応可だが YAGNI）。

## 5. 実行モデルと CLI

### CLI

```bash
# デフォルト: 「先週」（前 ISO 週、JST）を取得、既存ファイルはスキップ
uv run python -m crawler

# 既存ファイル上書き
uv run python -m crawler --force

# 特定週を指定（リカバリ用）
uv run python -m crawler --week 2026-W15

# 特定サーバ／チャンネルだけ（デバッグ用）
uv run python -m crawler --server "Splatoon道場" --channel "戦術談義"

# 設定ファイル差し替え
uv run python -m crawler --config config/discord.yaml
```

### Docker

`docker/crawler/Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --extra crawler --frozen --no-dev
COPY crawler/ ./crawler/
COPY config/discord.yaml ./config/discord.yaml
ENTRYPOINT ["uv", "run", "python", "-m", "crawler"]
```

実行：

```bash
docker build -t splatoon-crawler -f docker/crawler/Dockerfile .
docker run --rm \
  --env-file .env \
  -v $(pwd)/raw_cache:/app/raw_cache \
  splatoon-crawler
```

- **`raw_cache/` を bind mount** して出力をホスト側に永続化
- **`.env` を `--env-file` で渡す** （`DISCORD_BOT_TOKEN`）
- **コンテナは 1 回回って exit**（restart policy なし）

### `docker/crawler/crontab.example`

```cron
# 毎週月曜 09:00 JST に先週分を取得
0 9 * * 1 docker run --rm --env-file /path/to/.env -v /path/to/raw_cache:/app/raw_cache splatoon-crawler >> /var/log/splatoon-crawler.log 2>&1
```

### 1 回の実行フロー

```
1. main.py 起動（asyncio.run）
2. config.py: discord.yaml + .env をロード → CrawlConfig
3. week.py: 現在時刻（JST）から「先週」の (start, end, week_id) を算出
   ※ --week 指定時はそれを使用
4. client.py: discord.py Client にログイン
5. for server in config.servers:
     for channel in server.channels:
        out_path = raw_cache/discord/<server>/<channel>/<week_id>.md
        if out_path.exists() and not --force: skip, log
        msgs = await fetch.fetch_channel_week(client, channel, week_range)
        writer.write_week_file(out_path, msgs, week_id, ...)
        log "wrote N messages"
6. client.py: ログアウト・close
7. 集計を stdout に出力 (取得 channel 数、message 総数、skip 数、失敗数)
8. 失敗があれば exit 1、なければ exit 0
```

## 6. エラーハンドリングとテスト戦略

### エラーハンドリング

| エラー種別 | 対応 |
|---|---|
| **設定ファイル不正**（YAML 構文 / pydantic バリデーション失敗） | 起動時に即 fail、`exit 2`。スタックトレースを出さず、どのフィールドが問題か明示。 |
| **`DISCORD_BOT_TOKEN` 未設定** | 起動時に即 fail、`exit 2`。 |
| **Bot がサーバに参加していない／チャンネル ID が無効** | 当該 (server×channel) のみスキップ・WARN ログ、他は継続。最後に「N 件失敗」を集計。1 件でも失敗なら最終 `exit 1`。 |
| **Discord API レートリミット** | discord.py が自動リトライ。タイムアウト超過したら当該 channel のみ失敗扱い。 |
| **ネットワーク一時障害** | discord.py 内のリトライに任せる。それでも失敗なら当該 channel スキップ。 |
| **ファイル書き込み失敗**（ディスクフル等） | 即 fail、`exit 1`。途中まで書いたファイルは `.partial` 拡張子で残し、`writer.py` 内で finalize 時にリネーム。 |
| **メッセージのパース失敗**（想定外の embed 形式等） | 当該メッセージのみ skip・WARN ログ、ファイル全体は継続。 |

**冪等性の補強**: 書き込みは `*.md.partial` → `os.replace()` で atomic rename。途中 kill されても破損ファイルが残らない。

### テスト戦略

#### Unit tests

- `test_week.py` — 純粋関数。`iso_week_range_jst(datetime(2026, 4, 26, 12))` → `("2026-W17", start, end)` のような表で検証。年またぎ・月またぎ・週初日付近のエッジケース必須。
- `test_config.py` — YAML ロード成功、必須フィールド欠如、不正な ID 形式（数値で書かれた snowflake）等。
- `test_writer.py` — 与えられた `list[Message]` から正しい MD を生成。フロントマター、メッセージブロック、attachments / reactions の有無、空週（メッセージ 0 件）、`--force` 動作、`.partial` → 本ファイルの atomic rename。

#### Integration tests

- `test_fetch.py` — `FakeDiscordClient` を実装し、固定のメッセージ列を返す。fetch.py が「指定週範囲だけ抽出」「スレッド統合」「リアクション集計」を正しく行うか検証。実 Discord API は叩かない。
- `test_main_cli.py` — argparse の受け入れテスト（`--force`、`--week`、`--server`、`--config`）。E2E ではない。

#### E2E

- v1 では実 Discord API を叩く E2E は **作らない**（テストサーバ用意が重い、トークン管理が CI に乗らない）。
- 代わりに `FakeDiscordClient` を `main.py` に注入できる経路を確保し、`tests/crawler/test_e2e_fake.py` で「設定 → fetch → 書き込み → ファイル検証」を一気通貫で確認。

#### Lint / Format

- `ruff check crawler/ tests/crawler/`
- `ruff format --check crawler/ tests/crawler/`
- パイプライン #1 と同じルール（pyproject.toml の `[tool.ruff]` を共有）。

## 7. パイプライン #1 との接続（将来）

本サブプロジェクトの完了時点では、`raw_cache/discord/...` は生成されるが Ingest はそれを読まない。次以降のサブプロジェクトで以下が必要：

- Google Drive 連携（`raw_cache/` を Drive にアップ／ Drive を真の保管場所にする）
- Ingest 入力源切り替え（`sample_raw/` から Drive 経由 `raw_cache/` へ）
- `source_urls` マッピング供給（Compile が出典 URL を埋め込めるように）

これらは TODO.md の Important #1 とともに別サブプロで対処する。

## 8. 関連ドキュメント

- パイプライン #1 設計: [docs/superpowers/specs/2026-04-23-llm-wiki-pipeline-design.md](2026-04-23-llm-wiki-pipeline-design.md)
- パイプライン #1 実装プラン: [docs/superpowers/plans/2026-04-24-llm-wiki-pipeline.md](../plans/2026-04-24-llm-wiki-pipeline.md)
- 未対処 follow-ups: [TODO.md](../../../TODO.md)
