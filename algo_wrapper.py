"""
algo_wrapper.py — Drop-in stdlib-only Binance Futures algo-order client.

Replaces ccxt's `create_order(type="STOP_MARKET", ...)` for USD-M Futures
conditional orders, which started failing with `-4120 Order type not supported
for this endpoint. Please use the Algo Order API endpoints instead` after
Binance's 2025-12-09 cutover to the new Algo Service.

Scope: just the three algo endpoints. Keep ccxt for everything else
(market orders, position fetch, ticker, balances, etc).

Endpoints covered (USD-M Futures only):
    POST   /fapi/v1/algoOrder       Place STOP_MARKET / TAKE_PROFIT_MARKET
    GET    /fapi/v1/openAlgoOrders  List open algo orders
    DELETE /fapi/v1/algoOrder       Cancel an algo order

Param name change vs old endpoint:
    stopPrice  ->  triggerPrice    (silently ignored if you keep the old name)

The response includes `algoId` (numeric). Store this as the order id for
later cancel / lookup; it is NOT interchangeable with the old `orderId`.

License: MIT. Zero runtime deps (stdlib only).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


FAPI_MAINNET = "https://fapi.binance.com"
FAPI_TESTNET = "https://testnet.binancefuture.com"

DEFAULT_TIMEOUT = 15
DEFAULT_RECV_WINDOW = 5000


class BinanceAlgoError(RuntimeError):
    """Raised on any non-2xx HTTP response from the algo endpoints."""

    def __init__(self, method: str, path: str, status: int, body: str) -> None:
        super().__init__(f"{method} {path} HTTP {status}: {body}")
        self.method = method
        self.path = path
        self.status = status
        self.body = body
        self.code: int | None = None
        self.msg: str | None = None
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                self.code = parsed.get("code")
                self.msg = parsed.get("msg")
        except (ValueError, TypeError):
            pass


def _signed_request(
    method: str,
    path: str,
    params: dict[str, Any],
    api_key: str,
    api_secret: str,
    base_url: str = FAPI_MAINNET,
    timeout: int = DEFAULT_TIMEOUT,
    recv_window: int = DEFAULT_RECV_WINDOW,
) -> Any:
    """HMAC-SHA256 signed request to Binance Futures REST.

    Returns parsed JSON (dict or list) on success.
    Raises `BinanceAlgoError` on any non-2xx response.
    """
    if not api_key or not api_secret:
        raise ValueError("api_key and api_secret are required")

    signed_params = {
        **{k: v for k, v in params.items() if v is not None},
        "timestamp": int(time.time() * 1000),
        "recvWindow": recv_window,
    }
    qs = urllib.parse.urlencode(signed_params)
    sig = hmac.new(api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
    url = f"{base_url}{path}?{qs}&signature={sig}"

    req = urllib.request.Request(
        url,
        method=method.upper(),
        headers={"X-MBX-APIKEY": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise BinanceAlgoError(method, path, exc.code, body) from None


def create_stop_market(
    *,
    symbol: str,
    side: str,
    quantity: str | float,
    trigger_price: str | float,
    position_side: str = "BOTH",
    working_type: str = "CONTRACT_PRICE",
    client_algo_id: str | None = None,
    reduce_only: bool | None = None,
    api_key: str,
    api_secret: str,
    base_url: str = FAPI_MAINNET,
) -> dict[str, Any]:
    """POST /fapi/v1/algoOrder for type=STOP_MARKET.

    Args:
        symbol:        e.g. "BTCUSDT"
        side:          "BUY" or "SELL" (the side that closes; for a LONG
                       position SL/TP use "SELL")
        quantity:      contract size; prefer string to avoid float precision.
                       Use ccxt's `client.amount_to_precision(symbol, qty)`
                       if you have a ccxt client lying around.
        trigger_price: trigger price (NOT `stopPrice` — that param name is
                       silently ignored on the new endpoint).
        position_side: "LONG" / "SHORT" if account is in hedge mode,
                       "BOTH" otherwise. Wrong value triggers -4061.
        working_type:  "CONTRACT_PRICE" (default) or "MARK_PRICE"
        client_algo_id: optional caller-side id (<=36 chars). Useful for
                       tagging which engine/strategy placed the order
                       (e.g. "mybot-sl-<entry_id>"), so a list-and-diff sweep
                       can prove ownership without a local registry.
        reduce_only:   pass True if you want a pure protective stop that
                       can't accidentally open the opposite side.

    Returns the raw JSON response. The numeric `algoId` field is the
    handle you'll need for cancel/lookup later — store it.
    """
    params: dict[str, Any] = {
        "symbol": symbol,
        "side": side.upper(),
        "type": "STOP_MARKET",
        "algoType": "CONDITIONAL",
        "triggerPrice": str(trigger_price),
        "quantity": str(quantity),
        "positionSide": position_side.upper(),
        "workingType": working_type,
    }
    if client_algo_id:
        params["clientAlgoId"] = client_algo_id[:36]
    if reduce_only is not None:
        params["reduceOnly"] = "true" if reduce_only else "false"
    return _signed_request(
        "POST", "/fapi/v1/algoOrder", params,
        api_key, api_secret, base_url=base_url,
    )


def create_take_profit_market(
    *,
    symbol: str,
    side: str,
    quantity: str | float,
    trigger_price: str | float,
    position_side: str = "BOTH",
    working_type: str = "CONTRACT_PRICE",
    client_algo_id: str | None = None,
    reduce_only: bool | None = None,
    api_key: str,
    api_secret: str,
    base_url: str = FAPI_MAINNET,
) -> dict[str, Any]:
    """POST /fapi/v1/algoOrder for type=TAKE_PROFIT_MARKET.

    Same args as `create_stop_market`. Same response shape (algoId).
    """
    params: dict[str, Any] = {
        "symbol": symbol,
        "side": side.upper(),
        "type": "TAKE_PROFIT_MARKET",
        "algoType": "CONDITIONAL",
        "triggerPrice": str(trigger_price),
        "quantity": str(quantity),
        "positionSide": position_side.upper(),
        "workingType": working_type,
    }
    if client_algo_id:
        params["clientAlgoId"] = client_algo_id[:36]
    if reduce_only is not None:
        params["reduceOnly"] = "true" if reduce_only else "false"
    return _signed_request(
        "POST", "/fapi/v1/algoOrder", params,
        api_key, api_secret, base_url=base_url,
    )


def list_open_algo_orders(
    *,
    symbol: str | None = None,
    api_key: str,
    api_secret: str,
    base_url: str = FAPI_MAINNET,
) -> list[dict[str, Any]]:
    """GET /fapi/v1/openAlgoOrders.

    If `symbol` is None, returns all open algo orders across the account
    (useful for cross-bot zombie sweeps where one engine doesn't know which
    symbols a sibling engine owns).

    Always returns a list (the endpoint returns {"orders": [...]} on success;
    this helper unwraps it).
    """
    params: dict[str, Any] = {}
    if symbol:
        params["symbol"] = symbol
    res = _signed_request(
        "GET", "/fapi/v1/openAlgoOrders", params,
        api_key, api_secret, base_url=base_url,
    )
    if isinstance(res, dict):
        return res.get("orders", []) or []
    return res or []


def cancel_algo_order(
    *,
    symbol: str,
    algo_id: str | int,
    api_key: str,
    api_secret: str,
    base_url: str = FAPI_MAINNET,
) -> dict[str, Any]:
    """DELETE /fapi/v1/algoOrder.

    `algo_id` is the numeric handle returned by `create_*` calls.
    """
    params = {"symbol": symbol, "algoId": str(algo_id)}
    return _signed_request(
        "DELETE", "/fapi/v1/algoOrder", params,
        api_key, api_secret, base_url=base_url,
    )


__all__ = [
    "FAPI_MAINNET",
    "FAPI_TESTNET",
    "BinanceAlgoError",
    "create_stop_market",
    "create_take_profit_market",
    "list_open_algo_orders",
    "cancel_algo_order",
]
