"""Loader for the frozen pre-registration.

The code reads its thresholds from here and nowhere else. Nothing in the
pipeline is allowed to hold its own copy of a threshold, because the moment
two copies exist one of them is free to drift toward a nicer-looking answer.
"""

from __future__ import annotations

import json
from functools import lru_cache

from . import config

PREREG_PATH = config.ROOT / "hypotheses" / "preregistration.json"
HYPOTHESES_MD = config.ROOT / "HYPOTHESES.md"


@lru_cache(maxsize=1)
def load() -> dict:
    if not PREREG_PATH.exists():
        raise FileNotFoundError(f"pre-registration missing at {PREREG_PATH}")
    return json.loads(PREREG_PATH.read_text())


def defaults() -> tuple[int, int, float]:
    """The default (d, c, b) of the bot filter."""
    d = load()["bot_filter"]["defaults"]
    return (
        int(d["min_active_days"]),
        int(d["min_distinct_receivers"]),
        float(d["min_balance_near"]),
    )


def grid() -> list[tuple[int, int, float]]:
    """Every threshold combination in the sensitivity grid."""
    g = load()["bot_filter"]["grid"]
    return [
        (int(d), int(c), float(b))
        for d in g["min_active_days"]
        for c in g["min_distinct_receivers"]
        for b in g["min_balance_near"]
    ]


def hypothesis(hid: str) -> dict:
    for h in load()["hypotheses"]:
        if h["id"] == hid:
            return h
    raise KeyError(f"no hypothesis {hid!r} in the pre-registration")


def hypothesis_ids() -> list[str]:
    return [h["id"] for h in load()["hypotheses"]]


def confidence() -> float:
    return float(load()["verdict_rule"]["confidence"])


def verdict(direction: str, predicted: str, extra_bars_met: bool = True) -> str:
    """Apply the single pre-registered verdict rule.

    `direction` is the trend's own reading ('up' / 'down' / 'flat', where
    'flat' means the confidence interval contains zero). `predicted` is the
    hypothesis's predicted direction from the pre-registration.
    """
    if direction == "flat":
        return "INCONCLUSIVE"

    wants_up = predicted in ("up", "up_or_flat")
    agrees = (direction == "up") if wants_up else (direction == "down")

    if agrees:
        return "SUPPORTED" if extra_bars_met else "INCONCLUSIVE"
    return "REJECTED"
