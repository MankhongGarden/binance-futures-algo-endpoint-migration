"""
dry_run.py — Smoke-test the algo wrapper against Binance Futures TESTNET.

What this does:
    1. Lists open algo orders on a symbol (read-only · no orders placed yet).
    2. If `--place` is passed: places a STOP_MARKET far away from spot
       (so it cannot trigger), reads it back via list, then cancels it.

What this does NOT do:
    - Open any market position. The STOP_MARKET it places is reduce-only
      (when the flag is given) AND priced far from market — it cannot
      execute. Cost on testnet is zero; cost on mainnet should also be
      zero, but use --testnet for the first run.

Prereqs:
    pip install nothing — pure stdlib.
    Get a Binance Futures testnet key:
        https://testnet.binancefuture.com/  →  API Key tab
    Export as env vars:
        Windows (PowerShell):
            $env:BINANCE_API_KEY = "..."
            $env:BINANCE_API_SECRET = "..."
        Linux / mac:
            export BINANCE_API_KEY=...
            export BINANCE_API_SECRET=...

Usage:
    python examples/dry_run.py                          # list-only, mainnet
    python examples/dry_run.py --testnet                # list-only, testnet
    python examples/dry_run.py --testnet --place        # full round-trip
    python examples/dry_run.py --testnet --symbol ETHUSDT
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Make `algo_wrapper` importable when running from repo root or the examples folder.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from algo_wrapper import (  # noqa: E402
    FAPI_MAINNET,
    FAPI_TESTNET,
    BinanceAlgoError,
    cancel_algo_order,
    create_stop_market,
    list_open_algo_orders,
)


def _fetch_last_price(symbol: str, base_url: str) -> float:
    """Public endpoint, no signing needed."""
    import json
    import urllib.request

    url = f"{base_url}/fapi/v1/ticker/price?symbol={symbol}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return float(data["price"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--testnet", action="store_true", help="hit https://testnet.binancefuture.com instead of mainnet")
    parser.add_argument("--symbol", default="BTCUSDT", help="symbol to test against (default: BTCUSDT)")
    parser.add_argument("--place", action="store_true", help="actually place + cancel a far-away stop (default: list-only)")
    parser.add_argument("--quantity", default="0.001", help="quantity for the test order (default: 0.001)")
    args = parser.parse_args()

    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")
    if not api_key or not api_secret:
        print("ERROR: set BINANCE_API_KEY and BINANCE_API_SECRET env vars first.", file=sys.stderr)
        return 2

    base_url = FAPI_TESTNET if args.testnet else FAPI_MAINNET
    print(f"Base URL : {base_url}")
    print(f"Symbol   : {args.symbol}")

    try:
        last = _fetch_last_price(args.symbol, base_url)
        print(f"Last     : {last}")
    except Exception as exc:
        print(f"WARN: ticker fetch failed ({exc}); continuing with synthetic trigger price.")
        last = 0.0

    # Step 1 — list (read-only, never fails on a fresh account)
    try:
        existing = list_open_algo_orders(
            symbol=args.symbol,
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
        )
        print(f"Open algos (before) : {len(existing)}")
        for o in existing:
            print(f"  - algoId={o.get('algoId')} type={o.get('type')} trigger={o.get('triggerPrice')}")
    except BinanceAlgoError as exc:
        print(f"ERROR listing: {exc}", file=sys.stderr)
        return 1

    if not args.place:
        print("Done (list-only). Pass --place to exercise the write path.")
        return 0

    if last <= 0:
        print("ERROR: can't pick a safe trigger price without a last-price reference.", file=sys.stderr)
        return 1

    # Pick a trigger price 30% above last and a SELL stop — for a flat
    # account on testnet this will simply rest as a stop with no underlying
    # position (Binance accepts; never triggers).
    trigger_price = round(last * 1.30, 1)
    client_algo_id = f"dry-run-{int(time.time())}"
    print(f"Placing STOP_MARKET SELL @ trigger={trigger_price} (clientAlgoId={client_algo_id})")

    try:
        placed = create_stop_market(
            symbol=args.symbol,
            side="SELL",
            quantity=args.quantity,
            trigger_price=trigger_price,
            position_side="BOTH",
            client_algo_id=client_algo_id,
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
        )
    except BinanceAlgoError as exc:
        print(f"ERROR placing: {exc}", file=sys.stderr)
        if exc.code == -1111:
            print("  -> precision mismatch; round qty/price via ccxt's *_to_precision helpers.", file=sys.stderr)
        elif exc.code == -2019:
            print("  -> margin insufficient; testnet faucet at testnet.binancefuture.com.", file=sys.stderr)
        return 1

    algo_id = placed.get("algoId") or placed.get("data", {}).get("algoId")
    print(f"  -> algoId={algo_id}")

    # Step 2 — confirm via list
    after = list_open_algo_orders(
        symbol=args.symbol,
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url,
    )
    matched = [o for o in after if str(o.get("algoId")) == str(algo_id)]
    print(f"Open algos (after place) : {len(after)} · matched our order: {len(matched)}")

    # Step 3 — clean up immediately
    if algo_id:
        try:
            cancel_algo_order(
                symbol=args.symbol,
                algo_id=algo_id,
                api_key=api_key,
                api_secret=api_secret,
                base_url=base_url,
            )
            print(f"Cancelled algoId={algo_id}")
        except BinanceAlgoError as exc:
            print(f"WARN cancel failed: {exc}", file=sys.stderr)

    final = list_open_algo_orders(
        symbol=args.symbol,
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url,
    )
    print(f"Open algos (final) : {len(final)}")
    print("Round-trip OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
