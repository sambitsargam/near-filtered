"""Unit tests on tiny fixtures whose answers can be worked out by hand.

The point is not coverage for its own sake. These are the four functions
that carry the hypotheses — the bot filter, concentration, cohorts and the
settlement share — so each is checked against a case a reader can verify
with a pencil before trusting any chart built on it.
"""

import math

import pandas as pd
import pytest

from near_filtered import transforms as T

# --- concentration --------------------------------------------------------


def test_hhi_single_actor_is_one():
    assert T.hhi(pd.Series([100.0])) == pytest.approx(1.0)


def test_hhi_n_equal_actors_is_one_over_n():
    for n in (2, 4, 10):
        assert T.hhi(pd.Series([1.0] * n)) == pytest.approx(1.0 / n)


def test_hhi_is_scale_invariant():
    small = T.hhi(pd.Series([1.0, 3.0]))
    large = T.hhi(pd.Series([1000.0, 3000.0]))
    assert small == pytest.approx(large)
    # shares are 0.25 and 0.75 -> 0.0625 + 0.5625
    assert small == pytest.approx(0.625)


def test_hhi_empty_and_zero_totals_do_not_blow_up():
    assert T.hhi(pd.Series([0.0, 0.0])) == pytest.approx(0.0)


def test_top_n_share():
    values = pd.Series([50.0, 30.0, 10.0, 10.0])
    assert T.top_n_share(values, n=1) == pytest.approx(0.5)
    assert T.top_n_share(values, n=2) == pytest.approx(0.8)
    assert T.top_n_share(values, n=10) == pytest.approx(1.0)


def test_concentration_by_month_separates_months():
    df = pd.DataFrame(
        {
            "month": ["2026-01"] * 2 + ["2026-02"] * 4,
            "receiver_account_id": ["a", "b", "a", "b", "c", "d"],
            "tx_count": [1, 1, 1, 1, 1, 1],
        }
    )
    out = T.concentration_by_month(df, n=1).set_index("month")
    # January: two equal contracts -> top-1 share 0.5, HHI 0.5
    assert out.loc["2026-01", "top1_share"] == pytest.approx(0.5)
    assert out.loc["2026-01", "hhi"] == pytest.approx(0.5)
    # February: four equal contracts -> top-1 0.25, HHI 0.25 (less concentrated)
    assert out.loc["2026-02", "top1_share"] == pytest.approx(0.25)
    assert out.loc["2026-02", "hhi"] == pytest.approx(0.25)


# --- the bot filter -------------------------------------------------------


@pytest.fixture
def accounts():
    return pd.DataFrame(
        [
            # clears everything
            {"account_id": "human", "active_days": 9, "distinct_receivers": 4, "balance_near": 5.0},
            # many days, but hammers one contract: a bot shape
            {"account_id": "bot", "active_days": 30, "distinct_receivers": 1, "balance_near": 0.0},
            # broad but one-shot: an airdrop farmer shape
            {
                "account_id": "farmer",
                "active_days": 1,
                "distinct_receivers": 9,
                "balance_near": 0.0,
            },
            # right behaviour, empty wallet
            {"account_id": "broke", "active_days": 5, "distinct_receivers": 3, "balance_near": 0.0},
            # no balance column value at all
            {
                "account_id": "nobal",
                "active_days": 5,
                "distinct_receivers": 3,
                "balance_near": None,
            },
        ]
    )


def test_is_economic_at_default_thresholds(accounts):
    mask = T.is_economic(
        accounts, min_active_days=4, min_distinct_receivers=2, min_balance_near=0.1
    )
    kept = set(accounts.loc[mask, "account_id"])
    assert kept == {"human"}, "only the account clearing all three bars survives"


def test_is_economic_relaxing_balance_admits_the_broke_accounts(accounts):
    mask = T.is_economic(
        accounts, min_active_days=4, min_distinct_receivers=2, min_balance_near=0.0
    )
    assert set(accounts.loc[mask, "account_id"]) == {"human", "broke", "nobal"}


def test_is_economic_excludes_single_contract_bot_at_every_receiver_threshold(accounts):
    for c in (2, 3):
        mask = T.is_economic(accounts, 2, c, 0.0)
        assert "bot" not in set(accounts.loc[mask, "account_id"])


def test_missing_balance_counts_as_zero_not_as_pass(accounts):
    mask = T.is_economic(accounts, 1, 1, 0.1)
    assert "nobal" not in set(accounts.loc[mask, "account_id"])


def test_count_economic_accounts_is_monotonic_in_each_threshold(accounts):
    loose = T.count_economic_accounts(accounts, 1, 1, 0.0)
    tighter_days = T.count_economic_accounts(accounts, 8, 1, 0.0)
    tighter_recv = T.count_economic_accounts(accounts, 1, 3, 0.0)
    tighter_bal = T.count_economic_accounts(accounts, 1, 1, 1.0)
    assert tighter_days <= loose
    assert tighter_recv <= loose
    assert tighter_bal <= loose


# --- cohorts --------------------------------------------------------------


def test_month_index_counts_months_not_strings():
    assert T.month_index("2026-02") - T.month_index("2026-01") == 1
    assert T.month_index("2026-01") - T.month_index("2025-12") == 1
    assert T.month_index("2026-07") - T.month_index("2026-01") == 6


def test_cohort_retention_point_in_time():
    # Cohort 2026-01 has two accounts.
    #   'stayer'  is active in 01 and 02  -> retained at +1
    #   'churner' is active in 01 only    -> not retained at +1
    # Months run to 2026-02, so +3 and +6 are unobservable and must be NaN,
    # never 0 — "we cannot see it yet" is not "nobody came back".
    activity = pd.DataFrame(
        {
            "account_id": ["stayer", "churner", "stayer"],
            "month": ["2026-01", "2026-01", "2026-02"],
        }
    )
    out = T.cohort_retention(activity).set_index("cohort")
    assert out.loc["2026-01", "cohort_size"] == 2
    assert out.loc["2026-01", "retained_m1"] == pytest.approx(0.5)
    assert math.isnan(out.loc["2026-01", "retained_m3"])
    assert math.isnan(out.loc["2026-01", "retained_m6"])


def test_cohort_retention_ignores_a_gap_month():
    # Active in 01 and 03 but not 02: retained at +1 is 0, not 1. Retention
    # is point-in-time, so coming back later does not fill the earlier gap.
    activity = pd.DataFrame(
        {"account_id": ["gap", "gap", "other"], "month": ["2026-01", "2026-03", "2026-02"]}
    )
    out = T.cohort_retention(activity, offsets=(1, 2)).set_index("cohort")
    assert out.loc["2026-01", "retained_m1"] == pytest.approx(0.0)
    assert out.loc["2026-01", "retained_m2"] == pytest.approx(1.0)


def test_cohort_assigns_each_account_to_its_first_month_only():
    activity = pd.DataFrame({"account_id": ["a", "a"], "month": ["2026-01", "2026-02"]})
    out = T.cohort_retention(activity)
    assert list(out["cohort"]) == ["2026-01"]
    assert out["cohort_size"].sum() == 1


# --- settlement share -----------------------------------------------------


def test_settlement_share_basic():
    assert T.settlement_share(25.0, 75.0) == pytest.approx(0.25)
    assert T.settlement_share(1.0, 0.0) == pytest.approx(1.0)
    assert T.settlement_share(0.0, 1.0) == pytest.approx(0.0)


def test_settlement_share_with_no_activity_is_nan_not_zero():
    assert math.isnan(T.settlement_share(0.0, 0.0))
    assert math.isnan(T.settlement_share(None, None))


def test_settlement_share_by_month():
    df = pd.DataFrame(
        {
            "month": ["2026-01", "2026-02"],
            "intents_usd": [10.0, 30.0],
            "native_usd": [90.0, 70.0],
        }
    )
    out = T.settlement_share_by_month(df)
    assert list(out["settlement_share"].round(4)) == [0.1, 0.3]


# --- trends ---------------------------------------------------------------


def test_linear_trend_recovers_an_exact_line():
    y = [1 + 2 * i for i in range(12)]
    t = T.linear_trend(y)
    assert t.n == 12
    assert t.slope_per_month == pytest.approx(2.0)
    assert t.r_squared == pytest.approx(1.0)
    assert t.direction == "up"
    assert t.ci_low <= 2.0 <= t.ci_high


def test_linear_trend_on_noise_reports_flat_not_a_direction():
    y = [5, 4, 6, 5, 4, 6, 5, 4, 6, 5, 4, 6]
    t = T.linear_trend(y)
    assert t.direction == "flat", "a CI spanning zero must not be called a trend"
    assert t.ci_low < 0 < t.ci_high


def test_linear_trend_detects_a_decline():
    t = T.linear_trend([100, 90, 80, 70, 60, 50])
    assert t.direction == "down"
    assert t.slope_per_month == pytest.approx(-10.0)
    assert t.total_change_pct == pytest.approx(-50.0)


def test_linear_trend_needs_three_points():
    with pytest.raises(ValueError):
        T.linear_trend([1.0, 2.0])


def test_linear_trend_skips_missing_values():
    t = T.linear_trend([1.0, float("nan"), 3.0, 4.0])
    assert t.n == 3


def test_mom_growth():
    g = T.mom_growth([100.0, 110.0, 99.0])
    assert math.isnan(g.iloc[0])
    assert g.iloc[1] == pytest.approx(10.0)
    assert g.iloc[2] == pytest.approx(-10.0)


# --- sensitivity classification ------------------------------------------


def test_classify_robustness():
    assert T.classify_robustness(["up", "up", "up"], expected="up") == "robust"
    assert T.classify_robustness(["up", "flat", "up"], expected="up") == "depends"
    assert T.classify_robustness(["down", "down"], expected="up") == "reversed"
    assert T.classify_robustness(["flat", "flat"], expected="up") == "depends"
    assert T.classify_robustness([], expected="up") == "unknown"


def test_classify_robustness_does_not_round_a_mixed_grid_up():
    directions = ["up"] * 26 + ["down"]
    assert T.classify_robustness(directions, expected="up") == "depends"
