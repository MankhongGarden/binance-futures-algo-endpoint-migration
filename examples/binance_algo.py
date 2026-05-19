"""Binance USDⓈ-M Futures algo-endpoint wrapper · pure stdlib · MIT.

After 2025-12-09, STOP_MARKET / TAKE_PROFIT_MARKET / TRAILING_STOP_MARKET on
Binance USDⓈ-M Futures must go to /fapi/v1/algoOrder, not /fapi/v1/order.
This wrapper covers the three endpoints (create / list-open / cancel) with
the param renames and the response-field rename baked in.

Usage:
    from binance_algo import create_stop_market, list_open_algo_orders, cancel_algo_order

    order = create_stop_market(
        symbol="BTCUSDT",
        side="SELL",
        qty="0.002",
        trigger="60000",
        pos_side="LONG",
        api_key=API_KEY,
        api_secret=API_SECRET,
    )
    algo_id = order["algoId"]
    cancel_algo_order("BTCUSDT", algo_id, API_KEY, API_SECRET)

Not for production use without your own retry / rate-limit / signature-clock-skew handling.
"""

import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request

FAPI = "https://fapi.binance.com"


def _signed_request(method, path, params, api_key, api_secret):
    params = dict(params)
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 5000
    query = urllib.parse.urlencode(params)
    sig = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f"{FAPI}{path}?{query}&signature={sig}"
    req = urllib.request.Request(url, method=method, headers={"X-MBX-APIKEY": api_key})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def create_stop_market(symbol, side, qty, trigger, pos_side, api_key, api_secret, coid=None):
    """POST /fapi/v1/algoOrder · STOP_MARKET conditional order.

    side:     "BUY" or "SELL"
    pos_side: "LONG" / "SHORT" (hedge mode) · "BOTH" (one-way mode)
    trigger:  trigger price · MUST be passed as `triggerPrice`, not `stopPrice`
    coid:     optional client algo id (max 36 chars) for idempotency
    """
    p = {
        "symbol": symbol,
        "side": side.upper(),
        "type": "STOP_MARKET",
        "algoType": "CONDITIONAL",
        "triggerPrice": str(trigger),
        "quantity": str(qty),
        "positionSide": pos_side.upper(),
        "workingType": "CONTRACT_PRICE",
    }
    if coid:
        p["clientAlgoId"] = coid[:36]
    return _signed_request("POST", "/fapi/v1/algoOrder", p, api_key, api_secret)


def create_take_profit_market(symbol, side, qty, trigger, pos_side, api_key, api_secret, coid=None):
    """POST /fapi/v1/algoOrder · TAKE_PROFIT_MARKET conditional order."""
    p = {
        "symbol": symbol,
        "side": side.upper(),
        "type": "TAKE_PROFIT_MARKET",
        "algoType": "CONDITIONAL",
        "triggerPrice": str(trigger),
        "quantity": str(qty),
        "positionSide": pos_side.upper(),
        "workingType": "CONTRACT_PRICE",
    }
    if coid:
        p["clientAlgoId"] = coid[:36]
    return _signed_request("POST", "/fapi/v1/algoOrder", p, api_key, api_secret)


def list_open_algo_orders(symbol, api_key, api_secret):
    """GET /fapi/v1/openAlgoOrders · list open conditional orders.

    Pass symbol=None to list all symbols (heavier call).
    """
    params = {"symbol": symbol} if symbol else {}
    res = _signed_request("GET", "/fapi/v1/openAlgoOrders", params, api_key, api_secret)
    return res.get("orders", []) if isinstance(res, dict) else (res or [])


def cancel_algo_order(symbol, algo_id, api_key, api_secret):
    """DELETE /fapi/v1/algoOrder · cancel by algoId."""
    return _signed_request(
        "DELETE",
        "/fapi/v1/algoOrder",
        {"symbol": symbol, "algoId": algo_id},
        api_key,
        api_secret,
    )
