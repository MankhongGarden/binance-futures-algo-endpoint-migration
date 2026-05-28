# Changelog

## v0.2.0 — 2026-05-29

Merged content from sibling repo `binance-futures-algo-endpoint-workaround`
before deprecation.

- **Added** `algo_wrapper.py` — stdlib-only Python module (no third-party
  deps) covering the three USD-M Futures algo endpoints with a typed
  `BinanceAlgoError` exception that parses Binance's `code`/`msg` for
  caller-side branching on `-1111`, `-4045`, `-4061`, etc.
- **Added** `examples/dry_run.py` — round-trip smoke test against Binance
  Futures testnet (`--place` opts into the write path; default list-only).
- **Added** README pointer to the new drop-in module + ccxt 5.x status note:
  raw `fapiPrivate*` bindings are present in the abstract layer (e.g.
  `fapiPrivatePostAlgoOrder`); `pro/binance.ts` WebSocket path auto-routes
  conditional orders; REST `createOrder()` high-level helper is still
  unpatched as of 2026-05-29.
- **Noted** closed upstream issues: `ccxt/ccxt#26861`, `freqtrade#12610`,
  `nautilus_trader#3287` — fold these into the existing status table.

## v0.1.0 — 2026-05-29

Initial public release (originally shipped in sibling
`binance-futures-algo-endpoint-workaround` repo).

- `algo_wrapper.py` — stdlib-only Python module for the three USD-M Futures
  algo endpoints (`POST /fapi/v1/algoOrder`, `GET /fapi/v1/openAlgoOrders`,
  `DELETE /fapi/v1/algoOrder`).
- `examples/dry_run.py` — round-trip smoke test against Binance Futures
  testnet (read-only by default; `--place` for write path).
- README documents the `-4120` breaking change (Binance algo-service
  migration on 2025-12-09), the `stopPrice` -> `triggerPrice` param rename,
  the `-1111` precision trap, and when to use the upstream ccxt binding
  instead of this stopgap.
