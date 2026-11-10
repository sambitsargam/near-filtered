"""The analysis window, derived from the data rather than from the calendar.

Why this module exists, and why it is load-bearing:

The NEAR public BigQuery dataset's upstream ingestion source (NEAR Lake)
was retired on 2026-03-24, and the docs say only that the dataset "remains
available" — not that it is still being written to. So the dataset may end
well before today. If we hardcoded "the last 12 months" we would either
query empty partitions, or quietly compare a current Intents numerator
against a stale on-chain denominator and publish a ratio that only looks
like a trend. That single mistake would be the first thing a sceptical
reader found, and it would be fatal.

So the window is computed from `max(partition_id)` of the tables we use.
Every query, chart and sentence takes its dates from here, and the window is
printed on the dashboard and in THESIS.md so the reader always knows which
twelve months they are looking at — and how far behind today that is.

The comparable window is the intersection of what BOTH sides can see. The
Intents API is current, so for any month-by-month comparison we clip Intents
to the on-chain window. Intents data beyond the window is reported only in a
clearly labelled section, never inside the headline ratio.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
from dataclasses import asdict, dataclass

from . import config

# How far behind today the dataset may run before we call it stale in print.
FRESHNESS_TOLERANCE_DAYS = 7

# Months of history the hypotheses are tested over.
WINDOW_MONTHS = 12


def last_day_of_month(year: int, month: int) -> dt.date:
    return dt.date(year, month, calendar.monthrange(year, month)[1])


def add_months(d: dt.date, months: int) -> dt.date:
    total = (d.year * 12 + d.month - 1) + months
    year, month = divmod(total, 12)
    return dt.date(year, month + 1, min(d.day, calendar.monthrange(year, month + 1)[1]))


def parse_partition_id(partition_id: str) -> dt.date:
    """Partition ids come back as 'YYYYMMDD' for daily partitioning."""
    s = str(partition_id).strip()
    if len(s) == 8 and s.isdigit():
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
    return dt.date.fromisoformat(s)


@dataclass
class Window:
    """A closed date range plus everything a reader needs to judge it."""

    start: dt.date
    end: dt.date
    months: int
    data_latest: dt.date
    as_of: dt.date
    lag_days: int
    is_stale: bool
    note: str

    def to_dict(self) -> dict:
        d = asdict(self)
        for key in ("start", "end", "data_latest", "as_of"):
            d[key] = d[key].isoformat()
        return d

    @property
    def month_labels(self) -> list[str]:
        labels, cursor = [], dt.date(self.start.year, self.start.month, 1)
        while cursor <= self.end:
            labels.append(f"{cursor.year:04d}-{cursor.month:02d}")
            cursor = add_months(cursor, 1)
        return labels

    def describe(self) -> str:
        state = "STALE" if self.is_stale else "current"
        return (
            f"window {self.start.isoformat()} .. {self.end.isoformat()} "
            f"({self.months} months); dataset ends {self.data_latest.isoformat()}, "
            f"{self.lag_days} days behind {self.as_of.isoformat()} [{state}]"
        )


def derive_window(
    data_latest: dt.date,
    as_of: dt.date | None = None,
    months: int = WINDOW_MONTHS,
) -> Window:
    """Build the window ending at the last COMPLETE month in the data.

    A partial final month would show up as a collapse in every monthly
    series, so the last month is dropped unless the data runs to its final
    day. That is a presentation decision, and it is stated in METHODOLOGY.md
    rather than left for the reader to infer from a drooping chart.
    """
    as_of = as_of or dt.date.today()

    end_of_latest_month = last_day_of_month(data_latest.year, data_latest.month)
    if data_latest >= end_of_latest_month:
        end = end_of_latest_month
    else:
        previous = add_months(dt.date(data_latest.year, data_latest.month, 1), -1)
        end = last_day_of_month(previous.year, previous.month)

    start_month = add_months(dt.date(end.year, end.month, 1), -(months - 1))
    start = dt.date(start_month.year, start_month.month, 1)

    lag_days = (as_of - data_latest).days
    is_stale = lag_days > FRESHNESS_TOLERANCE_DAYS

    if is_stale:
        note = (
            f"The NEAR public dataset's most recent partition is "
            f"{data_latest.isoformat()}, {lag_days} days before this run "
            f"({as_of.isoformat()}). Every on-chain figure here therefore "
            f"describes the window ending {end.isoformat()}, not the present "
            f"day. Intents figures are clipped to the same window so the two "
            f"sides of the settlement share cover the same months."
        )
    else:
        note = (
            f"The NEAR public dataset is current to {data_latest.isoformat()} "
            f"({lag_days} days behind this run), so the window ends with the "
            f"last complete month, {end.isoformat()}."
        )

    return Window(
        start=start,
        end=end,
        months=months,
        data_latest=data_latest,
        as_of=as_of,
        lag_days=lag_days,
        is_stale=is_stale,
        note=note,
    )


# -- persistence -----------------------------------------------------------
WINDOW_PATH_NAME = "window.json"


def save(window: Window) -> None:
    config.ensure_dirs()
    path = config.RESULTS_DIR / WINDOW_PATH_NAME
    path.write_text(json.dumps(window.to_dict(), indent=2) + "\n")
    # A copy lives in the committed cache so `make rebuild` knows the window
    # without needing BigQuery.
    (config.CACHE_DIR / WINDOW_PATH_NAME).write_text(json.dumps(window.to_dict(), indent=2) + "\n")


def load() -> Window:
    for path in (
        config.RESULTS_DIR / WINDOW_PATH_NAME,
        config.CACHE_DIR / WINDOW_PATH_NAME,
    ):
        if path.exists():
            raw = json.loads(path.read_text())
            return Window(
                start=dt.date.fromisoformat(raw["start"]),
                end=dt.date.fromisoformat(raw["end"]),
                months=int(raw["months"]),
                data_latest=dt.date.fromisoformat(raw["data_latest"]),
                as_of=dt.date.fromisoformat(raw["as_of"]),
                lag_days=int(raw["lag_days"]),
                is_stale=bool(raw["is_stale"]),
                note=raw["note"],
            )
    raise FileNotFoundError(
        "No window.json found. Run `make inventory` (needs .env) to derive the "
        "window from the dataset's newest partition, or check that "
        "data/cache/window.json was committed."
    )
