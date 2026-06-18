# Embedding nb_cells into Claude Code

This document captures the conventions used to integrate `nb_cells.py` into a
Claude Code workflow. Drop the snippets below into a consuming project's
`CLAUDE.md` and `settings.json`, adjusting the absolute path to wherever you
cloned this repo.

> Replace `/ABS/PATH/TO/nb_cells/nb_cells.py` throughout with the real absolute
> path on your machine.

## 1. CLAUDE.md instructions

Add a block like this to your **global** (`~/.claude/CLAUDE.md`) or
**project-local** (`<project>/CLAUDE.md`) instructions. Two rules carry the
weight: always invoke by **absolute path**, and always pass cell bodies via
**`--file`** (never heredoc pipes).

````markdown
### nb_cells.py: notebook cell access

Invoke by **absolute path** so the permission allowlist in `settings.json`
matches and you are not prompted for approval:

```bash
python3 /ABS/PATH/TO/nb_cells/nb_cells.py <args>
```

Never use `cd ... && python3 nb_cells.py` or other relative-path invocations —
they bypass the permission rules and will prompt for approval.

#### Always use `--file`, never heredoc pipes

When passing cell content to `nb_cells.py edit` or `nb_cells.py add`, **always**
use the `--file` flag:

1. Write the cell content to a temp file with the **Write** tool (e.g.
   `./tmp/cell_<name>.py`).
2. Invoke `nb_cells.py` with `--file`:
   ```bash
   python3 /ABS/PATH/TO/nb_cells/nb_cells.py edit notebook.ipynb cell-name --file ./tmp/cell_<name>.py
   ```

**Never** pipe content via heredoc (`cat << 'EOF' | python3 nb_cells.py ...`).
Heredoc pipes trigger shell safety warnings ("Unhandled node type: pipeline",
"expansion obfuscation") that require manual approval, defeating the permission
allowlist.

#### Naming cells — `# [name]`

**Name every cell you create** with a tag on its first line. This is the
preferred way to address a cell: names are embedded in the source, so they
survive reordering and file saves, and you can refer to cells by meaning in
conversation ("edit the `load-data` cell").

- Code cells: `# [short-name]` (e.g. `# [load-data]`).
- Markdown cells: `<!-- [short-name] -->`.

Names must be unique within the notebook and tersely describe the cell. The
agent should refer to cells by these names; fall back to the nbformat `id`
(via `list`) only when a cell is unnamed, and avoid index-based addressing
(unstable — inserting a cell above shifts all later indices).
````

For the full rationale and resolution order, see
[docs/cell-naming-convention.md](./docs/cell-naming-convention.md).

## 2. settings.json permission rule

Add the tool's absolute path to the `permissions.allow` list so the agent can
run it without a prompt:

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 /ABS/PATH/TO/nb_cells/nb_cells.py *)"
    ]
  }
}
```

The trailing ` *` matches any arguments. Because the rule keys on the exact
absolute path, **relative-path invocations will not match** — which is why the
`CLAUDE.md` rule above insists on the absolute path.

## Why these rules exist

- **Absolute path** → the permission allowlist is path-keyed; a relative path
  (or a `cd && ...` prefix) won't match the rule and the agent gets prompted.
- **`--file` over heredoc** → piped heredocs read to Claude Code's shell parser
  as obfuscated/unhandled constructs and force manual approval; writing to a
  temp file and passing `--file` stays inside the allowlist.
