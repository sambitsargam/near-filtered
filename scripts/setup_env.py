"""Create or repair .env without ever clobbering a value already set.

`cp .env.example .env` is the obvious thing to type and it silently destroys
a working configuration. This does the safe version instead: it creates .env
from the example if it is missing, adds any keys the example has gained, and
leaves every existing value alone. It prints which keys still need filling,
never their values.
"""

from pathlib import Path

from near_filtered import config

EXAMPLE = config.ROOT / ".env.example"
TARGET = config.ROOT / ".env"

# Keys whose absence blocks something, and what it blocks.
NEEDED_FOR = {
    "GCP_PROJECT_ID": "BigQuery (make inventory / refresh)",
    "INTENTS_JWT": "the NEAR Intents pull",
}


def parse(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def is_filled(value: str) -> bool:
    return bool(value) and not value.startswith("your-")


def main() -> int:
    if not EXAMPLE.exists():
        print(f"error: {EXAMPLE.name} is missing")
        return 1

    existing = parse(TARGET)

    if not TARGET.exists():
        TARGET.write_text(EXAMPLE.read_text())
        TARGET.chmod(0o600)
        print(f"created .env from {EXAMPLE.name}")
    else:
        example_keys = parse(EXAMPLE)
        added = [k for k in example_keys if k not in existing]
        if added:
            with TARGET.open("a") as fh:
                fh.write("\n# Added by `make env` from .env.example\n")
                for key in added:
                    fh.write(f"{key}={example_keys[key]}\n")
            print(f"kept .env as it was; added {len(added)} new key(s): {', '.join(added)}")
        else:
            print("kept .env as it was; nothing to add")
        TARGET.chmod(0o600)

    values = parse(TARGET)
    print("\nstatus (values are never printed):")
    missing = []
    for key in values:
        filled = is_filled(values[key])
        note = NEEDED_FOR.get(key)
        if filled:
            state = f"set ({len(values[key])} chars)"
        else:
            state = "NOT SET" if note else "empty (optional)"
            if note:
                missing.append((key, note))
        print(f"  {key:<32} {state}")

    if missing:
        print("\nstill needed:")
        for key, note in missing:
            print(f"  {key} -> {note}")
    else:
        print("\nall required keys are set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
