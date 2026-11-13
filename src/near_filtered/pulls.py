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


def h1_params(start: dt.date, end: dt.date) -> dict:
    """Parameters for sql/h1_accounts.sql over one 30-day window."""
    grid = prereg.load()["bot_filter"]["grid"]
    return {
        "window_start": start,
        "window_end": end,
        "loosest_days": min(grid["min_active_days"]),
        "loosest_receivers": min(grid["min_distinct_receivers"]),
        "loosest_balance": min(grid["min_balance_near"]),
        "success_status": None,
    }


def h2_params(start: dt.date, end: dt.date) -> dict:
    """Parameters for sql/h2_concentration.sql over one 30-day window."""
    d, c, b = prereg.defaults()
    return {
        "window_start": start,
        "window_end": end,
        "min_active_days": d,
        "min_distinct_receivers": c,
        "min_balance_near": b,
    }


def h1_month_path(month: str):
    from . import config

    return config.RAW_DIR / f"h1_accounts_{month}.parquet"


def h1_combined_path():
    from . import config

    return config.RAW_DIR / "h1_accounts.parquet"


def h2_month_path(month: str):
    from . import config

    return config.RAW_DIR / f"h2_{month}.parquet"


def split_h1_combined() -> int:
    """Split a combined per-account file into per-month files, if needed.

    An earlier pull wrote only the combined file. The per-month files are
    what lets a refresh skip months it already holds, so this recovers them
    without querying anything. Returns how many month files were written.
    """
    combined = h1_combined_path()
    if not combined.exists():
        return 0
    written = 0
    accounts = pd.read_parquet(combined)
    for month, frame in accounts.groupby("month", sort=True):
        path = h1_month_path(month)
        if not path.exists():
            frame.to_parquet(path, index=False)
            written += 1
    return written


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

    frames, total = [], 0
    print(f"Per-account facts over {len(month_windows(window))} monthly windows")
    for month, start, end in month_windows(window):
        params = h1_params(start, end)
        name = f"h1_accounts_{month}"
        if dry_run_only:
            cost = runner.dry_run(sql, params, name)
            total += cost.bytes_processed
            print(f"  {month}  {cost.describe()}")
            continue

        # Each month is written before the next query starts, so an
        # interruption costs one month rather than the whole run. Without
        # this, a drop at month eleven re-bills every earlier scan.
        path = h1_month_path(month)
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
    # The combined file is what the H4 native leg reads its economic set from.
    out.to_parquet(h1_combined_path(), index=False)
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


def h2_concentration(
    runner: bq.BigQueryRunner, window: Window, dry_run_only: bool = False
) -> pd.DataFrame:
    """H2: top-10 receiver share and HHI, over economic accounts only.

    Recomputes the economic filter inline rather than reading it from a
    staged table, because the linked dataset forbids destination tables.
    That makes this the second expensive scan of account_changes; there is
    no cheaper route that keeps the pre-registered filter intact.
    """
    from . import config

    sql = bq.load_sql("h2_concentration")
    frames, total = [], 0

    print(f"H2: concentration over {len(month_windows(window))} monthly windows")
    for month, start, end in month_windows(window):
        params = h2_params(start, end)
        name = f"h2_concentration_{month}"
        if dry_run_only:
            cost = runner.dry_run(sql, params, name)
            total += cost.bytes_processed
            print(f"  {month}  {cost.describe()}")
            continue

        path = h2_month_path(month)
        if path.exists():
            frame = pd.read_parquet(path)
            print(f"  {month}  cached")
        else:
            frame = runner.run(sql, params, name=name)
            frame.insert(0, "month", month)
            tmp = path.with_suffix(".parquet.tmp")
            frame.to_parquet(tmp, index=False)
            tmp.rename(path)
            print(f"  {month}  top10={frame.top10_share.iloc[0]:.4f} hhi={frame.hhi.iloc[0]:.4f}")
        frames.append(frame)

    if dry_run_only:
        print(f"\n  total {config.human_bytes(total)} (~${config.bytes_to_usd(total):,.2f})")
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    bq.save_cache("h2_concentration", out)
    return out


def h4_native_leg(runner: bq.BigQueryRunner, window: Window) -> pd.DataFrame:
    """H4's native leg on the sampled days, filtered to economic accounts.

    The economic set is passed as an array parameter from the per-account
    results already on disk. Recomputing it in SQL would mean a second scan
    of account_changes at roughly 50 GiB a month to rediscover a set we
    already hold; this way the whole leg costs about 2 GiB.
    """
    from . import config
    from . import transforms as T
    from .intents_pull import sampled_days

    accounts = pd.read_parquet(config.RAW_DIR / "h1_accounts.parquet")
    d, c, b = prereg.defaults()
    economic = accounts[T.is_economic(accounts, d, c, b)]

    by_month: dict[str, list] = {}
    for day in sampled_days(window):
        by_month.setdefault(day.strftime("%Y-%m"), []).append(day)

    sql = bq.load_sql("h4_native_leg")
    rows = []
    print(f"H4 native leg over {len(by_month)} months of sampled days")
    for month, days in sorted(by_month.items()):
        ids = economic[economic.month == month].account_id.tolist()
        if not ids:
            print(f"  {month}  no economic accounts; skipped")
            continue
        frame = runner.run(
            sql,
            {"days": days, "economic_accounts": ids},
            name=f"h4_native_{month}",
        )
        record = frame.iloc[0].to_dict()
        record["month"] = month
        record["days_sampled"] = len(days)
        record["economic_accounts"] = len(ids)
        # Stored as a readable string: the top contracts are context for a
        # reader, not a series anything is computed from.
        # APPROX_TOP_COUNT returns an array of structs; pandas hands it back
        # as a numpy array, so it must be tested for None rather than
        # truth-tested.
        top = record.get("top_contracts")
        record["top_contracts"] = (
            "|".join(f"{t['value']}:{t['count']}" for t in top) if top is not None else ""
        )
        rows.append(record)
        print(
            f"  {month}  {int(record['native_transfers']):>10,} transfers "
            f"from {len(ids):,} economic accounts"
        )

    out = pd.DataFrame(rows)
    bq.save_cache("h4_native_leg", out)
    return out


def h5_params(window: Window) -> dict:
    """H5 is one query over the whole window: about 5 GiB a month."""
    return {"window_start": window.start, "window_end": window.end}


def h5_value_accrual(runner: bq.BigQueryRunner, window: Window) -> pd.DataFrame:
    """H5a: burn against gross issuance, month by month, read from the chain."""
    print("H5: burn and issuance over the window")
    out = runner.run(bq.load_sql("h5_value_accrual"), h5_params(window), name="h5_value_accrual")
    bq.save_cache("h5_value_accrual", out)
    print(f"  {len(out)} months")
    return out
