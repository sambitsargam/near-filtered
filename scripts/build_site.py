"""Assemble the static dashboard's data directory from the committed caches.

The site is a consumer of results, never a producer: it gets a copy of
metrics.json, one CSV per chart for the download links, and a copy of each
SQL file for the Show SQL toggles. Everything here re-runs inside
`make rebuild`, so the deployed site can never drift from the thesis.
"""

import shutil

from near_filtered import bq, config

SITE_DATA = config.SITE_DIR / "data"
SITE_SQL = config.SITE_DIR / "sql"

# chart name -> (cache stem, columns to publish). None = all columns.
CSVS = {
    "h1_series": ("h1_economic_accounts_grid", None),
    "h2_concentration": ("h2_concentration", None),
    "h3_cohorts": ("h3_cohort_retention", None),
    "h4_intents_daily": ("intents_daily", None),
    "h4_native_leg": ("h4_native_leg", None),
    "h5_value_accrual": ("h5_value_accrual", None),
}

SQL_FILES = [
    "h1_accounts.sql",
    "h2_concentration.sql",
    "h4_native_leg.sql",
    "h5_value_accrual.sql",
    "meta_partitions.sql",
]


def main() -> int:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    SITE_SQL.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(config.METRICS_PATH, SITE_DATA / "metrics.json")
    print("site: data/metrics.json")

    for out_name, (stem, columns) in CSVS.items():
        try:
            frame = bq.load_cached(stem)
        except FileNotFoundError:
            print(f"site: SKIP {out_name} ({stem} not cached yet)")
            continue
        if columns:
            frame = frame[columns]
        frame.to_csv(SITE_DATA / f"{out_name}.csv", index=False)
        print(f"site: data/{out_name}.csv ({len(frame)} rows)")

    for name in SQL_FILES:
        source = config.SQL_DIR / name
        if source.exists():
            shutil.copyfile(source, SITE_SQL / name)
    print(f"site: {len(SQL_FILES)} SQL files for the toggles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
