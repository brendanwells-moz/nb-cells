#!/usr/bin/env python3
"""Jupyter notebook cell accessor for AI agents and humans.

This tool lets you read and edit individual cells in a Jupyter notebook
without loading the entire file. Output is machine-readable JSON by default.

COMMANDS:

  nb_cells.py new <notebook> [--force]
      Create a new empty notebook. Errors if the file already exists.

  nb_cells.py list <notebook> [--human]
      List all cells with their identifiers, types, and a source preview.
      --human prints a plain-text table instead of JSON.

  nb_cells.py read <notebook> <cell-id> [...] [-C N] [-B N] [-A M] [--no-outputs | --outputs]
  nb_cells.py get  <notebook> <cell-id> [...] [-C N] [-B N] [-A M] [--no-outputs | --outputs]
      Read one or more cells, including their outputs. ('get' is an alias for 'read'.)
      -C / --context N       Include N cells on BOTH sides (like grep -C).
      -B / --context-before  Include N cells before.
      -A / --context-after   Include M cells after.
      --no-outputs           Source only (omit outputs and execution_count).
      --outputs              Outputs only (omit source). The inverse of --no-outputs.
      When a cell has image outputs, the JSON includes an "image_outputs" count and a
      "hint" pointing at 'extract-images' (the base64 is never dumped as text).

  nb_cells.py status <notebook> [--cell <cell-id>] [--human]
      Execution-status sweep across all cells (or one cell with --cell). For each
      code cell: executed?, execution_count, errored (+ename/evalue), a stream
      preview, and the output/MIME types it produced. --human prints a table.
      Use this instead of looping the notebook JSON in raw Python.

  nb_cells.py extract-images <notebook> <cell-id> [...] [--out-dir DIR]
      Decode a cell's image outputs (image/png, image/jpeg, image/svg+xml) to files
      and print their paths, so you can then Read them visually. Default --out-dir
      is ./tmp (typically gitignored). Use this instead of decoding base64 by hand.

  nb_cells.py edit <notebook> <cell-id> --file <path>
      Replace a cell's source with content from a file (or stdin).

      !! FULL REPLACE: the ENTIRE cell source is replaced with the new content.
      !! Sending partial content will result in a partial (broken) cell.
      !! Use --file with the COMPLETE new cell source.

  nb_cells.py add <notebook> [--after <id>] [--before <id>] [--end] [--type code|markdown] --file <path>
      Insert a new cell with source from a file (or stdin). Default position: --end.

  nb_cells.py import <notebook> <cells.json> [--after <id>] [--before <id>] [--end]
      Bulk-insert cells from a JSON file as a contiguous block. Default position: --end.
      JSON format: array of {"source": "...", "type": "code|markdown"} objects.
      "type" defaults to "code" if omitted.

  nb_cells.py move <notebook> <cell-id> --after <id> | --before <id> | --end
      Move a cell to a new position within the notebook.
      NOTE: --after/--before targets are resolved after the source cell is
      removed, so index references may shift. Use named cells or cell IDs.

  NOTE: There is no 'delete' command — automatic deletion by agents risks
  accidental data loss. To delete a cell manually, open the notebook in
  JupyterLab/Colab and delete it there, or use the --human flag to find the
  cell index and run:

      python3 -c "import json; f='NOTEBOOK.ipynb'; nb=json.load(open(f)); nb['cells'].pop(INDEX); json.dump(nb, open(f,'w'), indent=1, ensure_ascii=False)"

CELL IDENTIFIERS (resolved in this order):

  1. Named   — code cells:     "# [short-name]" on the first line.
               markdown cells: "<!-- [short-name] -->" on the first line.
               Stable: survives cell reordering because it is embedded in the source.
  2. Cell ID — the 'id' field from nbformat 4.5+ (e.g. "a1b2c3d4").
               Stable: persists through reordering and file saves.
               Find it with: nb_cells.py list <notebook>
  3. Index   — integer position (0-based). UNSTABLE: inserting a cell above shifts
               all subsequent indices. Use only when no stable identifier is available.
               Editing by index prints a warning to stderr.

OUTPUT:

  All output is JSON (machine-readable) unless --human is given to list.

EXAMPLES:

  # Create a new notebook
  nb_cells.py new analysis.ipynb

  # List all cells
  nb_cells.py list analysis.ipynb

  # Read a named cell
  nb_cells.py read analysis.ipynb load-data

  # Read a cell with 3 cells of context on each side
  nb_cells.py read analysis.ipynb load-data -C 3

  # Read source only (no outputs)
  nb_cells.py read analysis.ipynb load-data --no-outputs

  # Read outputs only (no source)
  nb_cells.py read analysis.ipynb fit-model --outputs

  # Execution-status sweep (did each cell run / error / print?)
  nb_cells.py status analysis.ipynb --human

  # Save a cell's plot to a file you can Read
  nb_cells.py extract-images analysis.ipynb plot-residuals --out-dir ./tmp

  # Edit a cell — write new source to a file, then pass with --file
  nb_cells.py edit analysis.ipynb load-data --file /tmp/load_data.py

  # Add a cell from a file
  nb_cells.py add analysis.ipynb --after load-data --file /tmp/validate.py

  # Bulk-insert multiple cells from a JSON spec
  nb_cells.py import analysis.ipynb cells.json --after setup

  # Stdin alternative (beware shell quoting — prefer --file)
  echo '# [setup]' | nb_cells.py add analysis.ipynb
"""

from __future__ import annotations

__version__ = "0.2.0-beta"

import argparse
import base64
import json
import os
import re
import secrets
import sys
import tempfile

# ---------------------------------------------------------------------------
# Notebook I/O
# ---------------------------------------------------------------------------

def load_notebook(path: str) -> dict:
    try:
        with open(path, "rb") as f:
            raw = f.read(8192)
        line_ending = "\r\n" if b"\r\n" in raw else "\n"
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        nb["_line_ending"] = line_ending
        return nb
    except FileNotFoundError:
        _die(f"Notebook not found: {path}")
    except json.JSONDecodeError as e:
        _die(f"Invalid notebook JSON in {path}: {e}")


def save_notebook_atomic(nb: dict, path: str):
    """Write notebook to a temp file in the same directory, then rename.

    Preserves the line-ending style detected by load_notebook (\r\n vs \n).
    """
    line_ending = nb.pop("_line_ending", "\n")
    dir_ = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            content = json.dumps(nb, indent=1, ensure_ascii=False)
            if line_ending == "\r\n":
                content = content.replace("\n", "\r\n")
            f.write(content)
            f.write(line_ending)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------

def cell_source(cell: dict) -> str:
    """Return cell source as a single string (nbformat stores it as str or list)."""
    src = cell.get("source", "")
    if isinstance(src, list):
        return "".join(src)
    return src


def cell_name(cell: dict) -> str | None:
    """Return the cell's short-name identifier, or None.

    Code cells:     # [short-name]       on the first line.
    Markdown cells: <!-- [short-name] --> on the first line.
    """
    src = cell_source(cell)
    first_line = src.split("\n")[0].rstrip()
    cell_type = cell.get("cell_type", "")
    if cell_type == "code":
        m = re.match(r"^#\s*\[(.+?)\]\s*$", first_line)
        return m.group(1) if m else None
    elif cell_type == "markdown":
        m = re.match(r"^<!--\s*\[(.+?)\]\s*-->\s*$", first_line)
        return m.group(1) if m else None
    return None


def cell_short_repr(cell: dict) -> str:
    """One-line source preview (≤60 chars), skipping the name line."""
    src = cell_source(cell)
    cell_type = cell.get("cell_type", "")
    lines = [l for l in src.splitlines() if l.strip()]
    if cell_type == "code":
        lines = [l for l in lines if not re.match(r"^#\s*\[.+?\]\s*$", l)]
    elif cell_type == "markdown":
        lines = [l for l in lines if not re.match(r"^<!--\s*\[.+?\]\s*-->\s*$", l)]
    preview = lines[0] if lines else "(empty)"
    if len(preview) > 60:
        preview = preview[:57] + "..."
    return preview


def format_outputs(outputs: list) -> list:
    """Normalize cell outputs into a consistent list of dicts."""
    result = []
    for out in outputs:
        otype = out.get("output_type", "")
        if otype == "stream":
            text = out.get("text", "")
            if isinstance(text, list):
                text = "".join(text)
            result.append({"output_type": "stream", "name": out.get("name", "stdout"), "text": text})
        elif otype in ("execute_result", "display_data"):
            data = out.get("data", {})
            entry = {"output_type": otype}
            if "text/plain" in data:
                txt = data["text/plain"]
                if isinstance(txt, list):
                    txt = "".join(txt)
                entry["text"] = txt
            if "text/html" in data:
                html = data["text/html"]
                if isinstance(html, list):
                    html = "".join(html)
                entry["html"] = html
            if "image/png" in data:
                entry["image_png"] = "(binary — omitted)"
            if "image/svg+xml" in data:
                svg = data["image/svg+xml"]
                if isinstance(svg, list):
                    svg = "".join(svg)
                entry["svg"] = svg
            if otype == "execute_result":
                entry["execution_count"] = out.get("execution_count")
            result.append(entry)
        elif otype == "error":
            result.append({
                "output_type": "error",
                "ename": out.get("ename", ""),
                "evalue": out.get("evalue", ""),
                "traceback": out.get("traceback", []),
            })
        else:
            result.append({"output_type": otype, "raw": out})
    return result


# Image MIME types we can extract to files, mapped to file extensions.
IMAGE_MIME_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/svg+xml": "svg",
}


def count_image_outputs(outputs: list) -> int:
    """Number of rich outputs carrying at least one extractable image."""
    n = 0
    for out in outputs:
        if out.get("output_type") in ("execute_result", "display_data"):
            if any(m in out.get("data", {}) for m in IMAGE_MIME_EXT):
                n += 1
    return n


def _filename_prefix(idx: int, cell: dict) -> str:
    """Filesystem-safe prefix for extracted files: name, else id, else cellN."""
    base = cell_name(cell) or cell.get("id") or f"cell{idx}"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)


def extract_cell_images(idx: int, cell: dict, out_dir: str) -> list:
    """Decode a cell's image outputs to files in out_dir.

    Returns [{"path": <abspath>, "mime": <mime>}, ...] for each image written.
    PNG/JPEG are base64-decoded to bytes; SVG is written as UTF-8 text.
    """
    written = []
    for out_i, out in enumerate(cell.get("outputs", [])):
        if out.get("output_type") not in ("execute_result", "display_data"):
            continue
        data = out.get("data", {})
        for mime, ext in IMAGE_MIME_EXT.items():
            if mime not in data:
                continue
            payload = data[mime]
            if isinstance(payload, list):
                payload = "".join(payload)
            fpath = os.path.join(out_dir, f"{_filename_prefix(idx, cell)}_out{out_i}.{ext}")
            if mime == "image/svg+xml":
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(payload)
            else:
                with open(fpath, "wb") as f:
                    f.write(base64.b64decode(payload))
            written.append({"path": os.path.abspath(fpath), "mime": mime})
    return written


def build_cell_status(idx: int, cell: dict) -> dict:
    """Execution-status summary for one cell (for the `status` command).

    For code cells: did it run, what was its execution_count, did it error
    (+ename/evalue), did it print to a stream (+preview), and what output/MIME
    types did it produce. This is the cross-cell sweep that replaces looping the
    notebook JSON in raw Python.
    """
    ctype = cell.get("cell_type", "unknown")
    info = {"index": idx, "id": cell.get("id"), "name": cell_name(cell), "type": ctype}
    if ctype != "code":
        return info

    outputs = cell.get("outputs", [])
    exec_count = cell.get("execution_count")
    info["executed"] = exec_count is not None
    info["execution_count"] = exec_count

    err = next((o for o in outputs if o.get("output_type") == "error"), None)
    info["errored"] = err is not None
    if err is not None:
        info["ename"] = err.get("ename", "")
        info["evalue"] = err.get("evalue", "")

    stream_parts = []
    for o in outputs:
        if o.get("output_type") == "stream":
            t = o.get("text", "")
            stream_parts.append("".join(t) if isinstance(t, list) else t)
    stream_text = "".join(stream_parts)
    info["has_stream"] = bool(stream_text)
    if stream_text:
        preview = " ".join(stream_text.split())
        info["stream_preview"] = preview[:200] + ("…" if len(preview) > 200 else "")

    info["output_types"] = sorted({o.get("output_type", "") for o in outputs})
    mimes = set()
    for o in outputs:
        if o.get("output_type") in ("execute_result", "display_data"):
            mimes.update(o.get("data", {}).keys())
    info["mime_types"] = sorted(mimes)
    info["image_outputs"] = count_image_outputs(outputs)
    return info


def _sanitize_shell_escapes(source: str) -> str:
    r"""Fix common shell-escaping artifacts in cell source.

    zsh treats ! as a history-expansion character.  When cell source is piped
    through a shell command (heredoc, echo, etc.), \! sequences can leak into
    the content.  A literal backslash before ! is never valid Python, so we
    unconditionally strip it.
    """
    cleaned = source.replace("\\!", "!")
    if cleaned != source:
        n = source.count("\\!") - cleaned.count("\\!")
        print(
            f"Warning: replaced {n} '\\!' shell-escape artifact(s) in cell source.",
            file=sys.stderr,
        )
    return cleaned


def _read_source(args) -> str:
    """Read cell source from --file if given, else from stdin."""
    if getattr(args, "file", None):
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            _die(f"Source file not found: {args.file}")
        except OSError as e:
            _die(f"Could not read source file {args.file}: {e}")
    return _sanitize_shell_escapes(sys.stdin.read())


def _make_cell(source: str, cell_type: str, existing_ids: set) -> dict:
    """Build a new cell dict with a unique ID."""
    while True:
        new_id = secrets.token_hex(4)
        if new_id not in existing_ids:
            existing_ids.add(new_id)
            break
    cell: dict = {
        "id": new_id,
        "cell_type": cell_type,
        "source": source,
        "metadata": {},
    }
    if cell_type == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
    return cell


# ---------------------------------------------------------------------------
# Cell resolution
# ---------------------------------------------------------------------------

def resolve_cell(nb: dict, identifier: str) -> tuple[int, dict, str]:
    """
    Find a cell by name, id, or index.
    Returns (index, cell, match_type) where match_type is 'name'|'id'|'index'.
    Exits with an error if not found or ambiguous.
    """
    cells = nb["cells"]

    # 1. Try name match (# [short-name])
    name_matches = [
        (i, c) for i, c in enumerate(cells)
        if cell_name(c) == identifier
    ]
    if len(name_matches) == 1:
        i, c = name_matches[0]
        return i, c, "name"
    if len(name_matches) > 1:
        indices = [i for i, _ in name_matches]
        _die(f"Ambiguous: multiple cells named [{identifier}] at indices {indices}. "
             f"Names must be unique.")

    # 2. Try cell id match
    id_matches = [
        (i, c) for i, c in enumerate(cells)
        if c.get("id") == identifier
    ]
    if len(id_matches) == 1:
        i, c = id_matches[0]
        return i, c, "id"
    if len(id_matches) > 1:
        indices = [i for i, _ in id_matches]
        _die(f"Ambiguous: multiple cells with id '{identifier}' at indices {indices}.")

    # 3. Try numeric index
    try:
        idx = int(identifier)
    except ValueError:
        _die(
            f"Cell not found: {identifier!r}\n"
            f"  Not a named cell (# [{identifier}]), not a cell id, and not an integer index.\n"
            f"  Run 'nb_cells.py list <notebook>' to see available identifiers."
        )

    if idx < 0 or idx >= len(cells):
        _die(f"Index {idx} out of range — notebook has {len(cells)} cells (0–{len(cells)-1}).")

    return idx, cells[idx], "index"


def _resolve_insert_position(nb: dict, args) -> tuple[int, dict | None]:
    """
    Resolve --after / --before / --end into (insert_at_index, ref_info_or_None).
    Shared by add and import.
    """
    cells = nb["cells"]
    n = len(cells)

    if args.after:
        ref_idx, ref_cell, ref_match = resolve_cell(nb, args.after)
        if ref_match == "index":
            print(
                f"Warning: --after references cell by index {ref_idx} — this is UNSTABLE.",
                file=sys.stderr,
            )
        ref_info = {"position": "after", "index": ref_idx, "id": ref_cell.get("id"), "name": cell_name(ref_cell)}
        return ref_idx + 1, ref_info
    elif args.before:
        ref_idx, ref_cell, ref_match = resolve_cell(nb, args.before)
        if ref_match == "index":
            print(
                f"Warning: --before references cell by index {ref_idx} — this is UNSTABLE.",
                file=sys.stderr,
            )
        ref_info = {"position": "before", "index": ref_idx, "id": ref_cell.get("id"), "name": cell_name(ref_cell)}
        return ref_idx, ref_info
    else:
        return n, None


def resolve_cells_with_context(
    nb: dict,
    identifiers: list[str],
    context_before: int,
    context_after: int,
    include_outputs: bool = True,
    include_source: bool = True,
) -> list[dict]:
    """
    Resolve a list of identifiers, expand context windows, deduplicate,
    and return an ordered list of cell info dicts with is_context flags.
    """
    cells = nb["cells"]
    n = len(cells)

    requested = {}  # index -> match_type
    for ident in identifiers:
        idx, _, mtype = resolve_cell(nb, ident)
        requested[idx] = mtype

    all_indices = set(requested.keys())
    for req_idx in list(requested.keys()):
        for offset in range(1, context_before + 1):
            ci = req_idx - offset
            if ci >= 0:
                all_indices.add(ci)
        for offset in range(1, context_after + 1):
            ci = req_idx + offset
            if ci < n:
                all_indices.add(ci)

    result = []
    for idx in sorted(all_indices):
        c = cells[idx]
        is_ctx = idx not in requested
        result.append(build_cell_info(
            idx, c,
            include_outputs=include_outputs,
            include_source=include_source,
            is_context=is_ctx,
        ))
    return result


# ---------------------------------------------------------------------------
# Cell info builders
# ---------------------------------------------------------------------------

def build_cell_info(
    idx: int,
    cell: dict,
    include_outputs: bool = False,
    include_source: bool = True,
    is_context: bool = False,
) -> dict:
    src = cell_source(cell)
    name = cell_name(cell)
    info = {
        "index": idx,
        "id": cell.get("id"),
        "name": name,
        "type": cell.get("cell_type", "unknown"),
    }
    if include_source:
        info["lines"] = len(src.splitlines()) if src.strip() else 0
        info["source"] = src
    if is_context:
        info["is_context"] = True
    if include_outputs:
        raw_outputs = cell.get("outputs", [])
        info["outputs"] = format_outputs(raw_outputs)
        info["execution_count"] = cell.get("execution_count")
        n_imgs = count_image_outputs(raw_outputs)
        if n_imgs:
            ident = name or cell.get("id") or str(idx)
            info["image_outputs"] = n_imgs
            info["hint"] = (
                f"{n_imgs} image output(s) not shown as text — view with: "
                f"nb_cells.py extract-images <notebook> {ident}"
            )
    return info


def build_cell_summary(idx: int, cell: dict) -> dict:
    """Compact summary for the list command."""
    src = cell_source(cell)
    name = cell_name(cell)
    has_output = bool(cell.get("outputs"))
    return {
        "index": idx,
        "id": cell.get("id"),
        "name": name,
        "type": cell.get("cell_type", "unknown"),
        "lines": len(src.splitlines()) if src.strip() else 0,
        "has_output": has_output,
        "source_preview": cell_short_repr(cell),
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args):
    nb = load_notebook(args.notebook)
    cells = nb["cells"]
    summaries = [build_cell_summary(i, c) for i, c in enumerate(cells)]

    if args.human:
        # Fixed-width plain-text table
        # Columns: INDEX  ID            NAME           TYPE      LINES  OUT  PREVIEW
        rows = []
        for s in summaries:
            rows.append((
                str(s["index"]),
                s["id"] or "",
                s["name"] or "",
                s["type"],
                str(s["lines"]),
                "Y" if s["has_output"] else "-",
                s["source_preview"],
            ))
        headers = ("IDX", "CELL-ID", "NAME", "TYPE", "LINES", "OUT", "PREVIEW")
        widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]
        # Cap preview column at 50
        widths[6] = min(widths[6], 50)
        fmt = "  ".join(f"{{:<{w}}}" for w in widths)
        print(fmt.format(*headers))
        print("  ".join("-" * w for w in widths))
        for r in rows:
            preview = r[6]
            if len(preview) > widths[6]:
                preview = preview[:widths[6] - 3] + "..."
            print(fmt.format(r[0], r[1], r[2], r[3], r[4], r[5], preview))
    else:
        print(json.dumps({"total": len(summaries), "cells": summaries}, indent=2, ensure_ascii=False))


def cmd_read(args):
    if args.outputs_only and args.no_outputs:
        _die("--outputs and --no-outputs are mutually exclusive: pick source-only, "
             "outputs-only, or neither (the default shows both).")
    nb = load_notebook(args.notebook)
    include_outputs = not args.no_outputs
    include_source = not args.outputs_only
    ctx_before = max(args.context, args.context_before)
    ctx_after = max(args.context, args.context_after)
    cell_infos = resolve_cells_with_context(
        nb,
        args.cell_ids,
        context_before=ctx_before,
        context_after=ctx_after,
        include_outputs=include_outputs,
        include_source=include_source,
    )
    print(json.dumps({"cells": cell_infos}, indent=2, ensure_ascii=False))


def cmd_extract_images(args):
    nb = load_notebook(args.notebook)
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    results = []
    total = 0
    for ident in args.cell_ids:
        idx, cell, _ = resolve_cell(nb, ident)
        images = extract_cell_images(idx, cell, out_dir)
        total += len(images)
        results.append({
            "cell": {"index": idx, "id": cell.get("id"), "name": cell_name(cell)},
            "images": images,
        })
    print(json.dumps({
        "out_dir": os.path.abspath(out_dir),
        "images_written": total,
        "cells": results,
    }, indent=2, ensure_ascii=False))


def cmd_status(args):
    nb = load_notebook(args.notebook)
    cells = nb["cells"]
    if args.cell:
        idx, cell, _ = resolve_cell(nb, args.cell)
        targets = [(idx, cell)]
    else:
        targets = list(enumerate(cells))
    statuses = [build_cell_status(i, c) for i, c in targets]

    if args.human:
        _print_status_table(statuses)
    else:
        print(json.dumps({"total": len(statuses), "cells": statuses}, indent=2, ensure_ascii=False))


def _print_status_table(statuses: list):
    rows = []
    for s in statuses:
        if s.get("type") != "code":
            rows.append((str(s["index"]), s.get("name") or "", s.get("type", ""), "", "", "", ""))
            continue
        exec_s = str(s.get("execution_count")) if s.get("executed") else "-"
        err_s = s.get("ename", "") if s.get("errored") else "-"
        stream_s = "Y" if s.get("has_stream") else "-"
        mime_s = ",".join(m.split("/")[-1] for m in s.get("mime_types", [])) or "-"
        rows.append((str(s["index"]), s.get("name") or "", s["type"], exec_s, err_s, stream_s, mime_s))
    headers = ("IDX", "NAME", "TYPE", "EXEC", "ERR", "STREAM", "MIME")
    widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt.format(*r))


def cmd_edit(args):
    new_source = _read_source(args)

    if not new_source.strip():
        _die(
            "Source is empty — refusing to replace cell with empty content.\n"
            "  If you intentionally want an empty cell, pipe a single newline or write one to --file."
        )

    nb = load_notebook(args.notebook)
    idx, cell, match_type = resolve_cell(nb, args.cell_id)

    if match_type == "index":
        print(
            f"Warning: cell referenced by index {idx} — this is UNSTABLE. "
            f"Adding a cell above will shift this index. "
            f"Add '# [{idx}]' to the cell source or use its cell ID instead.",
            file=sys.stderr,
        )

    old_source = cell_source(cell)
    old_lines = len(old_source.splitlines()) if old_source.strip() else 0
    new_lines = len(new_source.splitlines()) if new_source.strip() else 0

    if args.dry_run:
        print(json.dumps({
            "status": "dry_run",
            "replace_mode": "full",
            "cell": {"index": idx, "id": cell.get("id"), "name": cell_name(cell)},
            "lines_before": old_lines,
            "lines_after": new_lines,
            "outputs_would_clear": not args.keep_outputs,
            "new_source": new_source,
        }, indent=2, ensure_ascii=False))
        return

    original_sources = [cell_source(c) for c in nb["cells"]]
    original_outputs = [c.get("outputs", []) for c in nb["cells"]]
    original_exec = [c.get("execution_count") for c in nb["cells"]]

    cell["source"] = new_source
    if not args.keep_outputs:
        if "outputs" in cell:
            cell["outputs"] = []
        if "execution_count" in cell:
            cell["execution_count"] = None

    save_notebook_atomic(nb, args.notebook)

    nb2 = load_notebook(args.notebook)
    cells2 = nb2["cells"]
    changed = [
        i for i in range(len(nb["cells"]))
        if cell_source(cells2[i]) != original_sources[i]
          or cells2[i].get("outputs", []) != original_outputs[i]
          or cells2[i].get("execution_count") != original_exec[i]
    ]
    if changed != [idx]:
        _die(
            f"Post-write verification FAILED: expected only cell {idx} to change, "
            f"but these indices differ: {changed}\n"
            f"The notebook may be in an inconsistent state."
        )

    print(json.dumps({
        "status": "ok",
        "replace_mode": "full",
        "cell": {"index": idx, "id": cell.get("id"), "name": cell_name(cell)},
        "match_type": match_type,
        "lines_before": old_lines,
        "lines_after": new_lines,
        "outputs_cleared": not args.keep_outputs,
    }, indent=2, ensure_ascii=False))


def cmd_new(args):
    path = args.notebook
    if os.path.exists(path) and not args.force:
        _die(
            f"File already exists: {path}\n"
            f"  Use --force to overwrite."
        )

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
            },
        },
        "cells": [],
    }

    save_notebook_atomic(nb, path)
    print(json.dumps({"status": "ok", "path": path, "nbformat": 4, "nbformat_minor": 5, "cells": 0}, indent=2))


def cmd_add(args):
    new_source = _read_source(args)
    if not new_source.strip():
        _die(
            "Source is empty — refusing to add a cell with empty content.\n"
            "  If you intentionally want an empty cell, pipe a single newline or write one to --file."
        )

    nb = load_notebook(args.notebook)
    cells = nb["cells"]
    n = len(cells)

    insert_at, ref_info = _resolve_insert_position(nb, args)

    existing_ids = {c.get("id") for c in cells}
    new_cell = _make_cell(new_source, args.type, existing_ids)
    new_id = new_cell["id"]

    original_ids = [c.get("id") for c in cells]
    cells.insert(insert_at, new_cell)
    save_notebook_atomic(nb, args.notebook)

    nb2 = load_notebook(args.notebook)
    cells2 = nb2["cells"]
    if len(cells2) != n + 1:
        _die(f"Post-write verification FAILED: expected {n + 1} cells, got {len(cells2)}.")
    ids2 = [c.get("id") for c in cells2]
    if [i for i in ids2 if i != new_id] != original_ids:
        _die("Post-write verification FAILED: original cell order was disturbed.")
    if ids2[insert_at] != new_id:
        _die(f"Post-write verification FAILED: new cell landed at {ids2.index(new_id)}, expected {insert_at}.")
    if cell_source(cells2[insert_at]) != new_source:
        _die("Post-write verification FAILED: new cell source does not match input.")

    result: dict = {
        "status": "ok",
        "cell": {
            "index": insert_at,
            "id": new_id,
            "name": cell_name(new_cell),
            "type": args.type,
            "lines": len(new_source.splitlines()) if new_source.strip() else 0,
        },
    }
    if ref_info:
        result["reference_cell"] = ref_info
    else:
        result["position"] = "end"
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_import(args):
    # Load and validate the cells JSON file
    try:
        with open(args.cells_json, "r", encoding="utf-8") as f:
            cell_specs = json.load(f)
    except FileNotFoundError:
        _die(f"Cells JSON file not found: {args.cells_json}")
    except json.JSONDecodeError as e:
        _die(f"Invalid JSON in {args.cells_json}: {e}")

    if not isinstance(cell_specs, list):
        _die(f"{args.cells_json} must contain a JSON array of cell objects.")
    if not cell_specs:
        _die(f"{args.cells_json} is an empty array — nothing to import.")

    for i, spec in enumerate(cell_specs):
        if not isinstance(spec, dict):
            _die(f"Item {i} in {args.cells_json} is not an object.")
        if "source" not in spec:
            _die(f"Item {i} in {args.cells_json} is missing required field 'source'.")
        cell_type = spec.get("type", "code")
        if cell_type not in ("code", "markdown"):
            _die(f"Item {i} in {args.cells_json} has invalid type {cell_type!r}. Must be 'code' or 'markdown'.")

    nb = load_notebook(args.notebook)
    cells = nb["cells"]
    n = len(cells)

    insert_at, ref_info = _resolve_insert_position(nb, args)

    existing_ids = {c.get("id") for c in cells}
    original_ids = [c.get("id") for c in cells]

    new_cells = []
    for spec in cell_specs:
        cell_type = spec.get("type", "code")
        new_cell = _make_cell(spec["source"], cell_type, existing_ids)
        new_cells.append(new_cell)

    # Insert the block at insert_at (in order)
    for offset, new_cell in enumerate(new_cells):
        cells.insert(insert_at + offset, new_cell)

    save_notebook_atomic(nb, args.notebook)

    # Post-write verification
    nb2 = load_notebook(args.notebook)
    cells2 = nb2["cells"]
    k = len(new_cells)
    new_ids = [c["id"] for c in new_cells]

    if len(cells2) != n + k:
        _die(f"Post-write verification FAILED: expected {n + k} cells, got {len(cells2)}.")

    ids2 = [c.get("id") for c in cells2]
    ids2_without_new = [i for i in ids2 if i not in set(new_ids)]
    if ids2_without_new != original_ids:
        _die("Post-write verification FAILED: original cell order was disturbed.")

    block_ids = ids2[insert_at:insert_at + k]
    if block_ids != new_ids:
        _die(f"Post-write verification FAILED: inserted block is not at expected position {insert_at}.")

    created = [
        {
            "index": insert_at + offset,
            "id": c["id"],
            "name": cell_name(c),
            "type": c["cell_type"],
            "lines": len(cell_source(c).splitlines()) if cell_source(c).strip() else 0,
        }
        for offset, c in enumerate(new_cells)
    ]
    result: dict = {"status": "ok", "cells_imported": k, "cells": created}
    if ref_info:
        result["reference_cell"] = ref_info
    else:
        result["position"] = "end"
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_move(args):
    """Move a cell to a new position.

    --after/--before targets are resolved AFTER the source cell is removed from
    the list.  This means adjacent-cell references shift by one index, but the
    result is always correct: "move A --after B" puts A immediately after B.
    Use named cells or cell IDs to avoid index-shift surprises.
    """
    nb = load_notebook(args.notebook)
    cells = nb["cells"]
    n = len(cells)

    # Resolve source cell
    src_idx, src_cell, src_match = resolve_cell(nb, args.cell_id)
    if src_match == "index":
        print(
            f"Warning: source cell referenced by index {src_idx} — this is UNSTABLE. "
            f"Use a named cell or cell ID instead.",
            file=sys.stderr,
        )

    src_id = src_cell.get("id")
    src_name = cell_name(src_cell)

    # Pop the source cell — destination must be resolved on the post-pop list
    cells.pop(src_idx)

    # Resolve destination on the modified list
    insert_at, ref_info = _resolve_insert_position(nb, args)

    # If inserting back at the original index, the cell returns to its old spot — no-op
    if insert_at == src_idx:
        cells.insert(src_idx, src_cell)
        print(json.dumps({
            "status": "no_op",
            "message": "Cell is already at the requested position.",
            "cell": {"index": src_idx, "id": src_id, "name": src_name},
        }, indent=2, ensure_ascii=False))
        return

    # Insert at destination
    cells.insert(insert_at, src_cell)
    save_notebook_atomic(nb, args.notebook)

    # Post-write verification
    nb2 = load_notebook(args.notebook)
    cells2 = nb2["cells"]
    if len(cells2) != n:
        _die(f"Post-write verification FAILED: expected {n} cells, got {len(cells2)}.")

    ids2 = [c.get("id") for c in cells2]
    if ids2[insert_at] != src_id:
        _die(
            f"Post-write verification FAILED: moved cell expected at index {insert_at}, "
            f"found at {ids2.index(src_id) if src_id in ids2 else '(missing)'}."
        )

    original_ids = {c.get("id") for c in cells}
    actual_ids = {c.get("id") for c in cells2}
    if original_ids != actual_ids:
        _die("Post-write verification FAILED: cell IDs changed after move.")

    print(json.dumps({
        "status": "ok",
        "cell": {"index": insert_at, "id": src_id, "name": src_name},
        "moved_from": src_idx,
        "moved_to": insert_at,
    }, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------

def _die(message: str):
    print(json.dumps({"error": message}), file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nb_cells.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # new
    p_new = sub.add_parser(
        "new",
        help="Create a new empty notebook. Errors if the file already exists.",
    )
    p_new.add_argument("notebook", help="Path for the new .ipynb file")
    p_new.add_argument("--force", action="store_true", help="Overwrite if the file already exists")

    # list
    p_list = sub.add_parser(
        "list",
        help="List all cells with identifiers and previews.",
    )
    p_list.add_argument("notebook", help="Path to .ipynb file")
    p_list.add_argument(
        "--human",
        action="store_true",
        help="Print a plain-text table instead of JSON",
    )

    # read (alias: get)
    p_read = sub.add_parser(
        "read",
        aliases=["get"],
        help="Read one or more cells, including their outputs. Alias: 'get'.",
    )
    p_read.add_argument("notebook", help="Path to .ipynb file")
    p_read.add_argument("cell_ids", nargs="+", metavar="cell-id",
                        help="One or more cell identifiers (name, cell id, or index)")
    p_read.add_argument("--context", "-C", type=int, default=0, metavar="N",
                        help="Include N cells on BOTH sides of each requested cell (like grep -C)")
    p_read.add_argument("--context-before", "-B", type=int, default=0, metavar="N", dest="context_before",
                        help="Include N cells before each requested cell")
    p_read.add_argument("--context-after", "-A", type=int, default=0, metavar="M", dest="context_after",
                        help="Include M cells after each requested cell")
    p_read.add_argument("--no-outputs", action="store_true", dest="no_outputs",
                        help="Omit cell outputs and execution_count (source only)")
    p_read.add_argument("--outputs", action="store_true", dest="outputs_only",
                        help="Show ONLY outputs (omit source) — the inverse of --no-outputs")

    # edit
    p_edit = sub.add_parser(
        "edit",
        help=(
            "Replace a cell's source with content read from stdin or --file. "
            "FULL REPLACE: provide the COMPLETE new cell source."
        ),
    )
    p_edit.add_argument("notebook", help="Path to .ipynb file")
    p_edit.add_argument("cell_id", metavar="cell-id", help="Cell identifier (name, cell id, or index)")
    p_edit.add_argument("--file", metavar="path",
                        help="Read new source from this file instead of stdin")
    p_edit.add_argument("--keep-outputs", action="store_true",
                        help="Preserve existing cell outputs after editing (default: clear outputs)")
    p_edit.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing to disk")

    # add
    p_add = sub.add_parser(
        "add",
        help="Insert a new cell with source read from stdin or --file. Default position: --end.",
    )
    p_add.add_argument("notebook", help="Path to .ipynb file")
    pos_group = p_add.add_mutually_exclusive_group()
    pos_group.add_argument("--after", metavar="cell-id", default=None,
                           help="Insert after this cell (name, cell id, or index)")
    pos_group.add_argument("--before", metavar="cell-id", default=None,
                           help="Insert before this cell (name, cell id, or index)")
    pos_group.add_argument("--end", action="store_true", default=False,
                           help="Append at the end of the notebook (default if no position given)")
    p_add.add_argument("--type", choices=["code", "markdown"], default="code",
                       help="Cell type: code (default) or markdown")
    p_add.add_argument("--file", metavar="path",
                       help="Read cell source from this file instead of stdin")

    # import
    p_import = sub.add_parser(
        "import",
        help='Bulk-insert cells from a JSON file. Format: [{"source": "...", "type": "code"}, ...]',
    )
    p_import.add_argument("notebook", help="Path to .ipynb file")
    p_import.add_argument("cells_json", metavar="cells.json",
                          help='JSON file: array of {"source": "...", "type": "code|markdown"} objects')
    pos_group_i = p_import.add_mutually_exclusive_group()
    pos_group_i.add_argument("--after", metavar="cell-id", default=None,
                              help="Insert block after this cell")
    pos_group_i.add_argument("--before", metavar="cell-id", default=None,
                              help="Insert block before this cell")
    pos_group_i.add_argument("--end", action="store_true", default=False,
                              help="Append block at end (default)")

    # move
    p_move = sub.add_parser(
        "move",
        help="Move a cell to a new position within the notebook.",
    )
    p_move.add_argument("notebook", help="Path to .ipynb file")
    p_move.add_argument("cell_id", metavar="cell-id",
                        help="Cell to move (name, cell id, or index)")
    pos_group_m = p_move.add_mutually_exclusive_group(required=True)
    pos_group_m.add_argument("--after", metavar="cell-id", default=None,
                             help="Move after this cell")
    pos_group_m.add_argument("--before", metavar="cell-id", default=None,
                             help="Move before this cell")
    pos_group_m.add_argument("--end", action="store_true", default=False,
                             help="Move to the end of the notebook")

    # status
    p_status = sub.add_parser(
        "status",
        help="Execution-status sweep: per code cell — ran? errored? printed? output types?",
    )
    p_status.add_argument("notebook", help="Path to .ipynb file")
    p_status.add_argument("--cell", metavar="cell-id", default=None,
                          help="Limit to a single cell (name, cell id, or index); default: all cells")
    p_status.add_argument("--human", action="store_true",
                          help="Print a plain-text table instead of JSON")

    # extract-images
    p_extract = sub.add_parser(
        "extract-images",
        help="Save a cell's image outputs (e.g. plots) to files you can then Read.",
    )
    p_extract.add_argument("notebook", help="Path to .ipynb file")
    p_extract.add_argument("cell_ids", nargs="+", metavar="cell-id",
                           help="One or more cell identifiers (name, cell id, or index)")
    p_extract.add_argument("--out-dir", dest="out_dir", default="./tmp", metavar="DIR",
                           help="Directory to write images into (default: ./tmp, typically gitignored)")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "new": cmd_new,
        "list": cmd_list,
        "read": cmd_read,
        "get": cmd_read,
        "edit": cmd_edit,
        "add": cmd_add,
        "import": cmd_import,
        "move": cmd_move,
        "status": cmd_status,
        "extract-images": cmd_extract_images,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
