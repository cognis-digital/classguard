"""Smoke tests for CLASSGUARD. Standard library only, no network."""

import io
import os
import sys
import json
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classguard import (  # noqa: E402
    TOOL_NAME, TOOL_VERSION, classify_level, analyze_text, LEVEL_ORDER,
)
from classguard.cli import main  # noqa: E402


GOOD = (
    "CONFIDENTIAL\n\n"
    "(U) Intro paragraph for the record.\n\n"
    "(C) The assessment is CONFIDENTIAL.\n\n"
    "CONFIDENTIAL\n"
)

BAD_EXCEEDS = (
    "CONFIDENTIAL\n\n"
    "(S) This portion is SECRET, exceeding the banner.\n\n"
    "CONFIDENTIAL\n"
)

NO_BANNER = "(U) Just a portion-marked line with no banners at all.\n"


class TestCore(unittest.TestCase):
    def test_metadata(self):
        self.assertEqual(TOOL_NAME, "classguard")
        self.assertTrue(TOOL_VERSION)

    def test_classify_level(self):
        self.assertEqual(classify_level("SECRET"), "S")
        self.assertEqual(classify_level("cui//SP-PROPIN"), "CUI")
        self.assertEqual(classify_level("Unclassified"), "U")
        self.assertIsNone(classify_level("banana"))

    def test_level_order(self):
        self.assertEqual(LEVEL_ORDER.index("U"), 0)
        self.assertTrue(LEVEL_ORDER.index("S") > LEVEL_ORDER.index("C"))

    def test_good_document_passes(self):
        rep = analyze_text(GOOD, "good")
        self.assertTrue(rep.ok, rep.to_dict())
        self.assertEqual(rep.banner_level, "C")
        self.assertEqual(rep.highest_portion, "C")
        self.assertEqual(rep.error_count, 0)

    def test_portion_exceeds_banner_is_error(self):
        rep = analyze_text(BAD_EXCEEDS, "bad")
        self.assertFalse(rep.ok)
        codes = {f.code for f in rep.findings}
        self.assertIn("PORTION_EXCEEDS_BANNER", codes)

    def test_missing_banner_is_error(self):
        rep = analyze_text(NO_BANNER, "nb")
        self.assertFalse(rep.ok)
        codes = {f.code for f in rep.findings}
        self.assertIn("BANNER_TOP_MISSING", codes)

    def test_to_dict_serializable(self):
        rep = analyze_text(GOOD, "good")
        json.dumps(rep.to_dict())  # must not raise


class TestCli(unittest.TestCase):
    def _write(self, text):
        fd, path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_cli_pass_exit_zero(self):
        path = self._write(GOOD)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", path])
        self.assertEqual(rc, 0)

    def test_cli_fail_exit_one(self):
        path = self._write(BAD_EXCEEDS)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", path])
        self.assertEqual(rc, 1)

    def test_cli_json_format(self):
        path = self._write(GOOD)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", path, "--format", "json"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["tool"], "classguard")
        self.assertEqual(len(data["documents"]), 1)
        self.assertTrue(data["documents"][0]["ok"])

    def test_cli_strict_warns_fail(self):
        # Banner over-marked: banner C but highest portion U -> warn.
        text = "CONFIDENTIAL\n\n(U) Only unclassified content here.\n\nCONFIDENTIAL\n"
        path = self._write(text)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", path, "--strict"])
        self.assertEqual(rc, 1)

    def test_cli_io_error_exit_two(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", "/nonexistent/path/xyz.txt"])
        self.assertEqual(rc, 2)

    def test_no_command_returns_two(self):
        rc = main([])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
