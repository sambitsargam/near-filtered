"""Tests for `nf refresh`: the only command that spends money.

Run against a fake runner, so they prove the refresh prices every query,
refuses before spending when it should, and never executes a query without
a yes, all without touching BigQuery.
"""

import io

import pandas as pd
import pytest

from near_filtered import bq, config, pulls, refresh
from near_filtered import window as W

GIB = 1024**3


class FakeRunner:
    def __init__(self, bytes_by_prefix=None, max_bytes=70 * GIB):
        self.bytes_by_prefix = bytes_by_prefix or {}
        self.max_bytes = max_bytes
        self.dry_runs: list[str] = []
        self.runs: list[str] = []

    def dry_run(self, sql, params=None, name="query", metadata=False):
        bq.guard_sql(sql)  # the real guard still applies to every planned query
        self.dry_runs.append(name)
        size = next((v for k, v in self.bytes_by_prefix.items() if name.startswith(k)), GIB)
        return bq.QueryCost(name=name, bytes_processed=size, cache_hit=False)

    def run(self, sql, params=None, name="query", metadata=False):
        self.runs.append(name)
        raise AssertionError("a refresh test must never execute a query")


class Answer(io.StringIO):
    def __init__(self, text, tty=True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


@pytest.fixture
def win():
    return W.load()


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw_full")
    monkeypatch.setattr(config, "INTENTS_RAW_DIR", tmp_path / "intents_raw")
    (tmp_path / "raw_full").mkdir()
    (tmp_path / "intents_raw").mkdir()
    return tmp_path


def test_every_query_is_priced_and_none_is_run(win):
    runner = FakeRunner()
    plan = refresh.build_plan(runner, win)
    months = len(pulls.month_windows(win))
    names = [q.name for q in plan.queries]
    assert sum(n.startswith("h1_accounts_") for n in names) == months
    assert sum(n.startswith("h2_concentration_") for n in names) == months
    assert "h5_value_accrual" in names
    assert sum(n.startswith("h4_native_") for n in names) == months
    assert runner.runs == []
    assert plan.total_bytes == len(names) * GIB


def test_months_already_pulled_are_not_rebilled(win):
    month = pulls.month_windows(win)[0][0]
    pd.DataFrame({"month": [month], "account_id": ["a.near"]}).to_parquet(
        pulls.h1_month_path(month)
    )
    runner = FakeRunner()
    plan = refresh.build_plan(runner, win)
    assert f"h1_accounts_{month}" not in runner.dry_runs
    cached = [q for q in plan.queries if q.cached]
    assert [q.name for q in cached] == [f"h1_accounts_{month}"]


def test_a_combined_file_is_split_so_its_months_count_as_cached(win):
    months = [m for m, _, _ in pulls.month_windows(win)][:2]
    pd.DataFrame({"month": months, "account_id": ["a.near", "b.near"]}).to_parquet(
        pulls.h1_combined_path()
    )
    plan = refresh.build_plan(FakeRunner(), win)
    cached = {q.name for q in plan.queries if q.cached}
    assert cached == {f"h1_accounts_{m}" for m in months}


def test_a_query_over_the_ceiling_refuses_the_whole_refresh(win):
    runner = FakeRunner({"h5_value_accrual": 80 * GIB}, max_bytes=70 * GIB)
    plan = refresh.build_plan(runner, win)
    problem = refresh.check_budget(plan, runner.max_bytes, max_total_gib=10_000)
    assert problem and "h5_value_accrual" in problem


def test_the_total_cap_refuses_the_whole_refresh(win):
    runner = FakeRunner({"h1_": 60 * GIB, "h2_": 60 * GIB})
    plan = refresh.build_plan(runner, win)
    assert refresh.check_budget(plan, runner.max_bytes, max_total_gib=1024)
    assert refresh.check_budget(plan, runner.max_bytes, max_total_gib=2048) is None


def test_plan_mode_spends_nothing_and_succeeds(win, capsys):
    runner = FakeRunner()
    assert refresh.run(plan_only=True, runner=runner) == 0
    assert runner.runs == []
    assert "nothing was spent" in capsys.readouterr().out


def test_refused_plan_returns_before_any_query_runs(win):
    runner = FakeRunner({"h5_value_accrual": 80 * GIB})
    assert refresh.run(plan_only=True, runner=runner) == 2
    assert runner.runs == []


@pytest.mark.parametrize(
    "answer, tty, expected",
    [
        ("y\n", True, True),
        ("yes\n", True, True),
        ("\n", True, False),
        ("n\n", True, False),
        ("y\n", False, False),
    ],
)
def test_confirm_needs_an_explicit_yes_on_a_terminal(answer, tty, expected):
    assert refresh.confirm("? ", assume_yes=False, stdin=Answer(answer, tty)) is expected


def test_yes_flag_skips_the_prompt():
    assert refresh.confirm("? ", assume_yes=True, stdin=Answer("", tty=False)) is True
