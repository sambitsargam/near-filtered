"""Render THESIS.md from a template and results/metrics.json.

No number is typed into the template. Every figure arrives as a variable
from the generated metrics file, and the drift check fails the build if a
number appears in the output that is not traceable back to it.

The formatting filters here are the only place numbers become prose, so
they are deliberately few and blunt: a value is shown at a fixed precision
rather than at whatever precision happens to read well, because varying it
per sentence is how a number drifts from its source.
"""

from __future__ import annotations

import json

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import config

VERDICT_WORDS = {
    "SUPPORTED": "SUPPORTED",
    "REJECTED": "REJECTED",
    "INCONCLUSIVE": "INCONCLUSIVE",
    "PENDING": "NOT YET COMPUTED",
}


def num(value, places: int = 0) -> str:
    """A count, with thousands separators."""
    if value is None:
        return "n/a"
    return f"{float(value):,.{places}f}"


def pct(value, places: int = 1) -> str:
    """A fraction rendered as a percentage."""
    if value is None:
        return "n/a"
    return f"{float(value) * 100:,.{places}f}%"


def pct_direct(value, places: int = 1) -> str:
    """A value already expressed in percent."""
    if value is None:
        return "n/a"
    return f"{float(value):,.{places}f}%"


def signed_pct(value, places: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):+,.{places}f}%"


def signed(value, places: int = 0) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):+,.{places}f}"


def verdict_word(value) -> str:
    return VERDICT_WORDS.get(str(value), str(value))


def environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(config.TEMPLATES_DIR)),
        undefined=StrictUndefined,  # a missing variable is an error, not a blank
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters.update(
        num=num,
        pct=pct,
        pct_direct=pct_direct,
        signed_pct=signed_pct,
        signed=signed,
        verdict_word=verdict_word,
    )
    return env


def load_metrics() -> dict:
    if not config.METRICS_PATH.exists():
        raise FileNotFoundError(
            "results/metrics.json is missing. Run `make rebuild` first; it "
            "regenerates the metrics from the committed cache with no network."
        )
    return json.loads(config.METRICS_PATH.read_text())


def render(template_name: str, out_name: str) -> str:
    metrics = load_metrics()
    env = environment()
    template = env.get_template(template_name)
    text = template.render(m=metrics, h=metrics["hypotheses"], w=metrics["window"])
    (config.ROOT / out_name).write_text(text)
    print(f"rendered {out_name} from {template_name}")
    return text


def main() -> int:
    render("THESIS.md.j2", "THESIS.md")
    render("README.md.j2", "README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
