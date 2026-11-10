"""Tests for window derivation.

The window is where a stale dataset turns into either an honest, disclosed
limitation or a silently wrong chart, so each branch is pinned down.
"""

import datetime as dt

import pytest

from near_filtered import window as W


def test_complete_final_month_is_kept():
    # Data runs to the last day of March, so March is complete and included.
    w = W.derive_window(dt.date(2026, 3, 31), as_of=dt.date(2026, 3, 31))
    assert w.end == dt.date(2026, 3, 31)
    assert w.start == dt.date(2025, 4, 1)
    assert len(w.month_labels) == 12
    assert w.month_labels[0] == "2025-04"
    assert w.month_labels[-1] == "2026-03"


def test_partial_final_month_is_dropped():
    # Data stops mid-March: March would look like a collapse, so it is cut.
    w = W.derive_window(dt.date(2026, 3, 12), as_of=dt.date(2026, 3, 20))
    assert w.end == dt.date(2026, 2, 28)
    assert w.start == dt.date(2025, 3, 1)
    assert "2026-03" not in w.month_labels


def test_staleness_is_flagged_and_explained():
    w = W.derive_window(dt.date(2026, 3, 24), as_of=dt.date(2026, 11, 10))
    assert w.is_stale is True
    assert w.lag_days == 231
    assert "2026-03-24" in w.note
    assert "not the present" in w.note


def test_a_current_dataset_is_not_flagged_stale():
    w = W.derive_window(dt.date(2026, 11, 8), as_of=dt.date(2026, 11, 10))
    assert w.is_stale is False
    assert w.lag_days == 2
    assert "current to" in w.note


def test_tolerance_boundary():
    assert W.derive_window(dt.date(2026, 11, 3), as_of=dt.date(2026, 11, 10)).is_stale is False
    assert W.derive_window(dt.date(2026, 11, 2), as_of=dt.date(2026, 11, 10)).is_stale is True


def test_window_crosses_a_year_boundary_correctly():
    w = W.derive_window(dt.date(2026, 1, 31), as_of=dt.date(2026, 2, 1))
    assert w.start == dt.date(2025, 2, 1)
    assert w.end == dt.date(2026, 1, 31)
    assert len(w.month_labels) == 12


def test_leap_day_end_of_february():
    w = W.derive_window(dt.date(2028, 2, 29), as_of=dt.date(2028, 3, 1))
    assert w.end == dt.date(2028, 2, 29)


def test_parse_partition_id_accepts_both_forms():
    assert W.parse_partition_id("20260324") == dt.date(2026, 3, 24)
    assert W.parse_partition_id("2026-03-24") == dt.date(2026, 3, 24)


def test_add_months_clamps_to_month_length():
    assert W.add_months(dt.date(2026, 3, 31), -1) == dt.date(2026, 2, 28)


@pytest.mark.parametrize("months", [3, 6, 12])
def test_window_length_matches_requested_months(months):
    w = W.derive_window(dt.date(2026, 3, 31), as_of=dt.date(2026, 4, 1), months=months)
    assert len(w.month_labels) == months
