# nb_cells vs. Claude's native notebook tools

Anthropic ships a built-in notebook capability in Claude Code: **`Read`**
(renders an `.ipynb` as cells with their outputs) plus **`NotebookEdit`**
(replace / insert / delete a single cell). This doc compares that native path
against `nb_cells.py` so you can pick the right tool per task.

## Feature-by-feature

| Capability | `nb_cells.py` (this tool) | Native (`Read` + `NotebookEdit`) |
|---|---|---|
| Read one cell without loading the whole file | ✅ `read <id>`, optional `-C/-B/-A` context | ❌ `Read` pulls the whole notebook (all cells + outputs) into context |
| Cell addressing | Named tags `# [name]`, nbformat `id`, **and** index | nbformat `id` only |
| Edit a cell | ✅ `edit --file` (full replace) | ✅ `replace` |
| Insert a cell | ✅ `add --after/--before/--end --type` | ✅ `insert` (after a cell, or at top) |
| Delete a cell | ❌ deliberately omitted (agent safety) | ✅ `delete` |
| Move / reorder | ✅ `move` | ❌ |
| Create a new notebook | ✅ `new` | ❌ |
| Bulk insert | ✅ `import` (JSON array) | ❌ one at a time |
| List cells (ids/types/preview) | ✅ `list` (JSON or `--human`) | partial — comes free with a full `Read` |
| Read source-only / outputs-only | ✅ `--no-outputs` / `--outputs` | ❌ |
| Execution-status sweep (ran / errored / printed, per cell) | ✅ `status` (JSON or `--human`) | partial — must eyeball a full `Read` |
| Usable by humans / scripts / cron / other agents | ✅ it's a CLI | ❌ only inside Claude Code's tool loop |
| Rich output rendering (images shown visually) | ✅ `extract-images` writes PNG/JPEG/SVG to files, then native `Read` renders them | ✅ `Read` displays plots inline |
| Setup / dependencies | clone + path + allowlist entry | ✅ zero — always present |
| Requires a prior in-conversation Read | ❌ | ✅ mandatory before any edit |

## The differences that actually matter

1. **Context efficiency — this tool's reason to exist.** Native `Read` pulls the
   *entire* notebook into context before you can touch a cell, and that copy
   lingers in the context window for the rest of the conversation. A 2.4 MB
   notebook costs a 2.4 MB read; `nb_cells.py read <one-cell>` costs a few
   hundred tokens. Native cost scales with **notebook size**; this tool scales
   with **the one cell you asked for**.

2. **Portability.** This is a standalone, stdlib-only CLI — it runs for a human
   at a terminal, in cron, in CI, or under *any* agent. The native tools exist
   only inside Claude Code's call loop and can't be scripted.

3. **Stable, human-memorable addressing.** `# [name]` tags survive reordering
   and let you refer to a cell by meaning ("edit the `load-data` cell"). Native
   addressing is opaque nbformat ids you must first `Read` the notebook to
   discover. See [cell-naming-convention.md](./cell-naming-convention.md).

4. **Safety vs. completeness on delete.** This tool deliberately omits `delete`;
   native has it. The conservative choice here forces deletion to be a manual
   human act — safer for unattended agents, less convenient for autonomous
   cleanup.

## Where native is genuinely better

- **Zero friction** — no clone, no path, no allowlist rule, nothing to keep in
  sync across machines.
- **Visual outputs** — `Read` renders plot images inline in one step. This tool now
  bridges that gap with `extract-images` (decode to a file → native `Read`), but
  it's two steps vs. native's one.
- **Holistic reasoning** — because native drops the whole notebook into context,
  the model can reason across all cells at once (good for sweeping refactors).
  This tool optimizes for the opposite: surgical, low-context, one-cell edits.
- **One fewer moving part** — nothing to version or break.

## Bottom line — when to use which

They optimize for **opposite** things:

- **`nb_cells.py`** wins for **large notebooks, surgical edits, scripting, and
  non-Claude-Code use** — a context-frugal, portable, named-addressing scalpel.
  Its `new` / `import` / `move` / named-tag surface is strictly richer for
  *building and restructuring* notebooks.
- **Native** wins for **small notebooks, zero setup, visual output inspection,
  and one-shot holistic edits** inside Claude Code — plus it has `delete`.

Reasonable middle path: default to `nb_cells.py` for large data-science
notebooks (where context cost is real), and let the native tools handle quick
edits to small notebooks where loading the whole thing is cheap.

## How the native tool uses context (FAQ)

- **How many times does native load the notebook?** Once per `Read` call. You
  must `Read` at least once before editing, so the floor is one full load, and
  the loaded content stays in the context window for the rest of the
  conversation (until compaction). Re-reading N times costs N full loads.
- **Does a native edit force a re-read?** No. `NotebookEdit` does not trigger a
  re-`Read`, and Claude still knows the change is present (it has the prior read
  plus the diff it applied; the harness tracks file state). You only need to
  re-`Read` when the file changes **out-of-band** from the edit — most notably
  **after executing the notebook**, because `NotebookEdit` changes *source*
  only and never captures new execution **outputs** (plots, printed results).

## Inline plot rendering (implemented)

Claude Code's `Bash` tool captures this tool's stdout as **text**, so a CLI
cannot stream an image into the model's vision directly. But cell outputs store
plots as **base64** in the cell JSON (`output.data["image/png"]`), so we compose
with the native image `Read`:

> `nb_cells.py extract-images <nb> <cell> [--out-dir DIR]` decodes each image
> output (`image/png`, `image/jpeg`, `image/svg+xml`) to a file
> (`<dir>/<cell>_out<n>.<ext>`, default `./tmp`) and prints the paths. Claude
> then calls the native **`Read`** tool on those paths, and `Read` renders the
> images visually.

Shipped as a **dedicated command** (not a `read` flag) for discoverability; `read`
also surfaces an `image_outputs` count + a `hint` pointing here whenever a cell has
image outputs, so the path is obvious. Stdlib only (`base64` + file writes). This
closes the one row above where native was strictly better.

The same release added `status` (cross-cell execution sweep) and `--outputs`
(outputs-only read), which together remove the remaining reasons an agent would
drop to raw Python for post-execution output introspection.
