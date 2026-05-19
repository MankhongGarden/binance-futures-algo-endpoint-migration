"""CCXT idiom for Binance Futures algo-endpoint orders · MIT.

CCXT does not (as of 2026-05) have unified bindings for /fapi/v1/algoOrder.
But CCXT auto-generates per-exchange raw-endpoint methods from its API
descriptors, so the three algo endpoints are reachable via:

    exchange.fapiPrivatePostAlgoOrder({...})
    exchange.fapiPrivateGetOpenAlgoOrders({...})
    exchange.fapiPrivateDeleteAlgoOrder({...})

This file is a minimal reference. For production code, integrate with your
existing CCXT exchange instance.
"""

import asyncio

import ccxt.async_support as ccxt


async def main(api_key: str, api_secret: str):
    exchange = ccxt.binanceusdm({"apiKey": api_key, "secret": api_secret})

    try:
        # Place STOP_MARKET via algo endpoint.
        # Note: triggerPrice — not stopPrice. The old name silently fails.
        order = await exchange.fapiPrivatePostAlgoOrder(
            {
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "STOP_MARKET",
                "algoType": "CONDITIONAL",
                "triggerPrice": "60000",
                "quantity": "0.002",
                "positionSide": "LONG",
                "workingType": "CONTRACT_PRICE",
                "clientAlgoId": "demo-sl-1",
            }
        )
        algo_id = order["algoId"]
        print(f"placed algoId={algo_id}")

        # List open algo orders for this symbol.
        open_algo = await exchange.fapiPrivateGetOpenAlgoOrders({"symbol": "BTCUSDT"})
        print(f"open_algo={open_algo}")

        # Cancel by algoId.
        cancel_res = await exchange.fapiPrivateDeleteAlgoOrder(
            {"symbol": "BTCUSDT", "algoId": algo_id}
        )
        print(f"cancelled: {cancel_res}")

    finally:
        await exchange.close()


if __name__ == "__main__":
    import os

    asyncio.run(main(os.environ["BINANCE_API_KEY"], os.environ["BINANCE_API_SECRET"]))
