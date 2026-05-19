# Binance Futures algo-endpoint migration · the `-4120` survival guide

On 2025-12-09 Binance silently switched STOP_MARKET, TAKE_PROFIT_MARKET, and other conditional order types on USDⓈ-M Futures to a new "Algo Order" endpoint set. From that minute on, every bot still POSTing to `/fapi/v1/order` for a stop order started getting back:

```
{"code":-4120,"msg":"Order type not supported for this endpoint. Please use the Algo Order API endpoints instead."}
```

Six months later (as of 2026-05), [ccxt/ccxt](https://github.com/ccxt/ccxt) still ships no native bindings for the new endpoints, and several other major libraries took weeks to react. This repo is the framework-agnostic recipe — raw HTTP examples that work without any SDK, plus pointers to upstream issues for the SDKs that have or haven't been patched.

> **What this guide is not:** trading strategy advice, SL/TP placement rules, position-management patterns, or anything about *what* to trade. It's pure API-integration plumbing — the mechanical "how do I keep my bot from crashing on -4120" recipe.

## Who's affected

You're hitting `-4120` and using one of these:

| Library | Status (as of 2026-05) | Where to look |
|---|---|---|
| `ccxt/ccxt` (Python · JS · PHP) | ⚠️ no native bindings · use `fapiPrivate*` private endpoints directly | [#27486](https://github.com/ccxt/ccxt/issues/27486) (closed · OP posted workaround) · [#27474](https://github.com/ccxt/ccxt/issues/27474) |
| `freqtrade/freqtrade` | ✅ fixed Dec 2025 · upgrade | [#12610](https://github.com/freqtrade/freqtrade/issues/12610) (+5 reactions · 17 comments) |
| `nautechsystems/nautilus_trader` | ✅ fixed Dec 2025 · upgrade to ≥1.222 | [#3287](https://github.com/nautechsystems/nautilus_trader/issues/3287) (+3 reactions · 27 comments) |
| `JKorf/Binance.Net` (.NET) | ✅ fixed v11.x · upgrade | [#1542](https://github.com/JKorf/Binance.Net/issues/1542) |
| `tiagosiebler/binance` (Node.js) | ❌ **still open · use this guide** | [#609](https://github.com/tiagosiebler/binance/issues/609) (5+ months open · 7 comments) |
| `oliver-zehentleitner/unicorn-binance-rest-api` | ✅ fixed | [#93](https://github.com/oliver-zehentleitner/unicorn-binance-rest-api/issues/93) |
| `QuantConnect/Lean.Brokerages.Binance` | ✅ fixed | [#61](https://github.com/QuantConnect/Lean.Brokerages.Binance/issues/61) |
| Raw HTTP / custom HMAC code | n/a · this guide is for you | — |

If your library is below this list, search its issue tracker for `-4120` first — chances are good someone already filed it.

## What changed (the official version)

[Binance's 2025-11-06 changelog entry](https://developers.binance.com/docs/derivatives/change-log#2025-11-06) announced — about five weeks before the cutover — that conditional order types on USDⓈ-M Futures move to a new endpoint set:

**Affected order types (must go to `/fapi/v1/algoOrder` now):**
- `STOP_MARKET`, `STOP` (stop-limit)
- `TAKE_PROFIT_MARKET`, `TAKE_PROFIT`
- `TRAILING_STOP_MARKET`

**Unaffected (still go to `/fapi/v1/order`):**
- `LIMIT`, `MARKET`
- `LIMIT_MAKER`
- Post-only / time-in-force variants of the above

**The three new endpoints:**

| Action | Method · Path | Notes |
|---|---|---|
| Place algo order | `POST /fapi/v1/algoOrder` | response field renamed: `orderId` → `algoId` |
| List open algo orders | `GET /fapi/v1/openAlgoOrders` | separate from `/fapi/v1/openOrders` — you now have to poll **two** lists |
| Cancel algo order | `DELETE /fapi/v1/algoOrder` | by `symbol` + `algoId` |

**The param rename trap:** the new endpoint expects `triggerPrice`, not `stopPrice`. Passing the old name does not raise — the order is accepted but the trigger never fires. Verified 2026-05 against live Binance Futures. Always use `triggerPrice`.

## Raw HTTP recipe (no SDK · works in any language)

This is the canonical pure-Python wrapper using only stdlib. Translate to your language as needed — the HMAC + query-string signing is the same shape Binance has used for years.

```python
# binance_algo.py — no third-party deps
import hashlib, hmac, json, time, urllib.parse, urllib.request

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
    """Place a STOP_MARKET conditional order via the new algo endpoint.

    side:     "BUY" or "SELL"
    pos_side: "LONG", "SHORT", or "BOTH" (one-way mode)
    trigger:  trigger price (string or number); MUST be `triggerPrice` not `stopPrice`
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

def list_open_algo_orders(symbol, api_key, api_secret):
    """List open conditional orders for a symbol. Use `None` symbol to list all."""
    params = {"symbol": symbol} if symbol else {}
    res = _signed_request("GET", "/fapi/v1/openAlgoOrders", params, api_key, api_secret)
    return res.get("orders", []) if isinstance(res, dict) else (res or [])

def cancel_algo_order(symbol, algo_id, api_key, api_secret):
    """Cancel by algoId returned from create_stop_market."""
    return _signed_request(
        "DELETE", "/fapi/v1/algoOrder",
        {"symbol": symbol, "algoId": algo_id},
        api_key, api_secret,
    )
```

Sample call:

```python
order = create_stop_market(
    symbol="BTCUSDT",
    side="SELL",       # SELL to stop-loss a LONG
    qty="0.002",
    trigger="60000",
    pos_side="LONG",   # hedge-mode; use "BOTH" for one-way mode
    api_key=API_KEY,
    api_secret=API_SECRET,
    coid="bot-sl-12345",
)
print(order["algoId"])   # save this — you need it to cancel later
```

## CCXT-Python users · use `fapiPrivate*` raw endpoints

CCXT exposes Binance's raw private endpoints as methods even when there's no unified wrapper. The [OP of ccxt/ccxt#27486](https://github.com/ccxt/ccxt/issues/27486) documented this idiom — re-stating here so the recipe is findable without diving into a closed issue:

```python
import ccxt.async_support as ccxt

exchange = ccxt.binanceusdm({"apiKey": API_KEY, "secret": API_SECRET})

# Place STOP_MARKET via algo endpoint
order = await exchange.fapiPrivatePostAlgoOrder({
    "symbol": "BTCUSDT",
    "side": "SELL",
    "type": "STOP_MARKET",
    "algoType": "CONDITIONAL",
    "triggerPrice": "60000",       # NOT stopPrice
    "quantity": "0.002",
    "positionSide": "LONG",
    "workingType": "CONTRACT_PRICE",
})
algo_id = order["algoId"]

# List open algo orders
open_algo = await exchange.fapiPrivateGetOpenAlgoOrders({"symbol": "BTCUSDT"})

# Cancel by algoId
await exchange.fapiPrivateDeleteAlgoOrder({
    "symbol": "BTCUSDT",
    "algoId": algo_id,
})
```

Note: `fapiPrivatePostAlgoOrder`, `fapiPrivateGetOpenAlgoOrders`, and `fapiPrivateDeleteAlgoOrder` are auto-generated method names from CCXT's Binance API descriptor — they exist even without changelog mention.

## Trap #2 · the `-1111 Precision` cliff next door

While migrating, you'll likely also hit:

```
{"code":-1111,"msg":"Precision is over the maximum defined for this asset."}
```

This is unrelated to `-4120` but tends to surface in the same migration window because:

- The new algo endpoint enforces `triggerPrice` precision **per market's `pricePrecision`**, not per the looser "any-float" tolerance the old endpoint had.
- If your bot was using a homemade rounder (`round(price, 2)`) instead of CCXT's `price_to_precision`, the old endpoint silently accepted slightly-off values; the new endpoint rejects them.

Fix: use CCXT's `price_to_precision(symbol, price)` for `triggerPrice`, or fetch the market's `filters[].tickSize` from `/fapi/v1/exchangeInfo` and round to that step. **Do not rely on the old loose precision behaviour** — Binance has been tightening this across endpoints for two years.

## Param mapping reference

Mapping from old `/fapi/v1/order` STOP_MARKET payload to new `/fapi/v1/algoOrder`:

| Old (`/fapi/v1/order`) | New (`/fapi/v1/algoOrder`) | Notes |
|---|---|---|
| `type=STOP_MARKET` | `type=STOP_MARKET` + `algoType=CONDITIONAL` | new endpoint requires `algoType` |
| `stopPrice=60000` | `triggerPrice=60000` | rename · old name silently fails on new endpoint |
| `closePosition=true` | not supported · use `quantity` + `reduceOnly=true` | algo endpoint doesn't honour `closePosition` |
| `workingType=CONTRACT_PRICE` | `workingType=CONTRACT_PRICE` | unchanged |
| `positionSide=LONG` | `positionSide=LONG` | unchanged |
| `clientOrderId=...` | `clientAlgoId=...` | rename · 36 char max |
| (response) `orderId` | `algoId` | rename · used for fetch/cancel |
| (response) `status` | `status` | values include `NEW`, `TRIGGERED`, `EXPIRED`, `CANCELED` |

## Why didn't Binance announce this louder?

It was in the [official changelog](https://developers.binance.com/docs/derivatives/change-log#2025-11-06) about five weeks before the cutover — but the entry was a one-liner buried under several other 2025-11-06 items. Most bot teams found out at incident time, which is why nine major libraries filed `-4120` bugs within the same 48-hour window.

The takeaway is the obvious one: **subscribe to the developers.binance.com changelog RSS**, and treat any line item containing "endpoint", "deprecated", or "Algo" as a P1 review.

## Related upstream issues

If you want the full diagnostic thread (or want to add your own data point):

- [ccxt/ccxt#27486](https://github.com/ccxt/ccxt/issues/27486) — Python · workaround in OP body
- [ccxt/ccxt#27474](https://github.com/ccxt/ccxt/issues/27474) — same symptom · 中文
- [freqtrade/freqtrade#12610](https://github.com/freqtrade/freqtrade/issues/12610) — fix path · 17 comments
- [nautechsystems/nautilus_trader#3287](https://github.com/nautechsystems/nautilus_trader/issues/3287) — fix path · 27 comments
- [JKorf/Binance.Net#1542](https://github.com/JKorf/Binance.Net/issues/1542) — .NET fix path
- [tiagosiebler/binance#609](https://github.com/tiagosiebler/binance/issues/609) — **still open** · Node.js users
- [oliver-zehentleitner/unicorn-binance-rest-api#93](https://github.com/oliver-zehentleitner/unicorn-binance-rest-api/issues/93)
- [QuantConnect/Lean.Brokerages.Binance#61](https://github.com/QuantConnect/Lean.Brokerages.Binance/issues/61)

## Sponsors

This guide is free. If it saved you the half-day I spent debugging when my bot ate `-4120` at 3am:

- ⭐ Star this repo so other searchers find it (GitHub ranks by stars)
- 💛 [GitHub Sponsors](https://github.com/sponsors/MankhongGarden) — sustains weekend OSS writeups like this
- Hit an edge case not covered? [Open an issue](https://github.com/MankhongGarden/binance-futures-algo-endpoint-migration/issues) — I'd rather add a section than have you debug alone

## License

MIT — see [LICENSE](LICENSE). Use anything here however you want.

The code samples are also MIT and have no external dependencies beyond Python 3.7+ stdlib (for the raw HTTP path) or CCXT 4.x (for the `fapiPrivate*` path).
