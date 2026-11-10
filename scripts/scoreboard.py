"""Print the verdict for each hypothesis, read from results/metrics.json.

This is the summary `make verify` ends on. It reads the generated file and
reports what is in it; it computes nothing, so it cannot disagree with the
thesis.
"""

import json

from near_filtered import config


def main() -> int:
    if not config.METRICS_PATH.exists():
        print("results/metrics.json is missing; run `make rebuild` first.")
        return 1

    metrics = json.loads(config.METRICS_PATH.read_text())
    window = metrics["window"]
    print(f"window      {window['start']} .. {window['end']}  ({window['months']} months)")
    print(f"dataset to  {window['data_latest']}  ({window['lag_days']} days before the run)")
    print(f"generated   {metrics['generated_at_utc']}")
    print()

    for hid, verdict in metrics["scoreboard"].items():
        block = metrics["hypotheses"][hid]
        name = block.get("name", "")
        extra = ""
        if block.get("robustness"):
            extra = f"   [grid: {block['robustness']}]"
        print(f"  {hid}  {verdict:<14} {name}{extra}")

    amendments = metrics.get("amendments", [])
    if amendments:
        print(
            f"\n  {len(amendments)} pre-registration amendment(s): "
            f"{', '.join(a['id'] for a in amendments)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
