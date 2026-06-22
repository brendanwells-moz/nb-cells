"""Tests for nb_cells.py output-introspection features.

Covers the post-execution surface added in 0.2.0: `extract-images`, `status`,
and the `--outputs` / image-hint behavior of `read`. The CLI is exercised
end-to-end via subprocess against a fixture notebook generated in a tempdir
(no committed binary), so each assertion catches a real behavioral regression.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest

NB_CELLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "nb_cells.py"))

# Smallest valid PNG (1x1 transparent), base64-encoded — the payload an image
# output cell would carry under data["image/png"].
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
    "2mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _make_fixture(path):
    """Write a notebook with a stream cell, an image cell, and an error cell."""
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {"id": "md01", "cell_type": "markdown", "metadata": {},
             "source": "<!-- [intro] -->\n# Demo"},
            {"id": "cstream", "cell_type": "code", "metadata": {}, "execution_count": 1,
             "source": "# [printer]\nprint('hello world')",
             "outputs": [{"output_type": "stream", "name": "stdout", "text": "hello world\n"}]},
            {"id": "cimage", "cell_type": "code", "metadata": {}, "execution_count": 2,
             "source": "# [plot]\nplt.plot([1, 2, 3])",
             "outputs": [{"output_type": "display_data", "metadata": {},
                          "data": {"text/plain": "<Figure>", "image/png": PNG_B64}}]},
            {"id": "cerror", "cell_type": "code", "metadata": {}, "execution_count": 3,
             "source": "# [boom]\n1 / 0",
             "outputs": [{"output_type": "error", "ename": "ZeroDivisionError",
                          "evalue": "division by zero", "traceback": ["Traceback ..."]}]},
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f)


def _run(*args):
    return subprocess.run(
        [sys.executable, NB_CELLS, *args],
        capture_output=True, text=True,
    )


class OutputIntrospectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.nb = os.path.join(self.tmp, "fixture.ipynb")
        _make_fixture(self.nb)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _by_name(self, cells, name):
        return next(c for c in cells if c.get("name") == name)

    # --- extract-images -----------------------------------------------------

    def test_extract_images_writes_decoded_png(self):
        out_dir = os.path.join(self.tmp, "imgs")
        r = _run("extract-images", self.nb, "plot", "--out-dir", out_dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["images_written"], 1)
        img = data["cells"][0]["images"][0]
        self.assertEqual(img["mime"], "image/png")
        self.assertTrue(img["path"].endswith(".png"))
        # File exists and contains real PNG bytes (not the base64 text).
        with open(img["path"], "rb") as f:
            head = f.read(8)
        self.assertEqual(head[:4], b"\x89PNG")

    def test_extract_images_none_when_no_image(self):
        out_dir = os.path.join(self.tmp, "imgs2")
        r = _run("extract-images", self.nb, "printer", "--out-dir", out_dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["images_written"], 0)

    # --- status -------------------------------------------------------------

    def test_status_reports_execution_error_and_mime(self):
        r = _run("status", self.nb)
        self.assertEqual(r.returncode, 0, r.stderr)
        cells = json.loads(r.stdout)["cells"]

        plot = self._by_name(cells, "plot")
        self.assertTrue(plot["executed"])
        self.assertEqual(plot["execution_count"], 2)
        self.assertIn("image/png", plot["mime_types"])
        self.assertEqual(plot["image_outputs"], 1)

        boom = self._by_name(cells, "boom")
        self.assertTrue(boom["errored"])
        self.assertEqual(boom["ename"], "ZeroDivisionError")

        printer = self._by_name(cells, "printer")
        self.assertTrue(printer["has_stream"])
        self.assertIn("hello world", printer["stream_preview"])

    def test_status_single_cell(self):
        r = _run("status", self.nb, "--cell", "boom")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["total"], 1)
        self.assertTrue(data["cells"][0]["errored"])

    # --- read --outputs / --no-outputs / hint -------------------------------

    def test_read_outputs_only_omits_source(self):
        r = _run("read", self.nb, "printer", "--outputs")
        self.assertEqual(r.returncode, 0, r.stderr)
        cell = json.loads(r.stdout)["cells"][0]
        self.assertNotIn("source", cell)
        self.assertIn("outputs", cell)

    def test_read_no_outputs_omits_outputs(self):
        r = _run("read", self.nb, "printer", "--no-outputs")
        self.assertEqual(r.returncode, 0, r.stderr)
        cell = json.loads(r.stdout)["cells"][0]
        self.assertIn("source", cell)
        self.assertNotIn("outputs", cell)

    def test_read_default_has_both(self):
        cell = json.loads(_run("read", self.nb, "printer").stdout)["cells"][0]
        self.assertIn("source", cell)
        self.assertIn("outputs", cell)

    def test_read_image_cell_surfaces_hint(self):
        cell = json.loads(_run("read", self.nb, "plot").stdout)["cells"][0]
        self.assertEqual(cell["image_outputs"], 1)
        self.assertIn("extract-images", cell["hint"])

    def test_read_outputs_and_no_outputs_conflict(self):
        r = _run("read", self.nb, "printer", "--outputs", "--no-outputs")
        self.assertEqual(r.returncode, 1)
        self.assertIn("mutually exclusive", r.stderr)


if __name__ == "__main__":
    unittest.main()
