"""Tests for the Intents client's pure parts.

No network: the rate limiter and the asset-id parser are testable on their
own, and they are the two places a mistake would quietly corrupt the
cross-chain numbers.
"""

import time

from near_filtered.intents import RateLimiter, parse_chain


def test_parse_chain_from_omft_asset_ids():
    assert parse_chain("nep141:eth-0xa0b86991c.omft.near") == "eth"
    assert parse_chain("nep141:base-0x8335.omft.near") == "base"
    assert parse_chain("nep141:sol-abc123.omft.near") == "sol"


def test_parse_chain_handles_a_bridged_native_asset_with_no_address():
    # Regression: `btc.omft.near` carries no hyphen and no address, but it is
    # bridged Bitcoin, not a NEAR-native token. Reading it as NEAR would move
    # real cross-chain volume onto the native side of the settlement share.
    assert parse_chain("nep141:btc.omft.near") == "btc"
    assert parse_chain("nep141:zec.omft.near") == "zec"


def test_parse_chain_treats_plain_near_accounts_as_near():
    assert parse_chain("nep141:wrap.near") == "near"
    assert parse_chain("nep141:usdt.tether-token.near") == "near"


def test_parse_chain_is_case_insensitive_on_the_chain_label():
    assert parse_chain("nep141:ETH-0xabc.omft.near") == "eth"


def test_parse_chain_never_guesses():
    for bad in (None, "", "garbage", 42, "nep141:"):
        assert parse_chain(bad) == "unknown"


def test_rate_limiter_spaces_requests_out():
    limiter = RateLimiter(min_interval=0.25)
    start = time.monotonic()
    for _ in range(3):
        limiter.wait()
    elapsed = time.monotonic() - start
    # First call does not wait; the next two each wait one interval.
    assert elapsed >= 0.5, f"limiter let requests through too fast ({elapsed:.3f}s)"


def test_rate_limiter_does_not_delay_the_first_call():
    limiter = RateLimiter(min_interval=5.0)
    start = time.monotonic()
    limiter.wait()
    assert time.monotonic() - start < 0.1
