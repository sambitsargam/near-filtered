"""One-off probes that remove a guess before any metric SQL is written.

Each is a single-partition query, so the whole script costs a few cents of
nothing. It answers two questions the published documentation does not:
the vocabulary of `transactions.status`, and the units of the balance columns.
"""

from near_filtered import bq
from near_filtered import window as W


def main() -> int:
    runner = bq.BigQueryRunner()
    win = W.load()
    probe_date = win.end

    print(f"\nProbe date: {probe_date.isoformat()} (the window's last day)\n")

    print("1/2  distinct values of transactions.status")
    statuses = runner.run(
        bq.load_sql("meta_tx_status_values"),
        {"probe_date": probe_date},
        name="meta_tx_status_values",
    )
    print(statuses.to_string(index=False))
    bq.save_cache("meta_tx_status_values", statuses)

    print("\n2/2  scale of ft_balances_daily.liquid / .staked")
    # Balances lag by a day, so probe the last date we know exists.
    balance_date = min(probe_date, win.data_latest)
    scale = runner.run(
        bq.load_sql("meta_balance_scale"),
        {"probe_date": balance_date},
        name="meta_balance_scale",
    )
    print(scale.to_string(index=False))
    bq.save_cache("meta_balance_scale", scale)

    log10 = float(scale["log10_max_liquid"].iloc[0] or 0)
    print()
    if log10 > 18:
        print(f"  max liquid is ~1e{log10:.0f} -> yoctoNEAR. The /1e24 divisor is correct.")
    elif log10 > 0:
        print(
            f"  max liquid is ~1e{log10:.0f} -> already NEAR, NOT yoctoNEAR. "
            f"The /1e24 divisor in the H1 query is WRONG and must be removed."
        )
    else:
        print("  could not determine scale; inspect the output above before proceeding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
