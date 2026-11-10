"""Print the running BigQuery spend from the committed cost ledger.

This is where the README's "cost of a full refresh" figure comes from, so
it is read out of the ledger rather than quoted from memory.
"""

from near_filtered import bq, config


def main() -> int:
    ledger = bq.read_cost_ledger()
    if ledger.empty:
        print("No queries recorded yet. The ledger fills as `make refresh` runs.")
        return 0

    billed = int(ledger["bytes_billed"].sum())
    processed = int(ledger["bytes_processed"].sum())
    usd = float(ledger["est_usd"].sum())

    print(f"queries run       {len(ledger):,}")
    print(f"bytes processed   {config.human_bytes(processed)}")
    print(f"bytes billed      {config.human_bytes(billed)}")
    print(f"estimated cost    ${usd:,.2f} at ${config.USD_PER_TIB_SCANNED}/TiB")
    print()
    by_query = (
        ledger.groupby("query")
        .agg(
            runs=("query", "size"), bytes_billed=("bytes_billed", "sum"), est_usd=("est_usd", "sum")
        )
        .sort_values("bytes_billed", ascending=False)
    )
    print("most expensive queries")
    for name, row in by_query.head(10).iterrows():
        print(
            f"  {name:<34} {int(row['runs']):>3} run(s)  "
            f"{config.human_bytes(int(row['bytes_billed'])):>12}  "
            f"${row['est_usd']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
