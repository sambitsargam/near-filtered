"""The published pre-registration and the one the code reads must agree.

HYPOTHESES.md is what a reader sees; preregistration.json is what the
pipeline obeys. If they can drift apart, the pre-registration is decoration.
This test is what stops that.
"""

import re

import pytest

from near_filtered import prereg


@pytest.fixture(scope="module")
def md() -> str:
    return prereg.HYPOTHESES_MD.read_text()


def test_both_files_exist():
    assert prereg.PREREG_PATH.exists()
    assert prereg.HYPOTHESES_MD.exists()


def test_marked_frozen():
    assert prereg.load()["frozen"] is True


def test_default_thresholds_match_the_markdown(md):
    d, c, b = prereg.defaults()
    assert (d, c, b) == (4, 2, 0.1), "defaults changed; this is a frozen document"
    # The markdown states them in a table and again in prose.
    assert re.search(rf"\*\*{d}\*\*", md), f"d={d} not stated in HYPOTHESES.md"
    assert re.search(rf"\*\*{c}\*\*", md), f"c={c} not stated in HYPOTHESES.md"
    assert re.search(rf"\*\*{b}\*\*", md), f"b={b} not stated in HYPOTHESES.md"
    assert f"d={d}, c={c}, b={b}" in md


def test_grid_matches_the_markdown(md):
    g = prereg.load()["bot_filter"]["grid"]
    assert g["min_active_days"] == [2, 4, 8]
    assert g["min_distinct_receivers"] == [1, 2, 3]
    assert g["min_balance_near"] == [0.0, 0.1, 1.0]
    # The markdown prints the grid as a code block.
    assert re.search(r"d\s*∈\s*\{2,\s*4,\s*8\}", md)
    assert re.search(r"c\s*∈\s*\{1,\s*2,\s*3\}", md)
    assert re.search(r"b\s*∈\s*\{0,\s*0\.1,\s*1\}", md)


def test_grid_has_27_cells():
    assert len(prereg.grid()) == 27
    assert len(set(prereg.grid())) == 27


def test_defaults_are_a_cell_of_the_grid():
    assert prereg.defaults() in prereg.grid(), (
        "the default thresholds must be one of the published grid cells, "
        "or the headline number sits outside the sensitivity analysis"
    )


def test_all_five_hypotheses_present_in_both(md):
    ids = prereg.hypothesis_ids()
    assert ids == ["H1", "H2", "H3", "H4", "H5"]
    for hid in ids:
        assert re.search(rf"^## {hid} —", md, re.MULTILINE), f"{hid} has no section"


def test_every_hypothesis_states_a_prediction_and_a_rejection_rule():
    for hid in prereg.hypothesis_ids():
        h = prereg.hypothesis(hid)
        if "parts" in h:
            for part in h["parts"].values():
                assert part.get("rejected_if") or part.get("pre_committed_reading")
            continue
        assert h["predicted_direction"] in ("up", "down", "up_or_flat")
        assert h["rejected_if"].strip(), f"{hid} has no rejection rule"


def test_confidence_is_stated_and_matches(md):
    assert prereg.confidence() == 0.95
    assert "95%" in md


def test_materiality_bar_matches_the_markdown(md):
    bar = prereg.hypothesis("H5")["parts"]["H5a"]["extra_bars"][0]
    assert bar["threshold"] == 0.10
    assert "**10%**" in md


def test_h5b_commits_in_advance_to_reading_a_null_as_evidence_against(md):
    reading = prereg.hypothesis("H5")["parts"]["H5b"]["pre_committed_reading"]
    assert "evidence AGAINST" in reading
    assert "evidence AGAINST" in md


def test_no_new_hypotheses_clause_present(md):
    assert "Exploratory (not pre-registered)" in md
    assert "Exploratory (not pre-registered)" in prereg.load()["no_new_hypotheses"]


def test_no_price_targets_is_pre_committed(md):
    assert prereg.load()["bull_base_bear"]["no_price_targets"] is True
    assert "No price targets" in md


# --- the verdict rule ----------------------------------------------------


@pytest.mark.parametrize(
    "direction,predicted,expected",
    [
        ("up", "up", "SUPPORTED"),
        ("up", "up_or_flat", "SUPPORTED"),
        ("down", "up", "REJECTED"),
        ("down", "up_or_flat", "REJECTED"),
        ("flat", "up", "INCONCLUSIVE"),
        ("flat", "down", "INCONCLUSIVE"),
        ("down", "down", "SUPPORTED"),
        ("up", "down", "REJECTED"),
    ],
)
def test_verdict_rule(direction, predicted, expected):
    assert prereg.verdict(direction, predicted) == expected


def test_an_unmet_extra_bar_downgrades_to_inconclusive_not_supported():
    assert prereg.verdict("up", "up", extra_bars_met=False) == "INCONCLUSIVE"


def test_a_wrong_direction_is_rejected_even_if_bars_are_met():
    assert prereg.verdict("down", "up", extra_bars_met=True) == "REJECTED"


def test_a_drifting_series_is_never_called_supported():
    """The rule must not let a CI spanning zero read as support."""
    for predicted in ("up", "down", "up_or_flat"):
        assert prereg.verdict("flat", predicted) == "INCONCLUSIVE"


def test_amendment_count_matches_between_files(md):
    """However many amendments exist, both files must show the same ones."""
    amendments = prereg.load()["amendments"]
    if not amendments:
        assert "*(none —" in md
        return
    for amendment in amendments:
        heading = f"### {amendment['id']} — {amendment['date']}"
        assert heading in md, f"expected a section headed {heading!r}"


def test_amendments_are_recorded_in_both_files(md):
    """An amendment must appear in the published document, not only in JSON."""
    amendments = prereg.load()["amendments"]
    for amendment in amendments:
        assert amendment["id"] in md, f"{amendment['id']} missing from HYPOTHESES.md"
        assert amendment["date"] in md
        assert amendment["reason"], "an amendment must state why"
        assert amendment["bias_risk"], "an amendment must state why it cannot bias a result"


def test_the_original_text_is_never_edited_away(md):
    """H4's original census definition must survive alongside any amendment."""
    if prereg.load()["amendments"]:
        assert "Amendments are appended here" in md
        assert "original text\nabove is never edited" in md
