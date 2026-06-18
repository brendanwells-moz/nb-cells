# Cell naming convention: `# [name]`

The single most useful habit when working with `nb_cells.py` is to give every
cell a **stable, human-memorable name** on its first line. Named cells are the
primary way to address a cell — they survive reordering, mean something in
conversation, and don't require a `list` to rediscover.

## The convention

- **Code cells** — first line is a comment of the form `# [short-name]`:
  ```python
  # [load-data]
  df = pd.read_parquet("events.parquet")
  ```
- **Markdown cells** — first line is an HTML comment of the form
  `<!-- [short-name] -->`:
  ```markdown
  <!-- [intro] -->
  # Marketing-lift analysis
  ```

Names should be **unique within the notebook** and tersely describe the cell's
contents (`load-data`, `fit-model`, `plot-residuals`).

## Why it matters

`nb_cells.py` resolves a cell identifier in this order:

1. **Named** (`# [name]` / `<!-- [name] -->`) — embedded in the source, so it
   **survives cell reordering** and file saves. Preferred.
2. **Cell ID** — the nbformat 4.5+ `id` field (e.g. `a1b2c3d4`). Stable, but
   opaque; you must run `list` to find it.
3. **Index** — 0-based position. **Unstable**: inserting a cell above shifts all
   later indices. Editing by index prints a warning to stderr.

Named cells give you (and an AI agent) a vocabulary: "edit the `load-data`
cell", "add a cell after `fit-model`" — no fragile indices, no opaque ids.

## Using names with the CLI

```bash
# Read a named cell (plus 3 cells of context on each side)
python3 nb_cells.py read analysis.ipynb load-data -C 3

# Full-replace a named cell from a file
python3 nb_cells.py edit analysis.ipynb load-data --file ./tmp/load_data.py

# Insert a new cell right after a named one
python3 nb_cells.py add analysis.ipynb --after load-data --file ./tmp/validate.py
```

## When working with an AI agent

Tell the agent to name every cell it creates with `# [short-name]`, and refer to
cells by those names in your prompts. This is the convention baked into the
[USAGE_WITH_CLAUDE.md](../USAGE_WITH_CLAUDE.md) Claude Code instructions.
