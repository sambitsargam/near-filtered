"""Tests for the freshness check, on a fixture that mimics a stale dataset.

This is the check that decides what window the whole thesis is computed
over, so it is tested offline rather than only exercised against the live
dataset once.
"""

import datetime as dt

import pandas as pd
import pytest

from near_filtered import inventory


def partitions_fixture(latest: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "table_name": name,
                "partition_count": 500,
                "earliest_partition": "20200722",
                "latest_partition": value,
                "total_rows": 1_000_000,
                "total_logical_bytes": 10**11,
            }
            for name, value in latest.items()
        ]
    )


def test_freshness_flags_a_stale_table():
    df = partitions_fixture({"transactions": "20260324", "blocks": "20260324"})
    report = inventory.summarise_freshness(df, as_of=dt.date(2026, 11, 10))
    assert set(report["stale"]) == {True}
    assert report["lag_days"].max() == 231
    assert "WARNING" in inventory.format_freshness(report)


def test_freshness_passes_a_current_table():
    df = partitions_fixture({"transactions": "20261108", "blocks": "20261109"})
    report = inventory.summarise_freshness(df, as_of=dt.date(2026, 11, 10))
    assert set(report["stale"]) == {False}
    assert "WARNING" not in inventory.format_freshness(report)


def test_report_marks_the_tables_we_query():
    df = partitions_fixture({"transactions": "20261108", "near_social_transactions": "20261108"})
    report = inventory.summarise_freshness(df, as_of=dt.date(2026, 11, 10))
    used = dict(zip(report["table_name"], report["used_by_us"]))
    assert used["transactions"] is True
    assert used["near_social_transactions"] is False


def test_window_anchors_on_the_earliest_ending_table_we_use():
    # transactions runs to March but balances stop in February. Anchoring on
    # transactions would put a month in one series and not the other.
    df = partitions_fixture(
        {
            "transactions": "20260331",
            "ft_events": "20260331",
            "ft_balances_daily": "20260228",
            "execution_outcomes": "20260331",
            "blocks": "20260331",
            "circulating_supply": "20260331",
        }
    )
    win = inventory.derive_window_from(df, as_of=dt.date(2026, 11, 10))
    assert win.data_latest == dt.date(2026, 2, 28)
    assert win.end == dt.date(2026, 2, 28)
    assert win.is_stale is True


def test_window_ignores_tables_we_do_not_query():
    df = partitions_fixture(
        {
            "transactions": "20260331",
            "ft_events": "20260331",
            "ft_balances_daily": "20260331",
            "execution_outcomes": "20260331",
            "blocks": "20260331",
            "circulating_supply": "20260331",
            "near_social_transactions": "20240101",  # long dead, and unused
        }
    )
    win = inventory.derive_window_from(df, as_of=dt.date(2026, 11, 10))
    assert win.data_latest == dt.date(2026, 3, 31)


def test_missing_expected_tables_is_an_error_not_a_silent_default():
    df = partitions_fixture({"something_else": "20260331"})
    with pytest.raises(RuntimeError, match="INFORMATION_SCHEMA.PARTITIONS"):
        inventory.derive_window_from(df, as_of=dt.date(2026, 11, 10))
