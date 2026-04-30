スニペットを、固定されたカテゴリーと階層パス (path) に分類する。

入力として以下を受け取る:
- カテゴリーの一覧（id、ラベル、説明、固定層スキーマ）を YAML 形式で
- 既存の path 一覧（カテゴリ別、再利用候補）
- スニペット本文

タスク: カテゴリー ID を 1 つ選び、配下の階層パス (path) を決定する。

## 階層パス (path) について

各カテゴリは `fixed_levels` で 0 個以上の固定層を持つ:
- `mode: enumerated` の層: 入力の `values` または `values_by_parent` から
  必ず id（or label）の中から 1 つ選ぶ。それ以外は不可。
- `mode: open` の層: 既存 path に類似があれば再利用、なければ新規命名。
- `fixed_levels` 配下のさらに深い層は LLM が自由に追加できる（深さ可変）。
  既存 path を最大限再利用する。

path は最低 1 要素以上。各要素は `/` を含めない。

## 出力形式

JSON のみ、1 行で:
`{"category": "<category-id>", "path": ["<level0>", "<level1>", ...]}`

ルール:
- `category` は必ず提供された ID の中から選ぶ。
- enumerated 層では values の `id` をそのまま使う（`label` ではなく）。
- open 層・自由層は小文字ケバブケースまたは日本語可。
- 解説や前置き、コードブロックは出力に含めない。

## path 命名のルール（重要）

- 「**普遍的で長期的に成長しうる知識単位**」を表す名前にする
- **日付・個別事象・session 情報を含めない**
  - ❌ `["2026-04-26-general-dakai-home-base-clearing"]`
  - ✅ `["dakai-fundamentals"]`
- 既存 path に類似する内容なら、**必ず既存を再利用する**
- 迷ったら、最も近い既存 path を選ぶ
