# nb_cells

A single-file, dependency-free CLI for reading and editing **individual cells**
of a Jupyter notebook without loading the whole file into context. Output is
machine-readable JSON by default, so it works well as a tool for AI coding
agents (and is perfectly usable by humans with `--human`).

- **Zero dependencies** — Python 3 standard library only.
- **Stable cell addressing** — refer to cells by a named tag, by nbformat cell
  `id`, or by index (in that resolution order).
- **Agent-safe by design** — no `delete` command (deletion risks silent data
  loss); full-replace edits are explicit; index edits warn on stderr.

## Install

It's one file. Clone the repo and call it with `python3`:

```bash
python3 /path/to/nb_cells/nb_cells.py <command> ...
```

Optionally put it on your `PATH` (it has a `#!/usr/bin/env python3` shebang and
is executable):

```bash
ln -s /path/to/nb_cells/nb_cells.py ~/bin/nb_cells
```

## Commands

| Command | Purpose |
| --- | --- |
| `new <notebook> [--force]` | Create a new empty notebook. |
| `list <notebook> [--human]` | List all cells (id, type, source preview). `--human` prints a table. |
| `read`/`get <notebook> <cell-id> [...]` | Read one or more cells incl. outputs. `-C/-B/-A N` add context; `--no-outputs` = source only; `--outputs` = outputs only. Cells with image outputs surface a hint to `extract-images`. |
| `edit <notebook> <cell-id> --file <path>` | **Full-replace** a cell's source with file contents. |
| `add <notebook> [--after/--before/--end] [--type code\|markdown] --file <path>` | Insert a new cell. Default position: `--end`. |
| `import <notebook> <cells.json> [--after/--before/--end]` | Bulk-insert cells from a JSON array of `{"source","type"}`. |
| `move <notebook> <cell-id> --after/--before/--end` | Reposition a cell. |
| `status <notebook> [--cell <id>] [--human]` | Per-cell execution sweep: ran? errored (+ename/evalue)? printed? output/MIME types? |
| `extract-images <notebook> <cell-id> [...] [--out-dir DIR]` | Decode a cell's image outputs (plots) to files you can open/`Read`. Default dir `./tmp`. |

There is **no `delete`** command — see `nb_cells.py --help` for the manual
deletion recipe.

### Cell identifiers (resolved in this order)

1. **Named** — code cells start with `# [short-name]`; markdown cells start with
   `<!-- [short-name] -->`. Survives reordering (embedded in source). Preferred.
2. **Cell ID** — the nbformat 4.5+ `id` field (e.g. `a1b2c3d4`). Find via `list`.
3. **Index** — 0-based position. **Unstable**: inserting above shifts indices.

## Examples

```bash
# Create and inspect
python3 nb_cells.py new analysis.ipynb
python3 nb_cells.py list analysis.ipynb --human

# Read a named cell with 3 cells of context on each side
python3 nb_cells.py read analysis.ipynb load-data -C 3

# Edit a cell — write the COMPLETE new source to a file, then pass it
python3 nb_cells.py edit analysis.ipynb load-data --file ./tmp/load_data.py

# Add a cell after another
python3 nb_cells.py add analysis.ipynb --after load-data --file ./tmp/validate.py

# Execution-status sweep across all cells (table form)
python3 nb_cells.py status analysis.ipynb --human

# Save a cell's plot to a file, then Read it
python3 nb_cells.py extract-images analysis.ipynb plot-residuals --out-dir ./tmp
```

`example_notebook.ipynb` is bundled as a fixture for trying commands against.

Full help: `python3 nb_cells.py --help`

## Using nb_cells with Claude Code

This tool was extracted from a data-science workspace where it is wired into
Claude Code via `CLAUDE.md` instructions and a permission allowlist. If you use
Claude Code, replicating that setup makes the tool friction-free for the agent.
See [USAGE_WITH_CLAUDE.md](./USAGE_WITH_CLAUDE.md) for the exact `CLAUDE.md`
snippet and `settings.json` permission rule.
