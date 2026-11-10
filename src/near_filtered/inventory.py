"""Dataset inventory and the day-one freshness check.

All three queries here read INFORMATION_SCHEMA or __TABLES__, which is
metadata: they return the table list, the real column types and the newest
partition of every table without scanning any table data, so the whole
inventory costs nothing. That is deliberate — the first thing we needed to
know was the most expensive thing to ask the wrong way.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from . import bq
from . import window as W

TABLES_WE_USE = (
    "transactions",
    "ft_events",
    "ft_balances_daily",
    "execution_outcomes",
    "blocks",
    "circulating_supply",
)


def run(runner: bq.BigQueryRunner) -> dict:
    """Pull tables, columns and partitions; derive and save the window."""
    print("\nInventory (metadata only — no table data is scanned)\n")

    print("1/3  tables")
    tables = runner.run(bq.load_sql("meta_tables"), name="meta_tables", metadata=True)
    bq.save_cache("meta_tables", tables)

    print("2/3  columns")
    columns = runner.run(bq.load_sql("meta_columns"), name="meta_columns", metadata=True)
    bq.save_cache("meta_columns", columns)

    print("3/3  partitions (the freshness check)")
    partitions = runner.run(bq.load_sql("meta_partitions"), name="meta_partitions", metadata=True)
    bq.save_cache("meta_partitions", partitions)

    report = summarise_freshness(partitions)
    print("\n" + format_freshness(report))

    win = derive_window_from(partitions)
    W.save(win)
    print("\nDerived analysis window")
    print("  " + win.describe())
    print("  " + win.note)

    return {"tables": tables, "columns": columns, "partitions": partitions, "window": win}


def summarise_freshness(partitions: pd.DataFrame, as_of: dt.date | None = None) -> pd.DataFrame:
    """Per-table latest partition and how far behind `as_of` it runs."""
    as_of = as_of or dt.date.today()
    rows = []
    for _, r in partitions.iterrows():
        latest = W.parse_partition_id(r["latest_partition"])
        earliest = W.parse_partition_id(r["earliest_partition"])
        lag = (as_of - latest).days
        rows.append(
            {
                "table_name": r["table_name"],
                "earliest": earliest.isoformat(),
                "latest": latest.isoformat(),
                "lag_days": lag,
                "stale": lag > W.FRESHNESS_TOLERANCE_DAYS,
                "partitions": int(r.get("partition_count") or 0),
                "total_rows": int(r.get("total_rows") or 0),
                "logical_bytes": int(r.get("total_logical_bytes") or 0),
                "used_by_us": r["table_name"] in TABLES_WE_USE,
            }
        )
    out = pd.DataFrame(rows).sort_values(["used_by_us", "table_name"], ascending=[False, True])
    return out.reset_index(drop=True)


def format_freshness(report: pd.DataFrame) -> str:
    lines = ["Freshness", ""]
    header = f"  {'table':<24} {'earliest':<12} {'latest':<12} {'lag':>6}  {'rows':>15}  state"
    lines += [header, "  " + "-" * (len(header) - 2)]
    for _, r in report.iterrows():
        state = "STALE" if r["stale"] else "ok"
        mark = "*" if r["used_by_us"] else " "
        lines.append(
            f" {mark}{r['table_name']:<24} {r['earliest']:<12} {r['latest']:<12} "
            f"{r['lag_days']:>5}d  {r['total_rows']:>15,}  {state}"
        )
    lines.append("")
    lines.append("  * = a table this project queries")

    used = report[report["used_by_us"]]
    if len(used) and used["stale"].any():
        worst = int(used["lag_days"].max())
        lines += [
            "",
            f"  WARNING: tables we rely on are up to {worst} days behind today.",
            "  The analysis window is derived from the data, not the calendar,",
            "  and the lag is disclosed in THESIS.md and on the dashboard.",
        ]
    return "\n".join(lines)


def derive_window_from(
    partitions: pd.DataFrame,
    anchor_table: str = "transactions",
    as_of: dt.date | None = None,
) -> W.Window:
    """Window anchored on the newest partition shared by the tables we use.

    Anchoring on the minimum across our tables, not just `transactions`,
    stops a month appearing in one series and not another.
    """
    used = partitions[partitions["table_name"].isin(TABLES_WE_USE)]
    if used.empty:
        raise RuntimeError(
            f"none of {TABLES_WE_USE} appeared in INFORMATION_SCHEMA.PARTITIONS; "
            f"found {sorted(partitions['table_name'].tolist())}"
        )

    latest_per_table = {
        r["table_name"]: W.parse_partition_id(r["latest_partition"]) for _, r in used.iterrows()
    }
    shared_latest = min(latest_per_table.values())

    if anchor_table in latest_per_table:
        anchor_latest = latest_per_table[anchor_table]
        if anchor_latest != shared_latest:
            print(
                f"  note: {anchor_table} runs to {anchor_latest.isoformat()} but the "
                f"earliest-ending table we use stops at {shared_latest.isoformat()}; "
                f"anchoring the window on the shared date."
            )

    return W.derive_window(shared_latest, as_of=as_of)
