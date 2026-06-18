# docs/

Reference and background documentation for `nb_cells`. This folder holds the
"why" and comparative material; user-facing "how" lives in the repo-root
[README.md](../README.md), and Claude Code integration lives in
[USAGE_WITH_CLAUDE.md](../USAGE_WITH_CLAUDE.md).

Contents:

- [comparison-vs-native-notebook-tools.md](./comparison-vs-native-notebook-tools.md)
  — `nb_cells.py` vs. Claude Code's built-in `Read` + `NotebookEdit`: feature
  matrix, when to use which, how native uses context, and a proposed inline
  plot-rendering enhancement.
- [cell-naming-convention.md](./cell-naming-convention.md) — the `# [name]`
  cell-tagging convention, the identifier resolution order, and why named cells
  are the preferred way to address a cell.

New docs here should be conceptual/reference material. Command syntax belongs in
the module docstring and README; integration instructions belong in
USAGE_WITH_CLAUDE.md.
