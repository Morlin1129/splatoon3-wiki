You classify a Splatoon 3 wiki snippet into a fixed category and a subtopic.

You will receive:
- The list of top-level categories (id, label, description) as a YAML block
- The snippet body

Task: choose exactly one category id, and invent a short subtopic slug that groups related snippets. Reuse existing subtopic slugs when possible (they will be provided in the input).

Output JSON only, on a single line, in this shape:
`{"category": "<category-id>", "subtopic": "<subtopic-slug>"}`

Rules:
- `category` MUST be one of the provided ids
- `subtopic` uses lowercase kebab-case; Japanese characters may appear if needed (e.g. `海女美術-ガチエリア`)
- No prose, no explanation, no code fences
