"""Command-line interface for CLASSGUARD.

Usage:
    classguard check FILE [FILE ...] [--format table|json] [--strict]
    classguard --version

Exit codes:
    0  all documents compliant (no errors)
    1  one or more documents have marking errors (or warnings under --strict)
    2  usage / IO error
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import analyze_document, Report


def _print_table(report: Report) -> None:
    sev_mark = {"error": "ERROR", "warn": "WARN ", "info": "INFO "}
    status = "PASS" if report.ok else "FAIL"
    print("=" * 64)
    print("[%s] %s" % (status, report.source))
    print("  banner(top):    %s" % (report.banner_top or "<none>"))
    print("  banner(bottom): %s" % (report.banner_bottom or "<none>"))
    print("  banner level:   %s" % (report.banner_level or "<none>"))
    print("  highest portion:%s" % (report.highest_portion or "<none>"))
    print("  portions:       %d   unmarked paras: %d"
          % (report.portion_count, report.unmarked_paragraphs))
    print("  errors: %d   warnings: %d" % (report.error_count, report.warn_count))
    for f in report.findings:
        loc = ("L%d" % f.line) if f.line else "--"
        print("    %s %-6s %-22s %s"
              % (sev_mark.get(f.severity, f.severity), loc, f.code, f.message))


def _cmd_check(args: argparse.Namespace) -> int:
    reports: List[Report] = []
    had_io_error = False
    for path in args.files:
        try:
            reports.append(analyze_document(path))
        except OSError as exc:
            had_io_error = True
            print("%s: cannot read %s: %s" % (TOOL_NAME, path, exc),
                  file=sys.stderr)

    if args.format == "json":
        payload = {
            "tool": TOOL_NAME,
            "version": TOOL_VERSION,
            "documents": [r.to_dict() for r in reports],
        }
        print(json.dumps(payload, indent=2))
    else:
        for r in reports:
            _print_table(r)

    if had_io_error and not reports:
        return 2

    def failed(r: Report) -> bool:
        if not r.ok:
            return True
        if args.strict and r.warn_count > 0:
            return True
        return False

    return 1 if (had_io_error or any(failed(r) for r in reports)) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Validate classification banner & portion markings "
                    "in documents (ISOO-style compliance).",
    )
    parser.add_argument(
        "--version", action="version",
        version="%s %s" % (TOOL_NAME, TOOL_VERSION),
    )
    sub = parser.add_subparsers(dest="command")

    chk = sub.add_parser("check", help="Check one or more documents for marking compliance.")
    chk.add_argument("files", nargs="+", help="Document(s) to validate.")
    chk.add_argument("--format", choices=["table", "json"], default="table",
                     help="Output format (default: table).")
    chk.add_argument("--strict", action="store_true",
                     help="Treat warnings as failures.")
    chk.set_defaults(func=_cmd_check)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
