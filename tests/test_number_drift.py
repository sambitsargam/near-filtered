"""Tests for the number-drift check.

The check is what makes "every number is generated from the data" a testable
claim rather than a promise, so the check itself is tested — including the
cases where it must stay quiet (method constants in code spans) and the cases
where it must fire (a hand-typed finding).
"""

import pytest

from near_filtered import drift


@pytest.fixture
def allowed():
    return drift.build_allowlist()


# --- what the extractor ignores ------------------------------------------


def test_fenced_code_is_ignored(allowed):
    text = "Some prose.\n```sql\nSELECT 123456789 FROM t\n```\n"
    assert drift.check_file_text(text, allowed, "x.md") == []


def test_inline_code_is_ignored(allowed):
    assert drift.check_file_text("A divisor of `1e24` yocto.", allowed, "x.md") == []


def test_urls_and_link_targets_are_ignored(allowed):
    text = "See [the spec](https://example.org/v0/openapi.yaml#L4821) for details."
    assert drift.check_file_text(text, allowed, "x.md") == []


def test_html_comments_are_ignored(allowed):
    assert drift.check_file_text("<!-- GENERATED:99999 -->", allowed, "x.md") == []


def test_line_numbers_survive_stripping():
    text = "line one\n```\n9999999\n```\nprose 8675309 here\n"
    findings = drift.check_file_text(text, set(), "x.md")
    assert len(findings) == 1
    assert findings[0].line_no == 5, "stripping must not shift reported line numbers"


# --- what the allowlist permits ------------------------------------------


def test_years_are_allowed(allowed):
    assert drift.check_file_text("Data from 2025 to 2026.", allowed, "x.md") == []


def test_pre_registered_thresholds_are_allowed(allowed):
    text = "Defaults are d=4, c=2, b=0.1 over a 30-day window, at 95% confidence."
    assert drift.check_file_text(text, allowed, "x.md") == []


def test_grid_values_and_cell_count_are_allowed(allowed):
    assert drift.check_file_text("27 cells across 8 and 3 and 1.", allowed, "x.md") == []


def test_materiality_bar_is_allowed(allowed):
    assert drift.check_file_text("at least 10% of gross issuance", allowed, "x.md") == []


def test_allowlist_is_built_from_the_pre_registration_not_hardcoded():
    from near_filtered import prereg

    allowed = drift.build_allowlist()
    d, c, b = prereg.defaults()
    for value in (d, c, b):
        assert str(value) in allowed or f"{float(value):.1f}" in allowed


# --- what it catches ------------------------------------------------------


def test_an_untraceable_finding_is_caught(allowed):
    text = "Economic accounts grew 37.2% over the window."
    findings = drift.check_file_text(text, allowed, "THESIS.md")
    assert [f.number for f in findings] == ["37.2%"]


def test_a_thousands_separated_number_is_caught(allowed):
    findings = drift.check_file_text("We counted 1,284,502 accounts.", allowed, "x.md")
    assert len(findings) == 1


def test_several_findings_on_one_line_are_all_reported(allowed):
    findings = drift.check_file_text("Up 41.5% to 902,113 accounts.", allowed, "x.md")
    assert len(findings) == 2


def test_finding_describe_mentions_the_file_and_line(allowed):
    findings = drift.check_file_text("Grew 37.2%.", allowed, "THESIS.md")
    described = findings[0].describe()
    assert "THESIS.md:1" in described
    assert "metrics.json" in described


# --- metrics.json traceability -------------------------------------------


def test_a_number_present_in_metrics_passes(allowed, tmp_path):
    metrics = {"h1": {"total_change_pct": 37.2}}
    allowed_with_metrics = allowed | drift.collect_metric_numbers(metrics)
    text = "Economic accounts grew 37.2% over the window."
    assert drift.check_file_text(text, allowed_with_metrics, "THESIS.md") == []


def test_a_fraction_in_metrics_may_be_published_as_a_percentage(allowed):
    metrics = {"h4": {"settlement_share": 0.413}}
    allowed_with = allowed | drift.collect_metric_numbers(metrics)
    assert drift.check_file_text("share reached 41.3%", allowed_with, "x.md") == []


def test_a_rounded_rendering_of_a_metric_passes(allowed):
    metrics = {"n": 1284502.4}
    allowed_with = allowed | drift.collect_metric_numbers(metrics)
    assert drift.check_file_text("about 1,284,502 accounts", allowed_with, "x.md") == []


def test_nearby_but_wrong_numbers_still_fail(allowed):
    metrics = {"h1": {"total_change_pct": 37.2}}
    allowed_with = allowed | drift.collect_metric_numbers(metrics)
    findings = drift.check_file_text("grew 37.9%", allowed_with, "THESIS.md")
    assert len(findings) == 1, "a near-miss must not be accepted"


def test_collect_metric_numbers_walks_nested_structures():
    metrics = {"a": [{"b": 123.0}], "c": {"d": {"e": [456]}}}
    numbers = drift.collect_metric_numbers(metrics)
    assert "123" in numbers
    assert "456" in numbers


def test_booleans_and_nulls_are_not_treated_as_numbers():
    numbers = drift.collect_metric_numbers({"ok": True, "missing": None})
    assert "1" not in numbers and "0" not in numbers


# --- the repository as it stands -----------------------------------------


def test_the_committed_documents_pass_the_check():
    """The real check, against the real files. This is what `make verify` runs."""
    findings = drift.run()
    assert findings == [], "\n".join(f.describe() for f in findings)


def test_a_generated_thesis_cannot_exist_without_generated_metrics():
    from near_filtered import config

    if (config.ROOT / "THESIS.md").exists():
        assert config.METRICS_PATH.exists(), (
            "THESIS.md is present but results/metrics.json is not. A generated "
            "thesis with no generated metrics means the numbers came from "
            "somewhere else."
        )


def test_a_date_comma_is_not_read_as_a_thousands_separator(allowed):
    """Regression: 'Nov 14, 2026' must not parse as the number '14,'."""
    findings = drift.check_file_text("Submission target Nov 14, 2026.", allowed, "x.md")
    assert findings == []


def test_a_real_thousands_separated_number_still_parses_whole(allowed):
    findings = drift.check_file_text("We counted 1,284,502 accounts.", allowed, "x.md")
    assert [f.number for f in findings] == ["1,284,502"]


def test_identifiers_are_not_read_as_numbers(allowed):
    """Regression: 'HSP-029' must not parse as the number '-029'."""
    findings = drift.check_file_text("HSP-029 and NEP-491 and H1 and CIP-30.", allowed, "x.md")
    assert findings == [], [f.number for f in findings]


def test_a_real_negative_number_is_still_caught(allowed):
    findings = drift.check_file_text("the slope was -0.2546 per month", allowed, "x.md")
    assert [f.number for f in findings] == ["-0.2546"]


def test_the_thesis_template_does_no_arithmetic():
    """A template that computes produces numbers the data never generated.

    Regression: the cost line once did `bytes_billed / 1073741824`, which the
    drift check correctly rejected. Conversions belong in metrics.py.
    """
    import re

    from near_filtered import config

    template = config.TEMPLATES_DIR / "THESIS.md.j2"
    if not template.exists():
        return
    body = template.read_text()
    # Arithmetic operators inside a {{ ... }} expression, ignoring filters.
    for match in re.finditer(r"\{\{(.+?)\}\}", body, re.DOTALL):
        expression = match.group(1)
        assert not re.search(r"[*/+]|(?<!\w)-(?!\w)", expression.split("|")[0]), (
            f"template expression does arithmetic: {expression.strip()!r}"
        )


def test_html_script_and_style_blocks_are_code_not_prose(allowed):
    html = (
        "<style>.x { width: 960px; }</style>"
        "<script>const h = 320; fetch('data/metrics.json')</script>"
        "<p>prose here</p>"
    )
    assert drift.check_file_text(html, allowed, "index.html") == []


def test_html_prose_is_still_checked(allowed):
    html = "<p>Economic accounts grew 37.2% over the window.</p>"
    findings = drift.check_file_text(html, allowed, "index.html")
    assert [f.number for f in findings] == ["37.2%"]
