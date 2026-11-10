"""Cost-controlled BigQuery access.

Three rules are enforced here rather than left to discipline:

1. Every query must filter on a partition column with an explicit range.
   `guard_sql` rejects the query text otherwise, before a byte is scanned.
2. Every query is dry-run first and its estimate printed. If the estimate
   exceeds the configured ceiling, we refuse to run it and say by how much.
3. Every executed query carries `maximum_bytes_billed`, so BigQuery aborts
   the job server-side instead of running up a bill if the estimate was off.

Every run appends one row to data/cache/bq_cost_ledger.csv. That ledger is
committed, so the "cost of a full refresh" quoted in the README is itself a
generated number rather than a claim.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import config

_SELECT_STAR = re.compile(r"select\s+\*", re.IGNORECASE)
_PARTITION_COLS = ("block_date", "epoch_date")
# A partition column must be immediately compared or ranged, so that merely
# selecting `block_date` does not satisfy the rule while the scan stays open.
_PARTITION_FILTER = re.compile(
    r"\b(block_date|epoch_date)\s*(?:=|>=|>|<=|<|\bbetween\b|\bin\b)",
    re.IGNORECASE,
)


class QueryRejected(RuntimeError):
    """Raised when a query violates a cost rule. Never caught silently."""


def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def guard_sql(sql: str) -> None:
    """Reject a query that would be expensive by construction.

    Checked against the comment-stripped text so a commented-out filter
    cannot satisfy the rule.
    """
    body = strip_sql_comments(sql)
    lowered = body.lower()

    if _SELECT_STAR.search(body):
        raise QueryRejected(
            "SELECT * is not allowed: name the columns you need. BigQuery bills per column scanned."
        )

    if not any(col in lowered for col in _PARTITION_COLS):
        raise QueryRejected(
            "No partition column found. Every query must filter on "
            f"one of {_PARTITION_COLS} so it reads a bounded set of partitions."
        )

    if not _PARTITION_FILTER.search(body):
        raise QueryRejected(
            "A partition column is named but never compared. Expected a filter "
            "such as `block_date BETWEEN @start AND @end` or `epoch_date = @day`. "
            "An unbounded scan is not allowed."
        )


@dataclass
class QueryCost:
    name: str
    bytes_processed: int
    cache_hit: bool

    @property
    def usd(self) -> float:
        return config.bytes_to_usd(self.bytes_processed)

    def describe(self) -> str:
        return (
            f"{self.name}: would scan {config.human_bytes(self.bytes_processed)} "
            f"(~${self.usd:,.4f} at ${config.USD_PER_TIB_SCANNED}/TiB)"
        )


class BigQueryRunner:
    """Thin wrapper over google-cloud-bigquery that cannot skip the guards."""

    def __init__(self, project: str | None = None, max_bytes: int | None = None):
        from google.cloud import bigquery  # imported lazily: rebuild needs no GCP

        self._bq = bigquery
        self.project = project or config.require_env("GCP_PROJECT_ID")
        self.max_bytes = max_bytes or config.max_bytes_billed()
        self.client = bigquery.Client(project=self.project)

    # -- estimating -------------------------------------------------------
    def dry_run(
        self,
        sql: str,
        params: dict | None = None,
        name: str = "query",
        metadata: bool = False,
    ) -> QueryCost:
        # INFORMATION_SCHEMA views are metadata, not table data: they have no
        # partition column to filter on and BigQuery does not bill for them.
        # They are the only queries exempt from the partition guard.
        if not metadata:
            guard_sql(sql)
        job_config = self._bq.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            query_parameters=_to_params(self._bq, params or {}),
        )
        job = self.client.query(sql, job_config=job_config)
        return QueryCost(
            name=name,
            bytes_processed=int(job.total_bytes_processed or 0),
            cache_hit=bool(job.cache_hit),
        )

    # -- executing --------------------------------------------------------
    def run(
        self,
        sql: str,
        params: dict | None = None,
        name: str = "query",
        metadata: bool = False,
    ) -> pd.DataFrame:
        """Dry-run, check the ceiling, then execute under a hard byte cap."""
        cost = self.dry_run(sql, params, name, metadata=metadata)
        print(f"  dry run  {cost.describe()}")

        if cost.bytes_processed > self.max_bytes:
            raise QueryRejected(
                f"{name} would scan {config.human_bytes(cost.bytes_processed)}, over the "
                f"{config.human_bytes(self.max_bytes)} ceiling "
                f"(by {config.human_bytes(cost.bytes_processed - self.max_bytes)}). "
                f"Narrow the date range or raise MAX_BYTES_BILLED deliberately."
            )

        job_config = self._bq.QueryJobConfig(
            query_parameters=_to_params(self._bq, params or {}),
            maximum_bytes_billed=self.max_bytes,
        )
        job = self.client.query(sql, job_config=job_config)
        df = job.result().to_dataframe()

        billed = int(job.total_bytes_billed or 0)
        record_cost(name, int(job.total_bytes_processed or 0), billed)
        print(
            f"  ran      {name}: billed {config.human_bytes(billed)} "
            f"(~${config.bytes_to_usd(billed):,.4f}), {len(df):,} rows"
        )
        return df


def _to_params(bigquery, params: dict):
    """Map a plain dict to BigQuery named query parameters.

    Parameterised queries, not f-strings: the date range is data, and the
    SQL files stay readable and runnable in the console as-is.
    """
    out = []
    for key, value in params.items():
        if isinstance(value, bool):
            type_ = "BOOL"
        elif isinstance(value, int):
            type_ = "INT64"
        elif isinstance(value, float):
            type_ = "FLOAT64"
        elif isinstance(value, dt.date):
            type_ = "DATE"
        else:
            type_ = "STRING"
        out.append(bigquery.ScalarQueryParameter(key, type_, value))
    return out


# -- cost ledger ----------------------------------------------------------
_LEDGER_FIELDS = ("ran_at_utc", "query", "bytes_processed", "bytes_billed", "est_usd")


def record_cost(name: str, bytes_processed: int, bytes_billed: int) -> None:
    config.ensure_dirs()
    path = config.COST_LEDGER_PATH
    is_new = not path.exists()
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_LEDGER_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(
            {
                "ran_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "query": name,
                "bytes_processed": bytes_processed,
                "bytes_billed": bytes_billed,
                "est_usd": round(config.bytes_to_usd(bytes_billed), 6),
            }
        )


def read_cost_ledger() -> pd.DataFrame:
    path = config.COST_LEDGER_PATH
    if not path.exists():
        return pd.DataFrame(columns=list(_LEDGER_FIELDS))
    return pd.read_csv(path)


def load_sql(stem: str) -> str:
    path = config.SQL_DIR / f"{stem}.sql"
    if not path.exists():
        raise FileNotFoundError(f"no SQL file at {path}")
    return path.read_text()


def cache_path(name: str) -> Path:
    return config.CACHE_DIR / f"{name}.csv"


def save_cache(name: str, df: pd.DataFrame) -> Path:
    config.ensure_dirs()
    path = cache_path(name)
    df.to_csv(path, index=False)
    print(f"  cached   {path.relative_to(config.ROOT)} ({len(df):,} rows)")
    return path


def load_cached(name: str) -> pd.DataFrame:
    path = cache_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"{path.relative_to(config.ROOT)} is missing. "
            f"`make rebuild` works only from committed aggregates; "
            f"run `make refresh` to regenerate them from BigQuery."
        )
    return pd.read_csv(path)
