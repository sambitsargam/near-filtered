"""Live refresh: re-pull every series the metrics read, with the cost shown first.

    nf refresh --plan     dry-run every query and print the bill (free)
    nf refresh            the same, then ask before spending anything
    nf refresh --yes      no prompt, for the monthly workflow

The order of work:

1. Inventory re-derives the window from partition metadata, so a refresh
   always measures the latest complete months and never an empty partition.
   This reads INFORMATION_SCHEMA only, a few MiB, and no table data. (Skipped
   by --plan, which prices the window already committed.)
2. Every BigQuery query the refresh would run is dry-run, which is free, and
   the total is printed. A month already pulled to data/cache/raw_full/ is
   reused rather than re-billed: chain history for a closed month does not
   change. A query over the per-query ceiling stops the refresh here, before
   a byte is billed.
3. Nothing is spent without an explicit yes. Without a terminal to ask, the
   refresh stops unless --yes was given, and --max-total-gib caps the run
   whatever is said.
4. The pulls: H1 per-account facts (which also feed H3's cohorts and the H4
   economic set), H2, H5, the H4 native leg, then the Intents sample.

Afterwards `make rebuild` regenerates metrics.json, THESIS.md, README.md and
the site from the refreshed cache; `make refresh` runs both.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from . import bq, config, inventory, pulls
from . import window as W
from .intents_pull import sampled_days

# BigQuery's free tier, the default ceiling for one refresh.
DEFAULT_MAX_TOTAL_GIB = 1024.0
# An array parameter needs one element to be typed. A dry-run bills by
# columns and partitions read, not by what the filter matches, so the
# placeholder prices the H4 leg exactly as the real economic set would.
_PLACEHOLDER_ACCOUNT = "placeholder.near"


@dataclass
class PlannedQuery:
    name: str
    bytes_processed: int
    cached: bool = False


@dataclass
class Plan:
    queries: list[PlannedQuery] = field(default_factory=list)
    intents_days: int = 0
    intents_cached: int = 0

    @property
    def to_run(self) -> list[PlannedQuery]:
        return [q for q in self.queries if not q.cached]

    @property
    def total_bytes(self) -> int:
        return sum(q.bytes_processed for q in self.to_run)

    def over_ceiling(self, max_bytes: int) -> list[PlannedQuery]:
        return [q for q in self.to_run if q.bytes_processed > max_bytes]


def build_plan(runner, win: W.Window) -> Plan:
    """Dry-run every query the refresh would execute. Spends nothing."""
    plan = Plan()
    pulls.split_h1_combined()

    h1_sql = bq.load_sql("h1_accounts")
    h2_sql = bq.load_sql("h2_concentration")
    for month, start, end in pulls.month_windows(win):
        for name, sql, params, path in (
            (
                f"h1_accounts_{month}",
                h1_sql,
                pulls.h1_params(start, end),
                pulls.h1_month_path(month),
            ),
            (
                f"h2_concentration_{month}",
                h2_sql,
                pulls.h2_params(start, end),
                pulls.h2_month_path(month),
            ),
        ):
            if path.exists():
                plan.queries.append(PlannedQuery(name, 0, cached=True))
            else:
                cost = runner.dry_run(sql, params, name)
                plan.queries.append(PlannedQuery(name, cost.bytes_processed))

    cost = runner.dry_run(bq.load_sql("h5_value_accrual"), pulls.h5_params(win), "h5_value_accrual")
    plan.queries.append(PlannedQuery("h5_value_accrual", cost.bytes_processed))

    by_month: dict[str, list] = {}
    days = sampled_days(win)
    for day in days:
        by_month.setdefault(day.strftime("%Y-%m"), []).append(day)
    h4_sql = bq.load_sql("h4_native_leg")
    for month, month_days in sorted(by_month.items()):
        params = {"days": month_days, "economic_accounts": [_PLACEHOLDER_ACCOUNT]}
        cost = runner.dry_run(h4_sql, params, f"h4_native_{month}")
        plan.queries.append(PlannedQuery(f"h4_native_{month}", cost.bytes_processed))

    from .intents_pull import day_path

    plan.intents_days = len(days)
    plan.intents_cached = sum(1 for d in days if day_path(d).exists())
    return plan


def format_plan(plan: Plan, win: W.Window, max_bytes: int) -> str:
    lines = [f"Refresh plan for {win.describe()}", ""]
    for q in plan.queries:
        if q.cached:
            lines.append(f"  {q.name:<28} cached in data/cache/raw_full/, not re-billed")
        else:
            flag = "   OVER THE PER-QUERY CEILING" if q.bytes_processed > max_bytes else ""
            lines.append(f"  {q.name:<28} {config.human_bytes(q.bytes_processed):>10}{flag}")
    total = plan.total_bytes
    lines += [
        "",
        (
            f"  BigQuery: {len(plan.to_run)} queries, {config.human_bytes(total)} "
            f"(~${config.bytes_to_usd(total):,.2f} at ${config.USD_PER_TIB_SCANNED}/TiB on-demand)"
        ),
        f"  per-query ceiling: {config.human_bytes(max_bytes)}",
        (
            f"  Intents API: {plan.intents_days - plan.intents_cached} of {plan.intents_days} "
            f"sampled days to pull at 1 request / {config.INTENTS_MIN_INTERVAL_S:g} s "
            f"({plan.intents_cached} cached)"
        ),
    ]
    return "\n".join(lines)


def confirm(prompt: str, assume_yes: bool, stdin=None) -> bool:
    if assume_yes:
        return True
    stdin = stdin or sys.stdin
    if not stdin.isatty():
        print("\nNo terminal to ask on, and --yes was not given: no table data was scanned.")
        return False
    print(prompt, end="", flush=True)
    return stdin.readline().strip().lower() in {"y", "yes"}


def check_budget(plan: Plan, max_bytes: int, max_total_gib: float) -> str | None:
    """Why this plan must not run, or None if it may."""
    over = plan.over_ceiling(max_bytes)
    if over:
        names = ", ".join(q.name for q in over)
        return (
            f"{names} would exceed the per-query ceiling of {config.human_bytes(max_bytes)}. "
            f"No table data was scanned. Raise MAX_BYTES_BILLED deliberately if this is expected."
        )
    if plan.total_bytes > max_total_gib * 1024**3:
        return (
            f"the refresh would scan {config.human_bytes(plan.total_bytes)}, over the "
            f"--max-total-gib cap of {max_total_gib:g} GiB. No table data was scanned."
        )
    return None


def execute(runner, win: W.Window, skip_intents: bool = False) -> None:
    """Run the pulls. Callers must have shown the plan and had a yes."""
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    accounts = pulls.h1_accounts(runner, win)
    grid = pulls.h1_grid_from_accounts(accounts)
    pulls.h1_headline(grid)  # fails loudly if the grid and pre-registration diverged
    pulls.h3_cohorts_from_accounts(accounts)
    pulls.h2_concentration(runner, win)
    pulls.h5_value_accrual(runner, win)
    pulls.h4_native_leg(runner, win)
    if skip_intents:
        print("\nIntents pull skipped (--skip-intents); data/cache/intents_daily.csv is unchanged.")
    else:
        from . import intents_pull

        intents_pull.run(win)


def run(
    plan_only: bool = False,
    assume_yes: bool = False,
    max_total_gib: float = DEFAULT_MAX_TOTAL_GIB,
    skip_intents: bool = False,
    runner=None,
) -> int:
    runner = runner or bq.BigQueryRunner()
    if plan_only:
        win = W.load()
    else:
        win = inventory.run(runner)["window"]
        print()

    plan = build_plan(runner, win)
    print(format_plan(plan, win, runner.max_bytes))

    problem = check_budget(plan, runner.max_bytes, max_total_gib)
    if problem:
        print(f"\nRefusing: {problem}")
        return 2
    if plan_only:
        print("\n--plan: dry runs only, nothing was spent.")
        return 0
    if not confirm("\nRun these queries and pull from the Intents API? [y/N] ", assume_yes):
        print("Stopped. No table data was scanned.")
        return 1

    execute(runner, win, skip_intents=skip_intents)
    print("\nRefresh pulled. Next: `make rebuild` (make refresh runs it for you).")
    return 0
