"""Stratified day-sample pull of 1Click swaps (pre-registration amendment A1).

A census is roughly 10.5 million swaps and over fifteen hours at the
documented rate limit. Instead we pull four whole days from each month — the
5th, 12th, 19th and 26th — and report per-day rates with an interval across
those four days. The native leg of H4 is restricted to exactly the same days,
so both sides of the ratio cover identical periods.

The pull is resumable at day granularity: each finished day is written
atomically, and a re-run skips days already on disk. A day is about 29 pages,
so an interruption costs a couple of minutes rather than the whole job.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from . import config, prereg
from .intents import IntentsClient, parse_chain
from .window import Window, add_months

SUCCESS = "SUCCESS"


def sampled_days(window: Window) -> list[dt.date]:
    """The pre-registered sample: the same four dates in every month."""
    days = prereg.load()["hypotheses"]
    h4 = next(h for h in days if h["id"] == "H4")
    dates_in_month = h4["sampling"]["days_per_month"]

    out: list[dt.date] = []
    cursor = dt.date(window.start.year, window.start.month, 1)
    while cursor <= window.end:
        for day in dates_in_month:
            candidate = dt.date(cursor.year, cursor.month, day)
            if window.start <= candidate <= window.end:
                out.append(candidate)
        cursor = add_months(cursor, 1)
    return out


def _day_bounds(day: dt.date) -> tuple[int, int]:
    """Unix bounds for a whole UTC day.

    The API documents both timestamp filters as non-inclusive, so the bounds
    are widened by a second on each side to capture the full day.
    """
    start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)
    end = start + dt.timedelta(days=1)
    return int(start.timestamp()) - 1, int(end.timestamp())


def day_path(day: dt.date) -> config.Path:
    return config.INTENTS_RAW_DIR / f"day_{day.isoformat()}.parquet"


def _to_float(value) -> float:
    """amountInUsd arrives as a string, and reads '0' while a swap is in flight."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def pull_day(client: IntentsClient, day: dt.date, page_size: int = 1000) -> pd.DataFrame:
    """Every swap on one UTC day, reduced to the columns the metrics need.

    Pulled as one window normally. A few specific days make the server time
    out repeatedly on the full-day query while every other day answers in
    seconds; for those, the day is split into quarter-day windows, which the
    server handles. The result is identical — the windows abut exactly.
    """
    start_unix, end_unix = _day_bounds(day)
    try:
        return _pull_window(client, day, start_unix, end_unix, page_size)
    except RuntimeError as exc:
        print(f"    full-day pull failed ({str(exc)[:80]}); splitting {day} into quarters")
        frames = []
        span = (end_unix - start_unix) // 4
        for i in range(4):
            sub_start = start_unix + i * span
            sub_end = end_unix if i == 3 else start_unix + (i + 1) * span
            frames.append(_pull_window(client, day, sub_start, sub_end, page_size))
        merged = pd.concat(frames, ignore_index=True)
        # The sub-window bounds are non-inclusive on both sides, so a swap
        # landing exactly on a boundary second could appear in two windows.
        merged = merged.drop_duplicates()
        return merged


def _pull_window(
    client: IntentsClient,
    day: dt.date,
    start_unix: int,
    end_unix: int,
    page_size: int,
) -> pd.DataFrame:
    rows: list[dict] = []
    cursor_address: str | None = None
    cursor_memo: str | None = None
    seen: set[tuple] = set()

    while True:
        params: dict = {
            "numberOfTransactions": page_size,
            "direction": "next",
            "startTimestampUnix": start_unix,
            "endTimestampUnix": end_unix,
        }
        if cursor_address is not None:
            params["lastDepositAddress"] = cursor_address
            if cursor_memo:
                params["lastDepositMemo"] = cursor_memo

        page = client._get(params)
        if not page:
            break

        for record in page:
            senders = record.get("senders") or []
            rows.append(
                {
                    "created_at_ts": record.get("createdAtTimestamp"),
                    "status": record.get("status"),
                    "amount_in_usd": _to_float(record.get("amountInUsd")),
                    "amount_out_usd": _to_float(record.get("amountOutUsd")),
                    "origin_chain": parse_chain(record.get("originAsset")),
                    "destination_chain": parse_chain(record.get("destinationAsset")),
                    "origin_asset": record.get("originAsset"),
                    "destination_asset": record.get("destinationAsset"),
                    "sender": senders[0] if senders else None,
                    "has_sender": bool(senders),
                }
            )

        if len(page) < page_size:
            break
        last = page[-1]
        cursor_address = last.get("depositAddress")
        cursor_memo = last.get("depositMemo")
        key = (cursor_address, cursor_memo)
        if cursor_address is None or key in seen:
            break
        seen.add(key)

    frame = pd.DataFrame(rows)
    frame["day"] = day.isoformat()
    return frame


def summarise_day(frame: pd.DataFrame, day: dt.date) -> dict:
    """Per-day aggregates. Volume counts successful swaps only."""
    if frame.empty:
        return {
            "day": day.isoformat(),
            "month": day.strftime("%Y-%m"),
            "swaps_total": 0,
            "swaps_success": 0,
            "usd_volume_success": 0.0,
            "swaps_with_sender": 0,
            "unique_senders": 0,
            "sender_coverage": float("nan"),
        }
    success = frame[frame["status"] == SUCCESS]
    with_sender = success[success["has_sender"]]
    return {
        "day": day.isoformat(),
        "month": day.strftime("%Y-%m"),
        "swaps_total": len(frame),
        "swaps_success": len(success),
        "usd_volume_success": float(success["amount_in_usd"].sum()),
        "swaps_with_sender": len(with_sender),
        "unique_senders": int(with_sender["sender"].nunique()),
        # Stated next to the swapper count rather than left implicit: the API
        # does not always supply a sender.
        "sender_coverage": float(len(with_sender) / len(success)) if len(success) else float("nan"),
    }


def run(window: Window, client: IntentsClient | None = None) -> pd.DataFrame:
    client = client or IntentsClient()
    days = sampled_days(window)
    config.INTENTS_RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Intents pull: {len(days)} sampled days, {days[0]} .. {days[-1]}")
    summaries: list[dict] = []

    for index, day in enumerate(days, start=1):
        path = day_path(day)
        if path.exists():
            frame = pd.read_parquet(path)
            print(f"  [{index:>2}/{len(days)}] {day}  cached   {len(frame):>7,} swaps")
        else:
            frame = pull_day(client, day)
            tmp = path.with_suffix(".parquet.tmp")
            frame.to_parquet(tmp, index=False)
            tmp.rename(path)  # atomic: a half-written day is never read back
            print(
                f"  [{index:>2}/{len(days)}] {day}  pulled   {len(frame):>7,} swaps"
                f"   ({client.requests_made} requests so far)"
            )
        summaries.append(summarise_day(frame, day))
        # Written after every day, not only at the end, so a partial pull is
        # still usable and an interrupted run leaves something behind.
        pd.DataFrame(summaries).to_csv(config.CACHE_DIR / "intents_daily.csv", index=False)

    daily = pd.DataFrame(summaries)
    print(f"\nwrote data/cache/intents_daily.csv ({len(daily)} days)")
    return daily


def monthly_rates(daily: pd.DataFrame) -> pd.DataFrame:
    """Per-day rates by month, with the spread across the sampled days.

    Reported as a mean and a standard error rather than a total, because the
    four sampled days are a sample of the month and pretending otherwise
    would hide the uncertainty that sampling introduces.
    """
    grouped = daily.groupby("month")
    out = grouped.agg(
        days_sampled=("day", "count"),
        swaps_per_day=("swaps_success", "mean"),
        swaps_per_day_sd=("swaps_success", "std"),
        usd_per_day=("usd_volume_success", "mean"),
        usd_per_day_sd=("usd_volume_success", "std"),
        unique_senders_per_day=("unique_senders", "mean"),
        sender_coverage=("sender_coverage", "mean"),
    ).reset_index()
    out["swaps_per_day_se"] = out["swaps_per_day_sd"] / out["days_sampled"] ** 0.5
    out["usd_per_day_se"] = out["usd_per_day_sd"] / out["days_sampled"] ** 0.5
    return out
