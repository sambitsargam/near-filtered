"""One request against the Intents Explorer API to verify key and shape.

At one request every five seconds, a twelve-month pull is hundreds of
requests. This spends exactly one to answer: does the JWT work, does the
response carry the fields the OpenAPI spec promised, and does our asset-id
parser handle the asset ids that actually come back. Finding a renamed field
on request one is much cheaper than finding it on request four hundred.

No secrets and no account identifiers are printed.
"""

import datetime as dt

from near_filtered.intents import IntentsClient, parse_chain

# Fields the spec documents for GET /api/v0/transactions that we rely on.
REQUIRED = [
    "createdAt",
    "createdAtTimestamp",
    "originAsset",
    "destinationAsset",
    "amountInUsd",
    "amountOutUsd",
    "status",
    "senders",
    "depositAddress",
]
NICE_TO_HAVE = [
    "amountIn",
    "amountOut",
    "amountInFormatted",
    "amountOutFormatted",
    "depositMemo",
    "intentHashes",
    "nearTxHashes",
    "appFees",
    "referral",
]


def main() -> int:
    client = IntentsClient()
    end = dt.datetime.now(dt.UTC)
    start = end - dt.timedelta(days=2)

    print(f"one request: swaps between {start:%Y-%m-%d %H:%M} and {end:%Y-%m-%d %H:%M} UTC")
    rows = client._get(
        {
            "numberOfTransactions": 5,
            "direction": "next",
            "startTimestampUnix": int(start.timestamp()),
            "endTimestampUnix": int(end.timestamp()),
        }
    )
    print(f"  requests made: {client.requests_made}, rows returned: {len(rows)}\n")

    if not rows:
        print("  no swaps in that window; widen it and retry.")
        return 1

    present = set()
    for row in rows:
        present |= set(row.keys())

    print("field check against the OpenAPI spec")
    missing_required = [f for f in REQUIRED if f not in present]
    for field in REQUIRED:
        print(f"  {'OK  ' if field in present else 'MISS'} {field}")
    for field in NICE_TO_HAVE:
        print(f"  {'ok  ' if field in present else '--  '} {field}")

    extra = sorted(present - set(REQUIRED) - set(NICE_TO_HAVE))
    if extra:
        print(f"\n  undocumented/extra fields returned: {', '.join(extra)}")

    print("\nasset ids seen, and how our parser reads them")
    seen = set()
    for row in rows:
        for key in ("originAsset", "destinationAsset"):
            asset = row.get(key)
            if asset and asset not in seen:
                seen.add(asset)
                print(f"  {asset:<48} -> {parse_chain(asset)}")

    unknown = [a for a in seen if parse_chain(a) == "unknown"]
    print("\nsanity")
    statuses = sorted({str(r.get("status")) for r in rows})
    print(f"  statuses in sample      {statuses}")
    usd = [r.get("amountInUsd") for r in rows]
    print(f"  amountInUsd types       {sorted({type(v).__name__ for v in usd})}")
    print(f"  amountInUsd sample      {usd[:3]}")
    senders_shape = sorted({type(r.get("senders")).__name__ for r in rows})
    print(f"  senders field type      {senders_shape}")

    if missing_required:
        print(f"\nFAIL: required fields missing: {', '.join(missing_required)}")
        return 1
    if unknown:
        print(f"\nWARN: {len(unknown)} asset id(s) parsed as 'unknown'; parser needs a case.")
        return 1
    print("\nOK: key works, every required field present, every asset id parsed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
