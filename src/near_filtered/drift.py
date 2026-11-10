"""The number-drift check: no number in prose that the data did not produce.

The rule this enforces: every figure that appears in THESIS.md, README.md or
the dashboard must be traceable to results/metrics.json. If a number cannot
be found there, either the pipeline did not produce it or somebody typed it,
and both are failures.

What is deliberately NOT checked, and why:

- Fenced and inline code. SQL, file paths and identifiers are shown so a
  reader can audit a query, not asserted as findings. `1e24` in a yoctoNEAR
  conversion is part of the method, not a claim about NEAR.
- URLs and link targets, which carry version numbers and ids.
- An explicit allowlist: calendar years, the pre-registered thresholds, the
  confidence level, hypothesis ids and section numbers. The allowlist is
  built from the pre-registration rather than hand-maintained, so widening a
  threshold cannot quietly widen what prose may assert.

A number is matched against metrics.json in several renderings, because
"0.42", "42%" and "0.4" can all be honest presentations of the same value.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import config, prereg

# Spans removed before any number is extracted.
_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_INDENTED_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_MD_LINK_TARGET = re.compile(r"\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_HTML_ATTR = re.compile(r'\w+="[^"]*"')

# A number as a reader would see it: optional sign, digits with properly
# grouped thousands separators, optional decimal part, optional trailing %.
# The comma groups must be exactly three digits, so "Nov 14, 2026" yields
# "14" and "2026" rather than a spurious "14,".
# The lookbehind keeps identifiers out: the "029" in "HSP-029" and the "1"
# in "H1" are names, not quantities, and flagging them would train a reader
# to ignore this check.
_NUMBER = re.compile(r"(?<![A-Za-z0-9_-])-?\d+(?:,\d{3})*(?:\.\d+)?%?")

# Bare small integers and calendar years are structural: section numbers,
# list markers, "five hypotheses", "the 30-day window", a year in a date.
# They are allowed without appearing in metrics.json.
#
# A number carrying a percent sign, a thousands separator or a decimal point
# is NEVER structural. Those are how findings are written, so they must trace
# to metrics.json or to a pre-registered threshold, whatever their magnitude.
# Without this split, "grew 12%" would pass as if it were a section number.
STRUCTURAL: set[str] = {str(n) for n in range(32)} | {str(y) for y in range(2017, 2036)}


def _is_decorated(token: str) -> bool:
    return "%" in token or "," in token or "." in token


@dataclass
class Finding:
    file: str
    line_no: int
    number: str
    line: str

    def describe(self) -> str:
        return (
            f"{self.file}:{self.line_no}  {self.number!r} is not in metrics.json\n"
            f"    {self.line.strip()[:140]}"
        )


def strip_non_prose(text: str) -> str:
    """Blank out code, comments, links and URLs, preserving line numbers."""

    def blank(match: re.Match) -> str:
        # Keep newlines so reported line numbers still point at the source.
        return re.sub(r"[^\n]", " ", match.group(0))

    for pattern in (
        _FENCED_CODE,
        _INDENTED_HTML_COMMENT,
        _INLINE_CODE,
        _MD_LINK_TARGET,
        _URL,
        _HTML_ATTR,
    ):
        text = pattern.sub(blank, text)
    return text


def _normalise(token: str) -> str:
    return token.replace(",", "").rstrip("%").lstrip("-")


def collect_metric_numbers(obj) -> set[str]:
    """Every number in metrics.json, in the renderings prose may use."""
    out: set[str] = set()

    def visit(node) -> None:
        if isinstance(node, dict):
            for value in node.values():
                visit(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                visit(value)
        elif isinstance(node, bool) or node is None:
            return
        elif isinstance(node, (int, float)):
            out.update(_renderings(float(node)))
        elif isinstance(node, str):
            for match in _NUMBER.finditer(node):
                out.add(_normalise(match.group(0)))

    visit(obj)
    return out


def _renderings(value: float) -> set[str]:
    """How one metric value might legitimately be written in prose."""
    forms: set[str] = set()
    magnitude = abs(value)

    candidates = [value, magnitude]
    # A fraction is often published as a percentage, and vice versa.
    candidates += [magnitude * 100, magnitude / 100]

    for candidate in candidates:
        if candidate == int(candidate):
            forms.add(str(int(candidate)))
        for places in (0, 1, 2, 3, 4):
            forms.add(f"{candidate:.{places}f}")
            # A rounded form may drop a trailing zero in prose.
            forms.add(f"{candidate:.{places}f}".rstrip("0").rstrip("."))
        forms.add(f"{round(candidate):,}".replace(",", ""))
    return {_normalise(f) for f in forms if f not in ("", "-")}


def build_allowlist() -> set[str]:
    """Numbers prose may use that are not findings.

    Built from the pre-registration, not hand-written, so the set of
    assertable numbers cannot drift from the frozen document.
    """
    allowed: set[str] = set()

    # Calendar years and bare small integers are handled by STRUCTURAL, which
    # deliberately does not cover percentages or separated numbers.

    # Pre-registered thresholds, the grid, the confidence level, materiality.
    pre = prereg.load()
    bot = pre["bot_filter"]
    for value in bot["defaults"].values():
        allowed |= _renderings(float(value))
    for values in bot["grid"].values():
        for value in values:
            allowed |= _renderings(float(value))
    allowed |= _renderings(float(bot["window_days"]))
    allowed |= _renderings(prereg.confidence())
    allowed |= {"95", "0.95", "5"}
    allowed |= _renderings(float(pre["window"]["months"]))
    allowed |= _renderings(float(pre["window"]["freshness_tolerance_days"]))

    bar = pre["hypotheses"][-1]["parts"]["H5a"]["extra_bars"][0]["threshold"]
    allowed |= _renderings(float(bar))

    # The grid's cell count, and the count of hypotheses.
    allowed |= _renderings(float(len(prereg.grid())))
    allowed |= _renderings(float(len(pre["hypotheses"])))

    # Cohort offsets.
    for offset in prereg.hypothesis("H3")["offsets_months"]:
        allowed |= _renderings(float(offset))

    return allowed


def check_file_text(text: str, allowed: set[str], name: str) -> list[Finding]:
    """Check one document's text. Separated from the file read so the rules
    can be tested directly on strings."""
    stripped = strip_non_prose(text)
    findings: list[Finding] = []
    for line_no, line in enumerate(stripped.splitlines(), start=1):
        for match in _NUMBER.finditer(line):
            raw = match.group(0)
            token = _normalise(raw)
            if not token:
                continue
            if token in allowed:
                continue
            if not _is_decorated(raw) and token in STRUCTURAL:
                continue
            findings.append(Finding(name, line_no, raw, line))
    return findings


def check_file(path: Path, allowed: set[str]) -> list[Finding]:
    try:
        rel = str(path.relative_to(config.ROOT))
    except ValueError:
        rel = str(path)
    return check_file_text(path.read_text(), allowed, rel)


def documents_to_check() -> list[Path]:
    paths: list[Path] = []
    for name in ("THESIS.md", "README.md", "LIMITATIONS.md", "METHODOLOGY.md"):
        candidate = config.ROOT / name
        if candidate.exists():
            paths.append(candidate)
    if config.SITE_DIR.exists():
        paths.extend(sorted(config.SITE_DIR.glob("*.html")))
    return paths


def run() -> list[Finding]:
    """Check every published document. Returns the findings, empty if clean."""
    metrics_path = config.METRICS_PATH
    allowed = build_allowlist()

    if metrics_path.exists():
        allowed |= collect_metric_numbers(json.loads(metrics_path.read_text()))

    findings: list[Finding] = []
    for path in documents_to_check():
        findings.extend(check_file(path, allowed))
    return findings


def main() -> int:
    findings = run()
    if not findings:
        checked = (
            ", ".join(str(p.relative_to(config.ROOT)) for p in documents_to_check())
            or "(no documents yet)"
        )
        print(f"number-drift check: clean  [{checked}]")
        return 0

    print(f"number-drift check: {len(findings)} number(s) not traceable to metrics.json\n")
    for finding in findings:
        print("  " + finding.describe())
    print(
        "\nEvery figure in a published document must come from results/metrics.json.\n"
        "Either generate it from the data, or move it into a code span if it is\n"
        "part of the method rather than a finding."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
