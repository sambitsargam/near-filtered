"""Pure metric functions.

Everything here takes data in and returns numbers out, with no I/O and no
network. That is deliberate: these are the functions a sceptical reader will
want to check, so each one is small enough to read and is covered by a unit
test against a fixture whose answer can be worked out by hand
(see tests/test_transforms.py).

Definitions live in docstrings here and are restated in METHODOLOGY.md. If
the two ever disagree, this file is the implementation and the bug.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats

# --------------------------------------------------------------------------
# Concentration
# --------------------------------------------------------------------------


def shares(values: pd.Series) -> pd.Series:
    """Normalise to fractions of the total. An all-zero total gives zeros."""
    values = pd.Series(values, dtype="float64").fillna(0.0)
    total = values.sum()
    if total <= 0:
        return pd.Series([0.0] * len(values), index=values.index)
    return values / total


def hhi(values: pd.Series) -> float:
    """Herfindahl-Hirschman Index on the 0-1 scale (sum of squared shares).

    1.0 means a single actor holds everything; 1/n means n equal actors.
    We report the 0-1 form rather than the 0-10,000 form; METHODOLOGY.md
    says so, because the two differ by 10,000x and are easy to confuse.
    """
    s = shares(values)
    return float((s**2).sum())


def top_n_share(values: pd.Series, n: int = 10) -> float:
    """Fraction of the total held by the n largest entries."""
    s = shares(values).sort_values(ascending=False)
    return float(s.head(n).sum())


def concentration_by_month(
    df: pd.DataFrame,
    month_col: str = "month",
    entity_col: str = "receiver_account_id",
    value_col: str = "tx_count",
    n: int = 10,
) -> pd.DataFrame:
    """Per-month top-n share and HHI over `entity_col`, weighted by `value_col`."""
    rows = []
    for month, group in df.groupby(month_col, sort=True):
        per_entity = group.groupby(entity_col)[value_col].sum()
        rows.append(
            {
                month_col: month,
                "entities": int(per_entity.shape[0]),
                f"top{n}_share": top_n_share(per_entity, n),
                "hhi": hhi(per_entity),
                "total": float(per_entity.sum()),
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# The bot filter
# --------------------------------------------------------------------------


def is_economic(
    per_account: pd.DataFrame,
    min_active_days: int,
    min_distinct_receivers: int,
    min_balance_near: float,
) -> pd.Series:
    """Boolean mask for accounts that clear all three thresholds.

    An account is "economic" in a window when, within that window, it
    signed transactions on at least `min_active_days` distinct days,
    touched at least `min_distinct_receivers` distinct receiver contracts,
    and held at least `min_balance_near` NEAR-equivalent at window end.

    The three are ANDed. Any one of them alone is easy for a bot or an
    airdrop farmer to satisfy; together they are not impossible to fake,
    which is why LIMITATIONS.md says what this filter does not catch.

    Missing balance is treated as zero, not as missing: an account with no
    row in the balances table held nothing we can see, and silently
    dropping it would bias the count upward.
    """
    balance = pd.to_numeric(
        per_account.get("balance_near", pd.Series(0.0, index=per_account.index)),
        errors="coerce",
    ).fillna(0.0)
    return (
        (pd.to_numeric(per_account["active_days"], errors="coerce").fillna(0) >= min_active_days)
        & (
            pd.to_numeric(per_account["distinct_receivers"], errors="coerce").fillna(0)
            >= min_distinct_receivers
        )
        & (balance >= min_balance_near)
    )


def count_economic_accounts(
    per_account: pd.DataFrame,
    min_active_days: int,
    min_distinct_receivers: int,
    min_balance_near: float,
) -> int:
    return int(
        is_economic(per_account, min_active_days, min_distinct_receivers, min_balance_near).sum()
    )


# --------------------------------------------------------------------------
# Cohort retention
# --------------------------------------------------------------------------


def month_index(month: str) -> int:
    """Months since 1970-01 for a 'YYYY-MM' string, so gaps are countable."""
    year, mon = str(month).split("-")[:2]
    return int(year) * 12 + (int(mon) - 1)


def cohort_retention(
    activity: pd.DataFrame,
    account_col: str = "account_id",
    month_col: str = "month",
    offsets: tuple[int, ...] = (1, 3, 6),
) -> pd.DataFrame:
    """Share of each cohort still economically active at +1/+3/+6 months.

    A cohort is the set of accounts whose FIRST economic month is that month.
    Retention at +k is the share of the cohort that is economic again in the
    month exactly k months later — a point-in-time measure, not "active at
    any point since", which would only ever rise.

    `activity` must already be filtered to economic account-months: one row
    per (account, month).
    """
    act = activity[[account_col, month_col]].drop_duplicates().copy()
    act["m"] = act[month_col].map(month_index)

    first = act.groupby(account_col)["m"].min().rename("cohort_m")
    act = act.join(first, on=account_col)

    present = set(zip(act[account_col], act["m"]))
    max_m = int(act["m"].max()) if len(act) else 0

    rows = []
    for cohort_m, group in act[act["m"] == act["cohort_m"]].groupby("cohort_m", sort=True):
        members = group[account_col].unique()
        row = {
            "cohort": f"{int(cohort_m) // 12:04d}-{int(cohort_m) % 12 + 1:02d}",
            "cohort_size": len(members),
        }
        for k in offsets:
            target = int(cohort_m) + k
            if target > max_m:
                # The window does not extend far enough to observe this yet.
                row[f"retained_m{k}"] = np.nan
                row[f"retained_m{k}_n"] = np.nan
                continue
            retained = sum(1 for a in members if (a, target) in present)
            row[f"retained_m{k}_n"] = int(retained)
            row[f"retained_m{k}"] = retained / len(members) if len(members) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Cross-chain settlement share — the original metric
# --------------------------------------------------------------------------


def settlement_share(intents_usd: float, native_usd: float) -> float:
    """Intents share of settled USD value: intents / (intents + native).

    Returns NaN when both legs are zero, rather than 0, because "no activity"
    and "no cross-chain activity" are different findings and must not be
    silently merged.
    """
    intents = float(intents_usd or 0.0)
    native = float(native_usd or 0.0)
    denominator = intents + native
    if denominator <= 0:
        return float("nan")
    return intents / denominator


def settlement_share_by_month(
    df: pd.DataFrame,
    month_col: str = "month",
    intents_col: str = "intents_usd",
    native_col: str = "native_usd",
) -> pd.DataFrame:
    out = df[[month_col, intents_col, native_col]].copy()
    out["settlement_share"] = [
        settlement_share(i, n) for i, n in zip(out[intents_col], out[native_col])
    ]
    return out


# --------------------------------------------------------------------------
# Trends
# --------------------------------------------------------------------------


@dataclass
class Trend:
    """OLS fit of y on a 0-based time index."""

    n: int
    slope_per_month: float
    ci_low: float
    ci_high: float
    p_value: float
    r_squared: float
    first: float
    last: float
    total_change_pct: float

    @property
    def direction(self) -> str:
        """'up' / 'down' only when the CI excludes zero, else 'flat'."""
        if self.ci_low > 0:
            return "up"
        if self.ci_high < 0:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["direction"] = self.direction
        return d


def linear_trend(values, confidence: float = 0.95) -> Trend:
    """Least-squares slope per month with a two-sided confidence interval.

    Deliberately the simplest defensible method, and the only inferential
    one we use. The CI is the ordinary t-interval on the slope. With ~12
    monthly points it is wide, and we report it wide rather than reaching
    for something that would look more certain than the data is.
    """
    y = pd.Series(values, dtype="float64").dropna().reset_index(drop=True)
    n = len(y)
    if n < 3:
        raise ValueError(f"need at least 3 points to fit a trend, got {n}")

    x = np.arange(n, dtype="float64")
    fit = stats.linregress(x, y)
    df_resid = n - 2
    t_crit = stats.t.ppf(0.5 + confidence / 2, df_resid)
    half_width = t_crit * fit.stderr

    first, last = float(y.iloc[0]), float(y.iloc[-1])
    change_pct = ((last - first) / abs(first) * 100.0) if first != 0 else float("nan")

    return Trend(
        n=n,
        slope_per_month=float(fit.slope),
        ci_low=float(fit.slope - half_width),
        ci_high=float(fit.slope + half_width),
        p_value=float(fit.pvalue),
        r_squared=float(fit.rvalue**2),
        first=first,
        last=last,
        total_change_pct=float(change_pct),
    )


def mom_growth(values) -> pd.Series:
    """Month-over-month percentage change."""
    s = pd.Series(values, dtype="float64")
    return s.pct_change() * 100.0


# --------------------------------------------------------------------------
# Sensitivity classification
# --------------------------------------------------------------------------


def classify_robustness(directions: list[str], expected: str) -> str:
    """Label a hypothesis across a threshold grid.

    robust   — every cell in the grid agrees with the prediction
    depends  — some cells agree, others are flat or disagree
    reversed — no cell agrees and at least one points the other way

    Showing this instead of a single hand-picked threshold is the point of
    the grid. A "depends" result is reported as "depends", not rounded up.
    """
    if not directions:
        return "unknown"
    agree = sum(1 for d in directions if d == expected)
    opposite = {"up": "down", "down": "up", "flat": "flat"}[expected]
    against = sum(1 for d in directions if d == opposite)
    if agree == len(directions):
        return "robust"
    if agree == 0 and against > 0:
        return "reversed"
    return "depends"
