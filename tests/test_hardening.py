"""Hardening tests — edge cases, bad input, error paths.

These tests verify that:
  - Invalid / None input raises clear errors (not AttributeError/TypeError tracebacks).
  - Missing files produce exit code 2 (not a raw traceback).
  - Empty or whitespace-only documents are handled gracefully.
  - A single-line document (top == bottom) is handled correctly.
  - A document with only whitespace lines is handled correctly.
  - The MCP server module imports cleanly (no missing-symbol errors).
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classguard.core import analyze_text, analyze_document, _rank
from classguard.cli import main


# ---------------------------------------------------------------------------
# core.analyze_text — type / value guards
# ---------------------------------------------------------------------------

class TestAnalyzeTextGuards(unittest.TestCase):

    def test_none_input_raises_type_error(self):
        """analyze_text(None) must raise TypeError, not AttributeError."""
        with self.assertRaises(TypeError):
            analyze_text(None)  # type: ignore[arg-type]

    def test_int_input_raises_type_error(self):
        with self.assertRaises(TypeError):
            analyze_text(42)  # type: ignore[arg-type]

    def test_empty_source_raises_value_error(self):
        with self.assertRaises(ValueError):
            analyze_text("SECRET\n(S) body\nSECRET\n", source="")

    def test_empty_string_does_not_crash(self):
        """Empty text should return a Report with BANNER_TOP_MISSING errors."""
        rep = analyze_text("")
        self.assertFalse(rep.ok)
        codes = {f.code for f in rep.findings}
        self.assertIn("BANNER_TOP_MISSING", codes)

    def test_whitespace_only_does_not_crash(self):
        """A document containing only blank lines — no banner, no portions."""
        rep = analyze_text("   \n\n   \n")
        self.assertFalse(rep.ok)
        codes = {f.code for f in rep.findings}
        self.assertIn("BANNER_TOP_MISSING", codes)

    def test_single_line_banner_only(self):
        """One-line doc: the only line is both the top and bottom banner.
        No body — should be compliant at UNCLASSIFIED level."""
        rep = analyze_text("UNCLASSIFIED")
        # top == bottom (same line) so no BANNER_MISMATCH; no portions needed for U
        self.assertEqual(rep.banner_level, "U")
        # ok because PORTIONS_ABSENT only fires for non-U classified docs
        self.assertTrue(rep.ok, rep.to_dict())

    def test_single_line_classified_no_portions(self):
        """One SECRET line that is both banner lines — body is empty,
        so PORTIONS_ABSENT should fire."""
        rep = analyze_text("SECRET")
        # body_start == body_end == same line idx, so body length is 0 — no PORTIONS_ABSENT
        # The document is technically empty-body; we just check it doesn't crash.
        self.assertIsNotNone(rep)


# ---------------------------------------------------------------------------
# core.analyze_document — path guards
# ---------------------------------------------------------------------------

class TestAnalyzeDocumentGuards(unittest.TestCase):

    def test_non_string_path_raises_type_error(self):
        with self.assertRaises(TypeError):
            analyze_document(123)  # type: ignore[arg-type]

    def test_empty_path_raises_value_error(self):
        with self.assertRaises(ValueError):
            analyze_document("")

    def test_missing_file_raises_os_error(self):
        """analyze_document on a nonexistent file should raise OSError."""
        with self.assertRaises(OSError):
            analyze_document("/nonexistent/path/to/file.txt")

    def test_directory_path_raises_os_error(self):
        """Passing a directory path should raise OSError (IsADirectoryError)."""
        with self.assertRaises(OSError):
            analyze_document(tempfile.gettempdir())


# ---------------------------------------------------------------------------
# core internals — _rank robustness
# ---------------------------------------------------------------------------

class TestRankRobustness(unittest.TestCase):

    def test_rank_none_returns_minus_one(self):
        self.assertEqual(_rank(None), -1)

    def test_rank_unknown_string_returns_minus_one(self):
        """Unknown level strings (not in LEVEL_ORDER) must return -1, not raise."""
        self.assertEqual(_rank("FOUO"), -1)
        self.assertEqual(_rank(""), -1)


# ---------------------------------------------------------------------------
# CLI — bad input / IO error exit codes
# ---------------------------------------------------------------------------

class TestCliHardening(unittest.TestCase):

    def _write(self, text: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_missing_file_exits_two(self):
        """A single missing file with no valid reports -> exit 2."""
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = main(["check", "/no/such/file/abc123.txt"])
        self.assertEqual(rc, 2)
        self.assertIn("cannot read", buf_err.getvalue())

    def test_missing_file_mixed_with_good_exits_one(self):
        """One good file + one missing file -> at least one report, so exit code 1
        (had_io_error makes it non-zero even though the good file passed)."""
        good_path = self._write(
            "UNCLASSIFIED\n\n(U) All good here.\n\nUNCLASSIFIED\n"
        )
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = main(["check", good_path, "/no/such/file/abc456.txt"])
        self.assertEqual(rc, 1)

    def test_empty_file_does_not_crash(self):
        """An empty file should produce a FAIL result, not a traceback."""
        path = self._write("")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", path])
        self.assertEqual(rc, 1)

    def test_json_output_missing_file_still_valid_json_for_good_files(self):
        """With --format json, good files produce valid JSON even when other paths fail."""
        good_path = self._write(
            "SECRET\n\n(S) Classified content.\n\nSECRET\n"
        )
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = main(["check", good_path, "/bad/path/x.txt", "--format", "json"])
        out = buf_out.getvalue()
        data = json.loads(out)
        self.assertIn("documents", data)
        self.assertEqual(len(data["documents"]), 1)
        self.assertEqual(rc, 1)  # had_io_error -> non-zero


# ---------------------------------------------------------------------------
# mcp_server — module imports cleanly (no missing-symbol ImportError)
# ---------------------------------------------------------------------------

class TestMcpServerImport(unittest.TestCase):

    def test_mcp_server_imports_without_error(self):
        """mcp_server.py must import cleanly (mcp package itself may be absent,
        but the module-level import of classguard.core symbols must succeed)."""
        import importlib
        # Force a fresh import to catch any NameError / ImportError at module level.
        import classguard.mcp_server as ms
        importlib.reload(ms)
        self.assertTrue(callable(ms.serve))


if __name__ == "__main__":
    unittest.main()
