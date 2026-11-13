"""Command line entry point.

    nf inventory     dataset inventory + the freshness check   (free, needs GCP)
    nf sample-cost   dry-run one real metric query and price it (free, needs GCP)
    nf window        print the window currently in use          (no network)
    nf refresh       re-pull every series; prices it and asks first (costs money)

Commands that cost money are never the default and always print an estimate
before they spend anything.
"""

from __future__ import annotations

import argparse
import sys

from . import bq, config, inventory
from . import window as W


def cmd_inventory(args) -> int:
    runner = bq.BigQueryRunner()
    inventory.run(runner)
    return 0


def cmd_sample_cost(args) -> int:
    """Price the H1 query over the latest 30-day window without running it."""
    from . import pulls

    runner = bq.BigQueryRunner()
    try:
        win = W.load()
    except FileNotFoundError:
        print("no window.json yet; run `nf inventory` first")
        return 1

    month, start, end = pulls.month_windows(win)[-1]
    params = pulls.h1_params(start, end)
    if args.success_status:
        params["success_status"] = args.success_status

    print("\nSample query: H1 per-account facts (feeds all 27 grid cells and H3)")
    print(f"  window        {start.isoformat()} .. {end.isoformat()} (30 days, {month})")
    print(f"  success filter {args.success_status or 'none (all signed transactions)'}")
    cost = runner.dry_run(bq.load_sql("h1_accounts"), params, name=f"h1_accounts_{month}")
    print(f"\n  {cost.describe()}")
    print(f"  per-query ceiling: {config.human_bytes(runner.max_bytes)}")
    print("  For the whole refresh, priced query by query: nf refresh --plan")
    if cost.bytes_processed > runner.max_bytes:
        print("\n  OVER THE CEILING — this query will be refused until the range narrows.")
        return 2
    return 0


def cmd_refresh(args) -> int:
    from . import refresh

    return refresh.run(
        plan_only=args.plan,
        assume_yes=args.yes,
        max_total_gib=args.max_total_gib,
        skip_intents=args.skip_intents,
    )


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

    p_ref = sub.add_parser("refresh", help="re-pull every series live; prices it and asks first")
    p_ref.add_argument("--plan", action="store_true", help="dry-run and price only (free)")
    p_ref.add_argument("--yes", action="store_true", help="do not prompt (for CI)")
    p_ref.add_argument(
        "--max-total-gib",
        type=float,
        default=1024.0,
        help="refuse if the whole refresh would scan more than this (default: the 1 TiB free tier)",
    )
    p_ref.add_argument("--skip-intents", action="store_true", help="leave the Intents sample as is")

    args = parser.parse_args(argv)
    handlers = {
        "inventory": cmd_inventory,
        "sample-cost": cmd_sample_cost,
        "window": cmd_window,
        "refresh": cmd_refresh,
    }
    try:
        return handlers[args.command](args)
    except (RuntimeError, bq.QueryRejected) as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - a clean message beats a traceback
        # BigQuery errors are long and wrapped in retry frames. The first line
        # is the part that says what is actually wrong with the query.
        first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else repr(exc)
        print(f"\n{type(exc).__name__}: {first_line}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
