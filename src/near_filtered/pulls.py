"""Live BigQuery pulls, one function per hypothesis.

Every function here writes a small aggregate to data/cache/ and nothing else.
Row-level data never leaves BigQuery: each query aggregates in SQL and
returns tens or hundreds of rows, which is what makes `make rebuild` work
from a committed cache with no cloud account.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from . import bq, prereg
from .window import Window, add_months, last_day_of_month

WINDOW_DAYS = 30


def month_windows(window: Window) -> list[tuple[str, dt.date, dt.date]]:
    """One 30-day window per month, each ending on that month's last day.

    A 30-day window rather than the calendar month, because the
    pre-registration defines the bot filter over 30 days and a February
    measured over 28 days would not be comparable with a March measured
    over 31.
    """
    out = []
    cursor = dt.date(window.start.year, window.start.month, 1)
    while cursor <= window.end:
        end = min(last_day_of_month(cursor.year, cursor.month), window.end)
        start = end - dt.timedelta(days=WINDOW_DAYS - 1)
        out.append((f"{cursor.year:04d}-{cursor.month:02d}", start, end))
        cursor = add_months(cursor, 1)
    return out


def h1_accounts(
    runner: bq.BigQueryRunner, window: Window, dry_run_only: bool = False
) -> pd.DataFrame:
    """One scan per month returning per-account facts.

    Returns rows, not aggregates, because the Analytics Hub linked dataset
    forbids writing results to a destination table: the same query succeeds
    with no destination and returns 403 the moment one is set. See
    sql/h1_accounts.sql. Every row clears the loosest grid cell, so all 27
    cells and H3's cohorts come from this one result per month.
    """
    from . import config

    sql = bq.load_sql("h1_accounts")
    grid = prereg.load()["bot_filter"]["grid"]
    params_common = {
        "loosest_days": min(grid["min_active_days"]),
        "loosest_receivers": min(grid["min_distinct_receivers"]),
        "loosest_balance": min(grid["min_balance_near"]),
        "success_status": None,
    }

    frames, total = [], 0
    print(f"Per-account facts over {len(month_windows(window))} monthly windows")
    for month, start, end in month_windows(window):
        params = {"window_start": start, "window_end": end, **params_common}
        name = f"h1_accounts_{month}"
        if dry_run_only:
            cost = runner.dry_run(sql, params, name)
            total += cost.bytes_processed
            print(f"  {month}  {cost.describe()}")
            continue

        # Each month is written before the next query starts, so an
        # interruption costs one month rather than the whole run. Without
        # this, a drop at month eleven re-bills every earlier scan.
        path = config.RAW_DIR / f"h1_accounts_{month}.parquet"
        if path.exists():
            frame = pd.read_parquet(path)
            print(f"  {month}  {len(frame):,} accounts (cached, not re-queried)")
        else:
            frame = runner.run(sql, params, name=name)
            frame.insert(0, "month", month)
            tmp = path.with_suffix(".parquet.tmp")
            frame.to_parquet(tmp, index=False)
            tmp.rename(path)  # atomic: a half-written month is never read back
            print(f"  {month}  {len(frame):,} accounts above the loosest cell")
        frames.append(frame)

    if dry_run_only:
        print(f"\n  total {config.human_bytes(total)} (~${config.bytes_to_usd(total):,.2f})")
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    print(f"  {len(out):,} account-months in data/cache/raw_full/ (gitignored)")
    return out


def h1_grid_from_accounts(accounts: pd.DataFrame) -> pd.DataFrame:
    """Count every grid cell from the per-account rows, using tested code."""
    from . import transforms as T

    rows = []
    for month, frame in accounts.groupby("month", sort=True):
        all_signers = int(frame["all_signing_accounts"].iloc[0])
        for d, c, b in prereg.grid():
            mask = T.is_economic(frame, d, c, b)
            kept = frame[mask]
            rows.append(
                {
                    "month": month,
                    "min_active_days": d,
                    "min_distinct_receivers": c,
                    "min_balance_near": b,
                    "economic_accounts": int(mask.sum()),
                    "economic_transactions": int(kept["tx_count"].sum()),
                    "median_tx_per_account": (
                        float(kept["tx_count"].median()) if len(kept) else 0.0
                    ),
                    "all_signing_accounts": all_signers,
                }
            )
    out = pd.DataFrame(rows)
    bq.save_cache("h1_economic_accounts_grid", out)
    return out


def h3_cohorts_from_accounts(accounts: pd.DataFrame) -> pd.DataFrame:
    """Cohort retention at the default thresholds, from the same rows."""
    from . import transforms as T

    d, c, b = prereg.defaults()
    economic = accounts[T.is_economic(accounts, d, c, b)]
    activity = economic[["account_id", "month"]].drop_duplicates()
    offsets = tuple(prereg.hypothesis("H3")["offsets_months"])
    out = T.cohort_retention(activity, offsets=offsets)
    bq.save_cache("h3_cohort_retention", out)
    return out


def h1_headline(grid: pd.DataFrame) -> pd.DataFrame:
    """The default-threshold slice of the grid: the headline H1 series."""
    d, c, b = prereg.defaults()
    mask = (
        (grid["min_active_days"] == d)
        & (grid["min_distinct_receivers"] == c)
        & (abs(grid["min_balance_near"] - b) < 1e-9)
    )
    out = grid[mask].sort_values("month").reset_index(drop=True)
    if out.empty:
        raise RuntimeError(
            f"the default thresholds (d={d}, c={c}, b={b}) returned no grid rows; "
            f"the grid in SQL and the pre-registration have diverged"
        )
    return out
