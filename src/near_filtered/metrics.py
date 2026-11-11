"""Build results/metrics.json — the single source of every published number.

Nothing downstream computes a figure of its own. THESIS.md, the README and
the dashboard all read this file, and the number-drift check fails if any of
them shows a number that is not in it. That is what makes "every number is
generated from the data" testable rather than a promise.

Each hypothesis is reduced the same way: a monthly series, one OLS trend with
a 95% interval, and the pre-registered verdict rule applied mechanically.
The verdict is never written by hand.
"""

from __future__ import annotations

import datetime as dt
import json
import math

import pandas as pd

from . import bq, config, prereg
from . import transforms as T
from . import window as W

MISSING = "PENDING"


def _clean(value):
    """JSON has no NaN. Missing stays missing rather than becoming zero."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (pd.Timestamp, dt.date)):
        return str(value)
    return value


def _series(frame: pd.DataFrame, month_col: str, value_col: str) -> list[dict]:
    return [
        {"month": str(m), "value": _clean(float(v))}
        for m, v in zip(frame[month_col], frame[value_col])
    ]


def _trend_block(values: list[float]) -> dict:
    trend = T.linear_trend(values)
    out = {k: _clean(v) for k, v in trend.to_dict().items()}
    return out


# --------------------------------------------------------------------------
# H1
# --------------------------------------------------------------------------


def build_h1() -> dict:
    grid = bq.load_cached("h1_economic_accounts_grid")
    d, c, b = prereg.defaults()
    headline = grid[
        (grid.min_active_days == d)
        & (grid.min_distinct_receivers == c)
        & (abs(grid.min_balance_near - b) < 1e-9)
    ].sort_values("month")

    trend = _trend_block(headline.economic_accounts.tolist())

    cells, directions = [], []
    for (gd, gc, gb), sub in grid.groupby(
        ["min_active_days", "min_distinct_receivers", "min_balance_near"]
    ):
        sub = sub.sort_values("month")
        cell_trend = T.linear_trend(sub.economic_accounts.tolist())
        directions.append(cell_trend.direction)
        cells.append(
            {
                "d": int(gd),
                "c": int(gc),
                "b": float(gb),
                "first": _clean(cell_trend.first),
                "last": _clean(cell_trend.last),
                "change_pct": _clean(cell_trend.total_change_pct),
                "slope_per_month": _clean(cell_trend.slope_per_month),
                "direction": cell_trend.direction,
                "is_default": bool(gd == d and gc == c and abs(gb - b) < 1e-9),
            }
        )

    predicted = prereg.hypothesis("H1")["predicted_direction"]
    return {
        "id": "H1",
        "name": prereg.hypothesis("H1")["name"],
        "predicted_direction": predicted,
        "thresholds": {"d": d, "c": c, "b": b},
        "series": _series(headline, "month", "economic_accounts"),
        "all_signers_series": _series(headline, "month", "all_signing_accounts"),
        "trend": trend,
        "verdict": prereg.verdict(trend["direction"], predicted),
        "robustness": T.classify_robustness(directions, expected="up"),
        "grid": cells,
        "grid_summary": {
            "cells": len(directions),
            "down": directions.count("down"),
            "flat": directions.count("flat"),
            "up": directions.count("up"),
        },
    }


# --------------------------------------------------------------------------
# H2
# --------------------------------------------------------------------------


def build_h2() -> dict:
    try:
        frame = bq.load_cached("h2_concentration").sort_values("month")
    except FileNotFoundError:
        return {"id": "H2", "name": "Concentration", "verdict": MISSING}

    top10 = _trend_block(frame.top10_share.tolist())
    hhi = _trend_block(frame.hhi.tolist())
    predicted = prereg.hypothesis("H2")["predicted_direction"]

    # Pre-registered: rejected if EITHER series is rising.
    verdicts = [
        prereg.verdict(top10["direction"], predicted),
        prereg.verdict(hhi["direction"], predicted),
    ]
    if "REJECTED" in verdicts:
        verdict = "REJECTED"
    elif all(v == "SUPPORTED" for v in verdicts):
        verdict = "SUPPORTED"
    else:
        verdict = "INCONCLUSIVE"

    return {
        "id": "H2",
        "name": prereg.hypothesis("H2")["name"],
        "predicted_direction": predicted,
        "series": {
            "top10_share": _series(frame, "month", "top10_share"),
            "hhi": _series(frame, "month", "hhi"),
            "distinct_receivers": _series(frame, "month", "distinct_receivers"),
        },
        "trend": {"top10_share": top10, "hhi": hhi},
        "component_verdicts": {"top10_share": verdicts[0], "hhi": verdicts[1]},
        "verdict": verdict,
    }


# --------------------------------------------------------------------------
# H3
# --------------------------------------------------------------------------


def build_h3() -> dict:
    coh = bq.load_cached("h3_cohort_retention")
    observed = coh.dropna(subset=["retained_m3"])
    censored_cohort = str(coh.cohort.iloc[0])
    excluded = observed[observed.cohort != censored_cohort]

    with_censored = _trend_block(observed.retained_m3.tolist())
    headline = _trend_block(excluded.retained_m3.tolist())
    predicted = prereg.hypothesis("H3")["predicted_direction"]

    return {
        "id": "H3",
        "name": prereg.hypothesis("H3")["name"],
        "predicted_direction": predicted,
        "left_censored_cohort": censored_cohort,
        "cohorts": [
            {
                "cohort": str(r.cohort),
                "size": int(r.cohort_size),
                "retained_m1": _clean(r.retained_m1),
                "retained_m3": _clean(r.retained_m3),
                "retained_m6": _clean(r.retained_m6),
            }
            for r in coh.itertuples()
        ],
        "series": _series(excluded, "cohort", "retained_m3"),
        "trend": headline,
        "trend_including_censored": with_censored,
        "verdict": prereg.verdict(headline["direction"], predicted),
        "verdict_including_censored": prereg.verdict(with_censored["direction"], predicted),
    }


# --------------------------------------------------------------------------
# H5
# --------------------------------------------------------------------------


def build_h5() -> dict:
    frame = bq.load_cached("h5_value_accrual").sort_values("month")
    ratio = frame.burn_over_gross_issuance.tolist()
    trend = _trend_block(ratio)

    bar = prereg.hypothesis("H5")["parts"]["H5a"]["extra_bars"][0]
    final = float(ratio[-1])
    bar_met = final >= float(bar["threshold"])

    verdict = prereg.verdict(trend["direction"], "up", extra_bars_met=bar_met)

    total_burned = float(frame.burned_near.sum())
    total_net = float(frame.net_issuance_near.sum())

    return {
        "id": "H5",
        "name": prereg.hypothesis("H5")["name"],
        "predicted_direction": "up",
        "series": {
            "burn_over_gross_issuance": _series(frame, "month", "burn_over_gross_issuance"),
            "burned_near": _series(frame, "month", "burned_near"),
            "net_issuance_near": _series(frame, "month", "net_issuance_near"),
            "gross_issuance_near": _series(frame, "month", "gross_issuance_near"),
        },
        "trend": trend,
        "materiality_bar": {
            "threshold": float(bar["threshold"]),
            "final_month_value": final,
            "met": bar_met,
        },
        "totals": {
            "burned_near": total_burned,
            "net_issuance_near": total_net,
            "burn_as_pct_of_net_issuance": (total_burned / total_net * 100 if total_net else None),
            "measured_annual_issuance_pct": float(
                frame.gross_issuance_near.sum() / frame.supply_end_near.iloc[-1] * 100
            ),
            "ending_supply_near": float(frame.supply_end_near.iloc[-1]),
        },
        "verdict": verdict,
        # H5b is documentary and answered from primary sources, not data.
        "h5b": {
            "question": prereg.hypothesis("H5")["parts"]["H5b"]["metric"],
            "answer": MISSING,
        },
    }


# --------------------------------------------------------------------------
# H4
# --------------------------------------------------------------------------


def build_h4() -> dict:
    """Cross-chain settlement share: the count form is the headline.

    Both legs are measured on the same 48 sampled days (amendment A1), so
    the ratio compares like with like even though each leg is a sample.
    """
    name = prereg.hypothesis("H4")["name"]
    try:
        daily = bq.load_cached("intents_daily")
        native = bq.load_cached("h4_native_leg")
    except FileNotFoundError:
        return {"id": "H4", "name": name, "verdict": MISSING}

    from .intents_pull import monthly_rates

    intents_month = (
        daily.groupby("month")
        .agg(
            days_sampled=("day", "count"),
            intents_swaps=("swaps_success", "sum"),
            intents_usd=("usd_volume_success", "sum"),
            unique_senders=("unique_senders", "sum"),
            sender_coverage=("sender_coverage", "mean"),
        )
        .reset_index()
    )

    merged = intents_month.merge(
        native[["month", "native_transfers", "bridged_transfers", "distinct_accounts"]],
        on="month",
        how="inner",
    ).sort_values("month")

    # A month is only comparable when both legs sampled the same four days.
    complete = merged[merged.days_sampled == 4]
    if len(complete) < 3:
        return {
            "id": "H4",
            "name": name,
            "verdict": MISSING,
            "months_complete": len(complete),
            "months_needed": 3,
        }

    complete = complete.assign(
        settlement_share_count=[
            T.settlement_share(i, n)
            for i, n in zip(complete.intents_swaps, complete.native_transfers)
        ]
    )
    trend = _trend_block(complete.settlement_share_count.tolist())
    predicted = prereg.hypothesis("H4")["predicted_direction"]
    verdict = prereg.verdict(trend["direction"], predicted)

    return {
        "id": "H4",
        "name": name,
        "predicted_direction": predicted,
        "sampling": prereg.hypothesis("H4")["sampling"],
        "months_complete": len(complete),
        "months_total": len(merged),
        "months_expected": int(prereg.load()["window"]["months"]),
        # A verdict standing on part of the window must say so, loudly, in
        # every document that quotes it.
        "is_partial": bool(len(complete) < int(prereg.load()["window"]["months"])),
        "series": {
            "settlement_share_count": _series(complete, "month", "settlement_share_count"),
            "intents_swaps": _series(complete, "month", "intents_swaps"),
            "native_transfers": _series(complete, "month", "native_transfers"),
            "intents_usd": _series(complete, "month", "intents_usd"),
            "bridged_transfers": _series(complete, "month", "bridged_transfers"),
        },
        "trend": trend,
        "verdict": verdict,
        # A ratio can rise because its numerator grew or because its
        # denominator collapsed, and those are different findings. The
        # pre-registration asks for both growth rates next to the share, so
        # a reader is never left to assume the flattering one.
        "decomposition": {
            "intents_swaps_first": _clean(float(complete.intents_swaps.iloc[0])),
            "intents_swaps_last": _clean(float(complete.intents_swaps.iloc[-1])),
            "intents_growth_pct": _clean(
                (complete.intents_swaps.iloc[-1] / complete.intents_swaps.iloc[0] - 1) * 100
            ),
            "native_transfers_first": _clean(float(complete.native_transfers.iloc[0])),
            "native_transfers_last": _clean(float(complete.native_transfers.iloc[-1])),
            "native_growth_pct": _clean(
                (complete.native_transfers.iloc[-1] / complete.native_transfers.iloc[0] - 1) * 100
            ),
            "driven_by": (
                "numerator"
                if complete.intents_swaps.iloc[-1] > complete.intents_swaps.iloc[0]
                and complete.native_transfers.iloc[-1] >= complete.native_transfers.iloc[0]
                else "denominator"
                if complete.native_transfers.iloc[-1] < complete.native_transfers.iloc[0]
                and complete.intents_swaps.iloc[-1] <= complete.intents_swaps.iloc[0]
                else "both"
            ),
        },
        "sender_coverage_mean": _clean(float(complete.sender_coverage.mean())),
        # The value form needs token decimals, which the dataset does not
        # carry. Reported as uncomputed with its coverage, rather than
        # quietly dropped: the pre-registration promised a coverage figure.
        "value_form": {
            "computed": False,
            "native_token_coverage_pct": 0.0,
            "reason": (
                "ft_events carries no decimals column, so native transfers "
                "cannot be converted to USD without per-contract metadata. "
                "The count form is the pre-registered headline for this reason."
            ),
        },
        "monthly_rates": json.loads(monthly_rates(daily).to_json(orient="records")),
        "days_sampled": len(daily),
    }


# --------------------------------------------------------------------------


def build_diagnostics() -> dict:
    """Figures from the probes and from the pipeline's own behaviour.

    These are cited in LIMITATIONS.md and METHODOLOGY.md, so they belong in
    metrics.json like any other number. A figure a document quotes must be
    traceable, whether or not it supports a hypothesis.
    """
    out: dict = {}

    def cached(name):
        try:
            return bq.load_cached(name)
        except FileNotFoundError:
            return None

    coverage = cached("meta_balance_coverage")
    if coverage is not None:
        row = coverage.iloc[0]
        signers = int(row.distinct_signers)
        matched = int(row.signers_matched)
        out["balance_table_coverage"] = {
            "distinct_signers": signers,
            "accounts_with_balance_row": int(row.accounts_with_balance_row),
            "signers_matched": matched,
            "matched_pct": round(matched / signers * 100, 2) if signers else None,
        }

    status = cached("meta_tx_status_values")
    if status is not None:
        out["tx_status_probe"] = {
            "distinct_values": len(status),
            "rows_examined": int(status.transactions.sum()),
            "values": [str(v) for v in status.status.tolist()],
        }

    scale = cached("meta_balance_scale")
    if scale is not None:
        out["ft_balances_daily_probe"] = {
            "rows_in_partition": int(scale.rows_in_partition.iloc[0]),
            "max_liquid": float(scale.max_liquid.iloc[0]),
        }

    coverage_ft = cached("meta_ft_contract_coverage")
    if coverage_ft is not None:
        total = int(coverage_ft.transfers.sum())
        top2 = coverage_ft.nlargest(2, "transfers")
        out["ft_contract_concentration_probe"] = {
            "top25_transfers": total,
            "top2_contracts": [str(v) for v in top2.contract_account_id.tolist()],
            "top2_share_pct": round(float(top2.transfers.sum()) / total * 100, 1),
            "bridged_omft_share_pct": round(
                float(coverage_ft[coverage_ft.is_bridged_omft].transfers.sum()) / total * 100, 1
            ),
        }

    grid = cached("h1_economic_accounts_grid")
    if grid is not None:
        d, c, b = prereg.defaults()
        headline = grid[
            (grid.min_active_days == d)
            & (grid.min_distinct_receivers == c)
            & (abs(grid.min_balance_near - b) < 1e-9)
        ].sort_values("month")
        first = headline.iloc[0]
        out["bot_filter_residual_automation"] = {
            "month": str(first.month),
            "economic_accounts": int(first.economic_accounts),
            "economic_transactions": int(first.economic_transactions),
            "mean_tx_per_account": round(
                float(first.economic_transactions) / float(first.economic_accounts)
            ),
            "median_tx_per_account": int(first.median_tx_per_account),
        }

    return out


def build_exploratory() -> dict:
    """The April 2026 break. Not pre-registered, so it carries its label in
    its own structure and is never used as evidence for or against a
    hypothesis. Four independent series move at the same month; this block
    simply states each one's March and April values."""
    out: dict = {"label": "Exploratory (not pre-registered)", "break_month": "2026-04"}

    def month_value(frame, col, month):
        rows = frame[frame.month == month]
        return float(rows[col].iloc[0]) if len(rows) else None

    try:
        h5 = bq.load_cached("h5_value_accrual")
        out["burn_over_issuance"] = {
            "2026-03": month_value(h5, "burn_over_gross_issuance", "2026-03"),
            "2026-04": month_value(h5, "burn_over_gross_issuance", "2026-04"),
        }
        out["burned_near"] = {
            "2026-03": month_value(h5, "burned_near", "2026-03"),
            "2026-04": month_value(h5, "burned_near", "2026-04"),
        }
    except FileNotFoundError:
        pass
    try:
        h2 = bq.load_cached("h2_concentration")
        out["top10_share"] = {
            "2026-03": month_value(h2, "top10_share", "2026-03"),
            "2026-04": month_value(h2, "top10_share", "2026-04"),
        }
        out["distinct_receivers"] = {
            "2026-03": month_value(h2, "distinct_receivers", "2026-03"),
            "2026-04": month_value(h2, "distinct_receivers", "2026-04"),
        }
        out["economic_transactions"] = None
        grid = bq.load_cached("h1_economic_accounts_grid")
        d, c, b = prereg.defaults()
        headline = grid[
            (grid.min_active_days == d)
            & (grid.min_distinct_receivers == c)
            & (abs(grid.min_balance_near - b) < 1e-9)
        ]
        out["economic_transactions"] = {
            "2026-03": month_value(headline, "economic_transactions", "2026-03"),
            "2026-04": month_value(headline, "economic_transactions", "2026-04"),
        }
    except FileNotFoundError:
        pass
    out["reading"] = (
        "Four independent measures - fee burn, economic transaction volume, "
        "receiver counts and concentration - move sharply at the same month. "
        "That points to a real event rather than a pipeline artefact. We did "
        "not identify the cause and we pre-registered no hypothesis about it, "
        "so it is reported here and used as evidence for nothing."
    )
    return out


def build() -> dict:
    win = W.load()
    ledger = bq.read_cost_ledger()

    hypotheses = {
        "H1": build_h1(),
        "H2": build_h2(),
        "H3": build_h3(),
        "H4": build_h4(),
        "H5": build_h5(),
    }

    scoreboard = {h: hypotheses[h].get("verdict", MISSING) for h in sorted(hypotheses)}

    metrics = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "window": win.to_dict(),
        "scoreboard": scoreboard,
        "hypotheses": hypotheses,
        "cost": {
            "queries": len(ledger),
            "bytes_billed": int(ledger.bytes_billed.sum()) if len(ledger) else 0,
            # Pre-converted here rather than in a template. A template that
            # does arithmetic produces a number the data never generated,
            # which is exactly what the drift check exists to stop.
            "gib_billed": round(
                float(ledger.bytes_billed.sum()) / 1024**3 if len(ledger) else 0.0, 2
            ),
            "est_usd": round(float(ledger.est_usd.sum()) if len(ledger) else 0.0, 2),
        },
        "diagnostics": build_diagnostics(),
        "exploratory": build_exploratory(),
        "cases": json.loads((config.ROOT / "analysis" / "cases.json").read_text()),
        "amendments": prereg.load()["amendments"],
    }
    return metrics


def write() -> dict:
    config.ensure_dirs()
    metrics = build()
    config.METRICS_PATH.write_text(json.dumps(metrics, indent=2, default=str) + "\n")
    print(f"wrote {config.METRICS_PATH.relative_to(config.ROOT)}")
    return metrics


def main() -> int:
    metrics = write()
    print("\nScoreboard")
    for hid, verdict in metrics["scoreboard"].items():
        print(f"  {hid}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
