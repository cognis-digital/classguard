"""Core engine for CLASSGUARD.

Implements marking-compliance checks for cleared-work documents:

  * Banner detection (first and last non-empty lines should carry a banner).
  * Portion-marking detection: paragraphs/lines prefixed with (U), (CUI), (C),
    (S) style markers.
  * The 'highest portion must equal the banner' rule (ISOO-style).
  * Banner top == banner bottom consistency.
  * CUI structure sanity (CUI banner should carry a category/dissem block).
  * Unmarked-portion detection in a classified document.

Standard library only. No network. Pure text analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

# Ordered low -> high. Index is the sensitivity rank.
LEVEL_ORDER = ["U", "CUI", "C", "S"]

_LEVEL_CANON = {
    "U": "U",
    "UNCLASSIFIED": "U",
    "CUI": "CUI",
    "CONTROLLED": "CUI",
    "C": "C",
    "CONFIDENTIAL": "C",
    "S": "S",
    "SECRET": "S",
}

_LEVEL_FULL = {
    "U": "UNCLASSIFIED",
    "CUI": "CONTROLLED UNCLASSIFIED INFORMATION",
    "C": "CONFIDENTIAL",
    "S": "SECRET",
}

# A banner line is a line composed (mostly) of marking tokens, e.g.:
#   SECRET
#   CUI//SP-PROPIN
#   CONFIDENTIAL//NOFORN
_BANNER_RE = re.compile(
    r"^\s*(UNCLASSIFIED|CONFIDENTIAL|SECRET|CUI|CONTROLLED)\b(//[^\s]*)?\s*$",
    re.IGNORECASE,
)

# Portion marker at the start of a line: (U) text, (CUI) text, (S//NF) text
_PORTION_RE = re.compile(
    r"^\s*\(\s*(U|CUI|C|S|UNCLASSIFIED|CONFIDENTIAL|SECRET|CONTROLLED)"
    r"(?://[^\)]*)?\s*\)\s*",
    re.IGNORECASE,
)

# A line that looks like prose (has letters) but is not a banner.
_HAS_WORDS_RE = re.compile(r"[A-Za-z]{3,}")


def classify_level(token: str) -> Optional[str]:
    """Canonicalize a marking token to one of LEVEL_ORDER, or None."""
    if not token:
        return None
    key = token.strip().upper()
    # Strip control-marking suffix like //NOFORN or //SP-PROPIN
    key = key.split("//", 1)[0].strip()
    return _LEVEL_CANON.get(key)


def _rank(level: Optional[str]) -> int:
    if level is None:
        return -1
    try:
        return LEVEL_ORDER.index(level)
    except ValueError:
        return -1


@dataclass
class Finding:
    code: str
    severity: str  # "error" | "warn" | "info"
    message: str
    line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Report:
    source: str
    banner_top: Optional[str] = None
    banner_bottom: Optional[str] = None
    banner_level: Optional[str] = None
    highest_portion: Optional[str] = None
    portion_count: int = 0
    unmarked_paragraphs: int = 0
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warn")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "ok": self.ok,
            "banner_top": self.banner_top,
            "banner_bottom": self.banner_bottom,
            "banner_level": self.banner_level,
            "banner_level_full": _LEVEL_FULL.get(self.banner_level or ""),
            "highest_portion": self.highest_portion,
            "highest_portion_full": _LEVEL_FULL.get(self.highest_portion or ""),
            "portion_count": self.portion_count,
            "unmarked_paragraphs": self.unmarked_paragraphs,
            "error_count": self.error_count,
            "warn_count": self.warn_count,
            "findings": [f.to_dict() for f in self.findings],
        }


def _find_banner(lines: List[str], forward: bool):
    """Return (line_index, raw_text, level) of first banner from one end."""
    idxs = range(len(lines)) if forward else range(len(lines) - 1, -1, -1)
    for i in idxs:
        raw = lines[i].strip()
        if not raw:
            continue
        m = _BANNER_RE.match(raw)
        if m:
            return i, raw, classify_level(m.group(1))
        # First non-empty line is not a banner -> stop scanning that end.
        return None
    return None


def analyze_text(text: str, source: str = "<text>") -> Report:
    """Analyze raw document text and return a Report.

    Raises:
        TypeError: if *text* is not a string.
        ValueError: if *source* is not a non-empty string.
    """
    if not isinstance(text, str):
        raise TypeError(
            "analyze_text() expects a str, got %s" % type(text).__name__
        )
    if not isinstance(source, str) or not source:
        raise ValueError("source must be a non-empty string")
    lines = text.splitlines()
    report = Report(source=source)

    top = _find_banner(lines, forward=True)
    bottom = _find_banner(lines, forward=False)

    if top is None:
        report.findings.append(
            Finding("BANNER_TOP_MISSING", "error",
                    "No classification banner on the first content line.",
                    line=1)
        )
    else:
        report.banner_top = top[1]
        report.banner_level = top[2]

    if bottom is None:
        report.findings.append(
            Finding("BANNER_BOTTOM_MISSING", "error",
                    "No classification banner on the last content line.",
                    line=len(lines) or None)
        )
    else:
        report.banner_bottom = bottom[1]
        if report.banner_level is None:
            report.banner_level = bottom[2]

    if top is not None and bottom is not None:
        if top[1].upper() != bottom[1].upper():
            report.findings.append(
                Finding("BANNER_MISMATCH", "error",
                        "Top banner %r and bottom banner %r differ."
                        % (top[1], bottom[1]), line=bottom[0] + 1)
            )

    # Scan portion markings between the banners.
    body_start = (top[0] + 1) if top is not None else 0
    body_end = bottom[0] if bottom is not None else len(lines)

    highest_rank = -1
    highest_level: Optional[str] = None
    portion_count = 0
    unmarked = 0

    for i in range(body_start, body_end):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            continue
        # Skip lines that are themselves banners inside the body.
        if _BANNER_RE.match(stripped):
            continue
        m = _PORTION_RE.match(raw)
        if m:
            portion_count += 1
            lvl = classify_level(m.group(1))
            r = _rank(lvl)
            if r > highest_rank:
                highest_rank = r
                highest_level = lvl
        elif _HAS_WORDS_RE.search(stripped):
            # Prose paragraph with no portion marker.
            unmarked += 1
            if unmarked <= 25:
                report.findings.append(
                    Finding("PORTION_UNMARKED", "warn",
                            "Content paragraph lacks a portion marking.",
                            line=i + 1)
                )

    report.portion_count = portion_count
    report.unmarked_paragraphs = unmarked
    report.highest_portion = highest_level

    # Rule: highest portion marking must not exceed the banner.
    if report.banner_level is not None and highest_level is not None:
        if highest_rank > _rank(report.banner_level):
            report.findings.append(
                Finding("PORTION_EXCEEDS_BANNER", "error",
                        "Highest portion (%s) is more sensitive than banner (%s)."
                        % (highest_level, report.banner_level))
            )
        elif highest_rank < _rank(report.banner_level):
            # Banner over-marks relative to content: ISOO discourages this.
            report.findings.append(
                Finding("BANNER_OVERMARKED", "warn",
                        "Banner (%s) is higher than the highest portion (%s); "
                        "banner should equal the highest portion."
                        % (report.banner_level, highest_level))
            )

    if portion_count == 0 and (body_end - body_start) > 0:
        # Classified doc with body but no portion markings at all.
        if report.banner_level not in (None, "U"):
            report.findings.append(
                Finding("PORTIONS_ABSENT", "error",
                        "Classified document has no portion markings.")
            )

    # CUI structural sanity: CUI banner should carry a control suffix //...
    if report.banner_level == "CUI" and report.banner_top:
        if "//" not in report.banner_top:
            report.findings.append(
                Finding("CUI_NO_CATEGORY", "warn",
                        "CUI banner lacks a control marking block (e.g. CUI//SP-PROPIN).")
            )

    if report.ok and not report.findings:
        report.findings.append(
            Finding("COMPLIANT", "info", "Markings are consistent and compliant.")
        )

    return report


def analyze_document(path: str) -> Report:
    """Read a file from disk and analyze it.

    Raises:
        TypeError: if *path* is not a string.
        OSError: if the file cannot be opened (not found, permission denied, etc.).
    """
    if not isinstance(path, str):
        raise TypeError("analyze_document() expects a str path, got %s" % type(path).__name__)
    if not path:
        raise ValueError("path must be a non-empty string")
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return analyze_text(text, source=path)
