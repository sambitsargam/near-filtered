"""Paths, constants and environment loading.

Nothing in here is a research finding. Every constant that came from an
outside source carries a comment pointing at the entry in SOURCES.md that
cites it, so a reader can audit where it came from.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
RAW_DIR = CACHE_DIR / "raw_full"  # gitignored: never committed
INTENTS_RAW_DIR = CACHE_DIR / "intents_raw"  # gitignored: page-level cache
RESULTS_DIR = ROOT / "results"
TEMPLATES_DIR = ROOT / "templates"
SITE_DIR = ROOT / "site"

METRICS_PATH = RESULTS_DIR / "metrics.json"
COST_LEDGER_PATH = CACHE_DIR / "bq_cost_ledger.csv"
NOTES_PATH = ROOT / "NOTES.md"

# --- BigQuery -------------------------------------------------------------
BQ_DATASET = "bigquery-public-data.crypto_near_mainnet_us"

# On-demand analysis price used only to convert bytes -> an indicative USD
# figure for the README's "cost of a full refresh". Cited in SOURCES.md.
# This is a price, not a measurement, so it is allowed to be a constant.
USD_PER_TIB_SCANNED = 6.25
TIB = 1024**4

# Default per-query ceiling. Overridable via MAX_BYTES_BILLED in .env.
# BigQuery aborts the job rather than overrunning this, so it is a real cap.
DEFAULT_MAX_BYTES_BILLED = 50 * 1024**3  # 50 GiB

# --- NEAR Intents Explorer API -------------------------------------------
# Base URL and the 1-request-per-5-seconds partner rate limit are documented;
# see SOURCES.md. We add headroom because a 429 costs us more than a wait.
INTENTS_BASE_URL = "https://explorer.near-intents.org/api/v0"
INTENTS_MIN_INTERVAL_S = 5.2
INTENTS_PAGE_SIZE = 1000  # documented maximum for numberOfTransactions

# --- Prices ---------------------------------------------------------------
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"


def load_env() -> None:
    """Load .env if present. Absent .env is fine: `rebuild` needs no keys."""
    load_dotenv(ROOT / ".env", override=False)


def env(name: str, default: str | None = None) -> str | None:
    load_env()
    value = os.environ.get(name, default)
    if value is not None and value.strip() == "":
        return default
    return value


def require_env(name: str) -> str:
    value = env(name)
    if not value or value.startswith("your-"):
        raise RuntimeError(
            f"{name} is not set in .env (or still holds the placeholder from "
            f".env.example). This step needs live credentials; `make rebuild` "
            f"and `make verify` do not."
        )
    return value


def max_bytes_billed() -> int:
    raw = env("MAX_BYTES_BILLED")
    return int(raw) if raw else DEFAULT_MAX_BYTES_BILLED


def ensure_dirs() -> None:
    for d in (CACHE_DIR, RAW_DIR, INTENTS_RAW_DIR, RESULTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def bytes_to_usd(n_bytes: int) -> float:
    return (n_bytes / TIB) * USD_PER_TIB_SCANNED


def human_bytes(n_bytes: float) -> str:
    step = 1024.0
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n_bytes) < step or unit == "TiB":
            return f"{n_bytes:,.2f} {unit}"
        n_bytes /= step
    return f"{n_bytes:,.2f} TiB"
