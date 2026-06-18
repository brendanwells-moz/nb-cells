# CLAUDE.md — nb_cells repo

Instructions for an AI agent working **inside this repository** (developing the
tool itself). For how to *consume* the tool from another project, see
[USAGE_WITH_CLAUDE.md](./USAGE_WITH_CLAUDE.md).

## What this repo is

A single-file, standard-library-only CLI (`nb_cells.py`) for reading and editing
individual Jupyter notebook cells. The guiding constraints:

- **Zero runtime dependencies.** Standard library only. Do not add third-party
  imports to `nb_cells.py` — portability as a drop-in single file is the whole
  point.
- **Agent-safe.** No `delete` command. Edits are full-replace and explicit;
  index-based edits warn on stderr. Preserve these safety properties.
- **Machine-readable by default.** Commands emit JSON unless `--human` is given.

## Layout

- `nb_cells.py` — the tool. The module docstring is the canonical command
  reference; keep `--help`, `README.md`, and that docstring in sync when
  behavior changes.
- `example_notebook.ipynb` — fixture for manual testing. Not imported by code.
- `README.md` — user-facing overview.
- `USAGE_WITH_CLAUDE.md` — how to embed the tool into a consuming project's
  Claude Code config (CLAUDE.md snippet + permission rule).

## Working conventions

- Keep scratch/intermediate files in `./tmp/` (gitignored), never in the repo
  root.
- When you change command behavior or flags, update **all three** of: the
  module docstring, `README.md`, and any examples.
- If you add tests, mirror the source: `nb_cells.py` ↔ `tests/test_nb_cells.py`.
