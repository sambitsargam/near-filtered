"""NEAR Intents Explorer API client.

Scope caveat that must travel with every number this produces: the Explorer
API is documented as read-only and specific to 1Click Swap transactions, so
everything here is a LOWER BOUND on total Intents activity. See SOURCES.md
and LIMITATIONS.md.

The API is rate limited to one request every five seconds per partner, and
paginates by keyset (you pass the previous page's depositAddress/depositMemo),
not by offset. A twelve-month pull is therefore slow and must be resumable:
every page is written to disk before the next request goes out, so an
interrupted pull resumes instead of restarting, and a re-run costs no
requests at all.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from . import config

TERMINAL_STATUSES = ("SUCCESS", "FAILED", "REFUNDED")


@dataclass
class RateLimiter:
    """One request per `min_interval` seconds, measured between send times."""

    min_interval: float = config.INTENTS_MIN_INTERVAL_S
    _last: float = field(default=0.0, repr=False)

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if self._last and elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


def parse_chain(asset_id: str | None) -> str:
    """Extract the chain from an Intents asset id.

    Documented form is `nep141:<chain>-<address>.omft.near`, e.g.
    `nep141:eth-0xa0b8....omft.near`. Native assets of a bridged chain carry
    no address at all — `nep141:btc.omft.near` is bridged Bitcoin — so the
    `.omft.near` suffix, not the presence of a hyphen, is what marks an asset
    as foreign. Getting this backwards would file bridged BTC as NEAR-native
    and inflate the native side of the settlement share, so it is tested.

    NEAR's own assets appear as plain NEAR account ids such as
    `nep141:wrap.near`. Anything we cannot parse is reported as "unknown"
    rather than guessed, so an unparsed asset shows up in the output instead
    of being quietly absorbed into one side of the ratio.
    """
    if not asset_id or not isinstance(asset_id, str):
        return "unknown"
    body = asset_id.split(":", 1)[1] if ":" in asset_id else asset_id

    suffix = ".omft.near"
    if body.endswith(suffix):
        label = body[: -len(suffix)]
        chain = label.split("-", 1)[0].strip().lower()
        return chain or "unknown"

    if body.endswith((".near", ".testnet")):
        return "near"
    return "unknown"


class IntentsClient:
    def __init__(self, jwt: str | None = None, cache_dir: Path | None = None):
        self.jwt = jwt or config.require_env("INTENTS_JWT")
        self.cache_dir = cache_dir or config.INTENTS_RAW_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.limiter = RateLimiter()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.jwt}",
                "Accept": "application/json",
                "User-Agent": "near-filtered/0.1 (research pipeline)",
            }
        )
        self.requests_made = 0
        self.pages_from_cache = 0

    # -- low level --------------------------------------------------------
    def _cache_file(self, params: dict) -> Path:
        key = json.dumps(params, sort_keys=True)
        digest = hashlib.sha256(key.encode()).hexdigest()[:20]
        return self.cache_dir / f"page_{digest}.json"

    def _get(self, params: dict, max_retries: int = 6) -> list[dict]:
        cached = self._cache_file(params)
        if cached.exists():
            self.pages_from_cache += 1
            return json.loads(cached.read_text())

        url = f"{config.INTENTS_BASE_URL}/transactions"
        backoff = config.INTENTS_MIN_INTERVAL_S

        for attempt in range(1, max_retries + 1):
            self.limiter.wait()
            response = self.session.get(url, params=params, timeout=60)
            self.requests_made += 1

            if response.status_code == 200:
                payload = response.json()
                if not isinstance(payload, list):
                    raise RuntimeError(
                        f"expected a JSON array of transactions, got "
                        f"{type(payload).__name__}: {str(payload)[:200]}"
                    )
                cached.write_text(json.dumps(payload))
                return payload

            if response.status_code == 429:
                wait = min(backoff * 2**attempt, 120)
                print(
                    f"    429 rate limited; backing off {wait:.0f}s "
                    f"(attempt {attempt}/{max_retries})"
                )
                time.sleep(wait)
                continue

            if response.status_code in (401, 403):
                raise RuntimeError(
                    f"Intents API returned {response.status_code}. The JWT in .env is "
                    f"missing, expired or lacks access. Re-copy it from "
                    f"https://partners.near-intents.org/ . Body: {response.text[:200]}"
                )

            if 500 <= response.status_code < 600:
                wait = min(backoff * 2**attempt, 120)
                print(f"    {response.status_code} server error; retrying in {wait:.0f}s")
                time.sleep(wait)
                continue

            raise RuntimeError(f"Intents API {response.status_code}: {response.text[:300]}")

        raise RuntimeError(f"gave up after {max_retries} attempts for params={params}")

    # -- pagination -------------------------------------------------------
    def iter_transactions(
        self,
        start_unix: int,
        end_unix: int,
        page_size: int = config.INTENTS_PAGE_SIZE,
        max_pages: int | None = None,
    ):
        """Yield pages of transactions from `end_unix` backwards to `start_unix`.

        Walks with `direction=next` (documented as "older"), carrying the
        previous page's depositAddress/depositMemo as the keyset cursor. Stops
        on a short page, on a repeated cursor, or once the window is covered.
        """
        cursor_address: str | None = None
        cursor_memo: str | None = None
        seen_cursors: set[tuple[str | None, str | None]] = set()
        page_index = 0

        while True:
            if max_pages is not None and page_index >= max_pages:
                print(f"    stopping at max_pages={max_pages}")
                return

            params: dict = {
                "numberOfTransactions": page_size,
                "direction": "next",
                "startTimestampUnix": start_unix,
                "endTimestampUnix": end_unix,
            }
            if cursor_address is not None:
                params["lastDepositAddress"] = cursor_address
                if cursor_memo:
                    params["lastDepositMemo"] = cursor_memo

            page = self._get(params)
            page_index += 1
            if not page:
                return

            yield page

            if len(page) < page_size:
                return  # short page: the window is exhausted

            last = page[-1]
            cursor_address = last.get("depositAddress")
            cursor_memo = last.get("depositMemo")
            cursor = (cursor_address, cursor_memo)
            if cursor_address is None or cursor in seen_cursors:
                print("    cursor did not advance; stopping to avoid a loop")
                return
            seen_cursors.add(cursor)

    def fetch_window(self, start_unix: int, end_unix: int, **kwargs) -> list[dict]:
        rows: list[dict] = []
        for page in self.iter_transactions(start_unix, end_unix, **kwargs):
            rows.extend(page)
            print(
                f"    {len(rows):,} swaps fetched "
                f"({self.requests_made} requests, {self.pages_from_cache} pages from cache)"
            )
        return rows
