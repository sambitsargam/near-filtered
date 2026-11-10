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


# NEP-245 multi-tokens key their chain by numeric EVM chain id. Only ids seen
# in real traffic are named; anything else is reported as "eip155:<id>" rather
# than guessed, so an unmapped chain is visible instead of silently wrong.
_EVM_CHAIN_IDS = {
    "1": "eth",
    "10": "optimism",
    "56": "bsc",
    "137": "polygon",
    "196": "xlayer",
    "8453": "base",
    "42161": "arb",
}


def parse_chain(asset_id: str | None) -> str:
    """Which chain an Intents asset originates from, per its asset id.

    Four namespaces appear in real traffic, and all four are handled here
    because 14% of a sampled day fell outside the first one:

    `nep141:<chain>-<address>.omft.near`
        A bridged asset. The `.omft.near` suffix, not the presence of a
        hyphen, is what marks it foreign: `nep141:btc.omft.near` is bridged
        Bitcoin and carries no address. Reading that as NEAR would move real
        cross-chain volume onto the native side of the settlement share.

    `nep141:<near account>`
        Anything else under nep141 is a NEAR-native token, whatever its
        suffix: `wrap.near`, `token.sweat`, and bare 64-hex implicit account
        ids all qualify. Note that Rainbow-Bridge style tokens such as
        `*.factory.bridge.near` are NEAR-side representations of foreign
        assets and are counted as NEAR here, because the asset id encodes no
        origin chain. That limitation is recorded in LIMITATIONS.md.

    `1cs_v1:<chain>:<kind>:<id>`
        Chain is the second segment, e.g. `1cs_v1:btc:native:coin`.

    `nep245:<contract>:<evm chain id>_<token>`
        A multi-token; the chain is the numeric id before the underscore.

    Anything unrecognised returns "unknown" rather than a guess, so an
    unparsed asset shows up in the output instead of being absorbed into one
    side of a ratio.
    """
    if not asset_id or not isinstance(asset_id, str):
        return "unknown"

    standard, _, body = asset_id.partition(":")
    if not body:
        return "unknown"
    standard = standard.lower()

    if standard == "1cs_v1":
        chain = body.split(":", 1)[0].strip().lower()
        return chain or "unknown"

    if standard == "nep245":
        # <contract>:<chainid>_<token>
        _, _, tail = body.rpartition(":")
        chain_id = tail.split("_", 1)[0].strip()
        if chain_id.isdigit():
            return _EVM_CHAIN_IDS.get(chain_id, f"eip155:{chain_id}")
        return "unknown"

    if standard == "nep141":
        suffix = ".omft.near"
        if body.endswith(suffix):
            label = body[: -len(suffix)]
            chain = label.split("-", 1)[0].strip().lower()
            return chain or "unknown"
        # Every other nep141 asset is a token living natively on NEAR.
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

    def _get(
        self,
        params: dict,
        max_retries: int = 6,
        timeout: float = config.INTENTS_TIMEOUT_S,
    ) -> list[dict]:
        cached = self._cache_file(params)
        if cached.exists():
            self.pages_from_cache += 1
            return json.loads(cached.read_text())

        url = f"{config.INTENTS_BASE_URL}/transactions"
        backoff = config.INTENTS_MIN_INTERVAL_S

        for attempt in range(1, max_retries + 1):
            self.limiter.wait()
            try:
                response = self.session.get(url, params=params, timeout=timeout)
            except (requests.Timeout, requests.ConnectionError) as exc:
                # A single slow response must not end a pull that is hundreds
                # of requests long. Back off and try the same page again; the
                # page cache means nothing already fetched is re-fetched.
                self.requests_made += 1
                wait = min(backoff * 2**attempt, 120)
                print(
                    f"    {type(exc).__name__} after {timeout:.0f}s; "
                    f"retrying in {wait:.0f}s (attempt {attempt}/{max_retries})"
                )
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Intents API did not respond after {max_retries} attempts "
                        f"({type(exc).__name__}). The service may be down; the page "
                        f"cache means a later re-run resumes rather than restarts."
                    ) from exc
                time.sleep(wait)
                continue
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
