"""Command line entry point.

    nf inventory     dataset inventory + the freshness check   (free, needs GCP)
    nf sample-cost   dry-run one real metric query and price it (free, needs GCP)
    nf window        print the window currently in use          (no network)

Commands that cost money are never the default and always print an estimate
before they spend anything.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from . import bq, config, inventory
from . import window as W


def cmd_inventory(args) -> int:
    runner = bq.BigQueryRunner()
    inventory.run(runner)
    return 0


def cmd_sample_cost(args) -> int:
    """Price the H1 query over one 30-day window without running it."""
    runner = bq.BigQueryRunner()
    try:
        win = W.load()
        window_end = win.end
    except FileNotFoundError:
        print("no window.json yet; run `nf inventory` first")
        return 1

    window_start = window_end - dt.timedelta(days=29)
    sql = bq.load_sql("h1_economic_accounts_grid")
    params = {
        "window_start": window_start,
        "window_end": window_end,
        "balance_date": window_end,
        "success_status": args.success_status,
    }

    print("\nSample query: H1 economic accounts, full 3x3x3 threshold grid")
    print(f"  window        {window_start.isoformat()} .. {window_end.isoformat()} (30 days)")
    print(f"  balances at   {window_end.isoformat()}")
    print(f"  success filter {args.success_status or 'none (all signed transactions)'}")
    cost = runner.dry_run(sql, params, name="h1_economic_accounts_grid")
    print(f"\n  {cost.describe()}")
    print(f"  per-query ceiling: {config.human_bytes(runner.max_bytes)}")

    monthly = cost.bytes_processed * 12
    print(
        f"\n  Extrapolated to 12 monthly windows: "
        f"{config.human_bytes(monthly)} (~${config.bytes_to_usd(monthly):,.2f})"
    )
    if cost.bytes_processed > runner.max_bytes:
        print("\n  OVER THE CEILING — this query will be refused until the range narrows.")
        return 2
    return 0


def cmd_window(args) -> int:
    try:
        win = W.load()
    except FileNotFoundError as exc:
        print(exc)
        return 1
    print(win.describe())
    print(win.note)
    print(f"months: {', '.join(win.month_labels)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nf", description="NEAR, Filtered pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("inventory", help="tables, columns and the freshness check (free)")

    p_cost = sub.add_parser("sample-cost", help="dry-run one metric query and price it")
    p_cost.add_argument(
        "--success-status",
        default=None,
        help="value of transactions.status counted as successful "
        "(from `nf inventory`); omit to count every signed transaction",
    )

    sub.add_parser("window", help="print the analysis window in use (no network)")

    args = parser.parse_args(argv)
    handlers = {
        "inventory": cmd_inventory,
        "sample-cost": cmd_sample_cost,
        "window": cmd_window,
    }
    try:
        return handlers[args.command](args)
    except (RuntimeError, bq.QueryRejected) as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
